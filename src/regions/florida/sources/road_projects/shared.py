"""Paths and ArcGIS REST endpoint constants for the Florida `road_projects`
source.

Two live FDOT services, confirmed 2026-09-14 (see
`docs/data/florida/road_projects/README.md` for the full verification):

* `Work_Program_Current` FeatureServer -- 21 work-program-phase sublayers,
  EPSG:3087. This source only fetches layer 2 (Construction Phase) and
  layer 13 (PD&E Phase). Confirmed current-window only: a live query for
  `FISCALYR<2020` returns zero rows.
* `Active_Construction_Projects` FeatureServer, layer id **1** (not 0 --
  0 errors) -- EPSG:26917, Site Manager contract extract. NOT current-only
  despite the name: `StartDate` spans 2009-03-03 to 2026-04-16 (2,428 rows
  total, confirmed via `outStatistics`), the only usable pre-2020 signal
  from either live service.

Both services key roadways by `RDWYID`/`RoadwayId`, the same 8-digit-family
format as `road_network.roadway_id` -- confirmed by live sample values, and
by FDOT's own description of its downloadable historical archive being built
"using linear referencing ... in conjunction with RCI Basemap Roads". So the
join to `road_network` (and from there to `schools`/`traffic`) is a direct
id + milepost-overlap join, not a spatial nearest-line match.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "road_projects"

# Shared between `assemble.py`'s own per-school rollup and
# `panel/assemble.py`'s per-school-year rollup -- lives here (not in
# `assemble.py`) so both can import one definition instead of each keeping
# its own copy of the regex/tagging logic.
WIDENING_KEYWORD_RE = re.compile(r"\b(?:widen|add\s*lane|reconstr|interchange)\w*", re.IGNORECASE)


def tag_widening_keyword(description: pd.Series) -> pd.Series:
    return description.fillna("").str.contains(WIDENING_KEYWORD_RE)

ARCGIS_BASE = "https://gis.fdot.gov/arcgis/rest/services"

WORK_PROGRAM_SERVICE = f"{ARCGIS_BASE}/Work_Program_Current/FeatureServer"
# name -> sublayer id, restricted to the two phases Cluster D actually asks
# for (see road_projects/README.md's "Scope for a first pass").
WORK_PROGRAM_LAYERS = {
    "construction": 2,
    "pde": 13,
}

ACTIVE_CONSTRUCTION_SERVICE = f"{ARCGIS_BASE}/Active_Construction_Projects/FeatureServer"
ACTIVE_CONSTRUCTION_LAYER_ID = 1


def road_projects_paths(root: Path | None = None) -> dict[str, Path]:
    """The raw/processed/assembled dirs for `data/florida/road_projects`."""
    return domain_dirs(DOMAIN, root)


def raw_work_program_path(name: str, root: Path | None = None) -> Path:
    """`name` is one of `WORK_PROGRAM_LAYERS`' keys, e.g. `"construction"`."""
    if name not in WORK_PROGRAM_LAYERS:
        raise ValueError(f"Unknown Work Program layer '{name}'; choose from {sorted(WORK_PROGRAM_LAYERS)}")
    return road_projects_paths(root)["raw"] / f"work_program_{name}.parquet"


def raw_active_construction_path(root: Path | None = None) -> Path:
    return road_projects_paths(root)["raw"] / "active_construction_projects.parquet"


PROCESSED_PROJECTS_FILENAME = "road_projects.parquet"
PROCESSED_METADATA_FILENAME = "road_projects.json"


def processed_projects_path(root: Path | None = None) -> Path:
    """The tidy project-events table written by `preprocess`."""
    return road_projects_paths(root)["processed"] / PROCESSED_PROJECTS_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    return road_projects_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


SCHOOL_ROAD_MATCH_FILENAME = "school_road_match.parquet"
SCHOOL_ROAD_PROJECTS_FILENAME = "school_road_projects.parquet"
SCHOOL_ROAD_PROJECTS_SUMMARY_FILENAME = "school_road_projects_summary.parquet"


def school_road_match_path(root: Path | None = None) -> Path:
    """One row per placed `msid`: nearest arterial `roadway_id` + `dist_m` +
    `milepost` -- this source's own copy of the school<->roadway match
    (recomputed rather than reused from `traffic/assemble.py`, since that
    module doesn't persist milepost)."""
    return road_projects_paths(root)["assembled"] / SCHOOL_ROAD_MATCH_FILENAME


def school_road_projects_path(root: Path | None = None) -> Path:
    """One row per `(msid, road_projects row)` pair where the school's
    milepost falls within that project's `[begin_post, end_post]` (+
    tolerance) on the same `roadway_id`."""
    return road_projects_paths(root)["assembled"] / SCHOOL_ROAD_PROJECTS_FILENAME


def school_road_projects_summary_path(root: Path | None = None) -> Path:
    """One row per placed `msid`: counts/flags/date-range summary of its
    nearby projects."""
    return road_projects_paths(root)["assembled"] / SCHOOL_ROAD_PROJECTS_SUMMARY_FILENAME
