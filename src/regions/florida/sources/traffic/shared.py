"""Paths and helpers for the Florida `traffic` (AADT panel) source.

Built entirely from the FGDL `rciroads` releases `road_network` already
fetches -- each release is a point-in-time snapshot that carries an `AADT`
field per roadway segment (see `docs/data/florida/road_network/README.md`,
which flagged this as "a head start for the future `traffic` source").
Fetching *multiple* releases turns that single snapshot into a panel: each
release's own publication month/year (parsed from its version tag, e.g.
`jul26` -> 2026, via `road_network.shared.version_sort_key`) is used as the
panel's `release_year` -- not the raw, often-sentinel/missing `YEAR_` field
carried on the layer itself (~16% `0`-sentinel, see `road_network/preprocess.py`).

This module intentionally does not duplicate `road_network`'s HTTP/zip
download logic -- `fetch.py` calls straight into
`road_network.fetch.fetch_road_network` to get each release's raw shapefile
onto disk (written into `road_network`'s own `raw/` dir, so the two sources
share one copy of each release rather than each keeping their own), then
keeps only the small attribute table this source needs. See `fetch.py` for
why the geometry is deleted again by default.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs
from src.regions.florida.sources.road_network.shared import validate_version, version_sort_key

DOMAIN = "traffic"


def traffic_paths(root: Path | None = None) -> dict[str, Path]:
    """The raw/processed/assembled dirs for `data/florida/traffic`."""
    return domain_dirs(DOMAIN, root)


RAW_AADT_FILENAME_TEMPLATE = "aadt_{version}.parquet"
PROCESSED_AADT_PANEL_FILENAME = "aadt_panel.parquet"
PROCESSED_METADATA_FILENAME = "traffic.json"
ASSEMBLED_SCHOOL_ROAD_MATCH_FILENAME = "school_road_match.parquet"
ASSEMBLED_SCHOOL_AADT_PANEL_FILENAME = "school_aadt_panel.parquet"
ASSEMBLED_SCHOOL_NEARBY_AADT_FILENAME = "school_nearby_aadt.parquet"


def raw_aadt_path(version: str, root: Path | None = None) -> Path:
    """The per-release attribute-only table `fetch.py` writes."""
    resolved = validate_version(version)
    return traffic_paths(root)["raw"] / RAW_AADT_FILENAME_TEMPLATE.format(version=resolved)


def processed_aadt_panel_path(root: Path | None = None) -> Path:
    """The stacked roadway-segment x release-year AADT panel `preprocess`
    writes."""
    return traffic_paths(root)["processed"] / PROCESSED_AADT_PANEL_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    """The JSON provenance sidecar written next to the AADT panel."""
    return traffic_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


def school_road_match_path(root: Path | None = None) -> Path:
    """One row per placed school: its nearest arterial `roadway_id`."""
    return traffic_paths(root)["assembled"] / ASSEMBLED_SCHOOL_ROAD_MATCH_FILENAME


def school_aadt_panel_path(root: Path | None = None) -> Path:
    """`msid x release_year`: every matched school's roadway AADT time
    series."""
    return traffic_paths(root)["assembled"] / ASSEMBLED_SCHOOL_AADT_PANEL_FILENAME


def release_year(version: str) -> int:
    """The calendar year an FGDL release tag like `jul26` denotes (2026) --
    used as the panel's observation year, not the layer's own `YEAR_`
    field."""
    year, _month_index = version_sort_key(version)
    if year < 0:
        raise ValueError(f"Invalid FGDL version tag '{version}'.")
    return year


def school_nearby_aadt_path(root: Path | None = None) -> Path:
    """`msid x release_year`: the busiest RCI road within each radius of the school."""
    return traffic_paths(root)["assembled"] / ASSEMBLED_SCHOOL_NEARBY_AADT_FILENAME
