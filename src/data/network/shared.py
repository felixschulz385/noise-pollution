from __future__ import annotations

from pathlib import Path

from src.data.shared.paths import ensure_domain_dirs, find_repo_root


MANUAL_DOWNLOAD_WARNING = (
    "Network fetch is not implemented here. Download the Trafikverket GeoPackage manually and place it in data/network/raw."
)


def network_paths(root: Path | None = None) -> dict[str, Path]:
    return ensure_domain_dirs("network", root)


def default_network_gpkg(root: Path | None = None) -> Path:
    repo_root = find_repo_root(root)
    candidates = [
        repo_root
        / "data"
        / "network"
        / "raw"
        / "Järnvägsnät_bandel_aggregat_GeoPackage"
        / "Järnvägsnät_bandel_aggregat_GeoPackage.gpkg",
        repo_root
        / "data"
        / "raw"
        / "Järnvägsnät_bandel_aggregat_GeoPackage"
        / "Järnvägsnät_bandel_aggregat_GeoPackage.gpkg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
