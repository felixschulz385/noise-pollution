"""Paths, ACS variable registry, and boundary-file URLs for the Florida
`neighbourhood` source. Pure stdlib.
"""
from __future__ import annotations

import os
from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "neighbourhood"
FIPS_FLORIDA = "12"

CENSUS_API_KEY_ENV = "CENSUS_API_KEY"


def require_census_api_key() -> str:
    key = os.environ.get(CENSUS_API_KEY_ENV)
    if not key:
        raise RuntimeError(
            f"{CENSUS_API_KEY_ENV} is not set. The Census Data API has required a key for every "
            "request since 2026-05 (confirmed live — an unauthenticated request returns an HTML "
            "'Missing Key' page, not JSON). Get a free key at "
            "https://api.census.gov/data/key_signup.html and set it as an environment variable, "
            "e.g. `export CENSUS_API_KEY=...`, then re-run."
        )
    return key


# --- ACS 5-year: variable registry -----------------------------------------
#
# Every code below was checked directly against the live `variables.json`
# for the relevant vintage year, not assumed. `B19013`/`B17001`/`B25003`/
# `B07003` are stable across the whole 2009-2022+ span checked; the
# education table is NOT (see `education_variables` below).
ACS_DATASET = "acs/acs5"
ACS_FIRST_YEAR = 2009  # first ACS5 vintage (2005-2009 5-year estimates)
# Confirmed live 2026-09-17 (real fetch, `CENSUS_API_KEY` set): every year
# 2009-2024 returns real data in one request each, no errors. Not a guess.
ACS_LAST_KNOWN_YEAR = 2024

MEDIAN_HOUSEHOLD_INCOME_VAR = "B19013_001E"
POVERTY_TOTAL_VAR = "B17001_001E"
POVERTY_BELOW_VAR = "B17001_002E"
TENURE_TOTAL_VAR = "B25003_001E"
TENURE_OWNER_VAR = "B25003_002E"
MOBILITY_TOTAL_VAR = "B07003_001E"
MOBILITY_SAME_HOUSE_VAR = "B07003_004E"

# `B15003` (Educational Attainment for the Population 25 Years and Over, no
# sex split) was NOT YET published in the 2009-2011 ACS5 vintages -- confirmed
# live: `variables.json` for 2011 has no `B15003_*` keys at all, 2012 does.
# Those earlier vintages use the older, sex-split `B15002` table instead
# (Sex by Educational Attainment for the Population 25 Years and Over) --
# same universe, just split by sex, so the four degree categories need
# summing across both sexes.
EDUCATION_TABLE_TRANSITION_YEAR = 2012

EDUCATION_TOTAL_VAR_B15003 = "B15003_001E"
EDUCATION_BACHELORS_PLUS_VARS_B15003 = ("B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E")

EDUCATION_TOTAL_VARS_B15002 = ("B15002_002E", "B15002_019E")  # male total + female total
EDUCATION_BACHELORS_PLUS_VARS_B15002 = (
    "B15002_015E", "B15002_016E", "B15002_017E", "B15002_018E",  # male: bachelor's..doctorate
    "B15002_032E", "B15002_033E", "B15002_034E", "B15002_035E",  # female: bachelor's..doctorate
)


def education_variables(year: int) -> dict[str, tuple[str, ...]]:
    """`{"total": (...), "bachelors_plus": (...)}` -- which table to sum,
    depending on whether `year` predates `B15003`'s introduction."""
    if year < EDUCATION_TABLE_TRANSITION_YEAR:
        return {"total": EDUCATION_TOTAL_VARS_B15002, "bachelors_plus": EDUCATION_BACHELORS_PLUS_VARS_B15002}
    return {"total": (EDUCATION_TOTAL_VAR_B15003,), "bachelors_plus": EDUCATION_BACHELORS_PLUS_VARS_B15003}


def acs_variables(year: int) -> list[str]:
    edu = education_variables(year)
    return [
        MEDIAN_HOUSEHOLD_INCOME_VAR, POVERTY_TOTAL_VAR, POVERTY_BELOW_VAR,
        TENURE_TOTAL_VAR, TENURE_OWNER_VAR, MOBILITY_TOTAL_VAR, MOBILITY_SAME_HOUSE_VAR,
        *edu["total"], *edu["bachelors_plus"],
    ]


def acs_tract_url(year: int, api_key: str) -> str:
    variables = ",".join(["NAME", *acs_variables(year)])
    return (
        f"https://api.census.gov/data/{year}/{ACS_DATASET}"
        f"?get={variables}&for=tract:*&in=state:{FIPS_FLORIDA}&key={api_key}"
    )


