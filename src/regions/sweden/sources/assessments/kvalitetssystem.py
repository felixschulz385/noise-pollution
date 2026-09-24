"""Skolverket's live PxWeb "kvalitetssystem" API -- school-unit grain
achievement data, läsår 2022/23-2025/26 only. See
`docs/data/sweden/assessments/README.md` §1 for the full design and how the
query contract was reverse-engineered.

Query-contract facts confirmed live (not guessed) 2026-09-15:
- The `level` (huvudman/skolenhet) dimension's value list is too large for a
  plain metadata GET (it returns none); `{"filter": "top", "values": [N]}`
  returns it exhaustively -- only ~6k codes for Grundskola, well within one
  request.
- A school-unit row's code is the compound key
  `"{huvudman_orgnr}-{skolenhetskod}"`; the bare skolenhetskod is rejected
  (400).
- `variable` (mått) and `time` (läsår) are small and fully enumerable from
  the plain metadata GET -- no `top` trick needed for those two.
"""
from __future__ import annotations

import itertools
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from src.regions.sweden.sources.assessments.shared import assessments_paths


PXWEB_BASE = (
    "https://statistikdatabasen.skolverket.se/PxWeb/api/v1/sv/"
    "Skolverkets_statistikdatabas/Underlag_for_analys_inom_det_nationella_kvalitetssystemet"
)

DEFAULT_SKOLFORM = "Grundskola"
LEVEL_CODELIST_TOP = 20000
DEFAULT_LEVEL_BATCH_SIZE = 200
# PxWeb throttles bursts of POSTs with a bare "429 - Too many requests in too
# short timeframe" (no Retry-After header, confirmed live 2026-09-15 -- a
# full-country fetch died after exactly one successful batch otherwise).
# Fixed backoff schedule since there's no header to size the wait from.
RATE_LIMIT_BACKOFF_S = (5, 15, 30, 60, 120)
INTER_BATCH_DELAY_S = 2.0


def table_url(skolform: str = DEFAULT_SKOLFORM) -> str:
    return f"{PXWEB_BASE}/{skolform}/{skolform}.px"


def _get_json(url: str, *, timeout: int = 60) -> dict:
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


def fetch_table_metadata(skolform: str = DEFAULT_SKOLFORM) -> dict:
    return _get_json(table_url(skolform))


def extract_measure_codes(metadata: dict) -> dict[str, str]:
    """`{measure_code: label}` for the `variable` ("mått") dimension."""
    for variable in metadata.get("variables", []):
        if variable.get("code") == "variable":
            return dict(zip(variable.get("values", []), variable.get("valueTexts", [])))
    return {}


def extract_year_codes(metadata: dict) -> dict[str, str]:
    """`{year_code: label}` for the `time` ("läsår") dimension."""
    for variable in metadata.get("variables", []):
        if variable.get("code") == "time":
            return dict(zip(variable.get("values", []), variable.get("valueTexts", [])))
    return {}


def fetch_level_codelist(
    skolform: str = DEFAULT_SKOLFORM,
    *,
    probe_measure: str | None = None,
    probe_year: str | None = None,
    top: int = LEVEL_CODELIST_TOP,
) -> dict:
    """Fetch the full `level` codelist via the `top`-filter trick -- needs one
    real measure + year in the query even though only `level`'s codes are
    wanted, since PxWeb requires every dimension to appear."""
    metadata = fetch_table_metadata(skolform)
    measures = extract_measure_codes(metadata)
    years = extract_year_codes(metadata)
    if not measures or not years:
        raise RuntimeError(f"Could not read measure/year codes from {skolform} metadata.")
    probe_measure = probe_measure or next(iter(measures))
    probe_year = probe_year or next(iter(years))

    query = {
        "query": [
            {"code": "variable", "selection": {"filter": "item", "values": [probe_measure]}},
            {"code": "level", "selection": {"filter": "top", "values": [str(top)]}},
            {"code": "time", "selection": {"filter": "item", "values": [probe_year]}},
        ],
        "response": {"format": "json-stat2"},
    }
    return _post_json(table_url(skolform), query)


def parse_school_level_codes(codelist_payload: dict) -> list[dict]:
    """Filter the `level` codelist down to school-unit rows. **Not** a label
    text match on the word "SKOLENHET" -- checked live 2026-09-15 and found
    that's a false-friend: it only catches schools whose own *name*
    happens to contain "skolenhet" (a real, common Swedish naming pattern
    for split campuses, e.g. "ALLÉSKOLAN SKOLENHET ASK"), and misses every
    other school (e.g. "FJÄLLSKOLAN F-6"). The real, reliable discriminator
    is the **code shape**: a school-unit row's code is the compound key
    `"{huvudman_orgnr}-{skolenhetskod}"` (contains a literal hyphen); a
    huvudman-only row's code is a bare org number, and `"00"` is the
    national total -- neither contains a hyphen."""
    labels = codelist_payload.get("dimension", {}).get("level", {}).get("category", {}).get("label", {})
    results = []
    for code, label in labels.items():
        huvudman_orgnr, separator, skolenhetskod = code.partition("-")
        if not separator:
            continue
        results.append(
            {
                "level_code": code,
                "huvudman_orgnr": huvudman_orgnr,
                "skolenhetskod": skolenhetskod,
                "label": label,
            }
        )
    return results


