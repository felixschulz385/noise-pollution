"""Stage 2 for the Florida ``schools`` source: the school <-> barrier match.

``REQUIRES noise_barriers`` (its ``preprocess`` must already have written
``barriers.parquet``) and ``barrier_protection`` (its ``build`` must have
written the wall references, from ``road_network``) — this is why it is a separate
``assemble`` step rather than part of ``preprocess``: editing a Cluster-A
covariate definition should never re-run this geospatial join, and vice
versa.

Writes two artifacts, implementing matching algorithms 1-5 of the rigour
ladder in ``docs/data/florida/schools/README.md`` (algorithm 6,
``shielded_arc``, is a stretch goal — left as an ``NA`` placeholder column):

* **`schools_treatment.parquet`** — one row per candidate ``(msid, gcid)`` pair
  within ``MAX_DIST_M`` of each other.
* **`schools_treatment_rollup.parquet`** — one row per placed ``msid``: nearest-
  wall distance, buffer counts/length, first treatment year.

Treatment timing: ``treat_year = built_year`` of the matched wall for
``category == 'fdot_barrier'`` (the *original* construction year, per
``noise_barriers``, so ``REPLACED`` walls use their original year too);
``NA`` + ``timing_unknown`` when the wall's ``built_year`` is unknown;
``other_wall`` (private/perimeter, non-FDOT) is carried as a potential
shielding covariate but never as treatment (``treat_year`` always ``NA``).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.barrier_geometry.protection import BarrierReferences, classify_points
from src.regions.florida.sources._layout import METRIC_CRS
from src.regions.florida.sources.barrier_protection.shared import load_barrier_references
from src.regions.florida.sources.noise_barriers.shared import load_barriers
from src.regions.florida.sources.schools.shared import (
    assembled_rollup_path,
    assembled_treatment_path,
    processed_cross_section_path,
)

MAX_DIST_M = 1000
BUFFERS_M = (100, 200, 300, 500, 1000)

# Columns filled by algorithms 3-5 (road_gated, same_segment, same_side) and
# the protected-area tier via `match_barriers_road`. `shielded_frac`
# (algorithm 6, stretch goal) stays a documented `NA` placeholder — not
# implemented.
PENDING_ROAD_COLUMNS = (
    "road_id", "same_route", "side_method", "same_side", "same_side_unknown",
    "lateral_m", "along_offset_m", "protected", "protected_unknown", "shielded_frac",
)
ROAD_TIERS = ("same_route", "same_side", "protected")


def load_placed_cross_section(root: Path | None = None) -> gpd.GeoDataFrame:
    """The `schools preprocess` cross-section, restricted to schools that got a
    real coordinate (``geom_source != 'none'``)."""
    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    xs = gpd.read_parquet(path)
    return xs[xs["geom_source"] != "none"].reset_index(drop=True)


def match_barriers_point(
    placed: gpd.GeoDataFrame,
    barriers: gpd.GeoDataFrame,
    max_dist: float = MAX_DIST_M,
    buffers: tuple[int, ...] = BUFFERS_M,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Algorithms 1 (``euclid_nearest``) + 2 (``buffer_dose``): a dense
    school x wall distance matrix (a few thousand schools x ~1.3k walls is
    cheap), then the pair table + the per-school rollup."""
    if placed.crs != barriers.crs:
        raise ValueError(f"CRS mismatch: schools {placed.crs} vs barriers {barriers.crs}")

    dist = np.vstack([barriers.geometry.distance(p).to_numpy() for p in placed.geometry])
    is_fdot = (barriers["category"] == "fdot_barrier").to_numpy()
    seg_len = barriers["seg_len_m"].fillna(0).to_numpy()
    dist_fdot = np.where(is_fdot, dist, np.inf)

    rollup = placed[["msid", "ncessch"]].copy()
    rollup["nearest_fdot_dist_m"] = dist_fdot.min(axis=1).round(1)
    rollup["nearest_fdot_gcid"] = barriers["gcid"].to_numpy()[dist_fdot.argmin(axis=1)]
    for radius in buffers:
        rollup[f"n_walls_{radius}m"] = ((dist <= radius) & is_fdot).sum(axis=1)
    rollup["wall_len_500m"] = ((dist <= 500) & is_fdot) @ seg_len
    for radius in (500, 1000):
        rollup[f"ever_near_wall_{radius}m"] = rollup[f"n_walls_{radius}m"] > 0

    school_i, wall_i = np.where(dist <= max_dist)
    pair = pd.DataFrame({
        "msid": placed["msid"].to_numpy()[school_i],
        "ncessch": placed["ncessch"].to_numpy()[school_i],
        "gcid": barriers["gcid"].to_numpy()[wall_i],
        "category": barriers["category"].to_numpy()[wall_i],
        "dist_m": dist[school_i, wall_i].round(1),
        "built_year": barriers["built_year"].to_numpy()[wall_i],
    })
    pair["treat_year"] = np.where(pair["category"].eq("fdot_barrier"), pair["built_year"], np.nan)
    pair["timing_unknown"] = pair["category"].eq("fdot_barrier") & pair["built_year"].isna()
    for radius in buffers:
        pair[f"within_{radius}m"] = pair["dist_m"] <= radius
    nearest_by_msid = rollup.set_index("msid")["nearest_fdot_gcid"]
    pair["is_nearest_fdot"] = pair["category"].eq("fdot_barrier") & (
        pair["gcid"] == pair["msid"].map(nearest_by_msid)
    )
    for col in PENDING_ROAD_COLUMNS:
        pair[col] = pd.NA

    # Treatment-timing tier 1 of 3 (``_point``, algorithms 1-2). Tiers 2-3
    # (``_same_route`` / ``_same_side``, algorithms 4-5) are added by
    # `add_road_treatment_definitions` once `match_barriers_road` has run —
    # all three are kept side by side, never collapsed to one "the"
    # definition, so the analysis layer picks a baseline + robustness checks
    # downstream instead of the matching code deciding for it.
    fdot_pairs = pair[pair["category"].eq("fdot_barrier")]
    first_treat_point = fdot_pairs.groupby("msid")["treat_year"].min().rename("first_treat_year_point")
    rollup = rollup.merge(first_treat_point, on="msid", how="left")
    rollup["ever_treated_point"] = rollup["msid"].isin(set(fdot_pairs["msid"]))
    undated_point_msid = set(fdot_pairs.loc[fdot_pairs["timing_unknown"], "msid"])
    rollup["timing_unknown_point"] = rollup["msid"].isin(undated_point_msid)
    return pair, rollup


