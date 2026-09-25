"""Paths and loaders for the Sweden `barrier_protection` stage: every noise
barrier's reference (the road stretch it covers, its side, its `same_route`
corridor) and the national layer of protected areas built from them.

The references are computed once per barrier kind by `build.py` and saved,
so `schools`, `grid` and any later analysis load them rather than each
re-deriving them from the 2M-row road network. See
`docs/data/sweden/barrier_matching.md` for the method.

A reference file is keyed by `barrier_row`, the barrier's row position in
`load_noise_barriers(kind)`. `load_barrier_references` checks that the
barriers passed in still line up with it and refuses a stale file.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.barrier_geometry.protection import BarrierReferences
from src.regions.sweden.sources._layout import METRIC_CRS, domain_dirs
from src.regions.sweden.sources.network.shared import load_network_tracks
from src.regions.sweden.sources.road_network.shared import load_road_network

NETWORK_LOADERS = {"road": load_road_network, "rail": load_network_tracks}
ROUTE_COLUMNS = {"rail": "bandel", "road": None}
KEY_COLUMNS = ["element_id", "start_measure", "end_measure"]
TABLE_COLUMNS = ["primary_row", "side_method", "barrier_sign", "osm_id", "span_start_m", "span_end_m"]


def barrier_protection_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("barrier_protection", root)


def references_path(kind: str, root: Path | None = None) -> Path:
    return barrier_protection_paths(root)["processed"] / f"barrier_references_{kind}.parquet"


def zones_path(root: Path | None = None) -> Path:
    return barrier_protection_paths(root)["processed"] / "protection_zones.parquet"


def references_frame(refs: BarrierReferences, barriers_gdf: gpd.GeoDataFrame, crs) -> gpd.GeoDataFrame:
    """`refs` as one GeoDataFrame row per barrier: its key columns, the
    reference table, the through-line (`geometry`) and the corridor lines
    (`corridor`)."""
    n = len(refs.table)
    frame = gpd.GeoDataFrame(
        {
            "barrier_row": np.arange(n),
            **{col: barriers_gdf[col].to_numpy() for col in KEY_COLUMNS},
            **{col: refs.table[col].to_numpy() for col in refs.table.columns},
            "corridor": gpd.GeoSeries([refs.corridors[i] for i in range(n)], crs=crs),
            "buffer_m": refs.buffer_m,
        },
        geometry=gpd.GeoSeries([refs.lines[i] for i in range(n)], crs=crs),
    )
    return frame


def load_barrier_references(
    kind: str, root: Path | None = None, barriers_gdf: gpd.GeoDataFrame | None = None
) -> BarrierReferences:
    path = references_path(kind, root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data barrier-protection build` first.")
    frame = gpd.read_parquet(path).sort_values("barrier_row").reset_index(drop=True)
    if barriers_gdf is not None:
        current = barriers_gdf[KEY_COLUMNS].reset_index(drop=True)
        if len(current) != len(frame) or not current.equals(frame[KEY_COLUMNS]):
            raise ValueError(
                f"{path} no longer lines up with the {kind} barriers -- re-run `sweden data barrier-protection build`."
            )
    columns = [c for c in (*TABLE_COLUMNS, "route") if c in frame.columns]
    table = pd.DataFrame(frame[columns])
    table["osm_id"] = table["osm_id"].astype("Int64")
    return BarrierReferences(
        table=table,
        corridors=dict(enumerate(frame["corridor"])),
        lines=dict(enumerate(frame.geometry)),
        buffer_m=float(frame["buffer_m"].iat[0]) if len(frame) else 0.0,
        crs=METRIC_CRS,
    )


def load_protection_zones(root: Path | None = None, kind: str | None = None) -> gpd.GeoDataFrame:
    """The national protected-area layer: one polygon per barrier (both
    kinds, `kind` column), with `barrier_row`, the barrier's key columns,
    `side_method`, `zone_status` ("protected" / "side_unknown") and
    `built_year`. Spatially join any unit (address, area, grid cell) to it."""
    path = zones_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data barrier-protection build` first.")
    zones = gpd.read_parquet(path)
    return zones if kind is None else zones[zones["kind"] == kind].reset_index(drop=True)
