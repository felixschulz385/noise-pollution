from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from src.regions.sweden.sources._layout import domain_dirs


MANUAL_DOWNLOAD_WARNING = (
    "Network fetch is not implemented here. Download the Trafikverket GeoPackage "
    "manually and place it in data/sweden/network/raw."
)


def network_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("network", root)


def default_network_gpkg(root: Path | None = None) -> Path:
    raw_dir = domain_dirs("network", root)["raw"]
    candidates = [
        raw_dir
        / "Järnvägsnät_bandel_aggregat_GeoPackage"
        / "Järnvägsnät_bandel_aggregat_GeoPackage.gpkg",
        raw_dir / "Järnvägsnät_bandel_aggregat_GeoPackage.gpkg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_detailed_network_gpkg(root: Path | None = None) -> Path:
    """The `grundegenskaper` (fine-grained: real track geometry, per-row
    `Bandel`/`KmFr`/`KmTi` linear reference) GeoPackage -- the candidate
    network for `_barrier_reference.py`'s matching. Distinct from
    `default_network_gpkg`'s `bandel_aggregat` file (515 rows, coarser,
    used only by the existing summarize/plot commands)."""
    raw_dir = domain_dirs("network", root)["raw"]
    candidates = [
        raw_dir
        / "Järnvägsnät_grundegenskaper3_0_GeoPackage"
        / "Järnvägsnät_grundegenskaper3_0_GeoPackage.gpkg",
        raw_dir / "Järnvägsnät_grundegenskaper3_0_GeoPackage.gpkg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def processed_network_path(root: Path | None = None) -> Path:
    return domain_dirs("network", root)["processed"] / "network_tracks.parquet"


def load_network_tracks(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_network_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data network preprocess-tracks` first.")
    return gpd.read_parquet(path)
