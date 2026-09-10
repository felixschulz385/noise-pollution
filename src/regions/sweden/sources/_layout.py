"""Sweden's binding of the core path layout.

All Sweden pipeline data lives under ``data/sweden/<domain>/...``. Source
modules call :func:`domain_dirs` rather than naming the region themselves.
"""
from __future__ import annotations

from pathlib import Path

from src.core.pipeline.layout import region_data_root, region_dirs

REGION = "sweden"


def domain_dirs(domain: str, root: Path | None = None) -> dict[str, Path]:
    return region_dirs(REGION, domain, root)


def data_root(root: Path | None = None) -> Path:
    return region_data_root(REGION, root)