def fetch_measure_values(
    measure_codes: list[str],
    level_codes: list[str],
    year_codes: list[str],
    *,
    skolform: str = DEFAULT_SKOLFORM,
    batch_size: int = DEFAULT_LEVEL_BATCH_SIZE,
    root: Path | None = None,
    force: bool = False,
) -> dict:
    """POST the actual data query, batched over `level_codes` to keep each
    request body a sane size. Saves each batch to disk **as it's fetched**
    and skips a batch index already on disk unless `force` -- a full-country
    fetch is ~31 batches against a PxWeb instance that throttles bursts with
    a bare `429` (confirmed live, no `Retry-After` header to size a wait
    from), so a mid-run failure (rate limit exhausted, network blip) must
    not lose already-fetched batches; re-running the same command resumes
    instead of re-paying for every batch again. A small delay between newly
    fetched batches (`INTER_BATCH_DELAY_S`) is on top of `_read_json`'s own
    retry/backoff, to make hitting the limit less likely in the first
    place, not just recoverable when it happens.

    A cached batch is only trusted if its own `level` dimension actually
    covers every code this call expects at that index -- found live
    2026-09-15: a stale `batch_0000.json` left on disk from an earlier
    5-school smoke test was silently "resumed" as if it were the real
    first 200-school batch, dropping 195 real schools from the output with
    no error at any stage (the smoke test's batch is a valid, well-formed
    payload, just for the wrong, smaller query -- nothing about it looks
    broken on its own). Checking school-code coverage, not just file
    existence, catches that same trap for any future stale/partial batch
    file, not just this one instance."""
    saved, skipped = [], []
    n_batches = (len(level_codes) + batch_size - 1) // batch_size
    for index, start in enumerate(range(0, len(level_codes), batch_size)):
        batch = level_codes[start : start + batch_size]
        batch_path = kvalitetssystem_raw_dir(skolform, root) / f"batch_{index:04d}.json"
        if batch_path.exists() and not force:
            cached = json.loads(batch_path.read_text(encoding="utf-8"))
            cached_levels = set(cached.get("dimension", {}).get("level", {}).get("category", {}).get("label", {}))
            if set(batch) <= cached_levels:
                skipped.append(index)
                continue
        query = {
            "query": [
                {"code": "variable", "selection": {"filter": "item", "values": measure_codes}},
                {"code": "level", "selection": {"filter": "item", "values": batch}},
                {"code": "time", "selection": {"filter": "item", "values": year_codes}},
            ],
            "response": {"format": "json-stat2"},
        }
        payload = _post_json(table_url(skolform), query)
        save_measure_batch(index, payload, skolform, root)
        saved.append(index)
        if index < n_batches - 1:
            time.sleep(INTER_BATCH_DELAY_S)
    return {"n_batches": n_batches, "saved": saved, "skipped": skipped}


def kvalitetssystem_raw_dir(skolform: str = DEFAULT_SKOLFORM, root: Path | None = None) -> Path:
    raw_dir = assessments_paths(root)["raw"] / "kvalitetssystem" / skolform
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def save_metadata(payload: dict, skolform: str = DEFAULT_SKOLFORM, root: Path | None = None) -> str:
    path = kvalitetssystem_raw_dir(skolform, root) / "metadata.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def save_level_codelist(payload: dict, skolform: str = DEFAULT_SKOLFORM, root: Path | None = None) -> str:
    path = kvalitetssystem_raw_dir(skolform, root) / "level_codelist.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def save_measure_batch(index: int, payload: dict, skolform: str = DEFAULT_SKOLFORM, root: Path | None = None) -> str:
    path = kvalitetssystem_raw_dir(skolform, root) / f"batch_{index:04d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_measure_batches(skolform: str = DEFAULT_SKOLFORM, root: Path | None = None) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(kvalitetssystem_raw_dir(skolform, root).glob("batch_*.json"))
    ]


