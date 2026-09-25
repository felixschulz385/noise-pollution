"""Paths and loaders for the Florida `barrier_protection` stage: every FDOT
noise wall's reference (reference road, side, stretch, `same_route`
corridor) and the statewide layer of protected areas built from them.
Computed once by `build.py`; `schools assemble` and any later analysis load
them. See `docs/data/florida/barrier_protection.md`.

A reference file is keyed by `gcid` and stored in the row order of
`noise_barriers.shared.load_barriers`; `load_barrier_references` refuses a
file whose `gcid`s no longer line up with the walls passed in.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.barrier_geometry.protection import BarrierReferences
from src.regions.florida.sources._layout import METRIC_CRS, domain_dirs

TABLE_COLUMNS = [
    "gcid", "primary_row", "roadway_id", "reference_parallel", "side_method", "barrier_sign", "side_check",
    "offset_m", "span_start_m", "span_end_m",
]


def barrier_protection_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("barrier_protection", root)


def references_path(root: Path | None = None) -> Path:
    return barrier_protection_paths(root)["processed"] / "barrier_references.parquet"


def zones_path(root: Path | None = None) -> Path:
    return barrier_protection_paths(root)["processed"] / "protection_zones.parquet"


def references_frame(refs: BarrierReferences) -> gpd.GeoDataFrame:
    """`refs` as one row per wall: the reference table, the through-line
    (`geometry`) and the corridor lines (`corridor`)."""
    n = len(refs.table)
    return gpd.GeoDataFrame(
        {
            **{col: refs.table[col].to_numpy() for col in TABLE_COLUMNS},
            "corridor": gpd.GeoSeries([refs.corridors[i] for i in range(n)], crs=refs.crs),
            "buffer_m": refs.buffer_m,
        },
        geometry=gpd.GeoSeries([refs.lines[i] for i in range(n)], crs=refs.crs),
    )


def load_barrier_references(root: Path | None = None, barriers_gdf: gpd.GeoDataFrame | None = None) -> BarrierReferences:
    path = references_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `florida data barrier-protection build` first.")
    frame = gpd.read_parquet(path).reset_index(drop=True)
    if barriers_gdf is not None and not np.array_equal(
        barriers_gdf["gcid"].to_numpy(), frame["gcid"].to_numpy()
    ):
        raise ValueError(f"{path} no longer lines up with the barrier layer -- re-run `florida data barrier-protection build`.")
    table = pd.DataFrame(frame[TABLE_COLUMNS])
    return BarrierReferences(
        table=table,
        corridors=dict(enumerate(frame["corridor"])),
        lines=dict(enumerate(frame.geometry)),
        buffer_m=float(frame["buffer_m"].iat[0]) if len(frame) else 0.0,
        crs=METRIC_CRS,
    )


def load_protection_zones(root: Path | None = None) -> gpd.GeoDataFrame:
    """The statewide protection layer: one polygon per wall (EPSG:3087) with
    `gcid`, `category`, `side_method`, `zone_status` ("protected" /
    "side_unknown"), `built_year` and `is_programmed`. Spatially join any
    unit to it; `other_wall` rows are private/perimeter walls, a shielding
    covariate, never treatment."""
    path = zones_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `florida data barrier-protection build` first.")
    return gpd.read_parquet(path)
