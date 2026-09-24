"""Preprocess step for the Florida `neighbourhood` source's four
sub-sources: two tract-boundary vintages + one ZCTA boundary layer (tidy to
GeoParquet, reprojected to this repo's standard EPSG:3087), ACS tract data
(derive rates from the raw variable codes, year-aware education table),
and Zillow ZHVI (wide monthly -> one row per ZIP x calendar year).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

from src.regions.florida.sources.neighbourhood.shared import (
    education_variables,
    MEDIAN_HOUSEHOLD_INCOME_VAR,
    MOBILITY_SAME_HOUSE_VAR,
    MOBILITY_TOTAL_VAR,
    POVERTY_BELOW_VAR,
    POVERTY_TOTAL_VAR,
    TENURE_OWNER_VAR,
    TENURE_TOTAL_VAR,
    processed_acs_path,
    processed_metadata_path,
    processed_tract_boundaries_path,
    processed_zcta_boundaries_path,
    processed_zhvi_path,
    raw_acs_year_path,
)

TARGET_CRS = "EPSG:3087"

# ACS's standard sentinel for a suppressed/not-computed estimate (small
# populations, or a cell structurally undefined for that geography) --
# documented in every ACS technical-documentation appendix. Anything this
# negative is never a real count/dollar estimate.
ACS_SUPPRESSED_SENTINEL = -666666666


def tidy_tract_boundaries(raw: "gpd.GeoDataFrame", vintage: str) -> "gpd.GeoDataFrame":
    """`raw` is whatever `geopandas.read_file` returns for one Census
    cartographic-boundary tract shapefile -- its `GEOID`-like column name
    varies by vintage (`GEOID`/`GEOID20`/...), matched by prefix rather than
    hardcoded."""
    geoid_col = next((c for c in raw.columns if c.upper().startswith("GEOID")), None)
    if geoid_col is None:
        raise ValueError(f"No GEOID-like column in the tract boundary layer (columns: {list(raw.columns)}).")
    out = raw[[geoid_col, "geometry"]].rename(columns={geoid_col: "tract_geoid"}).to_crs(TARGET_CRS)
    out["tract_vintage"] = vintage
    return out


def tidy_zcta_boundaries(raw: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    zip_col = next((c for c in raw.columns if c.upper().startswith("ZCTA5CE")), None)
    if zip_col is None:
        raise ValueError(f"No ZCTA5CE-like column in the ZCTA boundary layer (columns: {list(raw.columns)}).")
    return raw[[zip_col, "geometry"]].rename(columns={zip_col: "zip_code"}).to_crs(TARGET_CRS)


def preprocess_tract_boundaries(shp_path: Path, vintage: str) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    return tidy_tract_boundaries(gpd.read_file(shp_path), vintage)


def preprocess_zcta_boundaries(shp_path: Path) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    return tidy_zcta_boundaries(gpd.read_file(shp_path))


def _suppressed_to_na(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(numeric != ACS_SUPPRESSED_SENTINEL)


def load_raw_acs_files(years: list[int], root: Path | None = None) -> dict[int, Path]:
    return {year: p for year in years if (p := raw_acs_year_path(year, root)).exists()}


def preprocess_acs(files: dict[int, Path]) -> pd.DataFrame:
    """One row per `(tract_geoid, year)`: median household income, poverty
    rate, % owner-occupied, % bachelor's-or-higher (year-aware table, see
    `shared.education_variables`), % moved in the past year. A tract-year
    with a suppressed/undefined denominator gets `NA` for that rate, not a
    divide-by-zero or negative value."""
    columns = [
        "tract_geoid", "year", "median_household_income", "poverty_rate",
        "pct_owner_occupied", "pct_bachelors_plus", "pct_moved_last_year",
    ]
    if not files:
        return pd.DataFrame(columns=columns)

    frames = []
    for year, path in sorted(files.items()):
        raw = pd.read_parquet(path)
        edu = education_variables(year)
        out = pd.DataFrame(
            {
                "tract_geoid": raw["state"].astype(str) + raw["county"].astype(str) + raw["tract"].astype(str),
                "year": year,
                "median_household_income": _suppressed_to_na(raw[MEDIAN_HOUSEHOLD_INCOME_VAR]),
            }
        )
        poverty_total = _suppressed_to_na(raw[POVERTY_TOTAL_VAR])
        poverty_below = _suppressed_to_na(raw[POVERTY_BELOW_VAR])
        out["poverty_rate"] = (poverty_below / poverty_total).where(poverty_total > 0)

        tenure_total = _suppressed_to_na(raw[TENURE_TOTAL_VAR])
        tenure_owner = _suppressed_to_na(raw[TENURE_OWNER_VAR])
        out["pct_owner_occupied"] = (tenure_owner / tenure_total).where(tenure_total > 0)

        edu_total = sum(_suppressed_to_na(raw[c]) for c in edu["total"])
        edu_bachelors_plus = sum(_suppressed_to_na(raw[c]) for c in edu["bachelors_plus"])
        out["pct_bachelors_plus"] = (edu_bachelors_plus / edu_total).where(edu_total > 0)

        mobility_total = _suppressed_to_na(raw[MOBILITY_TOTAL_VAR])
        mobility_same_house = _suppressed_to_na(raw[MOBILITY_SAME_HOUSE_VAR])
        out["pct_moved_last_year"] = (1 - mobility_same_house / mobility_total).where(mobility_total > 0)

        frames.append(out)

    return pd.concat(frames, ignore_index=True)[columns].sort_values(["tract_geoid", "year"]).reset_index(drop=True)


def load_raw_zhvi(root: Path | None = None) -> pd.DataFrame:
    from src.regions.florida.sources.neighbourhood.shared import raw_zhvi_path

    path = raw_zhvi_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data neighbourhood fetch --subsource zhvi` first.")
    return pd.read_parquet(path)


_MONTH_COL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def preprocess_zhvi(raw: pd.DataFrame) -> pd.DataFrame:
    """Melts Zillow's wide `RegionName` (ZIP) x month columns to one row per
    `(zip_code, year)`, keeping the LAST available month's value within
    each calendar year as that year's home-value snapshot (a documented
    choice, not an average — ZHVI is already a smoothed index, so a single
    December-ish snapshot per year is a reasonable "value as of that year"
    figure without re-smoothing an already-smoothed series)."""
    columns = ["zip_code", "year", "zhvi"]
    if raw.empty:
        return pd.DataFrame(columns=columns)

    month_cols = [c for c in raw.columns if _MONTH_COL_RE.match(c)]
    long = raw.melt(id_vars=["RegionName"], value_vars=month_cols, var_name="month", value_name="zhvi")
    long["month"] = pd.to_datetime(long["month"])
    long["year"] = long["month"].dt.year
    long = long.dropna(subset=["zhvi"]).sort_values(["RegionName", "month"])
    annual = long.groupby(["RegionName", "year"], as_index=False).last()[["RegionName", "year", "zhvi"]]
    return annual.rename(columns={"RegionName": "zip_code"})[columns].reset_index(drop=True)


def save_processed(
    tract_boundaries: dict[str, "gpd.GeoDataFrame"],
    zcta_boundaries: "gpd.GeoDataFrame",
    acs: pd.DataFrame,
    zhvi: pd.DataFrame,
    root: Path | None = None,
) -> dict[str, str]:
    import geopandas as gpd

    combined_tracts = gpd.GeoDataFrame(pd.concat(tract_boundaries.values(), ignore_index=True), crs=TARGET_CRS)
    tract_path = processed_tract_boundaries_path(root)
    zcta_path = processed_zcta_boundaries_path(root)
    acs_path = processed_acs_path(root)
    zhvi_path = processed_zhvi_path(root)
    meta_path = processed_metadata_path(root)
    for path in (tract_path, zcta_path, acs_path, zhvi_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    combined_tracts.to_parquet(tract_path, index=False)
    zcta_boundaries.to_parquet(zcta_path, index=False)
    acs.to_parquet(acs_path, index=False)
    zhvi.to_parquet(zhvi_path, index=False)

    provenance = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tract_boundary_rows": {v: int(len(g)) for v, g in tract_boundaries.items()},
        "zcta_boundary_rows": int(len(zcta_boundaries)),
        "acs_rows": int(len(acs)),
        "acs_years": sorted(int(y) for y in acs["year"].dropna().unique()),
        "zhvi_rows": int(len(zhvi)),
        "zhvi_years": sorted(int(y) for y in zhvi["year"].dropna().unique()),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "tract_boundaries": str(tract_path),
        "zcta_boundaries": str(zcta_path),
        "acs": str(acs_path),
        "zhvi": str(zhvi_path),
        "metadata": str(meta_path),
    }


def run_neighbourhood_preprocess(root: Path | None = None) -> dict[str, object]:
    from src.regions.florida.sources.neighbourhood.shared import (
        TRACT_BOUNDARY_URLS,
        raw_tract_boundary_dir,
        raw_zcta_boundary_dir,
    )

    tract_boundaries = {}
    for vintage in TRACT_BOUNDARY_URLS:
        vintage_dir = raw_tract_boundary_dir(vintage, root)
        shp_candidates = list(vintage_dir.glob("*.shp")) if vintage_dir.exists() else []
        if not shp_candidates:
            raise FileNotFoundError(
                f"No tract shapefile for vintage {vintage!r} — run "
                f"`... florida data neighbourhood fetch --subsource tract-boundaries` first."
            )
        tract_boundaries[vintage] = preprocess_tract_boundaries(shp_candidates[0], vintage)

    zcta_dir = raw_zcta_boundary_dir(root)
    zcta_shp = list(zcta_dir.glob("*.shp")) if zcta_dir.exists() else []
    if not zcta_shp:
        raise FileNotFoundError("No ZCTA shapefile — run `... florida data neighbourhood fetch --subsource zcta-boundaries` first.")
    zcta_boundaries = preprocess_zcta_boundaries(zcta_shp[0])

    from src.regions.florida.sources.neighbourhood.shared import ACS_FIRST_YEAR

    acs_files = load_raw_acs_files(list(range(ACS_FIRST_YEAR, dt.date.today().year + 1)), root)
    acs = preprocess_acs(acs_files)
    zhvi = preprocess_zhvi(load_raw_zhvi(root))

    saved = save_processed(tract_boundaries, zcta_boundaries, acs, zhvi, root)
    return {
        "tract_boundary_rows": {v: int(len(g)) for v, g in tract_boundaries.items()},
        "zcta_boundary_rows": int(len(zcta_boundaries)),
        "acs_rows": int(len(acs)),
        "zhvi_rows": int(len(zhvi)),
        "saved": saved,
    }