# --- Tract boundary vintages -------------------------------------------
#
# ACS 5-year estimates switched from 2010-vintage to 2020-vintage census
# tracts AT the "2020" 5-year release (confirmed against Census's own "2020
# Geography Changes" documentation page, not assumed) -- a vintage year
# <=2019 needs 2010-vintage tract polygons for a correct spatial join,
# >=2020 needs 2020-vintage ones. Cartographic boundary files (`cb_*_500k`,
# generalized 1:500,000 -- far smaller than the full-resolution TIGER
# files, ~2.4MB for one state vs the full state's ~14MB TIGER cut) are used
# rather than full-resolution TIGER: a school's point is rarely close enough
# to a tract/ZIP line for generalization error to matter, and this is a
# diagnostic covariate, not a treatment-defining match -- a real,
# documented approximation, not oversold.
TRACT_VINTAGE_2020_START_YEAR = 2020

TIGER_GENZ_BASE = "https://www2.census.gov/geo/tiger"
TRACT_BOUNDARY_URLS = {
    "2010": f"{TIGER_GENZ_BASE}/GENZ2015/shp/cb_2015_12_tract_500k.zip",
    "2020": f"{TIGER_GENZ_BASE}/GENZ2022/shp/cb_2022_12_tract_500k.zip",
}

# ZCTAs (ZIP Code Tabulation Areas) approximate USPS ZIP codes and are only
# published as one NATIONAL file (no per-state cut exists -- confirmed live,
# a per-state TIGER path 404s) -- one current vintage is enough for the
# school->ZIP match (Zillow's own ZHVI series isn't itself vintage-tagged).
ZCTA_BOUNDARY_URL = f"{TIGER_GENZ_BASE}/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"

# --- Zillow ZHVI ---------------------------------------------------------
#
# ZIP-level, single-family + condo, mid-tier (33rd-67th percentile),
# smoothed & seasonally adjusted, monthly -- Zillow's own default/flagship
# ZHVI cut. Public CSV, no key, confirmed live (wide format: one column per
# month back to 2000-01).
ZHVI_ZIP_URL = "https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"


def tract_vintage_for_year(year: int) -> str:
    return "2020" if year >= TRACT_VINTAGE_2020_START_YEAR else "2010"


def neighbourhood_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


def raw_tract_boundary_dir(vintage: str, root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["raw"] / f"tract_boundaries_{vintage}"


def raw_zcta_boundary_dir(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["raw"] / "zcta_boundaries"


def raw_zhvi_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["raw"] / "zhvi_zip.parquet"


def raw_acs_year_path(year: int, root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["raw"] / "acs" / f"{year}.parquet"


PROCESSED_TRACT_BOUNDARIES_FILENAME = "tract_boundaries.parquet"
PROCESSED_ZCTA_BOUNDARIES_FILENAME = "zcta_boundaries.parquet"
PROCESSED_ACS_FILENAME = "acs_tract.parquet"
PROCESSED_ZHVI_FILENAME = "zhvi_zip.parquet"
PROCESSED_METADATA_FILENAME = "neighbourhood.json"


def processed_tract_boundaries_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / PROCESSED_TRACT_BOUNDARIES_FILENAME


def processed_zcta_boundaries_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / PROCESSED_ZCTA_BOUNDARIES_FILENAME


def processed_acs_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / PROCESSED_ACS_FILENAME


def processed_zhvi_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / PROCESSED_ZHVI_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


ASSEMBLED_SCHOOL_TRACT_MATCH_FILENAME = "school_tract_match.parquet"
ASSEMBLED_SCHOOL_ZIP_MATCH_FILENAME = "school_zip_match.parquet"
ASSEMBLED_SCHOOL_ACS_PANEL_FILENAME = "school_acs_panel.parquet"
ASSEMBLED_SCHOOL_ZHVI_PANEL_FILENAME = "school_zhvi_panel.parquet"


def school_tract_match_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["assembled"] / ASSEMBLED_SCHOOL_TRACT_MATCH_FILENAME


def school_zip_match_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["assembled"] / ASSEMBLED_SCHOOL_ZIP_MATCH_FILENAME


def school_acs_panel_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["assembled"] / ASSEMBLED_SCHOOL_ACS_PANEL_FILENAME


def school_zhvi_panel_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["assembled"] / ASSEMBLED_SCHOOL_ZHVI_PANEL_FILENAME