def add_road_treatment_definitions(pair: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    """Adds the ``_same_route`` (algorithm 4), ``_same_side`` (algorithm 5)
    and ``_protected`` (same side and beside the wall's own stretch)
    treatment-timing tiers to ``rollup``, alongside the ``_point`` tier
    :func:`match_barriers_point` already computed. Must run after
    :func:`match_barriers_road` — each tier gates the same
    ``groupby("msid")["treat_year"].min()`` computation on progressively
    stricter matching criteria, same pattern as the ``_point`` tier.
    ``same_side_unknown`` / ``protected_unknown`` flag schools with an FDOT
    wall whose side couldn't be determined (so an analysis can drop them
    rather than count them as untreated).
    """
    fdot = pair[pair["category"].eq("fdot_barrier")].copy()

    out = rollup.copy()
    for name in ROAD_TIERS:
        qualifying = fdot[fdot[name].fillna(False).astype(bool)]
        first_year = qualifying.groupby("msid")["treat_year"].min()
        out[f"first_treat_year_{name}"] = out["msid"].map(first_year)
        out[f"ever_treated_{name}"] = out["msid"].isin(set(qualifying["msid"]))
        undated_msid = set(qualifying.loc[qualifying["timing_unknown"], "msid"])
        out[f"timing_unknown_{name}"] = out["msid"].isin(undated_msid)
    for flag in ("same_side_unknown", "protected_unknown"):
        out[flag] = out["msid"].isin(set(fdot.loc[fdot[flag].fillna(False).astype(bool), "msid"]))
    # The protecting FDOT wall nearest the school (by distance from its
    # road), and that wall's reference roadway: the road the school is
    # shielded from, whose traffic the panel attaches.
    protecting = (
        fdot[fdot["protected"].fillna(False).astype(bool)].sort_values("lateral_m").drop_duplicates("msid").set_index("msid")
    )
    out["protected_gcid"] = out["msid"].map(protecting["gcid"])
    out["protected_road_id"] = out["msid"].map(protecting["road_id"])
    return out


def match_barriers_road(
    pair: pd.DataFrame,
    placed: gpd.GeoDataFrame,
    barriers: gpd.GeoDataFrame,
    refs: BarrierReferences,
) -> pd.DataFrame:
    """Algorithms 3 (``road_gated``) + 4 (``same_segment``) + 5
    (``same_side``) and the protected-area tier: fills ``road_id`` /
    ``same_route`` / ``side_method`` / ``same_side`` / ``same_side_unknown`` /
    ``lateral_m`` / ``along_offset_m`` / ``protected`` / ``protected_unknown``
    on the existing point-only ``pair`` table (from
    :func:`match_barriers_point`) — does **not** add new candidate pairs, only
    annotates the ones already within ``MAX_DIST_M``.

    Each pair is judged against its wall's saved reference
    (``barrier_protection``): ``same_route`` when the school lies within the
    wall's corridor, ``same_side`` when it lies on the wall's side of the
    wall's own reference line, ``protected`` when it is also beside the
    wall's stretch (±50m) within 600m of the road. Every sign is taken
    against that one line, never against the school's own nearest segment
    (whose digitizing direction is unrelated). See
    ``src/core/barrier_geometry/protection.py`` and
    ``docs/data/florida/barrier_protection.md``.

    Run for every wall regardless of ``category`` — ``other_wall`` rows stay
    usable as a shielding covariate even though they're never
    ``treat_year``.
    """
    row_of_gcid = pd.Series(np.arange(len(barriers)), index=barriers["gcid"].to_numpy())
    barrier_rows = row_of_gcid.loc[pair["gcid"]].to_numpy()
    school_points = placed.to_crs(METRIC_CRS).set_index("msid").geometry
    classified = classify_points(school_points.loc[pair["msid"]].to_numpy(), barrier_rows, refs)

    out = pair.reset_index(drop=True).copy()
    out["road_id"] = refs.table["roadway_id"].to_numpy()[barrier_rows]
    for column in ("same_route", "side_method", "same_side", "same_side_unknown", "lateral_m", "along_offset_m",
                   "protected", "protected_unknown"):
        out[column] = classified[column].to_numpy()
    return out


def save_treatment(pair: pd.DataFrame, rollup: pd.DataFrame, root: Path | None = None) -> dict[str, str]:
    pair_path = assembled_treatment_path(root)
    rollup_path = assembled_rollup_path(root)
    for path in (pair_path, rollup_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    pair.to_parquet(pair_path, index=False)
    rollup.to_parquet(rollup_path, index=False)
    return {"treatment": str(pair_path), "rollup": str(rollup_path)}


def run_schools_assemble(
    root: Path | None = None,
    max_dist: float = MAX_DIST_M,
    buffers: tuple[int, ...] = BUFFERS_M,
) -> dict[str, object]:
    """Load the cross-section, the barrier layer and its saved references,
    match, validate, and persist."""
    placed = load_placed_cross_section(root)
    barriers = load_barriers(root).reset_index(drop=True)
    refs = load_barrier_references(root, barriers_gdf=barriers)
    pair, rollup = match_barriers_point(placed, barriers, max_dist, buffers)
    pair = match_barriers_road(pair, placed, barriers, refs)
    rollup = add_road_treatment_definitions(pair, rollup)

    if not rollup["msid"].is_unique:
        raise ValueError("schools_treatment_rollup must be one row per msid")
    fdot_pairs = pair[pair["category"].eq("fdot_barrier")]

    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/schools/assemble.py",
        "algorithms": {"implemented": ["euclid_nearest", "buffer_dose", "road_gated", "same_segment", "same_side",
                                       "protected"],
                       "pending": ["shielded_arc"]},
        "max_dist_m": max_dist,
        "buffers_m": list(buffers),
        "corridor_buffer_m": refs.buffer_m,
        "schools_placed": int(len(placed)),
        "pairs": int(len(pair)),
        "schools_matched": int(rollup["msid"].nunique()),
        "schools_within_500m": int((rollup["nearest_fdot_dist_m"] <= 500).sum()),
        "schools_within_1000m": int((rollup["nearest_fdot_dist_m"] <= 1000).sum()),
        "undated_fdot_pair_share": float(fdot_pairs["timing_unknown"].mean()) if len(fdot_pairs) else None,
        "ever_treated_by_definition": {
            name: int(rollup[f"ever_treated_{name}"].sum())
            for name in ("point", *ROAD_TIERS)
        },
        "schools_same_side_unknown": int(rollup["same_side_unknown"].sum()),
        "schools_protected_unknown": int(rollup["protected_unknown"].sum()),
        "fdot_pairs_by_side_method": {
            str(k): int(v) for k, v in fdot_pairs.loc[fdot_pairs["same_route"].fillna(False).astype(bool), "side_method"].value_counts().items()
        },
    }
    saved = save_treatment(pair, rollup, root)
    report["saved"] = saved
    return report
