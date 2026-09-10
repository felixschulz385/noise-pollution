"""On-disk path construction for the pipeline.

Every pipeline path is region-scoped: ``data/<region>/<domain>/{raw,processed,assembled}``.
This module is the one place that layout is defined — see
docs/design/01-multi-region-layout.md. It is parameterized by region and never
names one.
"""
from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "src").exists() and (candidate / "data").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root from the current working directory.")


def region_data_root(region: str, root: Path | None = None) -> Path:
    return find_repo_root(root) / "data" / region


def region_dirs(region: str, domain: str, root: Path | None = None) -> dict[str, Path]:
    """Create (if needed) and return the raw/processed/assembled dirs for one
    domain within one region: ``data/<region>/<domain>/...``."""
    base_dir = region_data_root(region, root) / domain
    paths = {
        "base": base_dir,
        "raw": base_dir / "raw",
        "processed": base_dir / "processed",
        "assembled": base_dir / "assembled",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
