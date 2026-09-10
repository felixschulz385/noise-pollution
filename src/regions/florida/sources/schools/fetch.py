"""Fetch step for the Florida ``schools`` source.

Pulls the selected subsources into ``data/florida/schools/raw/``, sequentially:

* ``msid``  — POST an empty body to the FLDOE EDS ColdFusion app (browser
  User-Agent) and write the tab-delimited export.
* ``edge``  — adopt a hand-placed ``EDGE_GEOCODE_PUBLICSCH_<vintage>.zip`` (from
  ``raw/`` or the domain dir), else best-effort download from NCES.
* ``ccd_directory`` / ``ccd_enrollment`` / ``crdc`` / ``edfacts`` — page the
  Urban Institute Education Data API for each year and cache one parquet per
  subsource/year, plus an ``api_query.json`` sidecar.

``--from-file`` copies a file you downloaded by hand into ``raw/``. Nothing here
calls another source's fetch; ``preprocess`` declares the cross-source
dependency on ``noise_barriers`` (stage 2).
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.regions.florida.sources._http import download_to_file
from src.regions.florida.sources.schools.shared import (
    API_SUBSOURCES,
    API_YEARS_DEFAULT,
    EDGE_DEFAULT_VINTAGE,
    FL_FIPS_STR,
    MANUAL_DOWNLOAD_STEPS,
    MSID_APP_URL,
    MSID_DEFAULT_DATASET,
    MSID_EXPECTED_PREFIX,
    URBAN_API_BASE,
    _EDGE_ZIP_MAGIC,
    api_query_sidecar_path,
    api_raw_path,
    api_url,
    csv_file_url,
    edge_raw_path,
    edge_url,
    is_api_subsource,
    msid_dataset_filename,
    msid_dataset_url,
    parse_year_range,
    resolve_subsources,
    scan_raw,
    schools_paths,
)

# eds.fldoe.org returns 403/500 to the default urllib UA; a browser UA is enough
# (unlike www.fldoe.org, there is no JS bot wall here).
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_API_UA = "noise-pollution-research/1.0 (+https://educationdata.urban.org)"


def _sanitize(name: str) -> str:
    cleaned = name.strip().replace("/", "_").replace("\\", "_")
    return cleaned or "schools_download.bin"


# --------------------------------------------------------------------------- #
# msid                                                                       #
# --------------------------------------------------------------------------- #

def _msid_post_download(url: str, *, timeout: int = 120) -> bytes:
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

    if not body.startswith(MSID_EXPECTED_PREFIX):
        raise RuntimeError(
            f"{url} did not return an MSID export "
            f"(got {len(body)} bytes starting {body[:40]!r})"
        )
    return body


def _fetch_msid(datasets: list[str], raw_dir: Path) -> dict[str, object]:
    downloaded: list[dict[str, object]] = []
    errors: list[str] = []
    for dataset in datasets:
        url = msid_dataset_url(dataset)  # raises ValueError on unknown name
        dest = raw_dir / msid_dataset_filename(dataset)
        try:
            body = _msid_post_download(url)
        except RuntimeError as exc:
            errors.append(f"{dataset}: {exc}")
            continue
        dest.write_bytes(body)
        downloaded.append({"dataset": dataset, "url": url, "path": str(dest), "bytes": len(body)})
    return {"downloaded": downloaded, "errors": errors}


# --------------------------------------------------------------------------- #
# edge                                                                       #
# --------------------------------------------------------------------------- #

def _looks_like_zip(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == _EDGE_ZIP_MAGIC
    except OSError:
        return False


def _fetch_edge(vintage: str, base_dir: Path, *, refresh: bool, root: Path | None) -> dict[str, object]:
    dest = edge_raw_path(vintage, root)
    if dest.exists() and not refresh:
        return {"path": str(dest), "action": "already-present", "errors": []}

    # Adopt a hand-placed zip sitting in the domain dir (not yet under raw/).
    stray = base_dir / dest.name
    if stray.is_file() and stray != dest:
        shutil.move(str(stray), str(dest))
        if not _looks_like_zip(dest):
            return {"path": str(dest), "action": "adopted", "errors": [f"{dest.name} is not a zip archive"]}
        return {"path": str(dest), "action": "adopted", "errors": []}

    try:
        download_to_file(edge_url(vintage), dest)
    except RuntimeError as exc:
        return {"path": None, "action": "failed", "errors": [f"edge {vintage}: {exc}"]}
    if not _looks_like_zip(dest):
        body = dest.read_bytes()[:200]
        dest.unlink(missing_ok=True)
        return {"path": None, "action": "failed",
                "errors": [f"edge {vintage}: response was not a zip ({body!r})"]}
    return {"path": str(dest), "action": "downloaded", "errors": []}


# --------------------------------------------------------------------------- #
# Urban Institute Education Data API                                          #
# --------------------------------------------------------------------------- #

def _download_with_resume(url: str, dest: Path, *, attempts: int = 5, timeout: int = 120) -> Path:
    """GET ``url`` to ``dest``, resuming a partial file with a Range request and
    retrying truncated / dropped connections. For the ~1 GB Urban CSV flat files,
    which a plain streamed GET often cuts short."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_error = ""
    for attempt in range(1, attempts + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = {"User-Agent": _API_UA}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                total = have + int(response.headers.get("Content-Length", 0) or 0)
                mode = "ab" if (have and response.status == 206) else "wb"
                if mode == "wb":
                    have = 0
                with tmp.open(mode) as handle:
                    shutil.copyfileobj(response, handle, length=1 << 20)
            size = tmp.stat().st_size
            if total and size < total:
                last_error = f"truncated at {size}/{total} bytes"
                continue
            tmp.replace(dest)
            return dest
        except HTTPError as exc:
            if exc.code == 416 and tmp.exists():  # range not satisfiable -> already complete
                tmp.replace(dest)
                return dest
            last_error = f"HTTP {exc.code}"
        except (URLError, OSError, ValueError) as exc:
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"download failed for {url}: {last_error} (after {attempts} attempts)")


