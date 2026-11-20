"""Minimal stdlib HTTP helpers shared by Florida sources.

Kept separate from any one domain so `assessments`, `schools`, and
`road_projects` can all use it without importing each other.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

USER_AGENT = "noise-pollution-research/1.0"

# 429/5xx are worth retrying (rate limiting, transient upstream trouble);
# anything else (404, 400, ...) is a real error a retry won't fix.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"


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


def get_json(
    url: str,
    *,
    user_agent: str = USER_AGENT,
    timeout: int = 120,
    attempts: int = 4,
    retry_status: frozenset[int] = RETRY_STATUS,
    not_found_exc: type[Exception] | None = None,
) -> dict:
    """GET JSON, retrying transient upstream failures (`retry_status` / a
    transport error) with exponential backoff. Was duplicated near-verbatim
    in `schools/fetch.py` and `road_projects/fetch.py` (two different
    upstreams, same retry shape) before being pulled here.

    `not_found_exc`, if given, is raised (instead of the default
    `RuntimeError`) on an HTTP 404 -- lets a caller distinguish "this
    specific query has no data" (expected, often recoverable by skipping)
    from a real failure, without every caller re-implementing that check."""
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"}, method="GET")
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
            return json.loads(payload)
        except HTTPError as exc:
            if exc.code == 404 and not_found_exc is not None:
                raise not_found_exc(url) from exc
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            last_error = f"HTTP {exc.code} for {url}: {detail}"
            if exc.code not in retry_status:
                raise RuntimeError(last_error) from exc
        except URLError as exc:
            last_error = f"Request failed for {url}: {exc}"
        except ValueError as exc:
            last_error = f"{url} did not return JSON: {exc}"
        if attempt < attempts:
            time.sleep(min(2**attempt, 15))
    raise RuntimeError(f"{last_error}  (gave up after {attempts} attempts)")


class WaybackNotArchivedError(RuntimeError):
    """No Internet Archive snapshot exists for the requested URL."""


def wayback_download(
    original_url: str,
    destination: Path,
    *,
    timeout: int = 300,
    attempts: int = 4,
) -> Path:
    """Download `original_url` via its most recent Internet Archive snapshot.

    Several `fldoe.org` file downloads are blocked outright for scripted
    clients (Akamai bot protection, confirmed live 2026-09: every direct
    `curl`/`WebFetch` attempt against `www.fldoe.org/file/...` and
    `www.fldoe.org/core/fileparse.php/...` returns HTTP 403, matching
    `assessments/fetch.py`'s long-documented "no unattended fetch" finding)
    -- but the Wayback Machine has independently crawled and archived many of
    these exact files, and `web.archive.org` itself has no such block.
    Confirmed live 2026-09 for `staff`'s FLDOE workbooks: the CDX index
    (`WAYBACK_CDX_URL`) resolves a capture timestamp, then
    `web.archive.org/web/<timestamp>id_/<url>` serves the raw archived bytes
    (the `id_` modifier suppresses Wayback's toolbar/rewrite wrapper).

    Raises :class:`WaybackNotArchivedError` if the CDX index has no capture
    at all (a real "this file was never archived" outcome, distinct from a
    transient failure) and ``RuntimeError`` on a retryable/transport failure
    (the Internet Archive has real, if infrequent, full-service outages --
    observed directly during this module's own development)."""
    query = f"{WAYBACK_CDX_URL}?url={quote(original_url, safe='')}&output=json&filter=statuscode:200&limit=-1"
    last_error = ""
    rows: list | None = None
    for attempt in range(1, attempts + 1):
        try:
            rows = get_json(query, attempts=1)
            break
        except RuntimeError as exc:
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(min(2**attempt, 15))
    if rows is None:
        raise RuntimeError(f"Wayback CDX lookup failed for {original_url}: {last_error}  (gave up after {attempts} attempts)")
    if len(rows) <= 1:
        raise WaybackNotArchivedError(f"No Wayback Machine snapshot found for {original_url}")

    timestamp = rows[-1][1]
    snapshot_url = f"https://web.archive.org/web/{timestamp}id_/{original_url}"
    return download_to_file(snapshot_url, destination, timeout=timeout)
