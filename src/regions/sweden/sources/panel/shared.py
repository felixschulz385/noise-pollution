"""Paths for the Sweden `panel` domain: the final event-study analysis
panel, mirroring Florida's `panel/shared.py`. No `fetch`/`preprocess` of its
own -- only `assembled` is used -- but `domain_dirs` creates all three for
consistency with every other Sweden source.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs

DOMAIN = "panel"

ASSEMBLED_PANEL_FILENAME = "event_study_panel.parquet"
ASSEMBLED_METADATA_FILENAME = "event_study_panel.json"


def panel_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


def assembled_panel_path(root: Path | None = None) -> Path:
    return panel_paths(root)["assembled"] / ASSEMBLED_PANEL_FILENAME


def assembled_metadata_path(root: Path | None = None) -> Path:
    return panel_paths(root)["assembled"] / ASSEMBLED_METADATA_FILENAME
