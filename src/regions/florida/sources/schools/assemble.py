"""Stage 2 for the Florida ``schools`` source: the school <-> barrier match.

``REQUIRES noise_barriers`` (its ``preprocess`` must already have written
``barriers.parquet``) — this is why it is a separate ``assemble`` step rather
than part of ``preprocess``: editing a Cluster-A covariate definition should
never re-run this geospatial join, and vice versa.

Writes two artifacts, both **point-only** (matching algorithms 1-2 of the
rigour ladder in ``docs/data/florida/schools/README.md``; algorithms 3-6 need
the FDOT RCI roadway network — a planned separate ``road_network`` source —
and are left as ``NA`` placeholder columns here):

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
from src.regions.florida.sources.schools.shared import (
    assembled_rollup_path,
    assembled_treatment_path,
    processed_cross_section_path,
)

MAX_DIST_M = 1000
BUFFERS_M = (100, 200, 300, 500, 1000)

# Placeholder columns for the road-network-dependent matching algorithms
# (3 road_gated, 4 same_segment, 5 same_side, 6 shielded_arc). Populated once
# a `road_network` source exists.
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
    """Load the cross-section + barrier layer, match, validate, and persist."""
    placed = load_placed_cross_section(root)
    barriers = load_barriers(root)
    pair, rollup = match_barriers_point(placed, barriers, max_dist, buffers)

    if not rollup["msid"].is_unique:
        raise ValueError("schools_treatment_rollup must be one row per msid")
    fdot_pairs = pair[pair["category"].eq("fdot_barrier")]

    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/schools/assemble.py",
        "algorithms": {"implemented": ["euclid_nearest", "buffer_dose"],
                       "pending_road_network": ["road_gated", "same_segment", "same_side", "shielded_arc"]},
        "max_dist_m": max_dist,
        "buffers_m": list(buffers),
        "schools_placed": int(len(placed)),
        "pairs": int(len(pair)),
        "schools_matched": int(rollup["msid"].nunique()),
        "schools_within_500m": int((rollup["nearest_fdot_dist_m"] <= 500).sum()),
        "schools_within_1000m": int((rollup["nearest_fdot_dist_m"] <= 1000).sum()),
        "undated_fdot_pair_share": float(fdot_pairs["timing_unknown"].mean()) if len(fdot_pairs) else None,
    }
    saved = save_treatment(pair, rollup, root)
    report["saved"] = saved
    return report
