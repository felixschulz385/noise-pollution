"""`sweden data barrier-protection build`: computes every barrier's
reference once per kind (`_barrier_reference.build_barrier_references`)
and saves it with the national protected-area layer
(`core.barrier_geometry.protection.protection_zones`) and the control-band
layer beyond it (`control_band_zones`). Manual answers from the
`barrier_audit` source are used when `barrier-audit preprocess` has run;
every audited barrier also carries the audit's decision (`audit_decision`),
so a barrier the reviewer could not see is `not_visible` there while its
side stays the automatic one. See `shared.py`."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from src.core.barrier_geometry.linear_ref import DEFAULT_CORRIDOR_BUDGET_M, DEFAULT_CORRIDOR_BUFFER_M
from src.core.barrier_geometry.protection import CONTROL_MAX_LATERAL_M, control_band_zones, protection_zones
from src.regions.sweden.sources._barrier_reference import build_barrier_references, register_chains
from src.regions.sweden.sources._layout import METRIC_CRS
from src.regions.sweden.sources.barrier_audit.shared import load_audit_decisions, load_manual_sides
from src.regions.sweden.sources.barrier_protection.shared import (
    KEY_COLUMNS,
    NETWORK_LOADERS,
    ROUTE_COLUMNS,
    control_band_zones_path,
    references_frame,
    references_path,
    zones_path,
)
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers
from src.regions.sweden.sources.osm_walls.shared import load_osm_walls

ZONE_COLUMNS = ["kind", "barrier_row", *KEY_COLUMNS, "side_method", "zone_status", "built_year", "osm_id", "geometry"]


def _zone_layer(zones, barriers_gdf, refs, kind):
    keyed = barriers_gdf[[*KEY_COLUMNS, "built_year"]].reset_index(names="barrier_row")
    zones = zones.merge(keyed, on="barrier_row", how="left").assign(kind=kind)
    return zones.join(refs.table["osm_id"], on="barrier_row")


def _audit_decision(frame, decisions) -> pd.Series:
    """Per reference row, the audit's decision on that barrier (shared by
    co-located records with the same key); NA where it was never audited."""
    if decisions is None:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    joined = frame[KEY_COLUMNS].merge(decisions, on=KEY_COLUMNS, how="left", validate="many_to_one")
    return pd.Series(joined["decision"].to_numpy(), index=frame.index, dtype="string")


def _area_km2(zones) -> dict:
    return {
        status: round(float(area) / 1e6, 1) for status, area in zones.dissolve(by="zone_status").geometry.area.items()
    }


def _save(layers, path):
    out = pd.concat(layers, ignore_index=True)[ZONE_COLUMNS].set_crs(METRIC_CRS, allow_override=True)
    out.to_parquet(path, index=False)


def run_barrier_protection_build(
    *,
    kinds: tuple[str, ...] = BARRIER_KINDS,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
    control_max_lateral_m: float = CONTROL_MAX_LATERAL_M,
    root: Path | None = None,
) -> dict:
    osm_walls = load_osm_walls(root)
    zones_by_kind, bands_by_kind, report = [], [], {}
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
        # Pieces of one physical wall that the register splits (see `register_chains`).
        chains = register_chains(barriers_gdf.to_crs(METRIC_CRS))
        frame[["chain_id", "chain_orient"]] = chains[["chain_id", "chain_orient"]].to_numpy()
        frame["audit_decision"] = _audit_decision(frame, load_audit_decisions(kind, root))
        frame.to_parquet(path, index=False)

        zones = _zone_layer(protection_zones(refs), barriers_gdf, refs, kind)
        zones_by_kind.append(zones)
        band = control_band_zones(refs, control_max_lateral_m=control_max_lateral_m)
        band = _zone_layer(band, barriers_gdf, refs, kind)
        bands_by_kind.append(band)
        report[kind] = {
            "n_barriers": int(len(barriers_gdf)),
            "n_manual_answers": 0 if manual is None else int(len(manual)),
            "side_method": {k: int(v) for k, v in refs.table["side_method"].value_counts().items()},
            "audit_decision": {k: int(v) for k, v in frame["audit_decision"].value_counts().items()},
            "n_zones": int(len(zones)),
            "n_records_in_chains": int((chains["chain_size"] > 1).sum()),
            "zone_area_km2": _area_km2(zones),
            "n_control_band_zones": int(len(band)),
            "control_band_area_km2": _area_km2(band),
            "seconds": round(time.time() - t0),
            "saved_references": str(path),
        }

    _save(zones_by_kind, zones_path(root))
    _save(bands_by_kind, control_band_zones_path(root))
    return {
        "kinds": report,
        "saved_zones": str(zones_path(root)),
        "saved_control_band_zones": str(control_band_zones_path(root)),
        "budget_m": budget_m,
        "buffer_m": buffer_m,
        "control_max_lateral_m": control_max_lateral_m,
    }
