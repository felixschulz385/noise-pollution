"""Stage: match geocoded schools to nearby road/rail noise barriers.

REQUIRES `noise_barriers preprocess`, `schools preprocess` and
`barrier-protection build` (which in turn needs `road-network preprocess`
/ `network preprocess-tracks` and `osm-walls preprocess`). Kept as its own
step rather than folded into `schools preprocess`, same isolation reason
Florida's `schools/assemble.py` is separate: editing a geocoding rule
should never re-run this geospatial join, and vice versa.

Writes two files (since 2026-10-20; before, thirteen: point and network
versions per kind, a wide combined rollup, and the vanished-school
recovery's own): `schools_barrier_pairs.parquet` and
`schools_barrier_rollup.parquet`, both long by `kind` -- read them with
`load_barrier_pairs` / `load_barrier_rollup`.

Algorithms 1-2 (`match_barriers_point`): a dense school x barrier distance
matrix in SWEREF 99 TM, then a pair table + per-school rollup. Algorithms
4-5 (`match_barriers_network`): `same_route` / `same_side` per pair, from
`_barrier_reference.py`, applied to the references `barrier-protection
build` saved -- the same ones the `grid` output uses; see
`docs/data/sweden/barrier_matching.md`. Road and rail are run
separately -- different noise sources, kept as two parallel
treatment-timing tiers rather than merged into one "nearest barrier of
either kind".
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.barrier_geometry.protection import BarrierReferences, classify_points
from src.regions.sweden.sources._layout import METRIC_CRS
from src.regions.sweden.sources.barrier_protection.shared import ROUTE_COLUMNS, load_barrier_references
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers
from src.regions.sweden.sources.schools.shared import schools_paths


MAX_DIST_M = 1000.0
BUFFERS_M = (100, 200, 300, 500, 1000)


def load_geocoded_schools(root: Path | None = None) -> gpd.GeoDataFrame:
    path = schools_paths(root)["processed"] / "schools.geojson"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data schools preprocess` first.")
    schools_gdf = gpd.read_file(path)
    return schools_gdf[schools_gdf.geometry.notna()].reset_index(drop=True)


def match_barriers_point(
    schools_gdf: gpd.GeoDataFrame,
    barriers_gdf: gpd.GeoDataFrame,
    *,
    max_dist: float = MAX_DIST_M,
    buffers: tuple[int, ...] = BUFFERS_M,
    metric_crs: str = METRIC_CRS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A dense school x barrier distance matrix (thousands of schools x a
    couple thousand barrier segments is cheap), then the pair table + the
    per-school rollup. `.distance()` from a Point to a LineString already
    gives the nearest-point-on-line distance, no extra handling needed."""
    schools_m = schools_gdf.to_crs(metric_crs)
    barriers_m = barriers_gdf.to_crs(metric_crs)

    dist = np.vstack([barriers_m.geometry.distance(point).to_numpy() for point in schools_m.geometry])

    rollup = schools_gdf[["skolenhetskod"]].copy()
    rollup["nearest_dist_m"] = dist.min(axis=1).round(1)
    rollup["nearest_barrier_row"] = dist.argmin(axis=1)
    rollup["nearest_element_id"] = barriers_gdf["element_id"].to_numpy()[rollup["nearest_barrier_row"]]
    for radius in buffers:
        rollup[f"n_barriers_{radius}m"] = (dist <= radius).sum(axis=1)
        rollup[f"ever_near_{radius}m"] = rollup[f"n_barriers_{radius}m"] > 0

    school_i, barrier_i = np.where(dist <= max_dist)
    pair = pd.DataFrame(
        {
            "skolenhetskod": schools_gdf["skolenhetskod"].to_numpy()[school_i],
            # `element_id` is NOT a unique key into `barriers_gdf` (a barrier
            # can be split into several geometry rows sharing one id, e.g.
            # rail: 827 distinct ids / 1,829 rows -- confirmed live
            # 2026-09-15) -- `barrier_row` (the positional row index) is the
            # only unambiguous way to look this pair's exact barrier
            # geometry back up, needed by the network-matching algorithms.
            "barrier_row": barrier_i,
            "element_id": barriers_gdf["element_id"].to_numpy()[barrier_i],
            "dist_m": dist[school_i, barrier_i].round(1),
            "built_year": barriers_gdf["built_year"].to_numpy()[barrier_i],
        }
    )
    pair["treat_year"] = pair["built_year"]
    pair["timing_unknown"] = pd.isna(pair["built_year"])
    for radius in buffers:
        pair[f"within_{radius}m"] = pair["dist_m"] <= radius
    # Compared on `barrier_row`, not `element_id` -- two different barrier
    # rows can share one `element_id` (see the note above), which would
    # otherwise mark more than one pair row "nearest" for the same school.
    nearest_by_school = rollup.set_index("skolenhetskod")["nearest_barrier_row"]
    pair["is_nearest"] = pair["barrier_row"] == pair["skolenhetskod"].map(nearest_by_school)

    first_treat = pair.groupby("skolenhetskod")["treat_year"].min().rename("first_treat_year")
    rollup = rollup.merge(first_treat, on="skolenhetskod", how="left")
    rollup["ever_treated"] = rollup["skolenhetskod"].isin(set(pair["skolenhetskod"]))
    undated_schools = set(pair.loc[pair["timing_unknown"], "skolenhetskod"])
    rollup["timing_unknown"] = rollup["skolenhetskod"].isin(undated_schools)

    return pair, rollup


