"""Paths, subsource registry and manual-download guidance for the Florida
``schools`` source. Pure stdlib so the CLI can import it cheaply.

Subsources (``fetch --subsource``, repeatable; ``all`` selects every one):

* ``msid``           — FLDOE Master School ID export (folded in from the old
                       ``master_file`` source). POST to the EDS ColdFusion app.
* ``edge``           — NCES EDGE public-school geocode zip (address-geocoded
                       lat/lon + precision flag), keyed on ``NCESSCH``.
* ``ccd_directory``  — Urban Institute Education Data API, one row/school-year.
* ``ccd_enrollment`` — same API: membership, race shares, teacher FTE.
* ``crdc``           — same API: %ELL / %SWD / %gifted (biennial). Off by default.
* ``edfacts``        — same API: LEP / IDEA counts, proficiency. Off by default.

Default set = ``msid, edge, ccd_directory, ccd_enrollment``.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "schools"


def schools_paths(root: Path | None = None) -> dict[str, Path]:
    """The raw/processed/assembled dirs for ``data/florida/schools``."""
    return domain_dirs(DOMAIN, root)


# --------------------------------------------------------------------------- #
# Subsource registry                                                         #
# --------------------------------------------------------------------------- #

SUBSOURCES: tuple[str, ...] = (
    "msid",
    "edge",
    "ccd_directory",
    "ccd_enrollment",
    "crdc",
    "edfacts",
)
DEFAULT_SUBSOURCES: tuple[str, ...] = (
    "msid",
    "edge",
    "ccd_directory",
    "ccd_enrollment",
)


def resolve_subsources(selected: list[str] | None) -> list[str]:
    """Normalise a ``--subsource`` list: ``None`` -> the default set, ``[]`` ->
    nothing, ``all`` -> every subsource. Order always follows :data:`SUBSOURCES`."""
    if selected is None:
        chosen = set(DEFAULT_SUBSOURCES)
    elif not selected:
        chosen = set()
    elif "all" in selected:
        chosen = set(SUBSOURCES)
    else:
        unknown = sorted(set(selected) - set(SUBSOURCES))
        if unknown:
            raise ValueError(
                f"Unknown subsource(s) {unknown}. Choose from: {', '.join(SUBSOURCES)} (or 'all')."
            )
        chosen = set(selected)
    return [s for s in SUBSOURCES if s in chosen]


# --------------------------------------------------------------------------- #
# `msid` subsource — FLDOE Master School ID (ported from `master_file`)       #
# --------------------------------------------------------------------------- #

EDS_BASE = "https://eds.fldoe.org/EDS/MasterSchoolID"
MSID_APP_URL = f"{EDS_BASE}/"
MSID_INFO_URL = "https://www.fldoe.org/accountability/data-sys/school-dis-data/"

# short name -> (POST endpoint relative to EDS_BASE, local filename).
# `all_schools` is the panel-relevant export: ~7.2k rows incl. closed schools,
# 77 columns with DISTRICT/SCHOOL, FEDERAL_DIST_NO/FEDERAL_SCHL_NO (the NCESSCH
# crosswalk), PHYSICAL_ADDRESS, LATITUDE/LONGITUDE, DATE_OPENED/DATE_CLOSED,
# ACTIVITY_CODE and the charter/magnet/type flags.
MSID_DATASETS: dict[str, tuple[str, str]] = {
    "all_schools": ("Downloads/All_schools.cfm", "MSID_all_schools.tsv"),
    "active_schools": ("Downloads/Active_schools.cfm", "MSID_active_schools.tsv"),
    "future_schools": ("Downloads/Future_school.cfm", "MSID_future_schools.tsv"),
    "verification": ("Downloads/Verification.cfm", "MSID_verification.tsv"),
    "mailing_list": ("Downloads/Mailing_list.cfm", "MSID_mailing_list.tsv"),
}
MSID_DEFAULT_DATASET = "all_schools"

# First bytes every valid MSID export starts with (tab-separated header).
MSID_EXPECTED_PREFIX = b"DISTRICT\t"


def msid_dataset_url(dataset: str) -> str:
    try:
        endpoint, _ = MSID_DATASETS[dataset]
    except KeyError:
        raise ValueError(
            f"Unknown MSID dataset '{dataset}'. Choose from: {', '.join(MSID_DATASETS)}."
        ) from None
    return f"{EDS_BASE}/{endpoint}"


def msid_dataset_filename(dataset: str) -> str:
    return MSID_DATASETS[dataset][1]


def msid_raw_path(dataset: str, root: Path | None = None) -> Path:
    return schools_paths(root)["raw"] / msid_dataset_filename(dataset)


# --------------------------------------------------------------------------- #
# `edge` subsource — NCES EDGE public-school geocode                          #
# --------------------------------------------------------------------------- #

# Vintage tag = the two 2-digit school-year endpoints, e.g. `2425` = SY 2024-25.
EDGE_DEFAULT_VINTAGE = "2425"
EDGE_URL_TEMPLATE = (
    "https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_PUBLICSCH_{vintage}.zip"
)
_EDGE_ZIP_MAGIC = b"PK\x03\x04"


def edge_zip_filename(vintage: str) -> str:
    return f"EDGE_GEOCODE_PUBLICSCH_{vintage}.zip"


def edge_url(vintage: str) -> str:
    return EDGE_URL_TEMPLATE.format(vintage=vintage)


def edge_raw_path(vintage: str, root: Path | None = None) -> Path:
    return schools_paths(root)["raw"] / edge_zip_filename(vintage)


# --------------------------------------------------------------------------- #
# API subsources — Urban Institute Education Data Portal                      #
# --------------------------------------------------------------------------- #

URBAN_API_BASE = "https://educationdata.urban.org/api/v1"
URBAN_CSV_BASE = "https://educationdata.urban.org/csv"
FL_FIPS = 12
FL_FIPS_STR = "12"  # the value in the CSV `fips` column (no leading zero)
API_YEARS_DEFAULT = (1990, 2026)  # inclusive; per-year 404s are recorded, not fatal

# Two ways to pull each subsource:
#
# * **REST** — ``{URBAN_API_BASE}/{path}/?{params}`` paginated JSON, filtered to
#   FL server-side. Right-sized, but educationdata.urban.org's ``/api/v1/`` is
#   behind Cloudflare and 502s for hours at a time (data *and* metadata
#   endpoints), which also breaks the official R client.
# * **CSV** — the static flat files under ``{URBAN_CSV_BASE}/<class>/<file>``
#   are served from a CDN and stay up during API outages. One file may hold every
#   year and state, so the fetch streams it and keeps ``fips == 12`` in range.
#   ``csv_files`` is the known file list; when it is ``None`` the names must be
#   resolved from ``/api/v1/api-downloads/?endpoint_id=...`` (needs the API up).
#
# ``params`` disaggregators (``grade-99`` = all grades; ``race``/``sex`` = 99 =
# school-year total) are first-pass guesses for the REST route — pin them down in
# schools.ipynb (step 3) and edit this registry, not the fetch loop.
#
# CSV column findings (from schools_ccd_directory.csv, 52 cols, 1986+):
# ``ccd/directory`` already carries ``enrollment``, ``teachers_fte``,
# ``free_lunch`` / ``reduced_price_lunch`` / ``free_or_reduced_price_lunch``,
# ``title_i_status`` / ``title_i_eligible`` / ``title_i_schoolwide``, ``charter``,
# ``magnet``, ``virtual``, ``latitude`` / ``longitude``, ``lowest_grade_offered``
# / ``highest_grade_offered``, ``seasch`` (state school id), ``state_leaid``,
# ``county_code``, ``cbsa``, ``urban_centric_locale``, ``school_status`` — so it
# covers most of covariates.md Cluster A on its own. ``ccd/enrollment`` is then
# only needed for race/sex-disaggregated shares.
API_SUBSOURCES: dict[str, dict] = {
    "ccd_directory": {
        "path": "schools/ccd/directory/{year}",
        "params": {"fips": FL_FIPS},
        "csv_class": "ccd",
        "csv_files": ["schools_ccd_directory.csv"],  # all years in one file
    },
    "ccd_enrollment": {
        "path": "schools/ccd/enrollment/{year}/grade-99",
        "params": {"fips": FL_FIPS, "race": 99, "sex": 99},
        "csv_class": "ccd",
        "csv_files": None,  # resolve from api-downloads (per-year/grade files)
    },
    "crdc": {
        "path": "schools/crdc/enrollment/{year}",
        "params": {"fips": FL_FIPS, "race": 99, "sex": 99, "disability": 99, "lep": 99},
        "csv_class": "crdc",
        "csv_files": None,
    },
    "edfacts": {
        "path": "schools/edfacts/assessments/{year}/grade-99",
        "params": {"fips": FL_FIPS},
        "csv_class": "edfacts",
        "csv_files": None,
    },
}

API_QUERY_SIDECAR = "api_query.json"


def csv_file_url(subsource: str, file_name: str) -> str:
    return f"{URBAN_CSV_BASE}/{API_SUBSOURCES[subsource]['csv_class']}/{file_name}".replace(" ", "")


def api_downloads_url(endpoint_id: str | int) -> str:
    return f"{URBAN_API_BASE}/api-downloads/?endpoint_id={endpoint_id}&mode=R"


def is_api_subsource(name: str) -> bool:
    return name in API_SUBSOURCES


def api_url(subsource: str, year: int) -> str:
    """Build the first-page URL for one API subsource / year."""
    spec = API_SUBSOURCES[subsource]
    path = spec["path"].format(year=year)
    query = "&".join(f"{k}={v}" for k, v in spec["params"].items())
    return f"{URBAN_API_BASE}/{path}/?{query}"


def api_raw_path(subsource: str, year: int, root: Path | None = None) -> Path:
    return schools_paths(root)["raw"] / f"{subsource}_{year}.parquet"


def api_query_sidecar_path(root: Path | None = None) -> Path:
    return schools_paths(root)["raw"] / API_QUERY_SIDECAR


# --------------------------------------------------------------------------- #
# processed / assembled artifact names (written by `preprocess`, steps 3-4)   #
# --------------------------------------------------------------------------- #

PROCESSED_CROSS_SECTION_FILENAME = "school_cross_section.parquet"
PROCESSED_PANEL_FILENAME = "school_year_panel.parquet"
PROCESSED_METADATA_FILENAME = "schools.json"
ASSEMBLED_TREATMENT_FILENAME = "schools_treatment.parquet"


def processed_cross_section_path(root: Path | None = None) -> Path:
    return schools_paths(root)["processed"] / PROCESSED_CROSS_SECTION_FILENAME


def processed_panel_path(root: Path | None = None) -> Path:
    return schools_paths(root)["processed"] / PROCESSED_PANEL_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    return schools_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


def assembled_treatment_path(root: Path | None = None) -> Path:
    return schools_paths(root)["assembled"] / ASSEMBLED_TREATMENT_FILENAME


# --------------------------------------------------------------------------- #
# misc helpers                                                               #
# --------------------------------------------------------------------------- #

_YEAR_RANGE_RE = re.compile(r"^\s*(\d{4})\s*(?:[:.\-]{1,2})\s*(\d{4})\s*$")


def parse_year_range(text: str | tuple[int, int]) -> tuple[int, int]:
    """``"1990:2026"`` / ``"1990-2026"`` / ``"1990..2026"`` -> ``(1990, 2026)``.
    A bare 4-digit string is treated as a single-year range."""
    if isinstance(text, tuple):
        lo, hi = text
    else:
        s = str(text).strip()
        match = _YEAR_RANGE_RE.match(s)
        if match:
            lo, hi = int(match.group(1)), int(match.group(2))
        elif re.fullmatch(r"\d{4}", s):
            lo = hi = int(s)
        else:
            raise ValueError(f"Invalid year range '{text}'. Expected 'LO:HI' like '1990:2026'.")
    if lo > hi:
        raise ValueError(f"Year range start {lo} is after end {hi}.")
    if not (1980 <= lo <= 2100 and 1980 <= hi <= 2100):
        raise ValueError(f"Year range {lo}:{hi} is outside 1980-2100.")
    return lo, hi


def scan_raw(root: Path | None = None) -> dict[str, object]:
    """What is already in ``raw/``, grouped by subsource."""
    raw = schools_paths(root)["raw"]
    found: dict[str, object] = {"msid": [], "edge": [], "api": {}}
    if not raw.exists():
        return found
    for f in sorted(raw.iterdir()):
        if not f.is_file():
            continue
        name = f.name
        if name.startswith("MSID_"):
            found["msid"].append(name)  # type: ignore[union-attr]
        elif name.startswith("EDGE_GEOCODE"):
            found["edge"].append(name)  # type: ignore[union-attr]
        else:
            match = re.match(r"(ccd_directory|ccd_enrollment|crdc|edfacts)_(\d{4})\.parquet$", name)
            if match:
                found["api"].setdefault(match.group(1), []).append(int(match.group(2)))  # type: ignore[union-attr]
    for years in found["api"].values():  # type: ignore[union-attr]
        years.sort()
    return found


MANUAL_DOWNLOAD_STEPS = (
    "Automated schools fetch failed for one or more subsources. Download by hand:\n"
    "\n"
    "  msid  (FLDOE Master School ID):\n"
    "    1. Open " + MSID_APP_URL + "\n"
    "    2. Click 'Download Files', then 'Download' next to 'All Schools'\n"
    "       (leave the district menu unselected), then 'Submit'.\n"
    "    3. Save into  data/florida/schools/raw/\n"
    "    4. Re-run `... schools fetch --subsource msid --from-file <path>`.\n"
    "    For a long panel, collect one MSID issue per school year (FLDOE reissues\n"
    "    it annually; older issues on request — " + MSID_INFO_URL + ").\n"
    "\n"
    "  edge  (NCES EDGE public-school geocode):\n"
    "    1. Open https://nces.ed.gov/programs/edge/Geographic/SchoolLocations\n"
    "    2. Download 'Public Schools' for the school year you want\n"
    "       (EDGE_GEOCODE_PUBLICSCH_<vintage>.zip).\n"
    "    3. Save into  data/florida/schools/raw/  and re-run\n"
    "       `... schools fetch --subsource edge --from-file <path>`.\n"
    "\n"
    "  ccd_* / crdc / edfacts  (Urban Institute Education Data API):\n"
    "    These need network access to educationdata.urban.org. Re-run\n"
    "    `... schools fetch --subsource ccd_directory --subsource ccd_enrollment`\n"
    "    from a machine that can reach it."
)
