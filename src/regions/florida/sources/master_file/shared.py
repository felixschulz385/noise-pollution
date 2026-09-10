"""Paths, dataset registry and manual-download fallback for the FLDOE MSID
source. Pure stdlib.

The MSID web app (https://eds.fldoe.org/EDS/MasterSchoolID/) is a ColdFusion
app whose "Download Files" page exposes each export as a POST form to a
``Downloads/<name>.cfm`` endpoint. Those endpoints accept an empty POST with no
session handshake and return a tab-delimited file (served as
``application/msexcel``, filename ``MSID_*.xls``, but the body is TSV). So the
fetch is fully automatable as long as the request carries a browser-like
User-Agent; `www.fldoe.org`'s bot wall does not apply to `eds.fldoe.org`.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "master_file"

EDS_BASE = "https://eds.fldoe.org/EDS/MasterSchoolID"
MSID_APP_URL = f"{EDS_BASE}/"
MSID_INFO_URL = "https://www.fldoe.org/accountability/data-sys/school-dis-data/"

# short name -> (POST endpoint relative to EDS_BASE, local filename)
# `all_schools` is the panel-relevant export: ~7.2k rows incl. closed schools,
# 77 columns with DISTRICT/SCHOOL, PHYSICAL_ADDRESS, LATITUDE/LONGITUDE,
# DATE_OPENED/DATE_CLOSED, CHARTER/TYPE flags. all_schools + active_schools are
# verified; the rest mirror the same CF form pattern.
DATASETS: dict[str, tuple[str, str]] = {
    "all_schools": ("Downloads/All_schools.cfm", "MSID_all_schools.tsv"),
    "active_schools": ("Downloads/Active_schools.cfm", "MSID_active_schools.tsv"),
    "future_schools": ("Downloads/Future_school.cfm", "MSID_future_schools.tsv"),
    "verification": ("Downloads/Verification.cfm", "MSID_verification.tsv"),
    "mailing_list": ("Downloads/Mailing_list.cfm", "MSID_mailing_list.tsv"),
}
DEFAULT_DATASET = "all_schools"

# First bytes every valid MSID export starts with (tab-separated header).
EXPECTED_PREFIX = b"DISTRICT\t"

DATA_SUFFIXES = (".tsv", ".xlsx", ".xls", ".csv", ".txt")


def master_file_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs(DOMAIN, root)


def dataset_url(dataset: str) -> str:
    try:
        endpoint, _ = DATASETS[dataset]
    except KeyError:
        raise ValueError(
            f"Unknown MSID dataset '{dataset}'. Choose from: {', '.join(DATASETS)}."
        ) from None
    return f"{EDS_BASE}/{endpoint}"


def dataset_filename(dataset: str) -> str:
    return DATASETS[dataset][1]


def scan_raw(root: Path | None = None) -> list[str]:
    raw = master_file_paths(root)["raw"]
    if not raw.exists():
        return []
    return sorted(
        f.name for f in raw.iterdir()
        if f.is_file() and f.suffix.lower() in DATA_SUFFIXES
    )


MANUAL_DOWNLOAD_STEPS = (
    "Automated MSID fetch failed. Download by hand instead:\n"
    "  1. Open " + MSID_APP_URL + "\n"
    "  2. Click 'Download Files', then 'Download' next to 'All Schools'\n"
    "     (leave the district menu unselected), then 'Submit'.\n"
    "  3. Save the file into  data/florida/master_file/raw/\n"
    "  4. Re-run `... master-file fetch --from-file <path>` to register it.\n"
    "\n"
    "For a long panel, collect one MSID issue per school year (FLDOE reissues it\n"
    "annually; older issues on request — background: " + MSID_INFO_URL + ")."
)
