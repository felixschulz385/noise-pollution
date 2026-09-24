"""Raw-stage fetch for the Florida `neighbourhood` source's four
sub-sources: two Census cartographic tract-boundary vintages, one national
ZCTA boundary layer, the Zillow ZHVI CSV, and per-year ACS 5-year tract
data (requires `CENSUS_API_KEY`, see `shared.py`).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from src.regions.florida.sources._http import download_to_file, get_json
from src.regions.florida.sources.neighbourhood.shared import (
    ACS_FIRST_YEAR,
    ACS_LAST_KNOWN_YEAR,
    TRACT_BOUNDARY_URLS,
    ZCTA_BOUNDARY_URL,
    ZHVI_ZIP_URL,
    acs_tract_url,
    raw_acs_year_path,
    raw_tract_boundary_dir,
    raw_zcta_boundary_dir,
    raw_zhvi_path,
    require_census_api_key,
)


def _extract_shapefile(zip_path: Path, target_dir: Path) -> Path:
    """Census cartographic-boundary zips are flat (one shapefile's parts at
    the archive root, no nested folder or stem ambiguity like FGDL's
    multi-release archives) -- extract every member and locate the `.shp`."""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        archive.extractall(target_dir)
    shp_candidates = list(target_dir.glob("*.shp"))
    if not shp_candidates:
        raise RuntimeError(f"No .shp found in {zip_path} (extracted to {target_dir}).")
    return shp_candidates[0]


def fetch_tract_boundaries(vintage: str, *, root: Path | None = None, keep_zip: bool = False) -> dict[str, object]:
    if vintage not in TRACT_BOUNDARY_URLS:
        raise ValueError(f"Unknown tract vintage {vintage!r}; expected one of {sorted(TRACT_BOUNDARY_URLS)}.")
    url = TRACT_BOUNDARY_URLS[vintage]
    target_dir = raw_tract_boundary_dir(vintage, root)
    zip_path = target_dir.parent / f"{target_dir.name}.zip"
    download_to_file(url, zip_path)
    shp_path = _extract_shapefile(zip_path, target_dir)
    if not keep_zip:
        zip_path.unlink()
    return {"vintage": vintage, "source_url": url, "shapefile_path": str(shp_path)}


def fetch_zcta_boundaries(*, root: Path | None = None, keep_zip: bool = False) -> dict[str, object]:
    target_dir = raw_zcta_boundary_dir(root)
    zip_path = target_dir.parent / f"{target_dir.name}.zip"
    download_to_file(ZCTA_BOUNDARY_URL, zip_path)
    shp_path = _extract_shapefile(zip_path, target_dir)
    if not keep_zip:
        zip_path.unlink()
    return {"source_url": ZCTA_BOUNDARY_URL, "shapefile_path": str(shp_path)}


def fetch_zhvi(*, root: Path | None = None) -> dict[str, object]:
    """Downloads Zillow's national ZIP-level ZHVI CSV (~120MB) and keeps
    only Florida rows -- the raw file is discarded after filtering, same
    "don't keep more than needed" posture `traffic/fetch.py` takes with
    FGDL's full releases."""
    tmp_path = raw_zhvi_path(root).with_suffix(".csv.tmp")
    download_to_file(ZHVI_ZIP_URL, tmp_path, timeout=600)
    raw = pd.read_csv(tmp_path, dtype={"RegionName": str})
    florida = raw[raw["State"] == "FL"].reset_index(drop=True)
    dest = raw_zhvi_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    florida.to_parquet(dest, index=False)
    tmp_path.unlink()
    return {"source_url": ZHVI_ZIP_URL, "florida_rows": int(len(florida)), "parquet": str(dest)}


def fetch_acs(years: list[int] | None = None, *, root: Path | None = None) -> dict[str, object]:
    api_key = require_census_api_key()
    target_years = sorted(years) if years else list(range(ACS_FIRST_YEAR, ACS_LAST_KNOWN_YEAR + 1))
    fetched: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for year in target_years:
        dest = raw_acs_year_path(year, root)
        if dest.exists():
            skipped.append(str(dest))
            continue
        try:
            payload = get_json(acs_tract_url(year, api_key))
        except RuntimeError as exc:
            # The query URL (embedded in get_json's own error text on a
            # non-2xx response) carries `key=<api_key>` as a plain query
            # param -- redact it before this ever reaches a returned dict,
            # printed output, or a saved report.
            errors.append(f"{year}: " + str(exc).replace(api_key, "REDACTED"))
            continue
        header, *rows = payload
        df = pd.DataFrame(rows, columns=header)
        df["year"] = year
        dest.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(dest, index=False)
        fetched.append(str(dest))

    return {"years_targeted": target_years, "fetched": fetched, "already_cached": skipped, "errors": errors}
