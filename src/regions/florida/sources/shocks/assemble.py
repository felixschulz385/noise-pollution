"""Stage 3 for the Florida `shocks` source: roll declarations up to
`county_name x assessment_year` and validate the county join against the
real FLDOE district roster.

`REQUIRES` `schools preprocess` (`school_cross_section.parquet`) and this
source's own `fetch` + `preprocess` (`disaster_declarations.parquet`).

**Output grain is `county_name x assessment_year`, NOT `msid x year`.**
Unlike `traffic`/`road_projects` (where each school gets a *different*
roadway match, so a per-school panel file is the only way to carry that),
every school in the same county sees the *identical* declaration history --
exploding this to one row per school would multiply a few-thousand-row
county-year table by ~7,000 schools for zero new information. So this
module stops at the compact county-year grain; `panel/assemble.py`'s future
`attach_shocks` joins it onto the event-study panel directly by
`(district_name, year)`, no per-school intermediate file needed.

**`Statewide` declarations are unioned into every county's year, not
dropped.** A statewide disaster declaration legitimately affects every
Florida county; `build_county_year_panel` expands each statewide row across
every real district-county name before aggregating, so a county's counts for
a year reflect both its own county-specific declarations and any statewide
ones.

**County-name join validated against the real FLDOE roster, not assumed.**
`shared.py`'s `normalize_county_name` already handles the one known alias
(`DADE` -> `MIAMI-DADE`), but this module is where a `county_name` that
still doesn't match any of `school_cross_section.parquet`'s 67 real county
districts (the 9 tribal-reservation/trust-land names, see
`docs/data/florida/shocks/README.md`) gets counted and reported, not
silently absorbed -- `run_shocks_assemble`'s report carries
`unmapped_county_rows`.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from src.regions.florida.sources.schools.shared import processed_cross_section_path
from src.regions.florida.sources.shocks.shared import (
    processed_declarations_path,
    school_shocks_panel_path,
)

# Florida school districts 01-67 are the real, one-per-county roster;
# districts 68+ are special entities (lab schools, DJJ, charter
# consortiums, virtual schools) whose `district_name` isn't a county name --
# excluding them keeps a special district's name from ever accidentally
# string-matching a real OpenFEMA county/area name.
MAX_COUNTY_DISTRICT_NUMBER = 67


def load_school_cross_section(root: Path | None = None) -> pd.DataFrame:
    import geopandas as gpd

    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    return gpd.read_parquet(path)[["msid", "district", "district_name"]]


def load_processed_shocks(root: Path | None = None) -> pd.DataFrame:
    path = processed_declarations_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data shocks preprocess` first.")
    return pd.read_parquet(path)


def real_county_names(cross_section: pd.DataFrame) -> pd.Series:
    """The 67 real county `district_name`s — districts numbered above
    `MAX_COUNTY_DISTRICT_NUMBER` are special entities, not counties."""
    district_number = pd.to_numeric(cross_section["district"], errors="coerce")
    is_county = district_number.between(1, MAX_COUNTY_DISTRICT_NUMBER)
    return cross_section.loc[is_county, "district_name"].dropna().drop_duplicates()


def build_county_year_panel(shocks: pd.DataFrame, district_names: pd.Series) -> pd.DataFrame:
    """One row per `(county_name, assessment_year)` with a declaration:
    `n_declarations`, `n_hurricane_declarations`, `any_major_disaster`
    (any row with `declaration_type == "DR"`). `Statewide` rows are
    expanded across every county in `district_names` before aggregating."""
    empty_result = pd.DataFrame(
        columns=["county_name", "assessment_year", "n_declarations", "n_hurricane_declarations", "any_major_disaster"]
    )
    if shocks.empty:
        return empty_result

    known = set(district_names.dropna().unique())
    timed = shocks[shocks["assessment_year"].notna()]
    if timed.empty:
        return empty_result

    county_rows = timed[~timed["is_statewide"]]
    mapped = county_rows[county_rows["county_name"].isin(known)]

    statewide_rows = timed[timed["is_statewide"]]
    if not statewide_rows.empty and known:
        statewide_years = statewide_rows[["assessment_year", "is_hurricane", "declaration_type"]]
        counties = pd.DataFrame({"county_name": sorted(known)})
        statewide_expanded = counties.merge(statewide_years, how="cross")
    else:
        statewide_expanded = pd.DataFrame(columns=["county_name", "assessment_year", "is_hurricane", "declaration_type"])

    combined = pd.concat(
        [mapped[["county_name", "assessment_year", "is_hurricane", "declaration_type"]], statewide_expanded],
        ignore_index=True,
    )
    if combined.empty:
        return empty_result

    grouped = combined.groupby(["county_name", "assessment_year"]).agg(
        n_declarations=("declaration_type", "size"),
        n_hurricane_declarations=("is_hurricane", "sum"),
        any_major_disaster=("declaration_type", lambda s: bool((s == "DR").any())),
    ).reset_index()
    grouped["n_declarations"] = grouped["n_declarations"].astype(int)
    grouped["n_hurricane_declarations"] = grouped["n_hurricane_declarations"].astype(int)
    grouped["assessment_year"] = grouped["assessment_year"].astype(int)
    return grouped.sort_values(["county_name", "assessment_year"]).reset_index(drop=True)


def save_assembled(county_year_panel: pd.DataFrame, root: Path | None = None) -> dict[str, str]:
    path = school_shocks_panel_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    county_year_panel.to_parquet(path, index=False)
    return {"county_year_panel": str(path)}


def run_shocks_assemble(root: Path | None = None) -> dict[str, object]:
    cross_section = load_school_cross_section(root)
    shocks = load_processed_shocks(root)
    district_names = real_county_names(cross_section)

    panel = build_county_year_panel(shocks, district_names)
    saved = save_assembled(panel, root)

    timed = shocks[shocks["assessment_year"].notna()]
    county_rows = timed[~timed["is_statewide"]]
    known = set(district_names.dropna().unique())
    unmapped = county_rows[~county_rows["county_name"].isin(known)]

    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/shocks/assemble.py",
        "distinct_counties": int(len(district_names)),
        "county_year_panel_rows": int(len(panel)),
        "counties_with_a_declaration": int(panel["county_name"].nunique()) if not panel.empty else 0,
        "unmapped_county_rows": int(len(unmapped)),
        "unmapped_county_names": sorted(unmapped["county_name"].dropna().unique().tolist()),
        "saved": saved,
    }
