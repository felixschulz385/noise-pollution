"""Fetch step for the FLDOE MSID source.

Real automated download: POST an empty body to the ColdFusion
``Downloads/<name>.cfm`` endpoint (browser User-Agent required) and write the
tab-delimited response into ``data/florida/master_file/raw/``. `--from-file`
imports a file you downloaded by hand; `--file-url` tries an arbitrary URL.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.regions.florida.sources._http import download_to_file
from src.regions.florida.sources.master_file.shared import (
    DEFAULT_DATASET,
    EXPECTED_PREFIX,
    MANUAL_DOWNLOAD_STEPS,
    MSID_APP_URL,
    dataset_filename,
    dataset_url,
    master_file_paths,
    scan_raw,
)

# eds.fldoe.org returns 403/500 to the default urllib UA; a browser UA is enough
# (unlike www.fldoe.org, there is no JS bot wall here).
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _sanitize(name: str) -> str:
    cleaned = name.strip().replace("/", "_").replace("\\", "_")
    return cleaned or "msid_download.bin"


def _post_download(url: str, *, timeout: int = 120) -> bytes:
    request = Request(
        url,
        data=b"",  # empty body -> POST
        method="POST",
        headers={
            "User-Agent": _BROWSER_UA,
            "Accept": "*/*",
            "Referer": MSID_APP_URL + "Downloads.cfm",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc

    if not body.startswith(EXPECTED_PREFIX):
        raise RuntimeError(
            f"{url} did not return an MSID export "
            f"(got {len(body)} bytes starting {body[:40]!r})"
        )
    return body


def fetch_master_file(
    datasets: list[str] | None = None,
    *,
    from_files: list[str] | None = None,
    file_url: str | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    raw_dir = master_file_paths(root)["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    imported: list[str] = []
    errors: list[str] = []

    for src in from_files or []:
        src_path = Path(src).expanduser()
        if not src_path.is_file():
            errors.append(f"--from-file not found: {src_path}")
            continue
        dest = raw_dir / _sanitize(src_path.name)
        shutil.copy2(src_path, dest)
        imported.append(str(dest))

    if file_url:
        dest = raw_dir / _sanitize(file_url.split("?")[0].split("/")[-1] or "msid_download.bin")
        try:
            download_to_file(file_url, dest)
            results.append({"source": "file_url", "url": file_url, "path": str(dest),
                            "bytes": dest.stat().st_size})
        except RuntimeError as exc:
            errors.append(str(exc))

    if not from_files and not file_url:
        for dataset in datasets or [DEFAULT_DATASET]:
            url = dataset_url(dataset)  # raises ValueError on unknown name
            dest = raw_dir / dataset_filename(dataset)
            try:
                body = _post_download(url)
                dest.write_bytes(body)
                results.append({"dataset": dataset, "url": url, "path": str(dest),
                                "bytes": len(body)})
            except RuntimeError as exc:
                errors.append(f"{dataset}: {exc}")

    out: dict[str, object] = {
        "app_url": MSID_APP_URL,
        "raw_dir": str(raw_dir),
        "downloaded": results,
        "imported": imported,
        "errors": errors,
        "files": scan_raw(root),
    }
    out["state"] = "present" if out["files"] else "missing"
    if errors and not results and not imported:
        out["instructions"] = MANUAL_DOWNLOAD_STEPS
    return out
