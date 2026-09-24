"""Paths and the per-source file/URL registries for the Florida `staff`
source. Pure stdlib (no pandas import — `fetch.py` needs this module without
paying for a pandas import in the common "just check what's cached" path).

**Two of three sub-sources are per-year FLDOE workbooks with irregular
filenames** — confirmed live 2026-09 by reading the Wayback Machine's own
capture of `.../pk-12-public-school-data-pubs-reports/archive.stml` (the
current `staff.stml` page only lists the newest 1-2 years; `archive.stml`
carries the full back-catalogue). Every filename below is a real link found
on that page, not a guessed pattern — FLDOE did not settle on one consistent
naming scheme (`1314teachsalarydata.xls` vs `2014-15-Teacher-Salaries-
Survey-3-Web.xls` vs `1516TeachersSalariesSurvey.xls` vs the modern
`<yy><yy+1>TeacherSalaryData.xlsx`; `IFOFTeach` with one `F` for 2014-15/
2015-16, `IFOFFTeach` with two from 2016-17 on), which is exactly why this
is a hand-typed registry rather than a derived pattern like
`assessments.shared.RESULTS_PAGES`. Two representative years (2024-25) were
downloaded via `_http.wayback_download` and parsed during this module's own
development to confirm the schema (see `docs/data/florida/staff/README.md`);
the rest are structurally verified (real links, real filenames) but not
individually re-downloaded in that same pass — a live `Internet Archive:
Temporarily Offline` outage interrupted broader verification, itself
evidence this dependency needs a retry, not just a single attempt.

**FLDOE's `DISTRICT #`/`SCHOOL #` numbering in both workbooks matches
`schools`' own `district`/`school` fields exactly, with NO crosswalk
needed** — confirmed empirically: district `01` = ALACHUA in both, and
school `01`/`0022` = "EARLY LEARNING ACADEMY AT DUVAL" in both the
`IFOFFTeach` workbook and `school_cross_section.parquet` (`msid =
district.zfill(2) + school.zfill(4)`, identical to `schools/preprocess.py`'s
`compose_ncessch`).

**Assessment-year convention**: FLDOE labels a workbook by its two-digit
school-year span (`"2425"` = 2024-25); this registry keys directly by the
*assessment year* (the spring half — `2425` -> `2025`), matching every other
Florida source's spring-year convention.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "staff"

FLDOE_ARCHIVE_BASE = "https://www.fldoe.org/core/fileparse.php/7584/urlt"
FLDOE_CURRENT_BASE = "https://www.fldoe.org/file/7584"

# assessment_year -> the "Average Salaries for Teachers" workbook (3 sheets:
# `Teachers` [avg salary / # employed / employment length], `Average Yrs
# Experience`, `Median Salary`), district-level (`DISTRICT #` 0-67, 0 =
# state total).
TEACHER_SALARY_FILES: dict[int, str] = {
    2014: f"{FLDOE_ARCHIVE_BASE}/1314teachsalarydata.xls",
    2015: f"{FLDOE_ARCHIVE_BASE}/2014-15-Teacher-Salaries-Survey-3-Web.xls",
    2016: f"{FLDOE_ARCHIVE_BASE}/1516TeachersSalariesSurvey.xls",
    2017: f"{FLDOE_ARCHIVE_BASE}/1617TeacherSalaryData.xls",
    2018: f"{FLDOE_ARCHIVE_BASE}/1718TeacherSalaryData.xls",
    2019: f"{FLDOE_ARCHIVE_BASE}/1819TeacherSalaryData.xlsx",
    2020: f"{FLDOE_ARCHIVE_BASE}/1920TeacherSalaryData.xlsx",
    2021: f"{FLDOE_ARCHIVE_BASE}/2021TeacherSalaryData.xlsx",
    2022: f"{FLDOE_ARCHIVE_BASE}/2122TeacherSalaryData.xlsx",
    2023: f"{FLDOE_ARCHIVE_BASE}/2223TeacherSalaryData.xlsx",
    2024: f"{FLDOE_ARCHIVE_BASE}/2324TeacherSalaryData.xlsx",
    2025: f"{FLDOE_CURRENT_BASE}/2425TeacherSalaryData.xlsx",
    2026: f"{FLDOE_CURRENT_BASE}/2526TeacherSalaryData.xlsx",
}

# assessment_year -> the "Total Number and Percent of Classes Taught by
# In-Field or Out-of-Field Teachers" workbook, SCHOOL-level (`District #` +
# `School #` + a `"DISTRICT TOTALS"` row per district, `"STATE TOTALS"` row
# for district 0).
OUT_OF_FIELD_FILES: dict[int, str] = {
    2015: f"{FLDOE_ARCHIVE_BASE}/IFOFTeach1415.xls",
    2016: f"{FLDOE_ARCHIVE_BASE}/IFOFTeach1516.xls",
    2017: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach1617.xls",
    2018: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach1718.xls",
    2019: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach1819.xlsx",
    2020: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach1920.xlsx",
    2021: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach2021.xlsx",
    2022: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach2122.xlsx",
    2023: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach2223.xlsx",
    2024: f"{FLDOE_ARCHIVE_BASE}/IFOFFTeach2324.xlsx",
    2025: f"{FLDOE_CURRENT_BASE}/IFOFFTeach2425.xlsx",
    2026: f"{FLDOE_CURRENT_BASE}/IFOFFTeach2526.xlsx",
}

# NCES CCD F-33 local-education-agency finance survey via the Urban
# Institute Education Data API (same no-auth API `schools` already uses for
# CCD/CRDC/EDFacts). Confirmed live 2026-09: FL (`fips=12`) has real,
# non-trivial data 1995-2020 (`count` 67-78 per year); 2021/2022 return
# `count: 0` (not yet ingested by Urban as of this check).
#
# **No `+1` offset here, unlike `schools`' CCD directory/enrollment/CRDC
# pulls.** Those surveys are fall-semester snapshots (Urban's own CRDC
# codebook: "Academic year (fall semester)"), so `year + 1` = the following
# spring/assessment year. F-33 finance data uses NCES's *fiscal-year*
# label instead, which is already the ending/spring calendar year --
# confirmed via NCES's own F-33 page (`nces.ed.gov/ccd/f33agency.asp`),
# which pairs `"2017-18" (Fiscal Year 2018)"`. So `assessment_year ==
# ccd_finance_year` directly.
CCD_FINANCE_BASE = "https://educationdata.urban.org/api/v1/school-districts/ccd/finance"
CCD_FINANCE_FIRST_YEAR = 1995
CCD_FINANCE_LAST_YEAR = 2020
FIPS_FLORIDA = 12


def ccd_finance_url(year: int) -> str:
    return f"{CCD_FINANCE_BASE}/{year}/?fips={FIPS_FLORIDA}"


def staff_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


def raw_teacher_salary_path(year: int, root: Path | None = None) -> Path:
    suffix = Path(TEACHER_SALARY_FILES[year]).suffix or ".xls"
    return staff_paths(root)["raw"] / "teacher_salary" / f"{year}{suffix}"


def raw_out_of_field_path(year: int, root: Path | None = None) -> Path:
    suffix = Path(OUT_OF_FIELD_FILES[year]).suffix or ".xls"
    return staff_paths(root)["raw"] / "out_of_field" / f"{year}{suffix}"


def raw_district_finance_path(year: int, root: Path | None = None) -> Path:
    return staff_paths(root)["raw"] / "district_finance" / f"{year}.parquet"


PROCESSED_TEACHER_SALARY_FILENAME = "teacher_salary.parquet"
PROCESSED_OUT_OF_FIELD_FILENAME = "out_of_field.parquet"
PROCESSED_DISTRICT_FINANCE_FILENAME = "district_finance.parquet"
PROCESSED_METADATA_FILENAME = "staff.json"


def processed_teacher_salary_path(root: Path | None = None) -> Path:
    return staff_paths(root)["processed"] / PROCESSED_TEACHER_SALARY_FILENAME


def processed_out_of_field_path(root: Path | None = None) -> Path:
    return staff_paths(root)["processed"] / PROCESSED_OUT_OF_FIELD_FILENAME


def processed_district_finance_path(root: Path | None = None) -> Path:
    return staff_paths(root)["processed"] / PROCESSED_DISTRICT_FINANCE_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    return staff_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


ASSEMBLED_DISTRICT_YEAR_FILENAME = "district_staff_panel.parquet"
ASSEMBLED_SCHOOL_YEAR_FILENAME = "school_staff_panel.parquet"


def district_staff_panel_path(root: Path | None = None) -> Path:
    """District x assessment-year panel (salary/experience + per-pupil
    expenditure) — one row per `(district, year)`, `panel/assemble.py`
    broadcasts it to every school in that district, same shape as `shocks`'
    county-year broadcast."""
    return staff_paths(root)["assembled"] / ASSEMBLED_DISTRICT_YEAR_FILENAME


def school_staff_panel_path(root: Path | None = None) -> Path:
    """School x assessment-year panel (in-field/out-of-field) — already at
    the `(msid, year)` grain `panel/assemble.py` needs, no broadcast."""
    return staff_paths(root)["assembled"] / ASSEMBLED_SCHOOL_YEAR_FILENAME