NETWORK_TIERS = ("same_route", "same_side", "protected")

def match_barriers_network(
    pair: pd.DataFrame,
    schools_gdf: gpd.GeoDataFrame,
    refs: BarrierReferences,
    *,
    kind: str,
) -> pd.DataFrame:
    """Algorithms 4 (`same_route`) + 5 (`same_side`): annotates the point-only
    `pair` table (from :func:`match_barriers_point`, keyed by `barrier_row`
    since `element_id` is the road link, not the barrier) with `same_route`,
    `side_method`, `same_side`, `same_side_unknown`, the protected-area
    columns `lateral_m` / `along_offset_m` / `protected` /
    `protected_unknown`, and the matched `osm_id` (plus `bandel` for rail),
    judged against `refs` (`barrier_protection.shared.load_barrier_references`).
    Adds no pairs -- only annotates those already within `MAX_DIST_M`. Every
    barrier within that distance is judged, so a school protected by any of
    them counts."""
    school_points = schools_gdf.to_crs(METRIC_CRS).set_index("skolenhetskod").geometry
    barrier_rows = pair["barrier_row"].to_numpy()
    classified = classify_points(school_points.loc[pair["skolenhetskod"]].to_numpy(), barrier_rows, refs)

    out = pair.reset_index(drop=True).copy()
    out["same_route"] = classified["same_route"]
    out["side_method"] = classified["side_method"]
    for column in ("same_side", "same_side_unknown", "lateral_m", "along_offset_m", "protected", "protected_unknown"):
        out[column] = classified[column]
    out["osm_id"] = refs.table["osm_id"].to_numpy()[barrier_rows]
    if ROUTE_COLUMNS[kind]:
        out[ROUTE_COLUMNS[kind]] = refs.table["route"].to_numpy()[barrier_rows]
    return out


