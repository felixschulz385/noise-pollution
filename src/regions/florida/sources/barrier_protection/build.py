"""`florida data barrier-protection build`: every FDOT noise wall's
reference (`reference.build_barrier_references`), saved with the statewide
protected-area layer (`core.barrier_geometry.protection.protection_zones`).
See `shared.py`."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from src.core.barrier_geometry.linear_ref import DEFAULT_CORRIDOR_BUDGET_M, DEFAULT_CORRIDOR_BUFFER_M
from src.core.barrier_geometry.protection import protection_zones
from src.regions.florida.sources.barrier_protection.reference import build_barrier_references
from src.regions.florida.sources.barrier_protection.shared import references_frame, references_path, zones_path
from src.regions.florida.sources.noise_barriers.shared import load_barriers
from src.regions.florida.sources.road_network.shared import load_road_network

ZONE_COLUMNS = ["gcid", "category", "side_method", "zone_status", "built_year", "is_programmed", "geometry"]


def run_barrier_protection_build(
    *,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
    root: Path | None = None,
) -> dict:
    t0 = time.time()
    barriers = load_barriers(root).reset_index(drop=True)
    refs = build_barrier_references(barriers, load_road_network(root), budget_m=budget_m, buffer_m=buffer_m)
    path = references_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    references_frame(refs).to_parquet(path, index=False)

    zones = protection_zones(refs)
    attributes = barriers[[c for c in ("gcid", "category", "built_year", "is_programmed") if c in barriers.columns]]
    zones = zones.join(attributes, on="barrier_row")
    zones = zones[[c for c in ZONE_COLUMNS if c in zones.columns]]
    zones.to_parquet(zones_path(root), index=False)

    table = refs.table
    return {
        "n_walls": int(len(barriers)),
        "side_method": {k: int(v) for k, v in table["side_method"].value_counts().items()},
        "side_check": {str(k): int(v) for k, v in table["side_check"].value_counts(dropna=False).items()},
        "reference_parallel_share": round(float(table["reference_parallel"].mean()), 4),
        "offset_m_median": round(float(table["offset_m"].median()), 1),
        "n_zones": int(len(zones)),
        "zone_area_km2": {
            status: round(float(area) / 1e6, 1)
            for status, area in zones.dissolve(by="zone_status").geometry.area.items()
        },
        "budget_m": budget_m,
        "buffer_m": buffer_m,
        "seconds": round(time.time() - t0),
        "saved": {"references": str(path), "zones": str(zones_path(root))},
    }
