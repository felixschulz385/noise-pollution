from __future__ import annotations

from pathlib import Path

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
