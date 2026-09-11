"""Paths for the Florida ``panel`` domain: the final event-study analysis
panel. No ``fetch``/``preprocess`` of its own, so ``raw``/``processed`` stay
empty — only ``assembled`` is used — but `domain_dirs` creates all three for
consistency with every other Florida source.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "panel"

ASSEMBLED_PANEL_FILENAME = "event_study_panel.parquet"
ASSEMBLED_METADATA_FILENAME = "event_study_panel.json"


def panel_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


def assembled_panel_path(root: Path | None = None) -> Path:
    return panel_paths(root)["assembled"] / ASSEMBLED_PANEL_FILENAME


def assembled_metadata_path(root: Path | None = None) -> Path:
    return panel_paths(root)["assembled"] / ASSEMBLED_METADATA_FILENAME
