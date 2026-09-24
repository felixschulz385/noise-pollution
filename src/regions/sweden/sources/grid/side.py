"""Stage: the "relevant side" vs. "wrong side" distinction for grid cells --
Moretti & Wheeler's core identification device (Section 3: "we focus on
properties on the noise-abated side... use those on the opposite side for a
placebo test"), and which cells a barrier actually protects.

Two judgements per cell, both from the references `barrier-protection
build` saved (the same ones `schools/assemble.py` uses; see
`docs/data/sweden/barrier_matching.md`):

- **Against the nearest barrier** (:func:`match_grid_side`): `same_route`,
  `side_method`, `same_side`, `same_side_unknown`, `lateral_m`,
  `along_offset_m` -- the tiers that mirror the point-distance match.
- **Against every barrier** (:func:`match_grid_protection`): a cell is
  `protected` if *any* barrier protects it. The nearest barrier isn't
  always the one beside the cell (e.g. a wall on a cross street can be
  nearer), so every barrier within `CANDIDATE_RADIUS_M` is judged by
  `classify_points`. This is exact; the national protection-zone layer
  (`barrier_protection`) draws the same areas as polygons for other uses.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.regions.sweden.sources._barrier_reference import (
    PROTECTED_MAX_LATERAL_M,
    PROTECTED_SPAN_MARGIN_M,
    BarrierReferences,
    classify_points,
)
from src.regions.sweden.sources._linear_ref import METRIC_CRS, nearest_segment
from src.regions.sweden.sources.barrier_protection.shared import load_barrier_references

# A protected point lies within 600m of its barrier's road, beside the
# barrier's stretch +-50m, so within ~602m of the barrier itself; the extra
# covers barriers whose own geometry sits a little off the road.
CANDIDATE_RADIUS_M = PROTECTED_MAX_LATERAL_M + PROTECTED_SPAN_MARGIN_M + 50.0

NEAREST_COLUMNS = ["same_route", "side_method", "same_side", "same_side_unknown", "lateral_m", "along_offset_m"]
PROTECTION_COLUMNS = [
    "protected",
    "protected_unknown",
    "n_protecting_barriers",
    "protected_barrier_row",
    "protected_side_method",
    "protected_lateral_m",
    "treat_year_protected",
    "protected_undated",
]


def match_grid_side(cells_gdf: gpd.GeoDataFrame, barriers_gdf: gpd.GeoDataFrame, refs: BarrierReferences) -> pd.DataFrame:
    """One row per grid cell: the :data:`NEAREST_COLUMNS`, against that
    cell's single nearest barrier (the same nearest-barrier join
    `assemble.py::match_grid_point` makes)."""
    cells_m = cells_gdf[["cell_id", "geometry"]].to_crs(METRIC_CRS).reset_index(drop=True)
    barriers_m = barriers_gdf.to_crs(METRIC_CRS).reset_index(drop=True)
    barrier_rows = nearest_segment(cells_m[["geometry"]], barriers_m)["index_right"].to_numpy()
    classified = classify_points(cells_m.geometry.to_numpy(), barrier_rows, refs)
    return pd.concat([cells_m[["cell_id"]], classified[NEAREST_COLUMNS]], axis=1)


def match_grid_protection(
    cells_gdf: gpd.GeoDataFrame, barriers_gdf: gpd.GeoDataFrame, refs: BarrierReferences
) -> pd.DataFrame:
    """One row per grid cell: the :data:`PROTECTION_COLUMNS`, over every
    barrier within `CANDIDATE_RADIUS_M` of the cell's centroid.

    - `protected` if any barrier protects the cell.
    - `protected_unknown` if none does, but one would if its side were
      known.
    - `n_protecting_barriers` counts the barriers that protect it.
    - The `protected_*` columns describe the protecting barrier nearest the
      cell (by `lateral_m`).
    - `treat_year_protected` is the earliest `built_year` among all
      protecting barriers, and `protected_undated` is True when any of them
      has none. This mirrors the schools rollup's `first_treat_year` /
      `timing_unknown`."""
    cells_m = cells_gdf[["cell_id", "geometry"]].to_crs(METRIC_CRS).reset_index(drop=True)
    points = cells_m.geometry.to_numpy()
    barriers_m = barriers_gdf.to_crs(METRIC_CRS).reset_index(drop=True)
    cell_idx, barrier_rows = barriers_m.sindex.query(points, predicate="dwithin", distance=CANDIDATE_RADIUS_M)
    classified = classify_points(points[cell_idx], barrier_rows, refs)

    built_year = pd.to_numeric(barriers_gdf["built_year"], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    pairs = pd.DataFrame(
        {
            "cell": cell_idx,
            "barrier_row": barrier_rows,
            "protected": classified["protected"].to_numpy(),
            "protected_unknown": classified["protected_unknown"].to_numpy(),
            "side_method": classified["side_method"].to_numpy(),
            "lateral_m": classified["lateral_m"].to_numpy(),
            "built_year": built_year[barrier_rows],
        }
    )
    protecting = pairs[pairs["protected"]]
    nearest = protecting.sort_values("lateral_m").drop_duplicates("cell").set_index("cell")
    by_cell = protecting.groupby("cell")

    out = cells_m[["cell_id"]].copy()
    cells = np.arange(len(out))
    out["protected"] = np.isin(cells, protecting["cell"].to_numpy())
    out["protected_unknown"] = np.isin(cells, pairs.loc[pairs["protected_unknown"], "cell"].to_numpy()) & ~out["protected"]
    out["n_protecting_barriers"] = by_cell.size().reindex(cells, fill_value=0).to_numpy()
    out["protected_barrier_row"] = nearest["barrier_row"].reindex(cells).astype("Int64").to_numpy()
    out["protected_side_method"] = nearest["side_method"].reindex(cells).to_numpy()
    out["protected_lateral_m"] = nearest["lateral_m"].reindex(cells).to_numpy()
    out["treat_year_protected"] = by_cell["built_year"].min().reindex(cells).astype("Int64").to_numpy()
    undated = protecting.loc[protecting["built_year"].isna(), "cell"].to_numpy()
    out["protected_undated"] = np.isin(cells, undated)
    return out


def match_grid_side_for_kind(
    cells_gdf: gpd.GeoDataFrame, barriers_gdf: gpd.GeoDataFrame, kind: str, *, root: Path | None = None
) -> pd.DataFrame:
    """Both judgements for one barrier kind, merged on `cell_id`."""
    refs = load_barrier_references(kind, root, barriers_gdf=barriers_gdf)
    nearest = match_grid_side(cells_gdf, barriers_gdf, refs)
    protection = match_grid_protection(cells_gdf, barriers_gdf, refs)
    return nearest.merge(protection, on="cell_id", how="left")
