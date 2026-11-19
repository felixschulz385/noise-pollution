"""Constants and paths of the `population` source.

Two open products, combined in `assemble`:

- **GHS-POP R2023A** (JRC Global Human Settlement Layer): residents per 100 m cell in Mollweide
  (ESRI:54009), epochs 1975-2030 every 5 years. Modelled: for Sweden, SCB's 2010 parish
  (församling) register counts spread over built-up volume, carried to other epochs with
  kommun growth rates and the built-up area of each epoch.
- **SCB "Statistik på rutor"**: register counts per 1 km cell with 5-year age groups, annual
  2015-2025, SWEREF99 TM. Real counts, coarse cells.

Docs: `docs/data/sweden/population/README.md`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from pyproj import Transformer

from noise_pollution.regions.sweden.sources._layout import METRIC_CRS, domain_dirs

GHS_CRS = "ESRI:54009"
GHS_EPOCHS = tuple(range(1975, 2031, 5))
# 2030 is a projection; not fetched unless asked for.
DEFAULT_GHS_EPOCHS = tuple(e for e in GHS_EPOCHS if e <= 2025)
GHS_TILE_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
    "GHS_POP_E{epoch}_GLOBE_R2023A_54009_100/V1-0/tiles/GHS_POP_E{epoch}_GLOBE_R2023A_54009_100_V1_0_{tile}.zip"
)
# The GHSL tiling of the Mollweide grid: 1,000 km tiles counted from the top-left corner, R1_C1.
GHS_TILE_ORIGIN = (-18_041_000.0, 9_000_000.0)
GHS_TILE_SIZE_M = 1_000_000.0

SCB_YEARS = tuple(range(2015, 2026))
SCB_WFS_URL = "https://geodata.scb.se/geoserver/stat/wfs"
SCB_LAYER = "stat:befolkning_1km_{year}"
# SCB's age columns (ald0_4 ... ald100w) are renamed age_0_4 ... age_100_plus.
SCB_AGE_PREFIX = "ald"

RESOLUTION_M = 100
KM_M = 1000
# The national raster in SWEREF99 TM, aligned to whole km so 10 x 10 blocks are SCB's 1 km
# cells. SCB's 1 km grid spans E 269-917 km, N 6,133-7,653 km.
SWEDEN_BOUNDS = (260_000, 6_120_000, 930_000, 7_670_000)


def population_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("population", root)


def ghs_raw_dir(epoch: int, root: Path | None = None) -> Path:
    return population_paths(root)["raw"] / "ghs_pop" / f"E{epoch}"


def scb_raw_path(year: int, root: Path | None = None) -> Path:
    return population_paths(root)["raw"] / "scb_1km" / f"befolkning_1km_{year}.gpkg"


def ghs_raster_path(epoch: int, root: Path | None = None) -> Path:
    return population_paths(root)["processed"] / f"ghs_pop_e{epoch}_sweref99tm_100m.tif"


def scb_processed_path(root: Path | None = None) -> Path:
    return population_paths(root)["processed"] / "scb_1km.parquet"


def grid_population_ghs_path(root: Path | None = None) -> Path:
    return population_paths(root)["assembled"] / "grid_population_ghs.parquet"


def grid_population_scb_path(root: Path | None = None) -> Path:
    return population_paths(root)["assembled"] / "grid_population_scb.parquet"


def grid_cells_path(root: Path | None = None) -> Path:
    """The `grid` source's 100 m cells (read by path)."""
    return domain_dirs("grid", root)["processed"] / "grid_cells.parquet"


def ghs_tiles(bounds=SWEDEN_BOUNDS, crs=METRIC_CRS, step_m: float = 10_000.0) -> list[str]:
    """The GHSL tile names (``R{row}_C{col}``) that `bounds` (in `crs`) touches, from a lattice
    of points `step_m` apart over it. Mollweide bends the box, so its outline alone would miss
    no tile but its bounding rectangle of tiles could add empty ones."""
    xmin, ymin, xmax, ymax = bounds
    xs, ys = np.meshgrid(np.append(np.arange(xmin, xmax, step_m), xmax), np.append(np.arange(ymin, ymax, step_m), ymax))
    mx, my = Transformer.from_crs(crs, GHS_CRS, always_xy=True).transform(xs.ravel(), ys.ravel())
    x0, y0 = GHS_TILE_ORIGIN
    cols = np.floor((np.asarray(mx) - x0) / GHS_TILE_SIZE_M).astype(int) + 1
    rows = np.floor((y0 - np.asarray(my)) / GHS_TILE_SIZE_M).astype(int) + 1
    return [f"R{r}_C{c}" for r, c in sorted(set(zip(rows.tolist(), cols.tolist())))]


def nearest_epoch(year: int, epochs=GHS_EPOCHS) -> int:
    """The epoch closest to `year` (the earlier one on a tie)."""
    epochs = sorted(epochs)
    return min(epochs, key=lambda e: (abs(e - year), e))
