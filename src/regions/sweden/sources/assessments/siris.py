"""Skolverket's pre-2020 SIRIS exports, preserved (not rehosted) on
Skolverket's own S3 bucket by the datajournalist project
`jplusplus/skolstatistik`. School-unit grain, läsår 1997/98-2018/19. See
`docs/data/sweden/assessments/README.md` §2 for how the two school-grain
dataset series here were identified and confirmed live.

Files are UTF-8 with a BOM (confirmed live 2026-09-15 by inspecting the raw
bytes -- `\xef\xbb\xbf` -- after an earlier session wrongly assumed
ISO-8859-1 from a terminal `iconv` round-trip that happened to look
plausible), `;`-delimited, decimal comma, with a banner + (for some
datasets) a two-row header before the real data starts -- `parse_siris_csv`
below handles both.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

from src.regions.sweden.sources.assessments.shared import assessments_paths


DATASETS_CSV_URL = "https://raw.githubusercontent.com/jplusplus/skolstatistik/master/datasets.csv"

# Confirmed live 2026-09-15 (real CSV headers checked) to be school-unit
# grain, not kommun/huvudman grain -- see assessments/README.md §2. The `dataset`
# value must match `datasets.csv`'s `dataset` column exactly (it's the
# Skolverket-assigned numeric id + title).
SIRIS_SCHOOL_GRAIN_DATASETS = {
    "slutbetyg_arskurs9": {
        "skolniva": "Grundskolan",
        "dataset": "139-Slutbetyg årskurs 9, samtliga elever",
    },
    "salsa": {
        "skolniva": "Grundskolan",
        "dataset": "95-Salsa, skolenheters resultat av slutbetygen i årskurs 9 med hänsyn till elevsammansättningen",
    },
}

IDENTITY_COLUMNS = {
    "skola_namn",
    "skolenhetskod",
    "kommun_namn",
    "kommunkod",
    "huvudman_typ",
    "huvudman_namn",
    "huvudman_orgnr",
}

_MISSING_SENTINELS = {"", ".", "..", "...", "-"}


def _get_bytes(url: str, *, timeout: int = 60) -> bytes:
    request = Request(quote(url, safe=":/?&=,%"), headers={"User-Agent": "noise-pollution-research/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def fetch_datasets_index() -> list[dict]:
    """Download and parse `datasets.csv`, the jplusplus/skolstatistik
    manifest of every `(school form x topic x year x format)` SIRIS export."""
    raw = _get_bytes(DATASETS_CSV_URL).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def find_dataset_rows(
    index: list[dict],
    skolniva: str,
    dataset: str,
    *,
    fmt: str = "CSV",
    years: list[str] | None = None,
) -> dict[str, str]:
    """`{year: url}` for one `(skolniva, dataset, format)` series, optionally
    restricted to `years`."""
    rows = {}
    for row in index:
        if row.get("skolnivå") != skolniva or row.get("dataset") != dataset or row.get("format") != fmt:
            continue
        year = row.get("år")
        if years is not None and year not in years:
            continue
        rows[year] = row.get("url")
    return rows


def siris_raw_dir(dataset_key: str, root: Path | None = None) -> Path:
    raw_dir = assessments_paths(root)["raw"] / "siris" / dataset_key
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def raw_siris_path(dataset_key: str, year: str, root: Path | None = None) -> Path:
    return siris_raw_dir(dataset_key, root) / f"{year}.csv"


def fetch_siris_dataset(
    dataset_key: str,
    *,
    years: list[str] | None = None,
    force: bool = False,
    root: Path | None = None,
) -> dict:
    """Fetch one confirmed school-grain SIRIS series (`dataset_key` in
    `SIRIS_SCHOOL_GRAIN_DATASETS`) for `years` (default: every year in the
    manifest), skipping a year already on disk unless `force=True`."""
    if dataset_key not in SIRIS_SCHOOL_GRAIN_DATASETS:
        raise ValueError(f"Unknown SIRIS dataset key '{dataset_key}'. Use one of: {list(SIRIS_SCHOOL_GRAIN_DATASETS)}.")
    spec = SIRIS_SCHOOL_GRAIN_DATASETS[dataset_key]

    index = fetch_datasets_index()
    year_urls = find_dataset_rows(index, spec["skolniva"], spec["dataset"], years=years)
    if not year_urls:
        raise RuntimeError(f"No rows found in datasets.csv for {spec} (years={years}).")

    fetched, skipped, failed = [], [], []
    for year, url in sorted(year_urls.items()):
        target_path = raw_siris_path(dataset_key, year, root)
        if target_path.exists() and not force:
            skipped.append(year)
            continue
        try:
            content = _get_bytes(url)
        except RuntimeError:
            failed.append(year)
            continue
        target_path.write_bytes(content)
        fetched.append(year)

    return {
        "dataset_key": dataset_key,
        "years_available": sorted(year_urls),
        "fetched": fetched,
        "skipped": skipped,
        "failed": failed,
    }


def _slugify(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\såäö]", " ", slug, flags=re.UNICODE)
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug.strip("_")


def _parse_numeric_se(raw_value: object) -> float | None:
    """Swedish-locale numeric parsing: decimal comma, `~100`-style
    approximate-value prefix, and the SIRIS missing/suppression sentinels
    (`.`/`..`/`...`/`-`) -> NA. `raw_value` is normally a `str` cell, but a
    column that's blank for every data row can come back from
    `pd.DataFrame.from_records` already coerced to float `NaN` -- handle
    that directly rather than crash on `.strip()`."""
    if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
        return None
    value = str(raw_value).strip()
    if value in _MISSING_SENTINELS:
        return None
    value = value.lstrip("~").replace(",", ".").replace("\xa0", "")
    try:
        return float(value)
    except ValueError:
        return None


def parse_siris_csv(raw_bytes: bytes) -> pd.DataFrame:
    """Parse one SIRIS export: skip the banner, detect a one- or two-row
    header (some datasets prefix a category row over repeated sub-columns,
    e.g. SALSA's "Andel (%) som uppn. kunskapskraven" spanning three
    Faktiskt/Modell/Residual columns), and coerce every non-identity column
    to a Swedish-locale float."""
    text = raw_bytes.decode("utf-8-sig")
    lines = text.splitlines()

    header_index = next((i for i, line in enumerate(lines) if "Skol-enhetskod" in line), None)
    if header_index is None:
        raise ValueError("Could not find a 'Skol-enhetskod' header row -- is this really a school-grain SIRIS export?")

    field_row = next(csv.reader([lines[header_index]], delimiter=";"))
    category_row = None
    if header_index > 0:
        candidate = next(csv.reader([lines[header_index - 1]], delimiter=";"))
        # A category row has real header cells but is not itself the field
        # row -- distinguished by not containing "Skol-enhetskod".
        if any(cell.strip() for cell in candidate) and "Skol-enhetskod" not in candidate:
            category_row = candidate

    column_names = []
    for i, field in enumerate(field_row):
        category = category_row[i].strip() if category_row and i < len(category_row) else ""
        field = field.strip()
        if not field and not category:
            column_names.append(None)
            continue
        combined = f"{category} - {field}" if category and category != field else field
        column_names.append(_slugify(combined))

    data_rows = []
    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        cells = next(csv.reader([line], delimiter=";"))
        data_rows.append(cells)

    records = []
    for cells in data_rows:
        record = {}
        for name, value in zip(column_names, cells):
            if name is None:
                continue
            record[name] = value
        records.append(record)

    df = pd.DataFrame.from_records(records)
    df = df.rename(
        columns={
            "skol_enhetskod": "skolenhetskod",
            "skola": "skola_namn",
            "skolkommun": "kommun_namn",
            "kommun_kod": "kommunkod",
            "typ_av_huvudman": "huvudman_typ",
            "huvudman": "huvudman_namn",
        }
    )

    for column in df.columns:
        if column in IDENTITY_COLUMNS:
            continue
        df[column] = df[column].apply(_parse_numeric_se)

    return df


def preprocess_siris_dataset(dataset_key: str, *, root: Path | None = None) -> pd.DataFrame:
    """Parse every fetched year for one dataset series and stack into one
    long table with a `year` column (from the filename, not file content --
    the `Valt läsår` banner line is not parsed)."""
    frames = []
    for path in sorted(siris_raw_dir(dataset_key, root).glob("*.csv")):
        year = path.stem
        frame = parse_siris_csv(path.read_bytes())
        frame.insert(0, "year", int(year))
        frame.insert(0, "dataset_key", dataset_key)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["dataset_key", "year", "skolenhetskod"])
    return pd.concat(frames, ignore_index=True)


def save_processed_siris(df: pd.DataFrame, dataset_key: str, *, root: Path | None = None) -> str:
    path = assessments_paths(root)["processed"] / f"siris_{dataset_key}.parquet"
    df.to_parquet(path, index=False)
    return str(path)
