"""Paths, the results-page registry and manual-download guidance for the FLDOE
assessment-results source. Pure stdlib.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "assessments"

RESULTS_INDEX = "https://www.fldoe.org/accountability/assessments/k-12-student-assessment/results/"

# Spring-administration year -> FLDOE results page. Confirmed (2026-09) that the
# <year>.stml pattern is NOT FSA/FAST-specific — it extends back at least to 2011
# (FCAT 2.0 era: results/2011.stml ... results/2014.stml resolve the same way as
# the modern pages). FIRST_MODERN_YEAR therefore marks the start of the per-year
# .stml registry, not a regime boundary — regime labeling lives in preprocess.py.
FIRST_MODERN_YEAR = 2011
LATEST_KNOWN_YEAR = 2026
# No statewide spring administration (COVID) — the page exists but has no
# school-level results to collect.
NO_SPRING_TESTING = frozenset({2020})
RESULTS_PAGES = {
    year: f"{RESULTS_INDEX}{year}.stml"
    for year in range(FIRST_MODERN_YEAR, LATEST_KNOWN_YEAR + 1)
    if year not in NO_SPRING_TESTING
}

# Not every EOC subject existed for the full 2011-2014 span — FLDOE phased in
# EOCs year by year (source: FLDOE EOC program history). `fetch`'s per-year
# instructions should not expect files that didn't exist yet.
EOC_FIRST_YEAR = {"ALG1": 2011, "GEO": 2012, "BIO1": 2012, "USHIST": 2013, "CIVICS": 2014}

# 1998-2010 (plain FCAT) is NOT yet confirmed to follow the same <year>.stml
# pattern — unlike FCAT 2.0, it predates verification. Listed for reference
# only; not a fetch target yet.
ARCHIVE_PAGES = {
    "fcat (1998-2010)": "https://www.fldoe.org/accountability/assessments/k-12-student-assessment/archive/fcat/",
}

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def assessments_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


# `preprocess` collapses every raw workbook into one tidy table (indexed on
# school x grade x subject x year) plus a JSON provenance sidecar.
PROCESSED_ASSESSMENTS_FILENAME = "assessments.parquet"
PROCESSED_METADATA_FILENAME = "assessments.json"


def processed_assessments_path(root: Path | None = None) -> Path:
    """The tidy merged assessment table written by ``preprocess``."""
    return assessments_paths(root)["processed"] / PROCESSED_ASSESSMENTS_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    """The JSON provenance sidecar written next to the assessment table."""
    return assessments_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


def validate_year(year: int | str) -> int:
    text = str(year).strip()
    if not _YEAR_RE.match(text):
        raise ValueError(f"Invalid assessment year '{year}'. Expected a 4-digit year, e.g. 2024.")
    return int(text)


def year_raw_dir(year: int | str, root: Path | None = None) -> Path:
    """`data/florida/assessments/raw/<year>/` — one folder per spring
    administration year (each holds one or more subject/grade workbooks)."""
    return assessments_paths(root)["raw"] / str(validate_year(year))


def scan_raw(root: Path | None = None) -> dict[int, list[str]]:
    """Map each year folder under raw/ to the file names it contains."""
    raw = assessments_paths(root)["raw"]
    found: dict[int, list[str]] = {}
    for child in sorted(raw.iterdir()) if raw.exists() else []:
        if child.is_dir() and _YEAR_RE.match(child.name):
            files = sorted(f.name for f in child.iterdir() if f.is_file())
            found[int(child.name)] = files
    return found


MANUAL_DOWNLOAD_STEPS = (
    "FLDOE assessment-result workbooks are downloaded by hand: www.fldoe.org "
    "blocks automated clients (HTTP 403 / bot protection).\n"
    "\n"
    "For each spring-administration year:\n"
    "  1. Open the results page (run `... assessments list-years` for URLs), e.g.\n"
    "     " + RESULTS_INDEX + "2024.stml\n"
    "  2. Under the 'State Report of Schools' headings, download the school-level\n"
    "     Excel workbook(s) you need (FAST / FSA ELA, Mathematics, Science,\n"
    "     B.E.S.T. EOC).\n"
    "  3. Save them into  data/florida/assessments/raw/<year>/  (one folder per\n"
    "     spring year).\n"
    "  4. Re-run `... assessments fetch` (optionally with --from-file) to import\n"
    "     and verify what is present.\n"
    "\n"
    "2011-2014 (FCAT 2.0) uses the same results/<year>.stml pages — FLDOE just\n"
    "labels the ELA-equivalent test 'Reading', not 'ELA'; rename it to the\n"
    "canonical FL<year>_ELA_G<NN>_school.xls on import like every other year.\n"
    "Not every EOC existed yet: Algebra 1 from 2011, Geometry/Biology 1 from\n"
    "2012, U.S. History from 2013, Civics from 2014 — don't expect files for an\n"
    "EOC before its first year.\n"
    "\n"
    "Pre-2011 (FCAT) lives in a differently-organised archive, not yet fetch-\n"
    "ready — see `... assessments list-years` for the archive hub URL."
)
