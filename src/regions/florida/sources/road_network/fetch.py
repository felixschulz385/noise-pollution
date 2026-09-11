"""Download step for the Florida road-network source.

``list_versions()``  -> which FGDL ``rciroads`` releases exist (archive index
scrape).
``fetch_road_network(version)``  -> download one release's zip into
``data/florida/road_network/raw/``, extract its shapefile parts, pull the
companion metadata XML, and (by default) delete the zip.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from src.regions.florida.sources.road_network.shared import (
    ARCHIVE_INDEX_URL,
    CURRENT_INDEX_URL,
    DEFAULT_VERSION,
    archive_zip_url,
    dataset_stem,
    metadata_xml_url,
    parse_index_versions,
    raw_metadata_path,
    raw_zip_path,
    road_network_paths,
    validate_version,
)

_USER_AGENT = "noise-pollution-research/1.0 (+https://fgdl.org)"


def _http_get_bytes(url: str, *, timeout: int = 180) -> bytes:
    request = Request(url, headers={"User-Agent": _USER_AGENT}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def _download_to_file(url: str, destination: Path, *, timeout: int = 300) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": _USER_AGENT}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    return destination


def list_versions() -> dict[str, object]:
    archive = parse_index_versions(_http_get_bytes(ARCHIVE_INDEX_URL).decode("utf-8", "replace"))
    current = parse_index_versions(_http_get_bytes(CURRENT_INDEX_URL).decode("utf-8", "replace"))
    return {
        "archive_index": ARCHIVE_INDEX_URL,
        "default": DEFAULT_VERSION,
        "current": current[0] if current else None,
        "count": len(archive),
        "versions": archive,
    }


def _find_shapefile_members(members: list[str], stem: str) -> list[str]:
    """Pick the archive members that make up one release's shapefile
    (``<stem>.shp`` + its ``.dbf``/``.shx``/``.prj``/etc sidecars), by
    basename regardless of folder nesting the zip might use (confirmed flat
    at the archive root for ``jul26`` and ``jun04``, but not exhaustively
    checked across all 57 releases)."""
    matches = [m for m in members if Path(m).name.lower().startswith(f"{stem.lower()}.")]
    if not matches:
        raise RuntimeError(
            f"no '{stem}.*' shapefile parts found in the archive; top-level entries: "
            f"{sorted({m.split('/', 1)[0] for m in members})}"
        )
    return matches


def _extract_shapefile(zip_path: Path, raw_dir: Path, version: str) -> Path:
    """Extract one release's shapefile parts into ``raw_dir/<stem>/``."""
    stem = dataset_stem(version)
    target_dir = raw_dir / stem
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(zip_path) as archive:
        members = [m for m in archive.namelist() if not m.endswith("/")]
        matches = _find_shapefile_members(members, stem)
        for member in matches:
            out = target_dir / Path(member).name
            with archive.open(member) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    shp_path = target_dir / f"{stem}.shp"
    if not shp_path.exists():
        raise RuntimeError(
            f"archive had no '{stem}.shp' despite matching parts: "
            f"{sorted(p.name for p in target_dir.iterdir())}"
        )
    return shp_path


def fetch_road_network(
    version: str | None = None,
    *,
    keep_zip: bool = False,
    with_metadata: bool = True,
) -> dict[str, object]:
    resolved = validate_version(version or DEFAULT_VERSION)
    paths = road_network_paths()
    raw_dir = paths["raw"]

    zip_path = raw_zip_path(resolved)
    _download_to_file(archive_zip_url(resolved), zip_path)
    shp_path = _extract_shapefile(zip_path, raw_dir, resolved)

    zip_bytes = zip_path.stat().st_size
    if keep_zip:
        zip_result: str | None = str(zip_path)
    else:
        zip_path.unlink()
        zip_result = None

    metadata_result: str | None = None
    if with_metadata:
        try:
            meta_path = raw_metadata_path(resolved)
            meta_path.write_bytes(_http_get_bytes(metadata_xml_url(resolved)))
            metadata_result = str(meta_path)
        except RuntimeError as exc:  # metadata is a nice-to-have, not fatal
            metadata_result = f"unavailable: {exc}"

    shapefile_parts = sum(1 for _ in shp_path.parent.glob("*") if _.is_file())
    return {
        "version": resolved,
        "source_url": archive_zip_url(resolved),
        "zip_bytes": zip_bytes,
        "zip_kept": zip_result,
        "shapefile_path": str(shp_path),
        "shapefile_part_count": shapefile_parts,
        "metadata_path": metadata_result,
    }
