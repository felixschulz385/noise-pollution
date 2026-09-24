"""Stage: build the 100m x 100m analysis grid ("statistikrutor") that
`assemble.py` matches to noise barriers.

REQUIRES `noise_barriers preprocess` (`road_noise_barriers.parquet` /
`rail_noise_barriers.parquet`).

A nationwide 100m tiling of Sweden would be ~45M cells -- pointless, since
every cell further than `BUFFER_M` from every barrier is guaranteed
`ever_near_*m = False` under every configured band. Instead: buffer every
barrier geometry (road + rail together) by `BUFFER_M`, take the union, and
tile only that corridor. Confirmed live 2026-09-22 against the real
barrier layers: the buffered union has 694 disjoint connected components
(not one country-spanning blob -- barriers cluster near settlements), total
area ~4,000 km^2 (~400k cells), largest single component ~185 km^2. Tiling
is done **per component**, each within its own small bounding box, rather
than one tile pass over the corridor's overall bounding box (~623km x
1392km for road alone) -- the latter would require materializing tens of
millions of candidate cells before filtering, the former only ~640k
(confirmed: summed per-component bbox tiling is ~1.6x the true corridor
cell count, cheap).
"""
from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

from src.regions.sweden.sources.grid.shared import (
    BUFFER_M,
    METRIC_CRS,
    RESOLUTION_M,
    cell_id,
    processed_grid_cells_path,
)
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers


def _tile_component(component, resolution_m: int) -> pd.DataFrame | None:
    minx, miny, maxx, maxy = component.bounds
    x0 = math.floor(minx / resolution_m) * resolution_m
    y0 = math.floor(miny / resolution_m) * resolution_m
    x1 = math.ceil(maxx / resolution_m) * resolution_m
    y1 = math.ceil(maxy / resolution_m) * resolution_m

    eastings = np.arange(x0, x1, resolution_m, dtype=np.int64)
    northings = np.arange(y0, y1, resolution_m, dtype=np.int64)
    xx, yy = np.meshgrid(eastings, northings)
    sw_easting = xx.ravel()
    sw_northing = yy.ravel()

    centroids = gpd.points_from_xy(sw_easting + resolution_m / 2, sw_northing + resolution_m / 2)
    within = gpd.GeoSeries(centroids).within(component).to_numpy()
    if not within.any():
        return None
    return pd.DataFrame({"easting": sw_easting[within], "northing": sw_northing[within]})


def build_grid_cells(
    barriers_by_kind: dict[str, gpd.GeoDataFrame],
    *,
    buffer_m: float = BUFFER_M,
    resolution_m: int = RESOLUTION_M,
    metric_crs: str = METRIC_CRS,
) -> gpd.GeoDataFrame:
    """One row per 100m cell whose centroid falls within `buffer_m` of any
    barrier of any kind. Columns: `cell_id`, `easting`/`northing` (the
    cell's SW corner in `metric_crs`), `geometry` (the cell centroid --
    matching, not mapping, is this module's job; the polygon is always
    reconstructible from `easting`/`northing`/`resolution_m`)."""
    all_geoms = [
        geom
        for barriers_gdf in barriers_by_kind.values()
        for geom in barriers_gdf.to_crs(metric_crs).geometry
    ]
    corridor = unary_union([geom.buffer(buffer_m) for geom in all_geoms])
    components = list(corridor.geoms) if corridor.geom_type == "MultiPolygon" else [corridor]

    tiles = [_tile_component(component, resolution_m) for component in components]
    cells = pd.concat([t for t in tiles if t is not None], ignore_index=True)
    cells = cells.drop_duplicates(subset=["easting", "northing"]).reset_index(drop=True)
    cells["cell_id"] = [cell_id(e, n, resolution_m) for e, n in zip(cells["easting"], cells["northing"])]

    geometry = gpd.points_from_xy(cells["easting"] + resolution_m / 2, cells["northing"] + resolution_m / 2)
    return gpd.GeoDataFrame(
        cells[["cell_id", "easting", "northing"]], geometry=geometry, crs=metric_crs
    )


def run_grid_preprocess(
    *,
    kinds: tuple[str, ...] = BARRIER_KINDS,
    buffer_m: float = BUFFER_M,
    resolution_m: int = RESOLUTION_M,
    root: Path | None = None,
) -> dict:
    barriers_by_kind = {kind: load_noise_barriers(kind, root) for kind in kinds}
    cells_gdf = build_grid_cells(barriers_by_kind, buffer_m=buffer_m, resolution_m=resolution_m)

    out_path = processed_grid_cells_path(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cells_gdf.to_parquet(out_path, index=False)

    return {
        "n_cells": int(len(cells_gdf)),
        "resolution_m": resolution_m,
        "buffer_m": buffer_m,
        "kinds": list(kinds),
        "saved": str(out_path),
    }
