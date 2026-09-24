"""Stage: match 100m grid cells to nearby road/rail noise barriers,
assigning treated/untreated binary flags in distance bands -- the grid
analogue of `schools/assemble.py`'s algorithm 1 (`euclid_nearest`), second
output spec alongside it (unit of analysis is a grid cell, not a school).

REQUIRES `grid preprocess` (`grid_cells.parquet`) and `noise_barriers
preprocess`. A `band_radii` value larger than the `buffer_m` `grid
preprocess` was run with will silently undercount `ever_near_*m` for that
band -- cells past `buffer_m` were never generated, not just excluded --
so a wider band needs a matching `grid preprocess --buffer-m` rerun first.

Run separately for road and rail, same reasoning as schools:
"different noise sources / exposure types... kept as two parallel
treatment-timing tiers rather than merged into one 'nearest barrier of
either kind'" (`schools/assemble.py`'s module docstring) -- that design
decision is inherited verbatim here, not re-litigated.

Unlike `schools/assemble.py::match_barriers_point` (a dense school x
barrier distance matrix -- cheap at a few thousand schools), grid cell
counts run to the hundreds of thousands, so this uses the same
spatial-index nearest-neighbour join (`_linear_ref.nearest_segment`,
`gpd.sjoin_nearest` under the hood) the road/rail network-matching
algorithms already use, rather than materializing a dense matrix.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.regions.sweden.sources._linear_ref import nearest_segment
from src.regions.sweden.sources.grid.shared import (
    ASSUMED_BARRIER_REDUCTION_DB,
    BAND_RADII_M,
    METRIC_CRS,
    REFERENCE_DB,
    REFERENCE_DIST_M,
    assembled_dir,
    processed_grid_cells_path,
)
from src.regions.sweden.sources.grid.side import match_grid_side_for_kind
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers

# Barrier physical attributes carried through from the nearest barrier as
# heterogeneity covariates (Moretti & Wheeler Table 6's analogue -- tree
# canopy/building density there, barrier material/height/absorbency here).
# Only those present on a given `kind`'s barrier layer are kept (road has
# `height_m`, rail has `height_above_rail_top_m`; schema drift tolerated the
# same way Florida's `noise_barriers/preprocess.py::OUTPUT_COLUMNS` is).
BARRIER_COVARIATE_COLUMNS = (
    "height_m",
    "height_above_rail_top_m",
    "absorbent",
    "material_type",
    "on_bridge",
    "extent_length_m",
)


def compute_relative_loudness_reduction_pct(
    dist_m: np.ndarray,
    *,
    reduction_db: float = ASSUMED_BARRIER_REDUCTION_DB,
    reference_dist_m: float = REFERENCE_DIST_M,
    reference_db: float = REFERENCE_DB,
) -> np.ndarray:
    """Moretti & Wheeler's Appendix Table A3 formula: inverse-square-law
    decibel decay from `reference_db` at `reference_dist_m` (-6 dB per
    doubling of distance), `reduction_db` (an ASSUMED, uniform barrier
    attenuation -- see `grid/shared.py`) subtracted, converted to a 0-100
    perceived-loudness scale (every 10 dB drop halves perceived loudness).
    Returns the drop in that index (positive = quieter, monotonically
    decreasing with distance) -- closely matches (within the paper's own
    table's rounding, +/- ~0.3 points) the worked values in the paper's
    Appendix Table A3 at their 7 dB reduction: 25m -> 38.4 (paper: 38.5),
    100m -> 16.7 (paper: 17.0), 800m -> 4.8 (paper: 4.9); checked live while
    building this function. A continuous, distance-only exposure-intensity
    proxy, not a per-barrier measured effect (see
    `ASSUMED_BARRIER_REDUCTION_DB`'s docstring).

    `dist_m` is floored at `reference_dist_m` (25m, the paper's own nearest
    tabulated distance) rather than letting the inverse-square law
    extrapolate below it: closer than that, the paper's own physics table
    stops being validated (near-field effects, point- vs line-source
    assumptions change at short range), and an unclamped extrapolation blows
    up as `dist_m` approaches 0 (confirmed live: an unclamped version
    produced index values over 250 for grid cells within a few metres of
    their nearest barrier -- not a meaningful "more than 100% quieter"
    claim). Clamping bounds the index above by its value at
    `reference_dist_m` (~38 at the default 7 dB assumed reduction), not
    unboundedly large."""
    dist = np.maximum(np.asarray(dist_m, dtype=float), reference_dist_m)
    db_before = reference_db - 6.0 * np.log2(dist / reference_dist_m)
    db_after = db_before - reduction_db
    loudness_before = 100.0 * (2.0 ** ((db_before - reference_db) / 10.0))
    loudness_after = 100.0 * (2.0 ** ((db_after - reference_db) / 10.0))
    return loudness_before - loudness_after


def build_dist_bin(dist_m: pd.Series, band_radii: tuple[int, ...]) -> pd.Categorical:
    """Mutually-exclusive distance bins from the cumulative `band_radii`
    thresholds (e.g. `(100, 200, 300, 400, 500, 1000)` ->
    `"0-100m", "100-200m", ..., "500-1000m", "beyond_1000m"`) -- the paper's
    Table 2/Figure 4 dose-response bins, as an alternative to the cumulative
    `ever_near_*m` threshold flags (kept alongside, not replaced -- some
    downstream code may already depend on them). A per-kind `nearest_dist_m`
    can exceed `max(band_radii)` even though the grid's own tiling buffer
    doesn't (the buffer is unioned across ALL kinds, so a cell inside the
    rail buffer can be farther than that from its nearest ROAD barrier) --
    `beyond_{max}m` catches that, rather than leaving it `NaN`."""
    radii = sorted(band_radii)
    edges = [0, *radii, np.inf]
    labels = [f"{lo}-{hi}m" for lo, hi in zip([0, *radii[:-1]], radii)] + [f"beyond_{radii[-1]}m"]
    return pd.cut(dist_m, bins=edges, labels=labels, right=True, include_lowest=True)


def load_grid_cells(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_grid_cells_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data grid preprocess` first.")
    return gpd.read_parquet(path)


def match_grid_point(
    cells_gdf: gpd.GeoDataFrame,
    barriers_gdf: gpd.GeoDataFrame,
    *,
    band_radii: tuple[int, ...] = BAND_RADII_M,
    metric_crs: str = METRIC_CRS,
) -> pd.DataFrame:
    """One row per grid cell: nearest barrier distance/id/built_year, plus
    an `ever_near_{radius}m` boolean per configured band -- the
    treated/untreated flags this output spec exists for, each just a
    threshold on the one nearest-distance value already computed.

    Only the single *nearest* barrier's `built_year` is looked up (not
    "any barrier within the widest band", unlike schools' pair-table
    `timing_unknown`, computed densely across every within-`max_dist`
    pair -- infeasible at grid-cell scale). `timing_unknown` is gated on
    `ever_treated` so an untreated cell's merely-nearest-but-irrelevant
    (often far outside every band) barrier having no recorded year doesn't
    mark it "unknown timing" -- unknown timing only means something for a
    cell that's actually treated.

    Also carries through, from that same nearest barrier: `dist_bin`
    (mutually-exclusive distance bin, see `build_dist_bin`),
    `relative_loudness_reduction_pct` (continuous distance-decay exposure
    index, see `compute_relative_loudness_reduction_pct`), and whichever of
    `BARRIER_COVARIATE_COLUMNS` exist on this `kind`'s barrier layer
    (heterogeneity covariates -- barrier height/material/absorbency)."""
    cells_m = cells_gdf[["cell_id", "geometry"]].to_crs(metric_crs).reset_index(drop=True)
    barriers_m = barriers_gdf.to_crs(metric_crs).reset_index(drop=True)

    nearest = nearest_segment(cells_m, barriers_m)
    nearest_idx = nearest["index_right"].to_numpy()
    rollup = pd.DataFrame(
        {
            "cell_id": cells_m["cell_id"].to_numpy(),
            "nearest_dist_m": nearest["dist_m"].to_numpy().round(1),
            # `element_id` is the barrier's road link, shared by several
            # barriers; the row position identifies the barrier itself.
            "nearest_barrier_row": nearest_idx,
            "nearest_element_id": barriers_m["element_id"].to_numpy()[nearest_idx],
            "built_year": barriers_m["built_year"].to_numpy()[nearest_idx],
        }
    )
    rollup["treat_year"] = rollup["built_year"]

    for column in BARRIER_COVARIATE_COLUMNS:
        if column in barriers_m.columns:
            rollup[column] = barriers_m[column].to_numpy()[nearest_idx]

    for radius in band_radii:
        rollup[f"ever_near_{radius}m"] = rollup["nearest_dist_m"] <= radius

    rollup["ever_treated"] = rollup[f"ever_near_{max(band_radii)}m"]
    rollup["timing_unknown"] = rollup["ever_treated"] & rollup["treat_year"].isna()
    rollup["dist_bin"] = build_dist_bin(rollup["nearest_dist_m"], band_radii)
    rollup["relative_loudness_reduction_pct"] = compute_relative_loudness_reduction_pct(
        rollup["nearest_dist_m"].to_numpy()
    )
    return rollup


def add_side_treatment_definitions(rollup: pd.DataFrame, side: pd.DataFrame) -> pd.DataFrame:
    """Merges `side.match_grid_side_for_kind`'s per-cell columns onto
    `match_grid_point`'s rollup and derives the tiers, gated on the
    point-distance `ever_treated`. This is the same tiering as
    `schools/assemble.py::add_network_treatment_definitions`.

    - **`ever_treated_same_route` / `ever_treated_same_side`** are judged
      against the cell's nearest barrier, whose `treat_year` they share.
      `same_side_unknown` marks `same_route` cells whose barrier side
      couldn't be determined (`same_side` is then False, not a verified
      wrong side).
    - **`ever_treated_protected`** is judged against every barrier, since
      any of them may protect the cell (see `side.match_grid_protection`).
      Its timing comes from the protecting barriers:
      `first_treat_year_protected` is the earliest of their `built_year`s,
      and `timing_unknown_protected` means one of them is undated.
      `protected_unknown` marks cells a barrier with an unknown side would
      protect."""
    out = rollup.merge(side, on="cell_id", how="left")
    out["same_route"] = out["same_route"].fillna(False).astype(bool)
    for flag in ("same_side", "same_side_unknown", "protected", "protected_unknown", "protected_undated"):
        out[flag] = out[flag].fillna(False).astype(bool)
    out["ever_treated_same_route"] = out["ever_treated"] & out["same_route"]
    out["ever_treated_same_side"] = out["ever_treated_same_route"] & out["same_side"]
    for tier in ("same_route", "same_side"):
        out[f"timing_unknown_{tier}"] = out[f"ever_treated_{tier}"] & out["treat_year"].isna()
    out["ever_treated_protected"] = out["ever_treated"] & out["protected"]
    out["first_treat_year_protected"] = out["treat_year_protected"].where(out["ever_treated_protected"])
    out["timing_unknown_protected"] = out["ever_treated_protected"] & out["protected_undated"]
    return out.drop(columns=["treat_year_protected", "protected_undated"])


def build_combined_rollup(cells_gdf: gpd.GeoDataFrame, rollups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per grid cell, `{kind}_`-prefixed columns from each kind's
    rollup -- mirrors `schools/assemble.py::build_combined_rollup`. The
    `same_route`/`same_side` tier columns are only filled when present --
    callers passing a bare `match_grid_point` rollup (no
    `add_side_treatment_definitions` applied, a legitimate standalone use)
    still get a valid combined rollup, just without that tier."""
    combined = cells_gdf[["cell_id"]].copy()
    for kind, rollup in rollups.items():
        renamed = rollup.rename(columns={col: f"{kind}_{col}" for col in rollup.columns if col != "cell_id"})
        combined = combined.merge(renamed, on="cell_id", how="left")
        for flag in (
            "ever_treated", "timing_unknown", "ever_treated_same_route", "ever_treated_same_side",
            "ever_treated_protected", "timing_unknown_protected", "same_side_unknown", "protected_unknown",
        ):
            column = f"{kind}_{flag}"
            if column in combined.columns:
                combined[column] = combined[column].fillna(False)
    return combined


