from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from src.data.network.shared import default_network_gpkg, network_paths


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
