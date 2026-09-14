"""Preprocess step for the Florida `shocks` source.

Tidies the raw OpenFEMA extract `fetch.py` wrote: normalizes
`designatedArea` to a `county_name` matching `school_cross_section
.parquet`'s `district_name` (see `shared.py`'s module docstring for the
county-name-not-FIPS join design), and derives `assessment_year` -- the
FLDOE spring assessment year a declaration most likely disrupted.

**`assessment_year` is a documented modeling assumption, not a guess.**
Mirrors the month-aware convention `schools/preprocess.py` already uses for
`in_operation` (`open_spring = year + (month >= 7)`): a declaration in the
second half of the calendar year (Jul-Dec, i.e. hurricane season and the
fall semester) is attributed to the *following* spring's assessment year; a
declaration in the first half (Jan-Jun) is attributed to that *same*
spring. This matches Florida's actual hurricane-season climatology
(Jun-Nov) closely enough that nearly every hurricane declaration falls on
the "next spring" side of the rule, but it is still an assumption -- flagged
here and in the module's row grain, not silently baked in.

Row grain is one row per raw disaster-declaration record (not collapsed to
county x year here -- that rollup is `assemble.py`'s job, same "grain over
pre-aggregation" choice `traffic`/`road_projects` made, so a consumer can
still see individual declarations, not just a count).
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from src.regions.florida.sources.shocks.shared import (
    STATEWIDE_AREA,
    normalize_county_name,
    processed_declarations_path,
    processed_metadata_path,
    raw_disaster_declarations_path,
)

OUTPUT_COLUMNS = [
    "disaster_number",
    "fema_declaration_string",
    "declaration_type",
    "incident_type",
    "declaration_title",
    "declaration_date",
    "assessment_year",
    "is_hurricane",
    "is_statewide",
    "county_name",
    "designated_area_raw",
    "fips_county_code",
    "incident_begin_date",
    "incident_end_date",
]

_RENAME = {
    "disasterNumber": "disaster_number",
    "femaDeclarationString": "fema_declaration_string",
    "declarationType": "declaration_type",
    "incidentType": "incident_type",
    "declarationTitle": "declaration_title",
    "declarationDate": "declaration_date",
    "designatedArea": "designated_area_raw",
    "fipsCountyCode": "fips_county_code",
    "incidentBeginDate": "incident_begin_date",
    "incidentEndDate": "incident_end_date",
}


def load_raw_disaster_declarations() -> pd.DataFrame:
    path = raw_disaster_declarations_path()
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `... florida data shocks fetch` first.")
    return pd.read_parquet(path)


def _derive_assessment_year(declaration_date: pd.Series) -> pd.Series:
    year = declaration_date.dt.year
    month = declaration_date.dt.month
    return (year + (month >= 7).astype("Int64")).astype("Int64")


def preprocess_shocks(raw: pd.DataFrame) -> pd.DataFrame:
    present = {src: dst for src, dst in _RENAME.items() if src in raw.columns}
    out = raw[list(present)].rename(columns=present).copy()

    for col in ("declaration_date", "incident_begin_date", "incident_end_date"):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")

    out["assessment_year"] = _derive_assessment_year(out["declaration_date"])
    out["county_name"] = normalize_county_name(out["designated_area_raw"])
    out["is_statewide"] = out["county_name"] == STATEWIDE_AREA
    out["is_hurricane"] = out["incident_type"] == "Hurricane"

    ordered = [column for column in OUTPUT_COLUMNS if column in out.columns]
    remaining = [column for column in out.columns if column not in ordered]
    out = out[ordered + remaining]
    return out.sort_values(["declaration_date", "county_name"], na_position="last").reset_index(drop=True)


def save_processed_shocks(df: pd.DataFrame) -> dict[str, str]:
    parquet_path = processed_declarations_path()
    meta_path = processed_metadata_path()
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)

    provenance = {
        "source": "openfema_disaster_declarations_summaries_v2",
        "grain": "one row per raw disaster-declaration record",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "assessment_year_range": (
            [int(df["assessment_year"].min()), int(df["assessment_year"].max())]
            if df["assessment_year"].notna().any()
            else None
        ),
        "hurricane_rows": int(df["is_hurricane"].sum()),
        "statewide_rows": int(df["is_statewide"].sum()),
        "columns": list(df.columns),
        "parquet": str(parquet_path),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"parquet": str(parquet_path), "metadata": str(meta_path)}


def run_shocks_preprocess() -> dict[str, object]:
    raw = load_raw_disaster_declarations()
    processed = preprocess_shocks(raw)
    saved = save_processed_shocks(processed)

    return {
        "raw_rows": int(len(raw)),
        "rows": int(len(processed)),
        "hurricane_rows": int(processed["is_hurricane"].sum()),
        "statewide_rows": int(processed["is_statewide"].sum()),
        "assessment_year_range": (
            [int(processed["assessment_year"].min()), int(processed["assessment_year"].max())]
            if processed["assessment_year"].notna().any()
            else None
        ),
        "columns": list(processed.columns),
        "saved": saved,
    }
