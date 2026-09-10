"""Paths, the results-page registry and manual-download guidance for the FLDOE
assessment-results source. Pure stdlib.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "assessments"

RESULTS_INDEX = "https://www.fldoe.org/accountability/assessments/k-12-student-assessment/results/"

# Spring-administration year -> FLDOE results page. The modern results pages
# (FSA 2015-2022, FAST / B.E.S.T. 2023-) follow the <year>.stml pattern.
FIRST_MODERN_YEAR = 2015
LATEST_KNOWN_YEAR = 2026
# No statewide spring administration (COVID) — the page exists but has no
# school-level results to collect.
NO_SPRING_TESTING = frozenset({2020})
RESULTS_PAGES = {
    year: f"{RESULTS_INDEX}{year}.stml"
    for year in range(FIRST_MODERN_YEAR, LATEST_KNOWN_YEAR + 1)
    if year not in NO_SPRING_TESTING
}

# Pre-2015 lives in the assessment archive, organised differently (not per-year
# .stml). Listed for reference only; not fetch targets yet.
ARCHIVE_PAGES = {
    "fcat_2_0 (2011-2014)": "https://www.fldoe.org/accountability/assessments/k-12-student-assessment/archive/fcat-2-0/",
    "fcat (1998-2010)": "https://www.fldoe.org/accountability/assessments/k-12-student-assessment/archive/fcat/",
    "fsa (2015-2022, retakes to 2024)": "https://www.fldoe.org/accountability/assessments/k-12-student-assessment/archive/fsa.stml",
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
    "Pre-2015 (FCAT 2.0, FCAT) lives in the assessment archive — see\n"
    "`... assessments list-years` for the archive hub URLs."
)