def fetch_kvalitetssystem(
    *,
    skolform: str = DEFAULT_SKOLFORM,
    measure_codes: list[str] | None = None,
    year_codes: list[str] | None = None,
    limit_schools: int | None = None,
    batch_size: int = DEFAULT_LEVEL_BATCH_SIZE,
    root: Path | None = None,
    force: bool = False,
) -> dict:
    """Orchestrator: metadata -> full level codelist -> batched measure
    fetch. `measure_codes`/`year_codes` default to every code in the table's
    metadata; `limit_schools` caps how many school-unit level codes are
    queried (smoke-test knob, mirrors Phase 1's `--limit`). Metadata and the
    level codelist are cached too (skipped unless `force`) -- both are POSTs
    against the same rate-limited endpoint the measure batches use, so a
    resumed run after a `429` shouldn't re-pay for them either."""
    raw_dir = kvalitetssystem_raw_dir(skolform, root)
    metadata_path = raw_dir / "metadata.json"
    if metadata_path.exists() and not force:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata = fetch_table_metadata(skolform)
        save_metadata(metadata, skolform, root)

    measure_codes = measure_codes or list(extract_measure_codes(metadata))
    year_codes = year_codes or list(extract_year_codes(metadata))

    codelist_path = raw_dir / "level_codelist.json"
    if codelist_path.exists() and not force:
        codelist_payload = json.loads(codelist_path.read_text(encoding="utf-8"))
    else:
        codelist_payload = fetch_level_codelist(skolform, probe_measure=measure_codes[0], probe_year=year_codes[0])
        save_level_codelist(codelist_payload, skolform, root)
    school_codes = parse_school_level_codes(codelist_payload)
    n_schools_in_codelist = len(school_codes)
    queried_codes = school_codes[:limit_schools] if limit_schools is not None else school_codes
    level_codes = [entry["level_code"] for entry in queried_codes]

    batch_result = fetch_measure_values(
        measure_codes, level_codes, year_codes, skolform=skolform, batch_size=batch_size, root=root, force=force
    )

    return {
        "skolform": skolform,
        "n_measures": len(measure_codes),
        "n_years": len(year_codes),
        "n_schools_in_codelist": n_schools_in_codelist,
        "n_schools_queried": len(level_codes),
        "n_batches": batch_result["n_batches"],
        "batches_fetched": len(batch_result["saved"]),
        "batches_skipped": len(batch_result["skipped"]),
    }


def flatten_jsonstat2(payload: dict) -> list[dict]:
    """Flatten one json-stat2 dataset (PxWeb's response format) into long
    rows, one per `(dimension combo)`. JSON-stat2 is row-major with the
    *last* `id` dimension changing fastest -- confirmed live against a real
    2-measure x 1-level x 3-year response (`size=[2,1,3]`,
    `value=[71.6,75,76.9,null,null,null]` -- the first 3 values are the
    first measure across all 3 years, matching `itertools.product`'s own
    fastest-last iteration order)."""
    dim_ids = payload["id"]
    dimensions = payload["dimension"]
    values = payload["value"]
    status = payload.get("status", {})

    codes_by_dim = []
    for dim_id in dim_ids:
        category = dimensions[dim_id]["category"]
        index_map = category["index"]
        label_map = category.get("label", {})
        ordered_codes = sorted(index_map, key=lambda code: index_map[code])
        codes_by_dim.append([(code, label_map.get(code)) for code in ordered_codes])

    rows = []
    for flat_index, combo in enumerate(itertools.product(*codes_by_dim)):
        row: dict = {}
        for dim_id, (code, label) in zip(dim_ids, combo):
            row[f"{dim_id}_code"] = code
            row[f"{dim_id}_label"] = label
        row["value"] = values[flat_index] if flat_index < len(values) else None
        row["status"] = status.get(str(flat_index))
        rows.append(row)
    return rows


def preprocess_kvalitetssystem(batches: list[dict]) -> pd.DataFrame:
    """Turn fetched measure-value batches into one tidy long-format table:
    one row per `(skolenhetskod, measure, year)`."""
    rows: list[dict] = []
    for batch in batches:
        rows.extend(flatten_jsonstat2(batch))
    if not rows:
        return pd.DataFrame(
            columns=[
                "skolenhetskod",
                "huvudman_orgnr",
                "measure_code",
                "measure_label",
                "year_code",
                "year_label",
                "value",
                "status",
            ]
        )

    df = pd.DataFrame.from_records(rows)
    split = df["level_code"].str.split("-", n=1, expand=True)
    df["huvudman_orgnr"] = split[0]
    df["skolenhetskod"] = split[1]
    df = df.rename(
        columns={
            "variable_code": "measure_code",
            "variable_label": "measure_label",
            "time_code": "year_code",
            "time_label": "year_label",
        }
    )
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[
        [
            "skolenhetskod",
            "huvudman_orgnr",
            "measure_code",
            "measure_label",
            "year_code",
            "year_label",
            "value",
            "status",
        ]
    ].sort_values(["skolenhetskod", "year_code", "measure_code"]).reset_index(drop=True)


def save_processed_kvalitetssystem(
    df: pd.DataFrame,
    *,
    parquet_name: str = "kvalitetssystem.parquet",
    root: Path | None = None,
) -> str:
    path = assessments_paths(root)["processed"] / parquet_name
    df.to_parquet(path, index=False)
    return str(path)
