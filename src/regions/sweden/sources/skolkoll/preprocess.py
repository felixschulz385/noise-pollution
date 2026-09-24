"""Parse Skolkoll's `schools.csv` into a tidy, geocoded table.

Real format, confirmed live 2026-09-23 (not assumed from the landing
page): UTF-8 with a BOM, `;`-delimited, a contiguous block of `#`-prefixed
metadata/variable-description lines before the real header row (no inline
`#` comments seen inside the data rows themselves, so stripping only that
leading block -- not every `#`-containing line -- is the safe way to skip
it; pandas' own `comment="#"` option would also truncate any data value
that happens to contain a literal `#`). Decimal values use a period, not a
comma -- the opposite convention from this repo's other Skolverket source
(SIRIS's archived exports use a decimal comma, see `assessments/siris.py`),
worth remembering if the two ever get parsed side by side.

`schoolCode` is Skolverket's own `api.skolverket.se` id (the modern
8-digit `skolenhetskod` format) for `GR`/`GY`/`VUX`-type rows; preschool
(`FORSK`) rows carry a Skolkoll-synthetic `forsk-######` code instead (no
real Skolverket id exists for those) -- left as-is, not filtered out here,
since `panel/vanished_recovery.py`'s exact-id join against SIRIS's
`skolenhetskod`s naturally never matches a synthetic code.

Renamed to this repo's existing Swedish-term column names where a direct
Skolenhetsregistret analogue exists (`skolenhetskod`, `namn`, `kommunkod`,
`kommun_namn`, `wgs84_lat`/`wgs84_lng`) so a future join reads the same
way it would against `schools.geojson` -- but `status` is deliberately
kept in Skolkoll's own raw vocabulary (`AKTIV`/`VILANDE`/`UPPHORT`/
`PLANERAD`, uppercase) rather than recased to match the registry's own
`Aktiv`/`Vilande`/`Planerad`, so it stays visually obvious downstream that
a row's status came from Skolkoll, not from Skolverket's live register
directly -- the whole point of this source is that Skolkoll retains
`UPPHORT` (ceased) units the live register purges outright, so collapsing
that distinction away would erase the one thing this source adds.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.regions.sweden.sources.skolkoll.shared import processed_skolkoll_path, raw_schools_csv_path

COLUMN_RENAME = {
    "schoolCode": "skolenhetskod",
    "schoolName": "namn",
    "municipalityName": "kommun_namn",
    "municipalityCode": "kommunkod",
    "county": "lan",
    "providerName": "huvudman_namn",
    "schoolForms": "skolformer",
    "status": "status",
    "lat": "wgs84_lat",
    "lng": "wgs84_lng",
    "totalPupils": "total_pupils",
    "pupilsPerTeacher": "pupils_per_teacher",
    "qualifiedTeachersPct": "qualified_teachers_pct",
    "meritValueYear9": "merit_value_year9",
    "eligibleUpperSecondaryPct": "eligible_upper_secondary_pct",
    "_source": "source",
    "_period": "period",
    "_qualityClass": "quality_class",
}

NUMERIC_COLUMNS = [
    "wgs84_lat",
    "wgs84_lng",
    "total_pupils",
    "pupils_per_teacher",
    "qualified_teachers_pct",
    "merit_value_year9",
    "eligible_upper_secondary_pct",
]

VERSION_RE = re.compile(r"^#\s*Version:\s*(\S+)", re.MULTILINE)


def extract_version(raw_text: str) -> str | None:
    match = VERSION_RE.search(raw_text)
    return match.group(1) if match else None


def _strip_leading_comment_block(raw_text: str) -> str:
    lines = raw_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#"):
            return "\n".join(lines[i:])
    raise ValueError("schools.csv has no real header row (every line is blank or a '#' comment)")


def parse_point(row: pd.Series) -> Point | None:
    lat, lng = row.get("wgs84_lat"), row.get("wgs84_lng")
    if pd.isna(lat) or pd.isna(lng):
        return None
    try:
        return Point(float(lng), float(lat))
    except (TypeError, ValueError):
        return None


def parse_schools_csv(raw_text: str) -> pd.DataFrame:
    body = _strip_leading_comment_block(raw_text)
    df = pd.read_csv(io.StringIO(body), sep=";", dtype=str)
    df = df.rename(columns=COLUMN_RENAME)
    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def preprocess_skolkoll_schools(raw_text: str) -> gpd.GeoDataFrame:
    df = parse_schools_csv(raw_text)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=df.apply(parse_point, axis=1) if len(df) else [],
        crs="EPSG:4326",
    )
    return gdf.sort_values("skolenhetskod", na_position="last").reset_index(drop=True)


def load_raw_schools_csv(root: Path | None = None) -> str:
    path = raw_schools_csv_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data skolkoll fetch` first.")
    return path.read_text(encoding="utf-8-sig")


def save_processed_skolkoll(schools_gdf: gpd.GeoDataFrame, root: Path | None = None) -> str:
    path = processed_skolkoll_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    schools_gdf.to_parquet(path, index=False)
    return str(path)


def load_processed_skolkoll(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_skolkoll_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data skolkoll preprocess` first.")
    return gpd.read_parquet(path)


def run_skolkoll_preprocess(root: Path | None = None) -> dict:
    raw_text = load_raw_schools_csv(root)
    version = extract_version(raw_text)
    schools_gdf = preprocess_skolkoll_schools(raw_text)
    saved = save_processed_skolkoll(schools_gdf, root)
    return {
        "version": version,
        "rows": int(len(schools_gdf)),
        "with_real_skolenhetskod": int(schools_gdf["skolenhetskod"].str.fullmatch(r"\d{8}").fillna(False).sum()),
        "geocoded": int(schools_gdf.geometry.notna().sum()),
        "status_counts": schools_gdf["status"].value_counts(dropna=False).to_dict(),
        "saved": saved,
    }
