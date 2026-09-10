"""`preprocess_barriers` filtering, tidying and unit rules, exercised on a
synthetic in-memory geodatabase-shaped frame (no local data needed)."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from src.regions.florida.sources.noise_barriers.preprocess import (
    BUILT_YEAR_MAX,
    BUILT_YEAR_MIN,
    TARGET_EPSG,
    preprocess_barriers,
)

FT_TO_M = 0.3048


def _raw(rows):
    """Build a GeoDataFrame with the raw FGDL column names used by preprocess."""
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{TARGET_EPSG}")


BASE_COLS = dict(
    FLAG="V",
    FDOT_DISTR="6",
    FED_ROUTE="SR9",
    FED_COUNTY="Miami-Dade",
    FED_NAC="B",
    FED_ANR=7.0,
    BEN_RCPTRS=10,
    TOT_RCPTRS=12,
    FED_MATERL="CONCRETE",
    FHWA_SUB_NOTES="EXISTING",
    FED_HEIGHT=20.0,
    FED_LENGTH=100.0,
    SHAPE_Length=30.5,
)


def _row(gcid, type_, geom, **overrides):
    row = {"GCID": gcid, "TYPE": type_, "FED_YRCON": 2010, "geometry": geom, **BASE_COLS}
    row.update(overrides)
    return row


def test_category_mapping_and_type_filter():
    line = LineString([(0, 0), (10, 0)])
    gdf = _raw([
        _row("a", "CONSTRUCTED BARRIERS", line),
        _row("b", "REPLACED BARRIERS", LineString([(0, 1), (10, 1)])),
        _row("c", "PRIVATE WALL", LineString([(0, 2), (10, 2)])),
        _row("d", "PERIMETER WALL", LineString([(0, 3), (10, 3)])),
        _row("e", "RECOMMENDED BARRIERS", LineString([(0, 4), (10, 4)])),
        _row("f", "REMOVED BARRIERS", LineString([(0, 5), (10, 5)])),
    ])
    out = preprocess_barriers(gdf)

    assert set(out["gcid"]) == {"a", "b", "c", "d"}  # study-only / removed dropped
    assert dict(zip(out["gcid"], out["category"])) == {
        "a": "fdot_barrier",
        "b": "fdot_barrier",
        "c": "other_wall",
        "d": "other_wall",
    }
    assert out.crs.to_epsg() == TARGET_EPSG


def test_built_year_window_and_sentinels():
    line = lambda y: LineString([(0, y), (10, y)])  # noqa: E731
    gdf = _raw([
        _row("keep", "CONSTRUCTED BARRIERS", line(0), FED_YRCON=2010),
        _row("sentinel", "CONSTRUCTED BARRIERS", line(1), FED_YRCON=9999),
        _row("zero", "CONSTRUCTED BARRIERS", line(2), FED_YRCON=0),
        _row("too_old", "CONSTRUCTED BARRIERS", line(3), FED_YRCON=BUILT_YEAR_MIN - 1),
        _row("too_new", "CONSTRUCTED BARRIERS", line(4), FED_YRCON=BUILT_YEAR_MAX + 1),
    ])
    out = preprocess_barriers(gdf).set_index("gcid")

    assert out.loc["keep", "built_year"] == 2010
    assert out["built_year"].dtype == "Int64"
    assert out.loc[["sentinel", "zero", "too_old", "too_new"], "built_year"].isna().all()


def test_units_and_programmed_flag():
    gdf = _raw([
        _row("x", "CONSTRUCTED BARRIERS", LineString([(0, 0), (10, 0)]),
             FLAG="FNV", FED_HEIGHT=20.0, FED_LENGTH=100.0, SHAPE_Length=42.0),
    ])
    out = preprocess_barriers(gdf).iloc[0]

    assert out["is_programmed"] is True or out["is_programmed"] == True  # noqa: E712
    assert out["height_m"] == pytest.approx(20.0 * FT_TO_M, abs=0.01)
    assert out["length_m"] == pytest.approx(100.0 * FT_TO_M, abs=0.1)
    assert out["seg_len_m"] == pytest.approx(42.0)


def test_exact_geometry_duplicates_dropped():
    shared = LineString([(0, 0), (10, 0)])
    gdf = _raw([
        _row("a", "CONSTRUCTED BARRIERS", shared),
        _row("b", "CONSTRUCTED BARRIERS", LineString([(0, 0), (10, 0)])),  # identical
        _row("c", "CONSTRUCTED BARRIERS", LineString([(0, 1), (10, 1)])),
    ])
    out = preprocess_barriers(gdf)
    assert len(out) == 2


def test_tolerates_missing_optional_columns():
    gdf = _raw([
        _row("a", "CONSTRUCTED BARRIERS", LineString([(0, 0), (10, 0)])),
    ]).drop(columns=["FED_ANR", "FED_MATERL", "SHAPE_Length"])

    out = preprocess_barriers(gdf)
    assert "fed_anr" not in out.columns
    assert "fed_materl" not in out.columns
    # seg_len_m is recomputed from geometry when SHAPE_Length is absent.
    assert out.iloc[0]["seg_len_m"] == pytest.approx(10.0)
    assert list(out.columns)[-1] == "geometry"
