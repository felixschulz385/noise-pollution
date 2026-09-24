"""Download Skolkoll's `schools.csv` (see `shared.py`'s module docstring).
One flat file, no pagination, no authentication -- confirmed live
2026-09-23 (~3.3MB, ~21.8k rows). Rebuilt daily on their end, so a fresh
fetch may return a newer `# Version:` than the one this repo last saved;
`preprocess.py` reads that line back out rather than tracking it
separately.
"""
from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.regions.sweden.sources.skolkoll.shared import SCHOOLS_CSV_URL, raw_schools_csv_path

USER_AGENT = "noise-pollution-research/1.0"


def _get_bytes(url: str, *, timeout: int = 120) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def fetch_schools_csv(root: Path | None = None) -> dict:
    payload = _get_bytes(SCHOOLS_CSV_URL)
    path = raw_schools_csv_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"url": SCHOOLS_CSV_URL, "bytes": len(payload), "saved": str(path)}
