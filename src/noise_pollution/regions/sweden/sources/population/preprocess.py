"""GHS-POP tiles -> one national SWEREF99 TM 100 m GeoTIFF per epoch; SCB's yearly 1 km
geopackages -> one long table.

**Warping.** GDAL's `sum` resampling adds up the source pixels each target cell overlaps, by
overlap share, so residents are carried over rather than densities averaged (both grids are
100 m and Mollweide is equal-area, so per-cell totals are kept up to edge effects). Each tile
is warped on its own and the results added, so a target cell on a tile edge gets its share
from both tiles. The raster is aligned to whole km: its 10 x 10 blocks are SCB's 1 km cells.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from noise_pollution.regions.sweden.sources._layout import METRIC_CRS
from noise_pollution.regions.sweden.sources.population.shared import (
    DEFAULT_GHS_EPOCHS,
    KM_M,
    RESOLUTION_M,
    SCB_AGE_PREFIX,
    SCB_YEARS,
    SWEDEN_BOUNDS,
    ghs_raster_path,
    ghs_raw_dir,
    scb_processed_path,
    scb_raw_path,
)


def raster_grid(bounds=SWEDEN_BOUNDS, resolution_m: int = RESOLUTION_M):
    """`(transform, height, width)` of the national raster."""
    xmin, ymin, xmax, ymax = bounds
    if any(v % KM_M for v in bounds):
        raise ValueError(f"bounds {bounds} must be whole km")
    return from_origin(xmin, ymax, resolution_m, resolution_m), (ymax - ymin) // resolution_m, (xmax - xmin) // resolution_m


def warp_to_sweref(tile_paths, bounds=SWEDEN_BOUNDS, resolution_m: int = RESOLUTION_M, dst_crs=METRIC_CRS) -> np.ndarray:
    """Residents per target cell, summed over every tile. Slow: ~4.5 minutes per epoch for
    Sweden's four tiles, spent in the `sum` resampling (warping each tile only into the
    window it covers is no faster)."""
    transform, height, width = raster_grid(bounds, resolution_m)
    out = np.zeros((height, width), dtype=np.float32)
    part = np.empty_like(out)
    for path in tile_paths:
        part.fill(0)
        with rasterio.open(path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=part,
                src_nodata=src.nodata,
                dst_transform=transform,
                dst_crs=dst_crs,
                dst_nodata=0,
                init_dest_nodata=True,
                resampling=Resampling.sum,
            )
        out += np.where(part > 0, part, 0)
    return out


def write_raster(array: np.ndarray, path: Path, bounds=SWEDEN_BOUNDS, resolution_m: int = RESOLUTION_M, crs=METRIC_CRS) -> None:
    transform, height, width = raster_grid(bounds, resolution_m)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": height,
        "width": width,
        "crs": crs,
        "transform": transform,
        "nodata": None,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def read_scb_year(path: Path, year: int) -> pd.DataFrame:
    """One row per populated 1 km cell: `year`, `km_e` / `km_n` (lower-left corner, from
    `rutid_scb`), `pop` (`beftotalt`), `men`, `women` and the age groups as `age_<lo>_<hi>`."""
    raw = gpd.read_file(path, ignore_geometry=True)
    code = raw["rutid_scb"].astype("int64").astype(str)
    out = pd.DataFrame({"year": np.int16(year), "km_e": code.str[:6].astype("int32"), "km_n": code.str[6:].astype("int32")})
    out["pop"] = raw["beftotalt"].astype("int32")
    out["men"] = raw["man"].astype("int32")
    out["women"] = raw["kvinna"].astype("int32")
    for col in [c for c in raw.columns if c.startswith(SCB_AGE_PREFIX)]:
        span = col[len(SCB_AGE_PREFIX):]
        name = "age_" + (span.replace("w", "") + "_plus" if span.endswith("w") else span)
        out[name] = raw[col].astype("int32")
    return out


def run_population_preprocess(epochs=DEFAULT_GHS_EPOCHS, years=SCB_YEARS, *, root: Path | None = None) -> dict:
    totals = {}
    for epoch in epochs:
        tiles = sorted(ghs_raw_dir(epoch, root).glob("*.tif"))
        if not tiles:
            raise FileNotFoundError(f"no GHS-POP tiles for {epoch} -- run `sweden data population fetch` first.")
        array = warp_to_sweref(tiles)
        write_raster(array, ghs_raster_path(epoch, root))
        totals[epoch] = round(float(array.sum()))
    frames = []
    for year in years:
        path = scb_raw_path(year, root)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing -- run `sweden data population fetch` first.")
        frames.append(read_scb_year(path, year))
    scb = pd.concat(frames, ignore_index=True)
    scb.to_parquet(scb_processed_path(root), index=False)
    return {
        "ghs_total_in_bounds": totals,
        "scb_total": {int(y): int(v) for y, v in scb.groupby("year")["pop"].sum().items()},
        "scb_rows": len(scb),
    }
