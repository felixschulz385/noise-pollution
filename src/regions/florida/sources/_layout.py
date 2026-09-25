"""Florida's binding of the core path layout, and its metric CRS.

All Florida pipeline data lives under ``data/florida/<domain>/...``. Source
modules call :func:`domain_dirs` rather than naming the region themselves.
"""
from __future__ import annotations

from pathlib import Path

from src.core.pipeline.layout import region_data_root, region_dirs

REGION = "florida"
# Florida GDL Albers (metres): every Florida geometry computation.
METRIC_CRS = "EPSG:3087"


def domain_dirs(domain: str, root: Path | None = None) -> dict[str, Path]:
    return region_dirs(REGION, domain, root)


def data_root(root: Path | None = None) -> Path:
    return region_data_root(REGION, root)
