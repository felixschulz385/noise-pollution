"""`neighbourhood` preprocess -- ACS rate derivation (incl. the year-aware
education table switch), ZHVI wide-to-long collapsing, and boundary tidying
-- exercised on synthetic data, no local data or network needed."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from src.regions.florida.sources.neighbourhood.preprocess import (
    ACS_SUPPRESSED_SENTINEL,
    preprocess_acs,
    preprocess_zhvi,
    tidy_tract_boundaries,
    tidy_zcta_boundaries,
)


def _acs_row(year, **overrides):
    row = {
        "NAME": "Census Tract 1, Alachua County, Florida",
        "state": "12", "county": "001", "tract": "000100",
        "B19013_001E": "55000",
        "B17001_001E": "1000", "B17001_002E": "150",
        "B25003_001E": "400", "B25003_002E": "300",
        "B07003_001E": "1000", "B07003_004E": "800",
    }
    if year >= 2012:
        row.update({"B15003_001E": "700", "B15003_022E": "100", "B15003_023E": "50", "B15003_024E": "10", "B15003_025E": "5"})
    else:
        row.update({
            "B15002_002E": "350", "B15002_019E": "350",
            "B15002_015E": "50", "B15002_016E": "20", "B15002_017E": "5", "B15002_018E": "2",
            "B15002_032E": "45", "B15002_033E": "18", "B15002_034E": "4", "B15002_035E": "1",
        })
    row.update(overrides)
    return row


def _write_acs_parquet(tmp_path, year, rows):
    path = tmp_path / f"{year}.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_preprocess_acs_derives_rates_modern_table(tmp_path):
    path = _write_acs_parquet(tmp_path, 2022, [_acs_row(2022)])
    out = preprocess_acs({2022: path})

    assert len(out) == 1
    row = out.iloc[0]
    assert row["tract_geoid"] == "12001000100"
    assert row["median_household_income"] == 55000.0
    assert row["poverty_rate"] == pytest.approx(0.15)
    assert row["pct_owner_occupied"] == pytest.approx(0.75)
    assert row["pct_bachelors_plus"] == pytest.approx((100 + 50 + 10 + 5) / 700)
    assert row["pct_moved_last_year"] == pytest.approx(0.2)


def test_preprocess_acs_uses_b15002_before_2012(tmp_path):
    path = _write_acs_parquet(tmp_path, 2011, [_acs_row(2011)])
    out = preprocess_acs({2011: path})

    row = out.iloc[0]
    male_total, female_total = 350, 350
    male_ba_plus = 50 + 20 + 5 + 2
    female_ba_plus = 45 + 18 + 4 + 1
    assert row["pct_bachelors_plus"] == pytest.approx((male_ba_plus + female_ba_plus) / (male_total + female_total))


def test_preprocess_acs_suppressed_sentinel_becomes_na(tmp_path):
    path = _write_acs_parquet(tmp_path, 2022, [_acs_row(2022, B19013_001E=str(ACS_SUPPRESSED_SENTINEL), B17001_001E="0")])
    out = preprocess_acs({2022: path})

    row = out.iloc[0]
    assert pd.isna(row["median_household_income"])
    assert pd.isna(row["poverty_rate"])  # zero denominator, not a divide-by-zero


def test_preprocess_acs_empty_when_no_files():
    out = preprocess_acs({})
    assert out.empty
    assert "pct_bachelors_plus" in out.columns


def test_preprocess_zhvi_keeps_last_month_per_year():
    raw = pd.DataFrame(
        {
            "RegionName": ["32601", "32601", "32601", "33101"],
            "2020-01-31": [200000.0, None, None, 300000.0],
            "2020-06-30": [None, 210000.0, None, None],
            "2020-12-31": [None, None, 215000.0, None],
        }
    )
    out = preprocess_zhvi(raw)

    row = out[(out["zip_code"] == "32601") & (out["year"] == 2020)].iloc[0]
    assert row["zhvi"] == 215000.0
    other = out[out["zip_code"] == "33101"].iloc[0]
    assert other["zhvi"] == 300000.0


def test_preprocess_zhvi_empty_input():
    out = preprocess_zhvi(pd.DataFrame(columns=["RegionName"]))
    assert out.empty
    assert list(out.columns) == ["zip_code", "year", "zhvi"]


def test_tidy_tract_boundaries_finds_geoid_by_prefix():
    raw = gpd.GeoDataFrame(
        {"GEOID20": ["12001000100"], "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]},
        crs="EPSG:4269",
    )
    out = tidy_tract_boundaries(raw, "2020")
    assert list(out["tract_geoid"]) == ["12001000100"]
    assert (out["tract_vintage"] == "2020").all()
    assert out.crs.to_string() == "EPSG:3087"


def test_tidy_zcta_boundaries_finds_zip_by_prefix():
    raw = gpd.GeoDataFrame(
        {"ZCTA5CE20": ["32601"], "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]},
        crs="EPSG:4269",
    )
    out = tidy_zcta_boundaries(raw)
    assert list(out["zip_code"]) == ["32601"]
