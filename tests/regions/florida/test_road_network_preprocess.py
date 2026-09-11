"""`preprocess_road_network` tidying, sentinel handling and geometry
flattening, exercised on a synthetic in-memory shapefile-shaped frame (no
local data needed)."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, MultiLineString

from src.regions.florida.sources.road_network.preprocess import (
    TARGET_EPSG,
    YEAR_SENTINEL,
    _flatten_multilinestring,
    preprocess_road_network,
)


def _raw(rows, crs=f"EPSG:{TARGET_EPSG}"):
    """Build a GeoDataFrame with the raw rciroads column names used by preprocess."""
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


BASE_COLS = dict(
    SEGMENTID=1,
    BEGIN_POST=0.0,
    END_POST=1.0,
    YEAR_=2025,
    FUNCLASSCO="17",
    FUNCLASS="URBAN: Major Collector",
    LANE_CNT=2.0,
    AADT=10000,
    RTLENGTH=1609.3,
    RCILENGTH=1609.3,
    ARCLENGTH=1609.3,
    SHAPE_LEN=1609.3,
    AUTOID=1,
    FGDLAQDATE="2026-01-01",
    DESCRIPT="URBAN: Major Collector",
)


def _row(roadway, geom, **overrides):
    row = {"ROADWAY": roadway, "geometry": geom, **BASE_COLS}
    row.update(overrides)
    return row


def test_column_renaming_and_output_schema():
    gdf = _raw([_row("01000001", LineString([(0, 0), (10, 0)]))])
    out = preprocess_road_network(gdf)

    assert list(out.columns) == [
        "roadway_id", "segmentid", "begin_post", "end_post", "year",
        "funclassco", "funclass", "lane_cnt", "aadt", "rtlength_m",
        "rcilength_m", "arclength_m", "shape_len_m", "autoid", "fgdlaqdate",
        "geometry",
    ]
    assert "descript" not in out.columns  # dropped: duplicates funclass, no route name
    assert out.crs.to_epsg() == TARGET_EPSG


def test_year_sentinel_becomes_na():
    gdf = _raw([
        _row("01000001", LineString([(0, 0), (10, 0)]), YEAR_=2025),
        _row("01000002", LineString([(0, 1), (10, 1)]), YEAR_=YEAR_SENTINEL),
    ])
    out = preprocess_road_network(gdf).set_index("roadway_id")

    assert out.loc["01000001", "year"] == 2025
    assert pd.isna(out.loc["01000002", "year"])
    assert out["year"].dtype == "Int64"


def test_lane_cnt_cast_to_nullable_int():
    gdf = _raw([_row("01000001", LineString([(0, 0), (10, 0)]), LANE_CNT=4.0)])
    out = preprocess_road_network(gdf)
    assert out.iloc[0]["lane_cnt"] == 4
    assert out["lane_cnt"].dtype == "Int64"


def test_reprojects_to_target_epsg():
    gdf = _raw([_row("01000001", LineString([(0, 0), (1, 0)]))], crs="EPSG:4326")
    out = preprocess_road_network(gdf)
    assert out.crs.to_epsg() == TARGET_EPSG


def test_sorted_by_roadway_and_segment():
    gdf = _raw([
        _row("02000000", LineString([(0, 0), (10, 0)]), SEGMENTID=2),
        _row("01000000", LineString([(0, 1), (10, 1)]), SEGMENTID=1),
        _row("01000000", LineString([(0, 2), (10, 2)]), SEGMENTID=0),
    ])
    out = preprocess_road_network(gdf)
    assert list(zip(out["roadway_id"], out["segmentid"])) == [
        ("01000000", 0), ("01000000", 1), ("02000000", 2),
    ]


def test_flatten_multilinestring_merges_contiguous_parts():
    contiguous = MultiLineString([[(0, 0), (5, 0)], [(5, 0), (10, 0)]])
    flattened = _flatten_multilinestring(contiguous)
    assert flattened.geom_type == "LineString"
    assert flattened.length == pytest.approx(10.0)


def test_flatten_multilinestring_keeps_longest_disjoint_part():
    disjoint = MultiLineString([[(0, 0), (1, 0)], [(100, 100), (100, 106)]])
    flattened = _flatten_multilinestring(disjoint)
    assert flattened.geom_type == "LineString"
    assert flattened.length == pytest.approx(6.0)  # the longer of the two parts


def test_flatten_leaves_linestring_unchanged():
    line = LineString([(0, 0), (10, 0)])
    assert _flatten_multilinestring(line) is line


def test_preprocess_flattens_multilinestring_rows():
    disjoint = MultiLineString([[(0, 0), (1, 0)], [(100, 100), (100, 106)]])
    gdf = _raw([_row("01000001", disjoint)])
    out = preprocess_road_network(gdf)
    assert out.iloc[0].geometry.geom_type == "LineString"


def test_tolerates_missing_optional_columns():
    gdf = _raw([_row("01000001", LineString([(0, 0), (10, 0)]))]).drop(columns=["AADT", "LANE_CNT"])
    out = preprocess_road_network(gdf)
    assert "aadt" not in out.columns
    assert "lane_cnt" not in out.columns
    assert list(out.columns)[-1] == "geometry"
