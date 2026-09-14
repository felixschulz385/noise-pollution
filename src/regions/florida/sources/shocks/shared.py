"""Paths, the OpenFEMA endpoint, and the county-name normalization helper
for the Florida `shocks` source.

**County join, not FIPS.** OpenFEMA's `designatedArea` is a county-name
string (`"Broward (County)"`), not just a FIPS code, and Florida has exactly
one school district per county -- confirmed live: `school_cross_section
.parquet`'s districts `01`-`67` are real county names, one-to-one with
Florida's 67 counties (districts `68`+ are special entities -- lab schools,
DJJ, charter consortiums -- that don't map to one county). So the join is a
normalized county-NAME match against `district_name`, not a hand-typed
FIPS crosswalk table. Checked the live `designatedArea` value set (79
distinct strings across all 2,794 FL rows, see
`docs/data/florida/shocks/README.md`) before committing to this design: 67
real counties suffixed `" (County)"`, one naming alias needed (`"Dade
(County)"`, the pre-1997 name, still appears on older declarations --
`Miami-Dade (County)` is current), `"Statewide"` (a real signal, not
dropped), and 10 tribal-reservation/trust-land names that don't map to any
FLDOE district (kept as their own upper-cased `county_name` in the
processed table, not coerced to NA or dropped -- `shocks/assemble.py` is
where "doesn't match any of the 67 real district names" gets resolved,
reported as `unmapped_county_rows`, and excluded from the per-county
rollup).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "shocks"

OPENFEMA_BASE = "https://www.fema.gov/api/open/v2"
DISASTER_DECLARATIONS_URL = f"{OPENFEMA_BASE}/DisasterDeclarationsSummaries"

# Confirmed live 2026-09-14: `$top=5000` returns every FL row (2,794) in one
# response -- no pagination loop needed, unlike every other Florida source's
# archive.
FETCH_TOP = 5000

_COUNTY_SUFFIX_RE = re.compile(r"\s*\(County\)\s*$", re.IGNORECASE)
# Pre-1997 name; still appears on older OpenFEMA declarations.
_COUNTY_NAME_ALIASES = {"DADE": "MIAMI-DADE"}
STATEWIDE_AREA = "STATEWIDE"


def normalize_county_name(designated_area: pd.Series) -> pd.Series:
    """`"Broward (County)"` -> `"BROWARD"`, matching
    `school_cross_section.parquet`'s `district_name`. Non-county areas
    (`"Statewide"`, tribal reservations/trust lands) are left as their
    upper-cased raw string -- callers distinguish `STATEWIDE_AREA` and
    otherwise treat anything not matching a real `district_name` as
    unmapped (excluded from the county-year rollup, reported not silently
    dropped -- see `assemble.py`'s `unmapped_county_rows`), not silently
    coerced into a county."""
    stripped = designated_area.astype("string").str.replace(_COUNTY_SUFFIX_RE, "", regex=True)
    upper = stripped.str.strip().str.upper()
    return upper.replace(_COUNTY_NAME_ALIASES)


def shocks_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


RAW_DISASTER_DECLARATIONS_FILENAME = "disaster_declarations.parquet"


def raw_disaster_declarations_path(root: Path | None = None) -> Path:
    return shocks_paths(root)["raw"] / RAW_DISASTER_DECLARATIONS_FILENAME


PROCESSED_DECLARATIONS_FILENAME = "disaster_declarations.parquet"
PROCESSED_METADATA_FILENAME = "shocks.json"


def processed_declarations_path(root: Path | None = None) -> Path:
    return shocks_paths(root)["processed"] / PROCESSED_DECLARATIONS_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    return shocks_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


ASSEMBLED_SCHOOL_YEAR_FILENAME = "school_shocks_panel.parquet"


def school_shocks_panel_path(root: Path | None = None) -> Path:
    return shocks_paths(root)["assembled"] / ASSEMBLED_SCHOOL_YEAR_FILENAME
