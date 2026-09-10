"""Download step for the Florida noise-barrier source.

``list_versions()``  -> which FGDL releases exist (archive index scrape).
``fetch_noise_barriers(version)``  -> download one release's zip into
``data/florida/noise_barriers/raw/``, extract the ``.gdb``, pull the companion
metadata XML, and (by default) delete the zip.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from src.regions.florida.sources.noise_barriers.shared import (
    ARCHIVE_INDEX_URL,
    CURRENT_INDEX_URL,
    DEFAULT_VERSION,
    archive_zip_url,
    dataset_stem,
    metadata_xml_url,
    noise_barrier_paths,
    parse_index_versions,
    raw_gdb_path,
    raw_metadata_path,
    raw_zip_path,
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


def _find_gdb_prefix(members: list[str]) -> str:
    """Locate the ``*.gdb/`` path component in a zip's member list. FGDL has
    shipped it both at the archive root (``noise_barriers_apr23.gdb/...``) and
    one folder down (``noise_barriers_jul26/noise_barriers_jul26.gdb/...``)."""
    prefixes = set()
    for member in members:
        parts = member.split("/")
        for i, part in enumerate(parts[:-1]):
            if part.lower().endswith(".gdb"):
                prefixes.add("/".join(parts[: i + 1]) + "/")
                break
    if len(prefixes) == 1:
        return prefixes.pop()
    if not prefixes:
        raise RuntimeError(
            "no '*.gdb/' geodatabase found in the archive; top-level entries: "
            f"{sorted({m.split('/', 1)[0] for m in members})}"
        )
    raise RuntimeError(f"archive contains multiple geodatabases: {sorted(prefixes)}")


def _extract_gdb(zip_path: Path, raw_dir: Path, version: str) -> Path:
    stem = dataset_stem(version)
    target = raw_dir / f"{stem}.gdb"
    if target.exists():
        shutil.rmtree(target)

    with ZipFile(zip_path) as archive:
        members = [m for m in archive.namelist() if not m.endswith("/")]
        prefix = _find_gdb_prefix(members)
        for member in members:
            if not member.startswith(prefix):
                continue
            rel = member[len(prefix):]
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return target


def fetch_noise_barriers(
    version: str | None = None,
    *,
    keep_zip: bool = False,
    with_metadata: bool = True,
) -> dict[str, object]:
    resolved = validate_version(version or DEFAULT_VERSION)
    paths = noise_barrier_paths()
    raw_dir = paths["raw"]

    zip_path = raw_zip_path(resolved)
    _download_to_file(archive_zip_url(resolved), zip_path)
    gdb_path = _extract_gdb(zip_path, raw_dir, resolved)

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

    gdb_files = sum(1 for _ in gdb_path.rglob("*") if _.is_file())
    return {
        "version": resolved,
        "source_url": archive_zip_url(resolved),
        "zip_bytes": zip_bytes,
        "zip_kept": zip_result,
        "gdb_path": str(gdb_path),
        "gdb_file_count": gdb_files,
        "metadata_path": metadata_result,
    }