class _ApiNotFound(RuntimeError):
    """The API has no data for this subsource/year (HTTP 404)."""


_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def _get_json(url: str, *, timeout: int = 120, attempts: int = 4) -> dict:
    """GET JSON, retrying transient upstream failures (5xx / 429 / transport)
    with exponential backoff. educationdata.urban.org sits behind Cloudflare and
    502s intermittently, which would otherwise kill a whole year's pull."""
    request = Request(url, headers={"User-Agent": _API_UA, "Accept": "application/json"}, method="GET")
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
            return json.loads(payload)
        except HTTPError as exc:
            if exc.code == 404:
                raise _ApiNotFound(url) from exc
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            last_error = f"HTTP {exc.code} for {url}: {detail}"
            if exc.code not in _RETRY_STATUS:
                raise RuntimeError(last_error) from exc
        except URLError as exc:
            last_error = f"Request failed for {url}: {exc}"
        except ValueError as exc:
            last_error = f"{url} did not return JSON: {exc}"
        if attempt < attempts:
            time.sleep(min(2 ** attempt, 15))
    raise RuntimeError(f"{last_error}  (gave up after {attempts} attempts)")


def _get_all_pages(first_url: str, *, timeout: int = 120, page_cap: int = 500) -> list[dict]:
    rows: list[dict] = []
    url: str | None = first_url
    pages = 0
    while url:
        payload = _get_json(url, timeout=timeout)
        rows.extend(payload.get("results", []))
        url = payload.get("next")
        pages += 1
        if pages > page_cap:
            raise RuntimeError(f"{first_url}: exceeded {page_cap} pages")
    return rows


def _years_needed(subsource: str, year_lo: int, year_hi: int, *, refresh: bool, root: Path | None):
    present, needed = [], []
    for year in range(year_lo, year_hi + 1):
        if api_raw_path(subsource, year, root).exists() and not refresh:
            present.append(year)
        else:
            needed.append(year)
    return present, needed


