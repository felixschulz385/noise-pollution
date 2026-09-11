"""Stage 2 for the Florida ``schools`` source: the school <-> barrier match.

``REQUIRES noise_barriers`` (its ``preprocess`` must already have written
``barriers.parquet``) and ``road_network`` (its ``preprocess`` must have
written ``road_network.parquet``) — this is why it is a separate
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

from src.regions.florida.sources.noise_barriers.shared import processed_barriers_path
from src.regions.florida.sources.road_network.linear_ref import (
    DEFAULT_CORRIDOR_BUDGET_M,
    DEFAULT_CORRIDOR_BUFFER_M,
    arterial_subset,
    build_adjacency,
    corridor_geometry,
    milepost_and_side,
    nearest_road,
)
from src.regions.florida.sources.road_network.shared import processed_road_network_path
from src.regions.florida.sources.schools.shared import (
    assembled_rollup_path,
    assembled_treatment_path,
    processed_cross_section_path,
)

MAX_DIST_M = 1000
BUFFERS_M = (100, 200, 300, 500, 1000)

# Columns filled by algorithms 3-5 (road_gated, same_segment, same_side) via
# `match_barriers_road`. `shielded_frac` (algorithm 6, stretch goal) stays a
# documented `NA` placeholder — not implemented.
PENDING_ROAD_COLUMNS = ("road_id", "same_route", "school_side", "wall_side", "shielded_frac")


def load_placed_cross_section(root: Path | None = None) -> gpd.GeoDataFrame:
    """The `schools preprocess` cross-section, restricted to schools that got a
    real coordinate (``geom_source != 'none'``)."""
    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    xs = gpd.read_parquet(path)
    return xs[xs["geom_source"] != "none"].reset_index(drop=True)


def load_barriers(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_barriers_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data noise-barriers preprocess` first.")
    return gpd.read_parquet(path)


def load_road_network(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_road_network_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data road-network preprocess` first.")
    return gpd.read_parquet(path)


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

    first_treat = (
        pair.loc[pair["category"].eq("fdot_barrier")]
        .groupby("msid")["treat_year"].min().rename("first_treat_year")
    )
    rollup = rollup.merge(first_treat, on="msid", how="left")
    undated_msid = set(pair.loc[pair["timing_unknown"], "msid"])
    rollup["any_timing_unknown"] = rollup["msid"].isin(undated_msid)
    return pair, rollup


def match_barriers_road(
    pair: pd.DataFrame,
    placed: gpd.GeoDataFrame,
    barriers: gpd.GeoDataFrame,
    road_network: gpd.GeoDataFrame,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
) -> pd.DataFrame:
    """Algorithms 3 (``road_gated``) + 4 (``same_segment``) + 5
    (``same_side``): fills ``road_id`` / ``same_route`` / ``school_side`` /
    ``wall_side`` on the existing point-only ``pair`` table (from
    :func:`match_barriers_point`) — does **not** add new candidate pairs,
    only annotates the ones already within ``MAX_DIST_M``.

    Design (validated in ``schools.ipynb`` §7, see
    ``road_network/linear_ref.py`` for the geometry helpers): each wall gets
    a network-distance-bounded "corridor" polygon grown outward from its
    point along the arterial road network's real connectivity; a pair is
    ``same_route`` when the school falls inside its wall's corridor, and
    ``school_side``/``wall_side`` (signed, pairwise-only — never a compass
    direction) come from each point's own nearest-segment projection.

    Run for every wall regardless of ``category`` — the corridor/side
    geometry is a general fact about the wall's location, not an
    FDOT-specific one, and ``other_wall`` rows are meant to be usable as a
    shielding covariate even though they're never ``treat_year``.
    """
    major = arterial_subset(road_network)
    geoms = major.geometry.to_numpy()
    lengths = major.geometry.length.to_numpy()
    endpoints = build_adjacency(major)

    walls = barriers.reset_index(drop=True)
    walls["rep_point"] = walls.geometry.interpolate(0.5, normalized=True)
    wall_pts = gpd.GeoDataFrame(
        {"gcid": walls["gcid"].to_numpy()}, geometry=walls["rep_point"].to_numpy(), crs=walls.crs
    )
    wj = nearest_road(wall_pts, major)
    wj["gcid"] = walls["gcid"].to_numpy()
    wj["wall_pt"] = walls["rep_point"].to_numpy()
    wall_res = [milepost_and_side(r.wall_pt, r.road_geometry, r.begin_post, r.end_post) for r in wj.itertuples()]
    wj[["milepost", "side", "offset_m"]] = pd.DataFrame(wall_res, index=wj.index)
    wj["roadway_id"] = major["roadway_id"].to_numpy()[wj["index_right"].to_numpy()]

    sj = nearest_road(placed[["geometry"]], major)
    sj["msid"] = placed["msid"].to_numpy()
    sj["school_pt"] = placed["geometry"].to_numpy()
    school_res = [milepost_and_side(r.school_pt, r.road_geometry, r.begin_post, r.end_post) for r in sj.itertuples()]
    sj[["milepost", "side", "offset_m"]] = pd.DataFrame(school_res, index=sj.index)

    corridors = {
        gcid: corridor_geometry(int(idx_right), wall_pt, geoms, lengths, endpoints, budget_m=budget_m).buffer(buffer_m)
        for gcid, idx_right, wall_pt in zip(wj["gcid"], wj["index_right"], wj["wall_pt"])
    }
    wj_by_gcid = wj.set_index("gcid")
    sj_by_msid = sj.set_index("msid")

    road_id, same_route, school_side, wall_side = [], [], [], []
    for row in pair.itertuples():
        corridor = corridors.get(row.gcid)
        if corridor is None or row.msid not in sj_by_msid.index:
            road_id.append(pd.NA)
            same_route.append(pd.NA)
            school_side.append(pd.NA)
            wall_side.append(pd.NA)
            continue
        wall_row = wj_by_gcid.loc[row.gcid]
        school_row = sj_by_msid.loc[row.msid]
        within = bool(corridor.contains(school_row["school_pt"]))
        road_id.append(wall_row["roadway_id"])
        same_route.append(within)
        school_side.append(school_row["side"] if within else pd.NA)
        wall_side.append(wall_row["side"] if within else pd.NA)

    out = pair.copy()
    out["road_id"] = road_id
    out["same_route"] = pd.array(same_route, dtype="boolean")
    out["school_side"] = school_side
    out["wall_side"] = wall_side
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
    corridor_budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    corridor_buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
) -> dict[str, object]:
    """Load the cross-section + barrier + road-network layers, match,
    validate, and persist."""
    placed = load_placed_cross_section(root)
    barriers = load_barriers(root)
    road_network = load_road_network(root)
    pair, rollup = match_barriers_point(placed, barriers, max_dist, buffers)
    pair = match_barriers_road(pair, placed, barriers, road_network, corridor_budget_m, corridor_buffer_m)

    if not rollup["msid"].is_unique:
        raise ValueError("schools_treatment_rollup must be one row per msid")
    fdot_pairs = pair[pair["category"].eq("fdot_barrier")]
    same_route_pairs = pair[pair["same_route"] == True]  # noqa: E712 (nullable boolean, != is not safe)
    same_side_pairs = same_route_pairs[same_route_pairs["school_side"] == same_route_pairs["wall_side"]]

    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/schools/assemble.py",
        "algorithms": {"implemented": ["euclid_nearest", "buffer_dose", "road_gated", "same_segment", "same_side"],
                       "pending": ["shielded_arc"]},
        "max_dist_m": max_dist,
        "buffers_m": list(buffers),
        "corridor_budget_m": corridor_budget_m,
        "corridor_buffer_m": corridor_buffer_m,
        "schools_placed": int(len(placed)),
        "pairs": int(len(pair)),
        "schools_matched": int(rollup["msid"].nunique()),
        "schools_within_500m": int((rollup["nearest_fdot_dist_m"] <= 500).sum()),
        "schools_within_1000m": int((rollup["nearest_fdot_dist_m"] <= 1000).sum()),
        "undated_fdot_pair_share": float(fdot_pairs["timing_unknown"].mean()) if len(fdot_pairs) else None,
        "pairs_same_route": int(len(same_route_pairs)),
        "pairs_same_side": int(len(same_side_pairs)),
        "schools_same_side_of_an_fdot_wall": int(
            same_side_pairs.loc[same_side_pairs["category"].eq("fdot_barrier"), "msid"].nunique()
        ),
    }
    saved = save_treatment(pair, rollup, root)
    report["saved"] = saved
    return report
