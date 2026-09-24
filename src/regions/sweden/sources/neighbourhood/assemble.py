"""Match schools to their containing DeSO 2018 area and attach that area's
income/education/employment time series -- Covariate Cluster F
(`docs/data/sweden/covariates.md`), the neighbourhood-composition/sorting
diagnostic for the barrier event study.

`REQUIRES` `schools preprocess` (`schools.geojson`) and this source's own
`preprocess-boundaries`/`preprocess-income`/`preprocess-education`/
`preprocess-employment` to already exist.

**Point-in-polygon, not nearest-segment** -- the one genuinely different
design point from every other Sweden covariate module (`traffic`,
`noise_barriers`, `road_network`), which all match schools to the nearest
*line* feature. DeSO tiles the whole country with no gaps, so every
geocoded school falls inside exactly one DeSO polygon (barring a
geocoding error placing it outside Sweden entirely) -- a
`gpd.sjoin(predicate="within")` match, not a distance threshold.

The DeSO match itself is static (one boundary vintage, doesn't vary by
year); all the year variation lives in the three subsource tables, each
joined by a plain `(desokod, year)` merge -- no interval-overlap logic
needed here, unlike `panel/assemble.py::attach_traffic`, since DeSO
boundaries (within one vintage) don't move year to year the way NVDB's
segment-level `Betraktelsedatum` windows do.

**The three subsources have different real coverage windows** (income
2011-2023, education 2015-2023, employment 2020-2023 -- see
`preprocess.py`'s per-table docstrings for why each stops at 2023, not
each table's own nominal end year) -- `merge_deso_panels` does an
**outer** merge on `(desokod, year)`, so a year covered by income alone
gets real `NA` for education/employment columns, not a dropped row."""
from __future__ import annotations

from functools import reduce
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources.neighbourhood.shared import (
    assembled_school_neighbourhood_path,
    processed_deso_boundaries_path,
    processed_education_path,
    processed_employment_path,
    processed_income_path,
)
from src.regions.sweden.sources.schools.assemble import load_geocoded_schools

METRIC_CRS = "EPSG:3006"  # SWEREF99 TM


def load_processed_deso_boundaries(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_deso_boundaries_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data neighbourhood preprocess-boundaries` first.")
    return gpd.read_parquet(path)


def load_processed_income(root: Path | None = None) -> pd.DataFrame:
    path = processed_income_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data neighbourhood preprocess-income` first.")
    return pd.read_parquet(path)


def load_processed_education(root: Path | None = None) -> pd.DataFrame:
    path = processed_education_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data neighbourhood preprocess-education` first.")
    return pd.read_parquet(path)


def load_processed_employment(root: Path | None = None) -> pd.DataFrame:
    path = processed_employment_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data neighbourhood preprocess-employment` first.")
    return pd.read_parquet(path)


def match_schools_to_deso(schools_gdf: gpd.GeoDataFrame, deso_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """One row per school: its containing DeSO's `desokod` (and
    `kommunkod`/`lanskod` for convenience). A school outside every DeSO
    polygon (a geocoding error, not expected for real Sweden coordinates)
    gets `NA`, not dropped -- same "no match is a real value" convention
    as every other assemble module in this pipeline."""
    schools_m = schools_gdf[["skolenhetskod", "geometry"]].to_crs(METRIC_CRS)
    deso_m = deso_gdf.to_crs(METRIC_CRS)

    joined = gpd.sjoin(schools_m, deso_m, how="left", predicate="within")
    joined = joined.drop_duplicates(subset="skolenhetskod", keep="first")
    return joined[["skolenhetskod", "desokod", "kommunkod", "lanskod"]].reset_index(drop=True)


def merge_deso_panels(income: pd.DataFrame, education: pd.DataFrame, employment: pd.DataFrame) -> pd.DataFrame:
    """Outer-merge the three DeSO-grain time series on `(desokod, year)` --
    each has a different real coverage window (see module docstring), so
    a year present in one but not another gets real `NA` in the other's
    columns, not a dropped row."""
    return reduce(lambda left, right: left.merge(right, on=["desokod", "year"], how="outer"), [income, education, employment])


def build_school_neighbourhood_panel(school_deso_match: pd.DataFrame, deso_panel: pd.DataFrame) -> pd.DataFrame:
    """Broadcast each matched DeSO's merged time series onto its school --
    one output row per `(school, year)` for a matched school's every real
    covered year (across any of the three subsources), one row (all-`NA`)
    for an unmatched school."""
    value_columns = [c for c in deso_panel.columns if c not in ("desokod", "year")]
    matched = school_deso_match.dropna(subset=["desokod"])
    unmatched = school_deso_match[school_deso_match["desokod"].isna()]

    joined = matched.merge(deso_panel, on="desokod", how="left")

    if not unmatched.empty:
        unmatched = unmatched.assign(year=pd.NA, **{col: pd.NA for col in value_columns})
        joined = pd.concat([joined, unmatched[[*school_deso_match.columns, "year", *value_columns]]])

    return joined.reset_index(drop=True)


def save_school_neighbourhood(school_neighbourhood: pd.DataFrame, root: Path | None = None) -> str:
    path = assembled_school_neighbourhood_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    school_neighbourhood.to_parquet(path, index=False)
    return str(path)


def run_neighbourhood_assemble(root: Path | None = None) -> dict[str, object]:
    schools_gdf = load_geocoded_schools(root)
    deso_gdf = load_processed_deso_boundaries(root)
    income = load_processed_income(root)
    education = load_processed_education(root)
    employment = load_processed_employment(root)

    school_deso_match = match_schools_to_deso(schools_gdf, deso_gdf)
    deso_panel = merge_deso_panels(income, education, employment)
    school_neighbourhood = build_school_neighbourhood_panel(school_deso_match, deso_panel)
    saved_path = save_school_neighbourhood(school_neighbourhood, root)

    matched = school_deso_match["desokod"].notna()
    return {
        "n_schools": int(len(school_deso_match)),
        "n_matched": int(matched.sum()),
        "n_unmatched": int((~matched).sum()),
        "n_panel_rows": int(len(school_neighbourhood)),
        "saved": saved_path,
    }
