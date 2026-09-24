"""Paths for the Sweden `road_network` source: NVDB's national road-traffic
network (`Vägtrafiknät`), the base geometry the `schools` source's road
matching algorithms 4/5 need. Manually downloaded via Lastkajen (a custom
Sverigefiler order, ~1.4 GB, 2.5M rows) -- no automated `fetch`, same
"place the file under `raw/`" pattern as `network` (rail)'s own manual
download. See `docs/data/sweden/road_network/README.md`.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from src.regions.sweden.sources._layout import domain_dirs


def road_network_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("road_network", root)


def default_road_network_gpkg(root: Path | None = None) -> Path:
    """The manually-downloaded `Vägtrafiknät` GeoPackage -- found by glob
    rather than a fixed filename, since Lastkajen bakes a per-order id into
    the name (e.g. `..._632503.gpkg`, different every time it's re-ordered)."""
    raw_dir = road_network_paths(root)["raw"]
    matches = sorted(raw_dir.glob("**/*.gpkg"))
    if not matches:
        raise FileNotFoundError(
            f"No .gpkg found under {raw_dir} -- download the NVDB Vägtrafiknät "
            "GeoPackage from Lastkajen and place it (zipped or already extracted) there."
        )
    return matches[0]


def processed_road_network_path(root: Path | None = None) -> Path:
    return road_network_paths(root)["processed"] / "road_network.parquet"


def load_road_network(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_road_network_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data road-network preprocess` first.")
    return gpd.read_parquet(path)
