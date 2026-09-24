"""Build the tidy `neighbourhood` layers from the raw DeSO 2018 boundary
pages and income batches `fetch.py` saved to disk.

Real schema, checked live 2026-09-17: a DeSO 2018 WFS feature carries
`desokod`/`regsokod`/`lanskod`/`kommunkod` plus `version`/
`referensdatum`/`objektidentitet` (kept as informational, not used
downstream). `EPSG:3006` (SWEREF99 TM), same CRS convention as every
other Sweden geospatial layer in this pipeline.

The income batches are one json-stat2 payload per `Region` batch, `Tid`
(year) as the only other free dimension (the query already fixes
`Inkomstkomponenter`/`Kon`/`ContentsCode` to single values) --
`flatten_jsonstat2` is reused directly from `assessments/kvalitetssystem.py`
rather than reimplemented, since it's a generic json-stat2 flattener with
no assessments-specific logic in it.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources.assessments.kvalitetssystem import flatten_jsonstat2
from src.regions.sweden.sources.neighbourhood.shared import (
    processed_deso_boundaries_path,
    processed_education_path,
    processed_employment_path,
    processed_income_path,
)


BOUNDARY_COLUMNS = ["desokod", "regsokod", "lanskod", "kommunkod"]

# A region code shaped like a DeSO2018 code, e.g. "1273C1050" or
# "0840A0010" -- 4-digit kommunkod + SCB's area-density letter (**A/B/C,
# not just "C"** -- a real bug caught 2026-09-17 by live-testing against
# real boundary codes: an earlier version of this pattern hardcoded "C"
# and silently dropped every real DeSO whose density tier is A or B, the
# majority of a live 30-area sample) + 4 digits. Excludes the co-mingled
# `_DeSO2025`-suffixed codes, RegSO codes (`...R0NN`), bare kommun codes,
# and "00" (national total) that `Tab2InkDesoRegso`'s own `Region`
# dimension also carries.
_DESO2018_CODE_PATTERN = r"^\d{4}[ABC]\d{4}$"


def preprocess_deso_boundaries(pages: list[dict]) -> gpd.GeoDataFrame:
    """Union every WFS page's features into one GeoDataFrame, deduplicated
    on `desokod` (pages are fetched by offset, not expected to overlap,
    but a re-fetched/force page could)."""
    frames = [gpd.GeoDataFrame.from_features(page["features"], crs="EPSG:3006") for page in pages if page["features"]]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset="desokod").reset_index(drop=True)
    return gpd.GeoDataFrame(combined[[*BOUNDARY_COLUMNS, "geometry"]], geometry="geometry", crs="EPSG:3006")


def save_processed_deso_boundaries(boundaries: gpd.GeoDataFrame, root: Path | None = None) -> str:
    path = processed_deso_boundaries_path(root)
    boundaries.to_parquet(path, index=False)
    return str(path)


def run_deso_boundaries_preprocess(root: Path | None = None) -> dict[str, object]:
    from src.regions.sweden.sources.neighbourhood.fetch import load_boundary_pages

    pages = load_boundary_pages(root)
    if not pages:
        raise FileNotFoundError("No boundary pages found -- run `sweden data neighbourhood fetch-boundaries` first.")
    boundaries = preprocess_deso_boundaries(pages)
    saved_path = save_processed_deso_boundaries(boundaries, root)
    return {
        "n_pages": len(pages),
        "n_deso_areas": int(len(boundaries)),
        "n_distinct_kommun": int(boundaries["kommunkod"].nunique()),
        "saved": saved_path,
    }


def preprocess_income(batches: list[dict]) -> pd.DataFrame:
    """One row per `(desokod, year)` -- mean net income, thousand SEK.
    Rows whose `Region` code isn't DeSO2018-shaped (RegSO/kommun/national/
    DeSO2025 codes also present in the raw PxWeb response's dimension, but
    never requested by `fetch.py` -- kept as a defensive filter, not
    assumed absent) are dropped.

    **Real coverage is 2011-2023, not 2011-2024** despite the table's own
    nominal year range -- confirmed live 2026-09-17: SCB's own table note
    states referensår 2024 onward is published under the *new* DeSO2025
    codes only ("Från och med referensåret 2024 publiceras en ny
    uppdaterad version av DeSO och RegSO"), and a real query against a
    DeSO2018 code returned a genuine `None`/`".."` (suppressed/
    unavailable) value for 2024, not a real number. `value` is coerced
    with `errors="coerce"`, so this shows up as a real `NaN`, not a
    silently wrong 0 or a crash."""
    rows: list[dict] = []
    for batch in batches:
        rows.extend(flatten_jsonstat2(batch))
    columns = ["desokod", "year", "mean_net_income_tkr"]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame.from_records(rows)
    df = df.rename(columns={"Region_code": "desokod", "Tid_code": "year"})
    df = df[df["desokod"].str.match(_DESO2018_CODE_PATTERN)]
    df["year"] = df["year"].astype(int)
    df["mean_net_income_tkr"] = pd.to_numeric(df["value"], errors="coerce")
    return df[columns].sort_values(["desokod", "year"]).reset_index(drop=True)


def save_processed_income(income: pd.DataFrame, root: Path | None = None) -> str:
    path = processed_income_path(root)
    income.to_parquet(path, index=False)
    return str(path)


def run_income_preprocess(root: Path | None = None) -> dict[str, object]:
    from src.regions.sweden.sources.neighbourhood.fetch import load_income_batches

    batches = load_income_batches(root)
    if not batches:
        raise FileNotFoundError("No income batches found -- run `sweden data neighbourhood fetch-income` first.")
    income = preprocess_income(batches)
    saved_path = save_processed_income(income, root)
    return {
        "n_batches": len(batches),
        "n_rows": int(len(income)),
        "n_distinct_deso": int(income["desokod"].nunique()),
        "year_range": [int(income["year"].min()), int(income["year"].max())] if len(income) else None,
        "saved": saved_path,
    }


# The 5 `UtbildningsNiva` category codes -> a readable column name. Sum of
# all 5 per (desokod, year) is the table's own real population total (this
# table's `ContentsCode` content is a plain "Befolkning" count per level,
# not a rate) -- there is no separate "total" row to cross-check against,
# unlike the employment table below.
_EDUCATION_LEVEL_COLUMNS = {
    "21": "pop_forgymnasial",
    "3+4": "pop_gymnasial",
    "5": "pop_eftergymnasial_kort",
    "6": "pop_eftergymnasial_lang",
    "US": "pop_uppgift_saknas",
}


def preprocess_education(batches: list[dict]) -> pd.DataFrame:
    """One row per `(desokod, year)`: population count per education
    level (`UtbSUNBefDesoRegso`'s own grain), plus `total_pop` (sum of all
    5 levels) and `share_eftergymnasial` (post-secondary share of
    `total_pop`).

    **Real coverage is 2015-2023 only** -- `UtbSUNBefDesoRegso` itself is
    frozen ("uppdateras ej") at 2023; its 2024-2025 successor table
    (`UtbSUNBefDesoRegsoN`) uses **only** `_DeSO2025`-suffixed region
    codes with no DeSO2018 alternative at all (confirmed live 2026-09-17
    from its own metadata) -- a harder break than income/employment's
    "DeSO2018 code exists but is suppressed" shape, so this v1 build
    doesn't fetch that successor table."""
    rows: list[dict] = []
    for batch in batches:
        rows.extend(flatten_jsonstat2(batch))
    value_columns = [*_EDUCATION_LEVEL_COLUMNS.values(), "total_pop", "share_eftergymnasial"]
    columns = ["desokod", "year", *value_columns]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame.from_records(rows)
    df = df.rename(columns={"Region_code": "desokod", "Tid_code": "year"})
    df = df[df["desokod"].str.match(_DESO2018_CODE_PATTERN)]
    df["year"] = df["year"].astype(int)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # `dropna=False` -- pivot_table's default silently drops any
    # (desokod, year) whose every pivoted column is NaN (confirmed live
    # in the employment table's real 2024 case, same shape here
    # defensively), which would turn a real "fully suppressed year" into
    # a missing row instead of a row of real `NaN`s.
    wide = df.pivot_table(
        index=["desokod", "year"], columns="UtbildningsNiva_code", values="value", aggfunc="first", dropna=False
    )
    wide = wide.rename(columns=_EDUCATION_LEVEL_COLUMNS).reset_index()
    for column in _EDUCATION_LEVEL_COLUMNS.values():
        if column not in wide.columns:
            wide[column] = pd.NA

    level_columns = list(_EDUCATION_LEVEL_COLUMNS.values())
    wide["total_pop"] = wide[level_columns].sum(axis=1, min_count=1)
    wide["share_eftergymnasial"] = (
        wide["pop_eftergymnasial_kort"] + wide["pop_eftergymnasial_lang"]
    ) / wide["total_pop"]

    return wide[columns].sort_values(["desokod", "year"]).reset_index(drop=True)


def save_processed_education(education: pd.DataFrame, root: Path | None = None) -> str:
    path = processed_education_path(root)
    education.to_parquet(path, index=False)
    return str(path)


def run_education_preprocess(root: Path | None = None) -> dict[str, object]:
    from src.regions.sweden.sources.neighbourhood.fetch import load_education_batches

    batches = load_education_batches(root)
    if not batches:
        raise FileNotFoundError("No education batches found -- run `sweden data neighbourhood fetch-education` first.")
    education = preprocess_education(batches)
    saved_path = save_processed_education(education, root)
    return {
        "n_batches": len(batches),
        "n_rows": int(len(education)),
        "n_distinct_deso": int(education["desokod"].nunique()),
        "year_range": [int(education["year"].min()), int(education["year"].max())] if len(education) else None,
        "saved": saved_path,
    }


# "antal sysselsatta" (employed count) / "antal totalt" (total population
# in this age/sex/region cell) -- confirmed live from the table's metadata.
_EMPLOYMENT_CONTENT_COLUMNS = {"0000089X": "antal_sysselsatta", "0000089Y": "antal_totalt"}


def preprocess_employment(batches: list[dict]) -> pd.DataFrame:
    """One row per `(desokod, year)`: employed count, total count, and
    `employment_rate` (`antal_sysselsatta / antal_totalt`), age 16-64,
    both sexes (the query fixes `Kon`/`Alder`, so those don't vary here).

    **Real coverage is 2020-2023, not the nominal 2020-2024** -- same
    "one year short" shape as income (confirmed live 2026-09-17: a real
    DeSO2018 code returns a genuine suppressed value for 2024, since
    `ArRegDesoStatusN`'s DeSO-tier codes for 2024 exist under the new
    DeSO2025 vintage)."""
    rows: list[dict] = []
    for batch in batches:
        rows.extend(flatten_jsonstat2(batch))
    columns = ["desokod", "year", "antal_sysselsatta", "antal_totalt", "employment_rate"]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame.from_records(rows)
    df = df.rename(columns={"Region_code": "desokod", "Tid_code": "year"})
    df = df[df["desokod"].str.match(_DESO2018_CODE_PATTERN)]
    df["year"] = df["year"].astype(int)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # `dropna=False` -- see `preprocess_education`'s comment on the same
    # pivot_table call; the real 2024 case for this table (every content
    # code suppressed for a DeSO2018 code) is exactly what this guards.
    wide = df.pivot_table(
        index=["desokod", "year"], columns="ContentsCode_code", values="value", aggfunc="first", dropna=False
    )
    wide = wide.rename(columns=_EMPLOYMENT_CONTENT_COLUMNS).reset_index()
    for column in _EMPLOYMENT_CONTENT_COLUMNS.values():
        if column not in wide.columns:
            wide[column] = pd.NA

    wide["employment_rate"] = wide["antal_sysselsatta"] / wide["antal_totalt"]
    return wide[columns].sort_values(["desokod", "year"]).reset_index(drop=True)


def save_processed_employment(employment: pd.DataFrame, root: Path | None = None) -> str:
    path = processed_employment_path(root)
    employment.to_parquet(path, index=False)
    return str(path)


def run_employment_preprocess(root: Path | None = None) -> dict[str, object]:
    from src.regions.sweden.sources.neighbourhood.fetch import load_employment_batches

    batches = load_employment_batches(root)
    if not batches:
        raise FileNotFoundError(
            "No employment batches found -- run `sweden data neighbourhood fetch-employment` first."
        )
    employment = preprocess_employment(batches)
    saved_path = save_processed_employment(employment, root)
    return {
        "n_batches": len(batches),
        "n_rows": int(len(employment)),
        "n_distinct_deso": int(employment["desokod"].nunique()),
        "year_range": [int(employment["year"].min()), int(employment["year"].max())] if len(employment) else None,
        "saved": saved_path,
    }