def add_network_treatment_definitions(pair: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    """Adds the `same_route` (algorithm 4), `same_side` (algorithm 5) and
    `protected` (same side AND beside the barrier's own stretch, see
    `_barrier_reference.classify_points`) treatment-timing tiers to
    `rollup`, alongside the point-only tier --
    each gates the same `groupby("skolenhetskod")["treat_year"].min()` on a
    stricter pair subset, mirroring Florida's
    `add_road_treatment_definitions`. `same_side_unknown` flags schools with
    at least one `same_route` pair whose barrier side couldn't be
    determined, so an analysis can drop them from the `same_side` contrast
    rather than count them as untreated; `protected_unknown` does the same
    for the `protected` tier (only pairs beside the stretch count).
    `protected_barrier_row` is the protecting barrier nearest the school."""
    out = rollup.copy()
    for name in NETWORK_TIERS:
        qualifying = pair[pair[name]]
        first_year = qualifying.groupby("skolenhetskod")["treat_year"].min()
        out[f"first_treat_year_{name}"] = out["skolenhetskod"].map(first_year)
        out[f"ever_treated_{name}"] = out["skolenhetskod"].isin(set(qualifying["skolenhetskod"]))
        undated_schools = set(qualifying.loc[qualifying["timing_unknown"], "skolenhetskod"])
        out[f"timing_unknown_{name}"] = out["skolenhetskod"].isin(undated_schools)
    for flag in ("same_side_unknown", "protected_unknown"):
        out[flag] = out["skolenhetskod"].isin(set(pair.loc[pair[flag], "skolenhetskod"]))
    # The protecting barrier nearest the school (by distance from its road):
    # the one whose road's traffic the panel attaches as the shielded road.
    protecting = pair[pair["protected"]].sort_values("lateral_m").drop_duplicates("skolenhetskod")
    out["protected_barrier_row"] = (
        out["skolenhetskod"].map(protecting.set_index("skolenhetskod")["barrier_row"]).astype("Int64")
    )
    return out


PAIRS_FILENAME = "schools_barrier_pairs.parquet"
ROLLUP_FILENAME = "schools_barrier_rollup.parquet"


def assembled_dir(root: Path | None = None) -> Path:
    return schools_paths(root)["assembled"]


def match_barriers(
    schools_gdf: gpd.GeoDataFrame,
    kind: str,
    *,
    max_dist: float = MAX_DIST_M,
    root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One barrier kind, all four tiers: the point match (algorithms 1-2),
    then the network annotation (4-5) against the references `barrier-
    protection build` saved. Returns the annotated pair table and the
    per-school rollup with every tier's treatment timing."""
    barriers_gdf = load_noise_barriers(kind, root)
    pair, rollup = match_barriers_point(schools_gdf, barriers_gdf, max_dist=max_dist)
    refs = load_barrier_references(kind, root, barriers_gdf=barriers_gdf)
    annotated_pair = match_barriers_network(pair, schools_gdf, refs, kind=kind)
    return annotated_pair, add_network_treatment_definitions(annotated_pair, rollup)


def _stack(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat([table.assign(kind=kind) for kind, table in tables.items()], ignore_index=True)[
        ["kind", *dict.fromkeys(col for table in tables.values() for col in table.columns)]
    ]


def _load_assembled(filename: str, kind: str | None, root: Path | None) -> pd.DataFrame:
    if kind is not None and kind not in BARRIER_KINDS:
        raise ValueError(f"Unknown barrier kind '{kind}'. Use one of: {BARRIER_KINDS}.")
    path = assembled_dir(root) / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data schools assemble` first.")
    table = pd.read_parquet(path)
    if kind is None:
        return table
    other_route_columns = [col for k, col in ROUTE_COLUMNS.items() if col and k != kind]
    return (
        table[table["kind"] == kind]
        .drop(columns=["kind", *[c for c in other_route_columns if c in table.columns]])
        .reset_index(drop=True)
    )


def load_barrier_pairs(kind: str | None = None, root: Path | None = None) -> pd.DataFrame:
    """`schools_barrier_pairs.parquet`: one row per school x barrier within
    `MAX_DIST_M`, with a `kind` column; `kind` given, that kind's rows
    without the column (the per-kind table `match_barriers` returned)."""
    return _load_assembled(PAIRS_FILENAME, kind, root)


def load_barrier_rollup(kind: str | None = None, root: Path | None = None) -> pd.DataFrame:
    """`schools_barrier_rollup.parquet`: one row per geocoded school and
    barrier kind, every tier's treatment timing; `kind` as in
    :func:`load_barrier_pairs`."""
    return _load_assembled(ROLLUP_FILENAME, kind, root)


def run_schools_assemble(
    *,
    kinds: tuple[str, ...] = BARRIER_KINDS,
    max_dist: float = MAX_DIST_M,
    root: Path | None = None,
) -> dict:
    schools_gdf = load_geocoded_schools(root)

    pairs: dict[str, pd.DataFrame] = {}
    rollups: dict[str, pd.DataFrame] = {}
    for kind in kinds:
        pairs[kind], rollups[kind] = match_barriers(schools_gdf, kind, max_dist=max_dist, root=root)

    pairs_path = assembled_dir(root) / PAIRS_FILENAME
    rollup_path = assembled_dir(root) / ROLLUP_FILENAME
    _stack(pairs).to_parquet(pairs_path, index=False)
    _stack(rollups).to_parquet(rollup_path, index=False)

    return {
        "n_schools": int(len(schools_gdf)),
        "kinds": {
            kind: {
                "n_pairs": int(len(pairs[kind])),
                **{
                    f"n_ever_treated_{tier}": int(rollups[kind][column].sum())
                    for tier, column in [("point", "ever_treated"), *((t, f"ever_treated_{t}") for t in NETWORK_TIERS)]
                },
                "n_same_side_unknown": int(rollups[kind]["same_side_unknown"].sum()),
                "n_protected_unknown": int(rollups[kind]["protected_unknown"].sum()),
            }
            for kind in kinds
        },
        "saved": {"pairs": str(pairs_path), "rollup": str(rollup_path)},
    }