def _fetch_api_via_rest(
    subsource: str, years: list[int], *, root: Path | None
) -> tuple[list[int], list[int], dict[int, int], list[str]]:
    import pandas as pd  # heavy; only needed to write parquet

    written, unavailable, errors = [], [], []
    rows_by_year: dict[int, int] = {}
    for year in years:
        try:
            records = _get_all_pages(api_url(subsource, year))
        except _ApiNotFound:
            unavailable.append(year)
            continue
        except RuntimeError as exc:
            errors.append(f"{subsource} {year}: {exc}")
            continue
        if not records:
            unavailable.append(year)
            continue
        pd.DataFrame.from_records(records).to_parquet(api_raw_path(subsource, year, root), index=False)
        written.append(year)
        rows_by_year[year] = len(records)
    return written, unavailable, rows_by_year, errors


def _fetch_api_via_csv(
    subsource: str, years: list[int], *, root: Path | None
) -> tuple[list[int], list[int], dict[int, int], list[str]]:
    """Download the static flat file(s) to a local cache (with retry / resume),
    keep ``fips == 12`` rows in the wanted years, and split to one parquet per
    year. The CDN flat files stay up during ``/api/v1/`` outages.

    One file can be ~1 GB (all years, all states) — it is cached under
    ``raw/_csv_source/`` and reused unless ``refresh``."""
    import pandas as pd

    files = API_SUBSOURCES[subsource].get("csv_files")
    if not files:
        return [], [], {}, [
            f"{subsource}: no known CSV file(s); the api-downloads endpoint that lists "
            f"them needs /api/v1/ up. Use --via api, or retry later."
        ]

    want = set(years)
    cache_dir = schools_paths(root)["raw"] / "_csv_source"
    cache_dir.mkdir(parents=True, exist_ok=True)

    keep: list[pd.DataFrame] = []
    errors: list[str] = []
    for file_name in files:
        local = cache_dir / file_name
        if not (local.exists() and not refresh):
            try:
                _download_with_resume(csv_file_url(subsource, file_name), local)
            except RuntimeError as exc:
                errors.append(f"{subsource} csv {file_name}: {exc}")
                continue
        try:
            reader = pd.read_csv(
                local, dtype=str, chunksize=200_000, na_values=["", "."], low_memory=False
            )
            for chunk in reader:
                if "fips" in chunk.columns:
                    chunk = chunk[pd.to_numeric(chunk["fips"], errors="coerce") == int(FL_FIPS_STR)]
                if "year" in chunk.columns:
                    chunk = chunk[pd.to_numeric(chunk["year"], errors="coerce").isin(want)]
                if not chunk.empty:
                    keep.append(chunk)
        except Exception as exc:  # noqa: BLE001 - parse errors reported like the rest
            errors.append(f"{subsource} csv {file_name}: parse failed: {exc}")

    if not keep:
        return [], sorted(want), {}, errors

    full = pd.concat(keep, ignore_index=True)
    if "year" not in full.columns:
        return [], sorted(want), {}, errors + [f"{subsource}: CSV has no 'year' column, cannot split"]

    written, rows_by_year = [], {}
    for year, part in full.groupby(pd.to_numeric(full["year"], errors="coerce").astype("Int64")):
        year = int(year)
        if year not in want:
            continue
        part.drop(columns=["year"]).assign(year=year).to_parquet(
            api_raw_path(subsource, year, root), index=False
        )
        written.append(year)
        rows_by_year[year] = len(part)
    return written, sorted(want - set(written)), rows_by_year, errors


