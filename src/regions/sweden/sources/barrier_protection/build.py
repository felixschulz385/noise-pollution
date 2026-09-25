"""`sweden data barrier-protection build`: computes every barrier's
reference once per kind (`_barrier_reference.build_barrier_references`)
and saves it with the national protected-area layer
(`_barrier_reference.protection_zones`). Manual answers from the
`barrier_audit` source are used when `barrier-audit preprocess` has run.
See `shared.py`."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from shapely import force_2d

from src.core.barrier_geometry.linear_ref import DEFAULT_CORRIDOR_BUDGET_M, DEFAULT_CORRIDOR_BUFFER_M, chain_lines
from src.core.barrier_geometry.protection import protection_zones
from src.regions.sweden.sources._barrier_reference import build_barrier_references
from src.regions.sweden.sources._layout import METRIC_CRS
from src.regions.sweden.sources.barrier_audit.shared import load_manual_sides
from src.regions.sweden.sources.barrier_protection.shared import (
    KEY_COLUMNS,
    NETWORK_LOADERS,
    ROUTE_COLUMNS,
    references_frame,
    references_path,
    zones_path,
)
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers
from src.regions.sweden.sources.osm_walls.shared import load_osm_walls


def run_barrier_protection_build(
    *,
    kinds: tuple[str, ...] = BARRIER_KINDS,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
    root: Path | None = None,
) -> dict:
    osm_walls = load_osm_walls(root)
    zones_by_kind, report = [], {}
    for kind in kinds:
        t0 = time.time()
        barriers_gdf = load_noise_barriers(kind, root).reset_index(drop=True)
        manual = load_manual_sides(kind, root)
        refs = build_barrier_references(
            barriers_gdf,
            NETWORK_LOADERS[kind](root),
            kind=kind,
            osm_walls=osm_walls,
            route_column=ROUTE_COLUMNS[kind],
            budget_m=budget_m,
            buffer_m=buffer_m,
            manual=manual,
        )
        path = references_path(kind, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = references_frame(refs, barriers_gdf, METRIC_CRS)
        # Pieces of one physical wall that the register splits (see `chain_lines`).
        pieces = [g if g.geom_type == "LineString" else max(g.geoms, key=lambda part: part.length)
                  for g in force_2d(barriers_gdf.to_crs(METRIC_CRS).geometry.to_numpy())]  # as barrier-audit export does
        chains = chain_lines(pieces)
        frame[["chain_id", "chain_orient"]] = chains[["chain_id", "chain_orient"]].to_numpy()
        frame.to_parquet(path, index=False)

        zones = protection_zones(refs)
        keyed = barriers_gdf[[*KEY_COLUMNS, "built_year"]].reset_index(names="barrier_row")
        zones = zones.merge(keyed, on="barrier_row", how="left").assign(kind=kind)
        zones = zones.join(refs.table["osm_id"], on="barrier_row")
        zones_by_kind.append(zones)
        report[kind] = {
            "n_barriers": int(len(barriers_gdf)),
            "n_manual_answers": 0 if manual is None else int(len(manual)),
            "side_method": {k: int(v) for k, v in refs.table["side_method"].value_counts().items()},
            "n_zones": int(len(zones)),
            "n_records_in_chains": int((chains["chain_size"] > 1).sum()),
            "zone_area_km2": {
                status: round(float(area) / 1e6, 1)
                for status, area in zones.dissolve(by="zone_status").geometry.area.items()
            },
            "seconds": round(time.time() - t0),
            "saved_references": str(path),
        }

    zones_all = pd.concat(zones_by_kind, ignore_index=True)
    columns = ["kind", "barrier_row", *KEY_COLUMNS, "side_method", "zone_status", "built_year", "osm_id", "geometry"]
    zones_all = zones_all[columns].set_crs(METRIC_CRS, allow_override=True)
    zones_all.to_parquet(zones_path(root), index=False)
    return {"kinds": report, "saved_zones": str(zones_path(root)), "budget_m": budget_m, "buffer_m": buffer_m}
