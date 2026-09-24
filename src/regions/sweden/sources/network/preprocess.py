from __future__ import annotations

import json
import re

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources.network.shared import (
    default_detailed_network_gpkg,
    default_network_gpkg,
    network_paths,
    processed_network_path,
)


def load_network(path=None) -> gpd.GeoDataFrame:
    network_path = path or default_network_gpkg()
    network = gpd.read_file(network_path)
    return network.to_crs(4326) if network.crs else network


def summarize_network(network: gpd.GeoDataFrame) -> pd.Series:
    return pd.Series(
        {
            "rows": len(network),
            "columns": len(network.columns),
            "crs": str(network.crs),
            "bounds": tuple(network.total_bounds) if len(network) else None,
        }
    )


def save_network_summary(summary: pd.Series, filename: str = "network_summary.json") -> str:
    paths = network_paths()
    output_path = paths["processed"] / filename
    output_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_path)


# The candidate network for `_barrier_reference.py`'s matching -- built
# from the fine-grained `grundegenskaper` file (194,047 rows: real per-row
# track geometry, `Bandel`/`KmFr`/`KmTi` linear reference), not the coarser
# `bandel_aggregat` file the summarize/plot commands above use. Kept
# separate so this doesn't change those commands' existing behavior.

_KM_PATTERN = re.compile(r"^(\d+)\+(\d+)$")


def parse_km(value: object) -> float | None:
    """Swedish railway "km+m" linear-position notation (e.g. `"66+280"` ->
    66280.0 metres) -> plain metres. Confirmed live 2026-09-15 against the
    real `grundegenskaper` file -- `KmFr`/`KmTi` are strings in this format,
    not plain numbers."""
    if value is None:
        return None
    match = _KM_PATTERN.match(str(value).strip())
    if not match:
        return None
    km, m = match.groups()
    return float(km) * 1000.0 + float(m)


def load_detailed_network(path=None) -> gpd.GeoDataFrame:
    network_path = path or default_detailed_network_gpkg()
    return gpd.read_file(network_path)


def preprocess_network_tracks(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clean the fine-grained rail network to the candidate network
    `_barrier_reference.py` matches against: **open** track only (`Status ==
    "Öppen"`, drops closed/decommissioned/planned track -- 188,357 of
    194,047 real rows checked live) with a real `Bandel` route id (drops
    ~500 null-`Bandel` rows plus non-route entries like "Ingår ej i
    bandelsindelning"/"Posten" that aren't part of the national route
    numbering and can't participate in a `same_route` test)."""
    tracks = raw[raw["Status"].eq("Öppen") & raw["Bandel"].notna()].copy()
    tracks["km_from_m"] = tracks["KmFr"].apply(parse_km)
    tracks["km_to_m"] = tracks["KmTi"].apply(parse_km)
    tracks = tracks.rename(
        columns={
            "ELEMENT_ID": "element_id",
            "Bandel": "bandel",
            "Bandelnamn": "bandel_namn",
            "START_MEASURE": "start_measure",
            "END_MEASURE": "end_measure",
            "SEGMENT_LENGTH": "segment_length_m",
            "VALID_FROM": "valid_from",
        }
    )
    columns = [
        "element_id",
        "bandel",
        "bandel_namn",
        "km_from_m",
        "km_to_m",
        "start_measure",
        "end_measure",
        "segment_length_m",
        "valid_from",
        "geometry",
    ]
    return tracks[columns].reset_index(drop=True)


def save_processed_network_tracks(tracks: gpd.GeoDataFrame) -> str:
    path = processed_network_path()
    tracks.to_parquet(path, index=False)
    return str(path)


def run_network_tracks_preprocess(path=None) -> dict[str, object]:
    raw = load_detailed_network(path)
    tracks = preprocess_network_tracks(raw)
    saved_path = save_processed_network_tracks(tracks)
    return {"rows": int(len(tracks)), "distinct_bandel": int(tracks["bandel"].nunique()), "saved": saved_path}
