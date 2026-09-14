"""Preprocess step for the Florida `road_projects` source.

Tidies the two raw ArcGIS extracts `fetch.py` wrote -- `Work_Program_Current`
layers 2 (Construction) + 13 (PD&E), and `Active_Construction_Projects` --
into one project-events table, `road_projects.parquet`.

**Row grain is one row per raw project-item record** (`(roadway_id,
begin_post, end_post, fiscal_year_or_date, work_type)`), not aggregated the
way `traffic/preprocess.py` collapses AADT to `roadway_id x release_year`:
here the *timing and type* of each individual project is the signal a
consumer needs (to test "was a widening co-timed with this wall"), so
collapsing multiple co-located projects into one row would destroy exactly
the information this source exists to carry.

**The two sources have different natural grains and are kept in one table
via a `source` tag column, not unioned into a single date/status scheme.**
`Work_Program_Current` only has `fiscal_year` (`FISCALYR`) granularity and is
current-Work-Program-window only (see the module's `shared.py` docstring: a
live `FISCALYR<2020` query returned zero rows). `Active_Construction_Projects`
has real `start_date`/`end_date` and reaches back to 2009 (confirmed via
`outStatistics` on `StartDate`), so it is the only usable pre-2020 signal --
see `docs/data/florida/road_projects/README.md` Open Question 1. A consumer
joining this table should not assume every row has both a fiscal year and a
start/end date; most rows have exactly one, by design of which raw source
they came from.

**`is_wall_project`**: a cheap keyword scan (`WALL`, `BARRIER`, `NOISE`,
case-insensitive) over each row's free-text description. Flagged in the
README as worth trying after a live `Active_Construction_Projects` sample
turned up a literal wall-adjacent contract description ("... Perimeter
Wall"). This is a heuristic screen for the "wall built as its own line item"
vs. "wall folded into a bigger widening" split Cluster D wants -- not a
validated ground truth, and false negatives are expected (a wall folded into
a project whose description only mentions "ADD LANES & RECONSTR" would not
match). Treat it as a starting point for manual/spatial cross-checking
against `noise_barriers`, not a finished treatment-split variable.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd

from src.regions.florida.sources.road_projects.shared import (
    processed_metadata_path,
    processed_projects_path,
    raw_active_construction_path,
    raw_work_program_path,
    road_projects_paths,
)

OUTPUT_COLUMNS = [
    "source",
    "roadway_id",
    "begin_post",
    "end_post",
    "fiscal_year",
    "start_date",
    "end_date",
    "work_type",
    "status",
    "description",
    "is_wall_project",
    "cost",
    "fin_proj_num",
    "district",
    "county",
]

_WALL_KEYWORD_RE = re.compile(r"\b(?:wall|barrier|noise)\b", re.IGNORECASE)

_WP_RENAME = {
    "RDWYID": "roadway_id",
    "BEGSECPT": "begin_post",
    "ENDSECPT": "end_post",
    "FISCALYR": "fiscal_year",
    "WPWKMIXN": "work_type",
    "WPITSTNM": "status",
    "LOCALFULL": "description",
    "FINPROJ": "fin_proj_num",
    "MANDISDV": "district",
    "CONTYNAM": "county",
}

_AC_RENAME = {
    "RoadwayId": "roadway_id",
    "BeginMP": "begin_post",
    "EndMP": "end_post",
    "StartDate": "start_date",
    "EstEndDate": "end_date",
    "Description": "description",
    "Cost": "cost",
    "FinProjNum": "fin_proj_num",
    "District": "district",
    "County": "county",
}


def load_raw_work_program(name: str) -> pd.DataFrame:
    path = raw_work_program_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `python -m src.cli florida data road-projects fetch` first."
        )
    return pd.read_parquet(path)


def load_raw_active_construction() -> pd.DataFrame:
    path = raw_active_construction_path()
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `python -m src.cli florida data road-projects fetch` first."
        )
    return pd.read_parquet(path)


def _clean_description(series: pd.Series) -> pd.Series:
    """Normalise whitespace -- FDOT's export line-wraps some free-text
    fields mid-word (confirmed live, e.g. "Peri meter Wall")."""
    return series.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()


def _tag_wall_keyword(description: pd.Series) -> pd.Series:
    return description.fillna("").str.contains(_WALL_KEYWORD_RE)


def _tidy_work_program(raw: pd.DataFrame, *, phase: str) -> pd.DataFrame:
    present = {src: dst for src, dst in _WP_RENAME.items() if src in raw.columns}
    out = raw[list(present)].rename(columns=present).copy()
    out["source"] = f"work_program_{phase}"
    if "fiscal_year" in out.columns:
        out["fiscal_year"] = pd.to_numeric(out["fiscal_year"], errors="coerce").astype("Int64")
    if "description" in out.columns:
        out["description"] = _clean_description(out["description"])
    out["start_date"] = pd.NaT
    out["end_date"] = pd.NaT
    out["cost"] = float("nan")
    return out


def _tidy_active_construction(raw: pd.DataFrame) -> pd.DataFrame:
    present = {src: dst for src, dst in _AC_RENAME.items() if src in raw.columns}
    out = raw[list(present)].rename(columns=present).copy()
    out["source"] = "active_construction"
    for col in ("start_date", "end_date"):
        if col in out.columns:
            # ArcGIS date fields come back as epoch milliseconds.
            out[col] = pd.to_datetime(pd.to_numeric(out[col], errors="coerce"), unit="ms", errors="coerce")
    if "description" in out.columns:
        out["description"] = _clean_description(out["description"])
    if "cost" in out.columns:
        cost = pd.to_numeric(out["cost"], errors="coerce")
        out["cost"] = cost.where(cost > 0)
    for missing in ("fiscal_year", "work_type", "status"):
        out[missing] = pd.NA
    return out


def preprocess_road_projects(
    work_program_construction: pd.DataFrame,
    work_program_pde: pd.DataFrame,
    active_construction: pd.DataFrame,
) -> pd.DataFrame:
    """Tidy and stack the three raw extracts into one project-events table."""
    parts = [
        _tidy_work_program(work_program_construction, phase="construction"),
        _tidy_work_program(work_program_pde, phase="pde"),
        _tidy_active_construction(active_construction),
    ]
    out = pd.concat(parts, ignore_index=True, sort=False)

    if "roadway_id" in out.columns:
        out["roadway_id"] = out["roadway_id"].astype("string").str.strip()
    out["description"] = out.get("description", pd.Series(dtype="string")).astype("string")
    out["is_wall_project"] = _tag_wall_keyword(out["description"])
    # Each source only ever fills one of {fiscal_year} / {start_date, end_date,
    # cost}, so the concat's other half is NA -- but pandas can still land on
    # a mixed-dtype `object` column (NaN float + real Timestamp/int) rather
    # than a clean typed one; force the dtype explicitly rather than trust
    # concat's own inference.
    out["start_date"] = pd.to_datetime(out["start_date"], errors="coerce")
    out["end_date"] = pd.to_datetime(out["end_date"], errors="coerce")
    out["cost"] = pd.to_numeric(out["cost"], errors="coerce")
    out["fiscal_year"] = pd.to_numeric(out["fiscal_year"], errors="coerce").astype("Int64")

    ordered = [column for column in OUTPUT_COLUMNS if column in out.columns]
    remaining = [column for column in out.columns if column not in ordered]
    out = out[ordered + remaining]
    sort_cols = [c for c in ("roadway_id", "begin_post") if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, na_position="last").reset_index(drop=True)
    return out


def save_processed_road_projects(df: pd.DataFrame) -> dict[str, str]:
    parquet_path = processed_projects_path()
    meta_path = processed_metadata_path()
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)

    provenance = {
        "source": "fdot_work_program_current_and_active_construction_projects",
        "grain": "one row per raw project-item record (roadway_id x begin_post/end_post x fiscal_year-or-date x work_type)",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "rows_by_source": (
            {str(k): int(v) for k, v in df["source"].value_counts().items()} if "source" in df.columns else {}
        ),
        "distinct_roadway_ids": int(df["roadway_id"].nunique()) if "roadway_id" in df.columns else None,
        "fiscal_year_range": (
            [int(df["fiscal_year"].min()), int(df["fiscal_year"].max())]
            if "fiscal_year" in df.columns and df["fiscal_year"].notna().any()
            else None
        ),
        "start_date_range": (
            [str(df["start_date"].min()), str(df["start_date"].max())]
            if "start_date" in df.columns and df["start_date"].notna().any()
            else None
        ),
        "wall_keyword_rows": int(df["is_wall_project"].sum()) if "is_wall_project" in df.columns else 0,
        "columns": list(df.columns),
        "parquet": str(parquet_path),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"parquet": str(parquet_path), "metadata": str(meta_path)}


def run_road_projects_preprocess() -> dict[str, object]:
    work_program_construction = load_raw_work_program("construction")
    work_program_pde = load_raw_work_program("pde")
    active_construction = load_raw_active_construction()

    processed = preprocess_road_projects(work_program_construction, work_program_pde, active_construction)
    saved = save_processed_road_projects(processed)

    return {
        "raw_rows": {
            "work_program_construction": int(len(work_program_construction)),
            "work_program_pde": int(len(work_program_pde)),
            "active_construction": int(len(active_construction)),
        },
        "rows": int(len(processed)),
        "distinct_roadway_ids": int(processed["roadway_id"].nunique()),
        "wall_keyword_rows": int(processed["is_wall_project"].sum()),
        "columns": list(processed.columns),
        "saved": saved,
    }
