"""Minimal stdlib HTTP download helper shared by Florida sources.

Kept separate from any one domain so `assessments` and `schools` can both
use it without importing each other.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "noise-pollution-research/1.0"


def download_to_file(url: str, destination: Path, *, timeout: int = 300) -> Path:
    """GET `url`, stream the body to `destination`. Raises RuntimeError on any
    HTTP or transport error (callers decide whether that is fatal)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    return destination
