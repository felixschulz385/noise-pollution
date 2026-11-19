"""Population of every cell of the `grid` source's 100 m grid.

- `grid_population_ghs.parquet`: one row per cell, `pop_<epoch>` = GHS-POP residents for each
  preprocessed epoch (modelled, see `shared.py`).
- `grid_population_scb.parquet`: one row per cell and SCB year with residents, `pop`, `men`,
  `women` and the `age_*` groups = the 1 km cell's register counts times the cell's share of
  the 1 km cell's GHS-POP residents in the nearest epoch. Totals and age structure are SCB's;
  GHS-POP only places people within the km. Where GHS-POP has nobody in a populated SCB km
  cell, the km's count is spread evenly over its 100 cells. Ages within a km are spread like
  the total (the km's age structure is assumed uniform over it).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from noise_pollution.regions.sweden.sources.population.shared import (
    GHS_EPOCHS,
    KM_M,
    RESOLUTION_M,
    SWEDEN_BOUNDS,
    ghs_raster_path,
    grid_cells_path,
    grid_population_ghs_path,
    grid_population_scb_path,
    nearest_epoch,
    scb_processed_path,
)

CELLS_PER_KM = (KM_M // RESOLUTION_M) ** 2


def cell_index(easting, northing, bounds=SWEDEN_BOUNDS, resolution_m: int = RESOLUTION_M):
    """Raster `(row, col)` of the cells whose lower-left corners are `easting` / `northing`."""
    xmin, _, _, ymax = bounds
    e = np.asarray(easting, dtype=np.int64)
    n = np.asarray(northing, dtype=np.int64)
    return (ymax - n) // resolution_m - 1, (e - xmin) // resolution_m


def km_sums(array: np.ndarray, resolution_m: int = RESOLUTION_M) -> np.ndarray:
    """The raster summed over whole-km blocks."""
    k = KM_M // resolution_m
    h, w = array.shape
    return array.reshape(h // k, k, w // k, k).sum(axis=(1, 3), dtype=np.float64)


def km_shares(array: np.ndarray, rows, cols, resolution_m: int = RESOLUTION_M) -> np.ndarray:
    """Each cell's share of its km's residents; 1/100 where the km has none."""
    k = KM_M // resolution_m
    km = km_sums(array, resolution_m)[rows // k, cols // k]
    cell = array[rows, cols].astype(np.float64)
    return np.where(km > 0, cell / np.where(km > 0, km, 1.0), 1.0 / CELLS_PER_KM)


def distribute_scb(cells: pd.DataFrame, scb_year: pd.DataFrame, share: np.ndarray) -> pd.DataFrame:
    """SCB's km counts of one year spread over `cells` (`cell_id`, `easting`, `northing`) by
    `share`; only cells with residents."""
    value_cols = [c for c in scb_year.columns if c not in ("year", "km_e", "km_n")]
    keys = pd.DataFrame(
        {"km_e": (cells["easting"].to_numpy() // KM_M) * KM_M, "km_n": (cells["northing"].to_numpy() // KM_M) * KM_M}
    )
    km = keys.merge(scb_year, on=["km_e", "km_n"], how="left")[value_cols].fillna(0).to_numpy(dtype=np.float64)
    values = km * share[:, None]
    out = pd.DataFrame(values.astype(np.float32), columns=value_cols)
    out.insert(0, "cell_id", cells["cell_id"].to_numpy())
    return out[out["pop"] > 0]


def _available_epochs(root: Path | None) -> list[int]:
    return [e for e in GHS_EPOCHS if ghs_raster_path(e, root).exists()]


def _read(epoch: int, root: Path | None) -> np.ndarray:
    with rasterio.open(ghs_raster_path(epoch, root)) as src:
        return src.read(1)


def run_population_assemble(*, root: Path | None = None) -> dict:
    cells_path = grid_cells_path(root)
    if not cells_path.exists():
        raise FileNotFoundError(f"{cells_path} missing -- run `sweden data grid preprocess` first.")
    cells = pd.read_parquet(cells_path, columns=["cell_id", "easting", "northing"])
    rows, cols = cell_index(cells["easting"], cells["northing"])
    epochs = _available_epochs(root)
    if not epochs:
        raise FileNotFoundError("no GHS-POP rasters -- run `sweden data population preprocess` first.")
    scb = pd.read_parquet(scb_processed_path(root))
    by_epoch = {}
    for year in sorted(scb["year"].unique()):
        by_epoch.setdefault(nearest_epoch(int(year), epochs), []).append(int(year))

    ghs = cells[["cell_id"]].copy()
    distributed = []
    for epoch in epochs:
        array = _read(epoch, root)
        ghs[f"pop_{epoch}"] = array[rows, cols]
        if epoch in by_epoch:
            share = km_shares(array, rows, cols)
            for year in by_epoch[epoch]:
                part = distribute_scb(cells, scb[scb["year"] == year], share)
                part.insert(1, "year", np.int16(year))
                distributed.append(part)
        del array
    scb_cells = pd.concat(distributed, ignore_index=True)

    grid_population_ghs_path(root).parent.mkdir(parents=True, exist_ok=True)
    ghs.to_parquet(grid_population_ghs_path(root), index=False)
    scb_cells.to_parquet(grid_population_scb_path(root), index=False)
    return {
        "cells": len(cells),
        "ghs_epochs": epochs,
        "ghs_pop_in_grid": {e: round(float(ghs[f"pop_{e}"].sum())) for e in epochs},
        "scb_years": sorted(int(y) for y in scb_cells["year"].unique()),
        "scb_pop_in_grid": {int(y): round(float(v)) for y, v in scb_cells.groupby("year")["pop"].sum().items()},
        "scb_epoch_used": {y: e for e, ys in by_epoch.items() for y in ys},
    }
