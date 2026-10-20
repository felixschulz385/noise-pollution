"""Fetch the `Skolenhetsregistret` (school unit register, API v2): the
nationwide list, then one detail record per school unit (geocoding, grade
span, operator, dates). No authentication.

The list endpoint returns every school unit in one call, closed (`UPPHORT`)
ones included (12,037 on 2026-10-20). The detail endpoint is one HTTP call
per `Skolenhetskod` -- `fetch_details` is idempotent (skips a code whose
detail file already exists on disk unless `force=True`), runs a few
requests in parallel, and accepts `limit`/`codes` so a smoke test doesn't
have to pull the whole country.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.regions.sweden.sources.schools.shared import (
    schools_paths,
    skolenhet_detail_url,
    skolenhet_list_url,
)


DETAIL_WORKERS = 4


def _get_json(url: str, *, timeout: int = 60) -> dict:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} fetching {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def fetch_skolenhet_list() -> dict:
    return _get_json(skolenhet_list_url(), timeout=180)


def fetch_skolenhet_detail(skolenhetskod: str) -> dict:
    return _get_json(skolenhet_detail_url(skolenhetskod))


def list_entries(list_payload: dict) -> list[dict]:
    return (list_payload.get("data") or {}).get("attributes") or []


def extract_skolenhet_codes(list_payload: dict, *, status: str | None = None) -> list[str]:
    codes = []
    for entry in list_entries(list_payload):
        code = entry.get("schoolUnitCode")
        if not code:
            continue
        if status is not None and entry.get("status") != status:
            continue
        codes.append(code)
    return codes


def raw_list_path(root: Path | None = None) -> Path:
    return schools_paths(root)["raw"] / "school_units.json"


def raw_detail_dir(root: Path | None = None) -> Path:
    detail_dir = schools_paths(root)["raw"] / "school_unit"
    detail_dir.mkdir(parents=True, exist_ok=True)
    return detail_dir


def raw_detail_path(skolenhetskod: str, root: Path | None = None) -> Path:
    return raw_detail_dir(root) / f"{skolenhetskod}.json"


def save_raw_list(payload: dict, root: Path | None = None) -> str:
    path = raw_list_path(root)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_raw_list(root: Path | None = None) -> dict:
    return json.loads(raw_list_path(root).read_text(encoding="utf-8"))


def save_raw_detail(skolenhetskod: str, payload: dict, root: Path | None = None) -> str:
    path = raw_detail_path(skolenhetskod, root)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_raw_detail(skolenhetskod: str, root: Path | None = None) -> dict:
    return json.loads(raw_detail_path(skolenhetskod, root).read_text(encoding="utf-8"))


def fetched_detail_codes(root: Path | None = None) -> set[str]:
    return {path.stem for path in raw_detail_dir(root).glob("*.json")}


def fetch_details(
    codes: list[str],
    *,
    force: bool = False,
    workers: int = DETAIL_WORKERS,
    root: Path | None = None,
) -> dict[str, list[str]]:
    """Fetch and save one detail record per code in `codes`, skipping codes
    already on disk unless `force=True`. Returns the codes actually fetched,
    the ones skipped (already present), and the ones that failed, each in
    `codes` order."""
    already_present = fetched_detail_codes(root) if not force else set()
    to_fetch = [code for code in codes if force or code not in already_present]

    def fetch_one(code: str) -> bool:
        try:
            detail = fetch_skolenhet_detail(code)
        except RuntimeError:
            return False
        save_raw_detail(code, detail, root)
        return True

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        ok = list(pool.map(fetch_one, to_fetch))

    fetched = [code for code, success in zip(to_fetch, ok) if success]
    failed = [code for code, success in zip(to_fetch, ok) if not success]
    skipped = [code for code in codes if code not in to_fetch]
    return {"fetched": fetched, "skipped": skipped, "failed": failed}


def fetch_skolenhetsregistret(
    *,
    limit: int | None = None,
    status: str | None = None,
    codes: list[str] | None = None,
    force: bool = False,
    root: Path | None = None,
) -> dict:
    """Fetch the register: always the full list, then detail records for
    `codes` if given, else every code from the list (optionally filtered by
    `status` and capped at `limit`)."""
    list_payload = fetch_skolenhet_list()
    list_path = save_raw_list(list_payload, root)

    target_codes = codes if codes is not None else extract_skolenhet_codes(list_payload, status=status)
    if limit is not None:
        target_codes = target_codes[:limit]

    detail_result = fetch_details(target_codes, force=force, root=root)

    return {
        "list_path": list_path,
        "total_in_register": len(list_entries(list_payload)),
        "requested_details": len(target_codes),
        **detail_result,
    }