def run_grid_assemble(
    *,
    kinds: tuple[str, ...] = BARRIER_KINDS,
    band_radii: tuple[int, ...] = BAND_RADII_M,
    root: Path | None = None,
) -> dict:
    cells_gdf = load_grid_cells(root)

    rollups: dict[str, pd.DataFrame] = {}
    for kind in kinds:
        barriers_gdf = load_noise_barriers(kind, root)
        rollup = match_grid_point(cells_gdf, barriers_gdf, band_radii=band_radii)
        side = match_grid_side_for_kind(cells_gdf, barriers_gdf, kind, root=root)
        rollup = add_side_treatment_definitions(rollup, side)
        rollups[kind] = rollup
        rollup.to_parquet(assembled_dir(root) / f"grid_{kind}_rollup.parquet", index=False)

    combined = build_combined_rollup(cells_gdf, rollups)
    combined_path = assembled_dir(root) / "grid_barrier_rollup.parquet"
    combined.to_parquet(combined_path, index=False)

    return {
        "n_cells": int(len(cells_gdf)),
        "band_radii_m": list(band_radii),
        "kinds": {
            kind: {
                "n_barriers": int(len(load_noise_barriers(kind, root))),
                "n_ever_treated": int(rollups[kind]["ever_treated"].sum()),
                "n_timing_unknown": int(rollups[kind]["timing_unknown"].sum()),
                "n_ever_treated_same_route": int(rollups[kind]["ever_treated_same_route"].sum()),
                "n_ever_treated_same_side": int(rollups[kind]["ever_treated_same_side"].sum()),
                "n_ever_treated_same_side_unknown": int(
                    (rollups[kind]["ever_treated_same_route"] & rollups[kind]["same_side_unknown"]).sum()
                ),
                "n_ever_treated_protected": int(rollups[kind]["ever_treated_protected"].sum()),
                "n_ever_treated_protected_unknown": int(rollups[kind]["protected_unknown"].sum()),
                "n_ever_treated_protected_by_several_barriers": int(
                    (rollups[kind]["ever_treated_protected"] & (rollups[kind]["n_protecting_barriers"] > 1)).sum()
                ),
                "n_ever_treated_protected_not_by_nearest": int(
                    (
                        rollups[kind]["ever_treated_protected"]
                        & (rollups[kind]["protected_barrier_row"] != rollups[kind]["nearest_barrier_row"])
                    ).sum()
                ),
                "ever_treated_same_route_by_side_method": {
                    str(k): int(v)
                    for k, v in rollups[kind].loc[rollups[kind]["ever_treated_same_route"], "side_method"].value_counts().items()
                },
                "dist_bin_counts": {
                    str(label): int(count)
                    for label, count in rollups[kind]["dist_bin"].value_counts(dropna=False).sort_index().items()
                },
                **{
                    f"n_ever_near_{radius}m": int(rollups[kind][f"ever_near_{radius}m"].sum())
                    for radius in band_radii
                },
            }
            for kind in kinds
        },
        "combined_rollup_path": str(combined_path),
    }