def _fetch_api_subsource(
    subsource: str, year_lo: int, year_hi: int, *, via: str, refresh: bool, root: Path | None
) -> dict[str, object]:
    present, needed = _years_needed(subsource, year_lo, year_hi, refresh=refresh, root=root)

    written: set[int] = set()
    rows_by_year: dict[int, int] = {}
    errors: list[str] = []
    routes: list[str] = []

    if needed and via in ("csv", "auto"):
        w, _u, r, e = _fetch_api_via_csv(subsource, needed, root=root)
        written.update(w)
        rows_by_year.update(r)
        errors += e
        routes.append("csv")

    remaining = [y for y in needed if y not in written]
    if remaining and (via == "api" or via == "auto"):
        w, _u, r, e = _fetch_api_via_rest(subsource, remaining, root=root)
        written.update(w)
        rows_by_year.update(r)
        errors += e
        routes.append("api")

    return {
        "route": "+".join(routes) or "none",
        "path_template": API_SUBSOURCES[subsource]["path"],
        "params": API_SUBSOURCES[subsource]["params"],
        "years_written": sorted(written),
        "years_present": present,
        "years_unavailable": sorted(y for y in needed if y not in written),
        "rows_by_year": rows_by_year,
        "errors": errors,
    }


def _write_api_sidecar(api_results: dict[str, dict], year_lo: int, year_hi: int, root: Path | None) -> None:
    sidecar = {
        "pulled_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "api_base": URBAN_API_BASE,
        "year_range": [year_lo, year_hi],
        "subsources": api_results,
    }
    api_query_sidecar_path(root).write_text(json.dumps(sidecar, indent=2, default=str))


# --------------------------------------------------------------------------- #
# orchestrator                                                               #
# --------------------------------------------------------------------------- #

def fetch_schools(
    subsources: list[str] | None = None,
    *,
    years: str | tuple[int, int] | None = None,
    via: str = "auto",
    msid_datasets: list[str] | None = None,
    edge_vintage: str | None = None,
    from_files: list[str] | None = None,
    refresh: bool = False,
    root: Path | None = None,
) -> dict[str, object]:
    if via not in ("auto", "api", "csv"):
        raise ValueError(f"via must be 'auto', 'api' or 'csv' (got {via!r}).")
    selected = resolve_subsources(subsources)
    year_lo, year_hi = parse_year_range(years if years is not None else API_YEARS_DEFAULT)
    paths = schools_paths(root)
    raw_dir = paths["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    out: dict[str, object] = {
        "raw_dir": str(raw_dir),
        "subsources": selected,
        "year_range": [year_lo, year_hi],
    }
    errors: list[str] = []
    any_success = False

    # --from-file: copy into raw/ (subsource inferred later from the filename).
    imported: list[str] = []
    for src in from_files or []:
        src_path = Path(src).expanduser()
        if not src_path.is_file():
            errors.append(f"--from-file not found: {src_path}")
            continue
        dest = raw_dir / _sanitize(src_path.name)
        if src_path.resolve() != dest.resolve():
            shutil.copy2(src_path, dest)
        imported.append(str(dest))
        any_success = True
    if imported:
        out["imported"] = imported

    api_results: dict[str, dict] = {}
    for subsource in selected:
        if subsource == "msid":
            res = _fetch_msid(msid_datasets or [MSID_DEFAULT_DATASET], raw_dir)
            out["msid"] = res
            errors.extend(res["errors"])  # type: ignore[arg-type]
            any_success = any_success or bool(res["downloaded"])
        elif subsource == "edge":
            res = _fetch_edge(edge_vintage or EDGE_DEFAULT_VINTAGE, paths["base"], refresh=refresh, root=root)
            out["edge"] = res
            errors.extend(res["errors"])  # type: ignore[arg-type]
            any_success = any_success or res["action"] in {"downloaded", "adopted", "already-present"}
        elif is_api_subsource(subsource):
            res = _fetch_api_subsource(subsource, year_lo, year_hi, via=via, refresh=refresh, root=root)
            out[subsource] = res
            api_results[subsource] = res
            errors.extend(res["errors"])  # type: ignore[arg-type]
            any_success = any_success or bool(res["years_written"] or res["years_present"])

    if api_results:
        _write_api_sidecar(api_results, year_lo, year_hi, root)

    out["errors"] = errors
    out["present"] = scan_raw(root)
    out["state"] = "present" if any_success and not errors else "partial" if any_success else "missing"
    if not any_success:
        out["instructions"] = MANUAL_DOWNLOAD_STEPS
    return out
