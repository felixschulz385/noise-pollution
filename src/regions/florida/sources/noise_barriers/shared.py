"""Paths, version tags and archive-layout helpers for the Florida noise-barrier
source. Pure stdlib so the CLI can import it cheaply.

FGDL distributes each release as ``noise_barriers_<mon><yy>.zip`` (e.g.
``noise_barriers_apr23.zip``), containing a single Esri File Geodatabase
``noise_barriers_<mon><yy>.gdb/``. Releases are irregular, so the set of
versions can only be discovered by listing the archive index (see
``fetch.list_versions``); there is no computable "latest".
"""
from __future__ import annotations

import re
from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "noise_barriers"
DATASET_PREFIX = "noise_barriers"

# The release the exploratory notebook is built against. This is the one place
# the default lives; the CLI reads it from here.
DEFAULT_VERSION = "jul26"

FGDL_ZIPS_BASE = "https://fgdl.org/zips"
ARCHIVE_INDEX_URL = f"{FGDL_ZIPS_BASE}/geospatial_data/archive/"
CURRENT_INDEX_URL = f"{FGDL_ZIPS_BASE}/geospatial_data/current/"
METADATA_XML_DIR = f"{FGDL_ZIPS_BASE}/metadata/xml"

_VERSION_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(\d{2})$")
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def noise_barrier_paths(root: Path | None = None) -> dict[str, Path]:
    """The raw/processed/assembled dirs for ``data/florida/noise_barriers``."""
    return domain_dirs(DOMAIN, root)


def validate_version(version: str) -> str:
    """Normalise and check an FGDL version tag such as ``apr23``."""
    normalized = version.strip().lower()
    if not _VERSION_RE.match(normalized):
        raise ValueError(
            f"Invalid FGDL version tag '{version}'. Expected '<mon><yy>' like 'apr23'."
        )
    return normalized


def version_sort_key(version: str) -> tuple[int, int]:
    """Chronological key for a version tag; 2-digit year read as 20YY."""
    match = _VERSION_RE.match(version.strip().lower())
    if not match:
        return (-1, -1)
    month, year = match.group(1), int(match.group(2))
    return (2000 + year, _MONTHS.index(month) + 1)


def dataset_stem(version: str) -> str:
    return f"{DATASET_PREFIX}_{validate_version(version)}"


def archive_zip_url(version: str) -> str:
    """The archive holds every release, including the most recent one."""
    return f"{ARCHIVE_INDEX_URL}{dataset_stem(version)}.zip"


def metadata_xml_url(version: str) -> str:
    return f"{METADATA_XML_DIR}/{dataset_stem(version)}.xml"


def raw_zip_path(version: str, root: Path | None = None) -> Path:
    return noise_barrier_paths(root)["raw"] / f"{dataset_stem(version)}.zip"


def raw_gdb_path(version: str, root: Path | None = None) -> Path:
    return noise_barrier_paths(root)["raw"] / f"{dataset_stem(version)}.gdb"


def raw_metadata_path(version: str, root: Path | None = None) -> Path:
    return noise_barrier_paths(root)["raw"] / f"{dataset_stem(version)}.xml"


def parse_index_versions(index_html: str) -> list[str]:
    """Pull ``noise_barriers_<mon><yy>`` tags out of an FGDL autoindex page,
    newest first, de-duplicated."""
    tags = set(re.findall(rf'href="{DATASET_PREFIX}_([a-z]{{3}}\d{{2}})\.zip"', index_html))
    valid = [t for t in tags if _VERSION_RE.match(t)]
    return sorted(valid, key=version_sort_key, reverse=True)
