"""Paths, version tags and archive-layout helpers for the Florida road-network
source. Pure stdlib so the CLI can import it cheaply.

FGDL distributes each release as ``rciroads_<mon><yy>.zip`` (e.g.
``rciroads_jul26.zip``), containing a single **Esri Shapefile**
(``rciroads_<mon><yy>.shp`` + its ``.dbf``/``.shx``/``.prj``/``.sbn``/``.sbx``/
``.cpg``/``.shp.xml`` sidecars) — confirmed both for the current release
(``jul26``) and the oldest archived one (``jun04``), so this is not the zipped
File Geodatabase ``noise_barriers`` ships (the road-network README's Open
Question 1 assumed a ``.gdb``; it isn't one). Same publisher and archive
layout otherwise — releases are irregular, so the set of versions can only be
discovered by listing the archive index (see ``fetch.list_versions``); there
is no computable "latest". The ``.prj`` confirms EPSG:3087 (NAD83(HARN)
Florida GDL Albers), the same CRS ``noise_barriers`` uses.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.regions.florida.sources._layout import domain_dirs

DOMAIN = "road_network"
DATASET_PREFIX = "rciroads"

# Version-matched to the noise_barriers snapshot already fetched, so the two
# layers describe the same point in time.
DEFAULT_VERSION = "jul26"

FGDL_ZIPS_BASE = "https://fgdl.org/zips"
ARCHIVE_INDEX_URL = f"{FGDL_ZIPS_BASE}/geospatial_data/archive/"
CURRENT_INDEX_URL = f"{FGDL_ZIPS_BASE}/geospatial_data/current/"
METADATA_XML_DIR = f"{FGDL_ZIPS_BASE}/metadata/xml"

_VERSION_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(\d{2})$")
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def road_network_paths(root: Path | None = None) -> dict[str, Path]:
    """The raw/processed/assembled dirs for ``data/florida/road_network``."""
    return domain_dirs(DOMAIN, root)


# `preprocess` collapses whichever FGDL release into these two version-agnostic
# artifacts (the release tag is recorded inside the sidecar, not in the name) —
# same convention as `noise_barriers`' `barriers.parquet` / `barriers.json`.
PROCESSED_ROAD_NETWORK_FILENAME = "road_network.parquet"
PROCESSED_METADATA_FILENAME = "road_network.json"


def processed_road_network_path(root: Path | None = None) -> Path:
    """The tidy GeoParquet roadway-segment layer written by ``preprocess``."""
    return road_network_paths(root)["processed"] / PROCESSED_ROAD_NETWORK_FILENAME


def processed_metadata_path(root: Path | None = None) -> Path:
    """The JSON provenance sidecar written next to the road-network layer."""
    return road_network_paths(root)["processed"] / PROCESSED_METADATA_FILENAME


def validate_version(version: str) -> str:
    """Normalise and check an FGDL version tag such as ``jul26``."""
    normalized = version.strip().lower()
    if not _VERSION_RE.match(normalized):
        raise ValueError(
            f"Invalid FGDL version tag '{version}'. Expected '<mon><yy>' like 'jul26'."
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
    return road_network_paths(root)["raw"] / f"{dataset_stem(version)}.zip"


def raw_shapefile_dir(version: str, root: Path | None = None) -> Path:
    """The directory holding one release's extracted shapefile parts."""
    return road_network_paths(root)["raw"] / dataset_stem(version)


def raw_shapefile_path(version: str, root: Path | None = None) -> Path:
    """The extracted ``.shp`` itself (its sibling ``.dbf``/``.shx``/``.prj``
    etc. live alongside it in the same directory)."""
    stem = dataset_stem(version)
    return raw_shapefile_dir(version, root) / f"{stem}.shp"


def raw_metadata_path(version: str, root: Path | None = None) -> Path:
    return road_network_paths(root)["raw"] / f"{dataset_stem(version)}.xml"


def parse_index_versions(index_html: str) -> list[str]:
    """Pull ``rciroads_<mon><yy>`` tags out of an FGDL autoindex page, newest
    first, de-duplicated."""
    tags = set(re.findall(rf'href="{DATASET_PREFIX}_([a-z]{{3}}\d{{2}})\.zip"', index_html))
    valid = [t for t in tags if _VERSION_RE.match(t)]
    return sorted(valid, key=version_sort_key, reverse=True)
