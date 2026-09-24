"""Fetch DeSO 2018 boundaries (SCB geoserver WFS) and three DeSO-grain
PxWebApi tables -- mean net income, population by education level, and
labour-market status -- Covariate Cluster F.

All endpoints confirmed live 2026-09-17:
- `https://geodata.scb.se/geoserver/stat/wfs` exposes `stat:DeSO_2018`
  (5,984 areas) and `stat:DeSO_2025` (6,160 areas, the 2025 redraw -- not
  used here, see `shared.py`'s module docstring) as separate WFS layers,
  EPSG:3006, one polygon per DeSO with `desokod`/`regsokod`/`lanskod`/
  `kommunkod` attributes. **Genuinely slow per feature** (~500 features
  took ~90s in a live timing test -- full-resolution national boundary
  geometry, no simplified/generalized layer variant exists on this
  geoserver), so `fetch_all_deso_boundaries` pages and saves incrementally
  (same resumable-batch convention as `assessments/kvalitetssystem.py`)
  rather than one giant request.
- `api.scb.se`'s PxWeb v1 API (same underlying tech as Skolverket's own
  PxWeb, `assessments/kvalitetssystem.py` -- query-contract lessons
  transfer directly) serves:
  - **Income**: `Tab2InkDesoRegso` (`HE/HE0110/HE0110I`) -- net income
    structure by region/income-component/kön/year, 2011-2024 nominal, real
    DeSO2018 coverage 2011-2023 (see `preprocess.py`).
  - **Education**: `UtbSUNBefDesoRegso` (`UF/UF0506/UF0506D`) -- population
    by region/education-level/year, 2015-2023. Its successor table
    (`UtbSUNBefDesoRegsoN`, 2024-2025) uses **only** `_DeSO2025`-suffixed
    region codes -- no DeSO2018 alternative exists for those years at
    all, unlike income/employment where a DeSO2018 code exists but is
    suppressed -- so this v1 build doesn't fetch the successor table.
  - **Employment**: `ArRegDesoStatusN` (`AM/AM0210/AM0210G`) -- employed/
    total counts by region/kön/age/year, 2020-2024 nominal, real DeSO2018
    coverage 2020-2023 (same "one year short" shape as income, confirmed
    live).

  All three tables' `Region` dimension mixes DeSO2018, DeSO2025, RegSO,
  kommun and national codes in one dimension; this module only ever
  queries the DeSO2018 codes recovered from the boundary fetch. A
  dimension not restricted to specific codes is queried with
  PxWeb's `{"filter": "all", "values": ["*"]}` wildcard (confirmed live to
  return every real value, e.g. all 5 education levels or all years) rather
  than enumerating codes by hand.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.regions.sweden.sources.neighbourhood.shared import (
    deso_boundaries_raw_dir,
    education_raw_dir,
    employment_raw_dir,
    income_raw_dir,
)


DESO_WFS_URL = "https://geodata.scb.se/geoserver/stat/wfs"
DESO_TYPE_NAME = "stat:DeSO_2018"
DEFAULT_BOUNDARY_PAGE_SIZE = 1000

PXWEB_INCOME_TABLE_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/HE/HE0110/HE0110I/Tab2InkDesoRegso"
# `nettoinkomst` (net income), `1+2` (totalt, both sexes), `000008A4`
# ("Medelvärde för samtliga, tkr" -- mean, thousand SEK). Confirmed live
# 2026-09-17 from the table's own metadata; the other 16 income-component
# codes and the per-sex/`Andel med inkomstslag`/`Antal personer` content
# codes are catalogued but not pulled by this v1 fetch.
INCOME_COMPONENT_CODE = "240"
KON_CODE = "1+2"
CONTENT_CODE = "000008A4"

PXWEB_EDUCATION_TABLE_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/UF/UF0506/UF0506D/UtbSUNBefDesoRegso"
EDUCATION_CONTENT_CODE = "000005MO"  # "Befolkning" -- population count per education level

PXWEB_EMPLOYMENT_TABLE_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/AM/AM0210/AM0210G/ArRegDesoStatusN"
EMPLOYMENT_KON_CODE = "1+2"
EMPLOYMENT_ALDER_CODE = "16-64"
# "antal sysselsatta" (employed count), "antal totalt" (total population
# in this age/sex/region cell) -- confirmed live from the table's metadata.
EMPLOYMENT_CONTENT_CODES = ["0000089X", "0000089Y"]

DEFAULT_REGION_BATCH_SIZE = 500
# PxWeb throttles POST bursts (confirmed live for Skolverket's instance,
# `assessments/kvalitetssystem.py`); same fixed-backoff schedule applied
# here defensively even though SCB's own throttling hasn't been hit yet.
RATE_LIMIT_BACKOFF_S = (5, 15, 30, 60, 120)
INTER_BATCH_DELAY_S = 2.0


def _get_json(url: str, *, timeout: int = 180) -> dict:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    return _read_json(request, timeout=timeout, url=url)


def _post_json(url: str, body: dict, *, timeout: int = 120) -> dict:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    return _read_json(request, timeout=timeout, url=url)


def _read_json(request: Request, *, timeout: int, url: str) -> dict:
    for attempt, wait_s in enumerate((*RATE_LIMIT_BACKOFF_S, None)):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and wait_s is not None:
                time.sleep(wait_s)
                continue
            raise RuntimeError(f"HTTP {exc.code} calling {url}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    raise AssertionError("unreachable")  # loop always returns or raises


# --- DeSO boundaries (WFS) --------------------------------------------------


def deso_boundary_page_url(start_index: int, count: int) -> str:
    params = {
        "service": "wfs",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": DESO_TYPE_NAME,
        "outputFormat": "application/json",
        "count": count,
        "startIndex": start_index,
    }
    return f"{DESO_WFS_URL}?{urlencode(params)}"


def fetch_deso_boundary_page(start_index: int, count: int) -> dict:
    return _get_json(deso_boundary_page_url(start_index, count))


def boundary_page_path(page_index: int, root: Path | None = None) -> Path:
    return deso_boundaries_raw_dir(root) / f"page_{page_index:04d}.json"


def save_boundary_page(page_index: int, payload: dict, root: Path | None = None) -> str:
    path = boundary_page_path(page_index, root)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def load_boundary_pages(root: Path | None = None) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(deso_boundaries_raw_dir(root).glob("page_*.json"))
    ]


def fetch_all_deso_boundaries(
    *, page_size: int = DEFAULT_BOUNDARY_PAGE_SIZE, root: Path | None = None, force: bool = False
) -> dict:
    """Page through every DeSO 2018 polygon, saving each page to disk as
    it's fetched. Resumable: a page already on disk with `numberReturned
    == page_size` (i.e. not a truncated/partial earlier attempt) is
    skipped unless `force` -- avoids re-paying for the ~90s/500-feature
    cost of a page already safely fetched."""
    start_index = 0
    page_index = 0
    saved, skipped = [], []
    number_matched: int | None = None

    while True:
        path = boundary_page_path(page_index, root)
        if path.exists() and not force:
            cached = json.loads(path.read_text(encoding="utf-8"))
            n_returned = cached.get("numberReturned", 0)
            number_matched = cached.get("numberMatched", number_matched)
            skipped.append(page_index)
        else:
            payload = fetch_deso_boundary_page(start_index, page_size)
            n_returned = payload.get("numberReturned", 0)
            number_matched = payload.get("numberMatched", number_matched)
            save_boundary_page(page_index, payload, root)
            saved.append(page_index)
            if n_returned == page_size:
                time.sleep(INTER_BATCH_DELAY_S)

        start_index += n_returned
        page_index += 1
        if n_returned < page_size or (number_matched is not None and start_index >= number_matched):
            break

    return {
        "number_matched": number_matched,
        "n_pages": page_index,
        "pages_fetched": len(saved),
        "pages_skipped": len(skipped),
    }


# --- Shared PxWeb batched-by-region fetch ------------------------------------


def _batch_path(raw_dir: Path, index: int) -> Path:
    return raw_dir / f"batch_{index:04d}.json"


def _save_batch(raw_dir: Path, index: int, payload: dict) -> str:
    path = _batch_path(raw_dir, index)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _load_batches(raw_dir: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(raw_dir.glob("batch_*.json"))]


def _fetch_batched_by_region(
    table_url: str,
    other_query_dims: list[dict],
    region_codes: list[str],
    *,
    raw_dir: Path,
    batch_size: int,
    force: bool,
) -> dict:
    """POST a query batched over `region_codes`, one batch per
    `batch_size` DeSO2018 codes, against `table_url` with every other
    dimension fixed by `other_query_dims`. Resumable, same "trust a
    cached batch only if its own `Region` dimension covers every code
    this call expects" discipline as `assessments/kvalitetssystem.py`'s
    `fetch_measure_values` -- a stale/partial batch is re-fetched, not
    silently trusted. Shared by `fetch_income_values`/
    `fetch_education_values`/`fetch_employment_values` -- the three
    PxWeb tables this module queries all page over the same region list
    the same way, only their fixed dimensions differ."""
    saved, skipped = [], []
    n_batches = (len(region_codes) + batch_size - 1) // batch_size
    for index, start in enumerate(range(0, len(region_codes), batch_size)):
        batch = region_codes[start : start + batch_size]
        path = _batch_path(raw_dir, index)
        if path.exists() and not force:
            cached = json.loads(path.read_text(encoding="utf-8"))
            cached_regions = set(cached.get("dimension", {}).get("Region", {}).get("category", {}).get("label", {}))
            if set(batch) <= cached_regions:
                skipped.append(index)
                continue
        query = {
            "query": [{"code": "Region", "selection": {"filter": "item", "values": batch}}, *other_query_dims],
            "response": {"format": "json-stat2"},
        }
        payload = _post_json(table_url, query)
        _save_batch(raw_dir, index, payload)
        saved.append(index)
        if index < n_batches - 1:
            time.sleep(INTER_BATCH_DELAY_S)
    return {"n_batches": n_batches, "saved": saved, "skipped": skipped}


# --- Income -------------------------------------------------------------------


def fetch_income_table_metadata() -> dict:
    return _get_json(PXWEB_INCOME_TABLE_URL)


def income_batch_path(index: int, root: Path | None = None) -> Path:
    return _batch_path(income_raw_dir(root), index)


def save_income_batch(index: int, payload: dict, root: Path | None = None) -> str:
    return _save_batch(income_raw_dir(root), index, payload)


def load_income_batches(root: Path | None = None) -> list[dict]:
    return _load_batches(income_raw_dir(root))


def fetch_income_values(
    region_codes: list[str],
    *,
    income_component: str = INCOME_COMPONENT_CODE,
    kon: str = KON_CODE,
    content_code: str = CONTENT_CODE,
    batch_size: int = DEFAULT_REGION_BATCH_SIZE,
    root: Path | None = None,
    force: bool = False,
) -> dict:
    other_query_dims = [
        {"code": "Inkomstkomponenter", "selection": {"filter": "item", "values": [income_component]}},
        {"code": "Kon", "selection": {"filter": "item", "values": [kon]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [content_code]}},
    ]
    return _fetch_batched_by_region(
        PXWEB_INCOME_TABLE_URL, other_query_dims, region_codes,
        raw_dir=income_raw_dir(root), batch_size=batch_size, force=force,
    )


# --- Education ----------------------------------------------------------------


def fetch_education_table_metadata() -> dict:
    return _get_json(PXWEB_EDUCATION_TABLE_URL)


def education_batch_path(index: int, root: Path | None = None) -> Path:
    return _batch_path(education_raw_dir(root), index)


def save_education_batch(index: int, payload: dict, root: Path | None = None) -> str:
    return _save_batch(education_raw_dir(root), index, payload)


def load_education_batches(root: Path | None = None) -> list[dict]:
    return _load_batches(education_raw_dir(root))


def fetch_education_values(
    region_codes: list[str],
    *,
    content_code: str = EDUCATION_CONTENT_CODE,
    batch_size: int = DEFAULT_REGION_BATCH_SIZE,
    root: Path | None = None,
    force: bool = False,
) -> dict:
    """Every `UtbildningsNiva` (education level) and `Tid` (year) value,
    via PxWeb's `{"filter": "all", "values": ["*"]}` wildcard -- confirmed
    live 2026-09-17 to return all 5 real levels x all 9 real years (2015-
    2023) without enumerating either by hand."""
    other_query_dims = [
        {"code": "UtbildningsNiva", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [content_code]}},
        {"code": "Tid", "selection": {"filter": "all", "values": ["*"]}},
    ]
    return _fetch_batched_by_region(
        PXWEB_EDUCATION_TABLE_URL, other_query_dims, region_codes,
        raw_dir=education_raw_dir(root), batch_size=batch_size, force=force,
    )


# --- Employment -----------------------------------------------------------------


def fetch_employment_table_metadata() -> dict:
    return _get_json(PXWEB_EMPLOYMENT_TABLE_URL)


def employment_batch_path(index: int, root: Path | None = None) -> Path:
    return _batch_path(employment_raw_dir(root), index)


def save_employment_batch(index: int, payload: dict, root: Path | None = None) -> str:
    return _save_batch(employment_raw_dir(root), index, payload)


def load_employment_batches(root: Path | None = None) -> list[dict]:
    return _load_batches(employment_raw_dir(root))


def fetch_employment_values(
    region_codes: list[str],
    *,
    kon: str = EMPLOYMENT_KON_CODE,
    alder: str = EMPLOYMENT_ALDER_CODE,
    content_codes: list[str] = EMPLOYMENT_CONTENT_CODES,
    batch_size: int = DEFAULT_REGION_BATCH_SIZE,
    root: Path | None = None,
    force: bool = False,
) -> dict:
    other_query_dims = [
        {"code": "Kon", "selection": {"filter": "item", "values": [kon]}},
        {"code": "Alder", "selection": {"filter": "item", "values": [alder]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": content_codes}},
        {"code": "Tid", "selection": {"filter": "all", "values": ["*"]}},
    ]
    return _fetch_batched_by_region(
        PXWEB_EMPLOYMENT_TABLE_URL, other_query_dims, region_codes,
        raw_dir=employment_raw_dir(root), batch_size=batch_size, force=force,
    )
