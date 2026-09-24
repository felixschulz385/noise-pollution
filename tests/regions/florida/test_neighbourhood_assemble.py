"""`neighbourhood` assemble -- the point-in-polygon school->tract/ZIP
match (incl. the nearest-polygon fallback and the two-tract-vintage split)
and the two time-varying panel joins -- exercised on synthetic square
polygons, no local data needed."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import GeometryCollection, Point, Polygon

from src.regions.florida.sources.neighbourhood.assemble import (
    build_school_acs_panel,
    build_school_tract_match,
    build_school_zhvi_panel,
    build_school_zip_match,
    placed_school_points,
)

CRS = "EPSG:3087"


def _square(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _points(rows):
    # rows: (msid, x, y)
    return gpd.GeoDataFrame([{"msid": m, "geometry": Point(x, y)} for m, x, y in rows], geometry="geometry", crs=CRS)


def test_build_school_tract_match_within_and_nearest_fallback():
    points = _points([("a", 5, 5), ("b", 105, 5)])  # "b" is outside every polygon
    tracts = gpd.GeoDataFrame(
        [
            {"tract_geoid": "T1", "tract_vintage": "2020", "geometry": _square(0, 0, 10, 10)},
            {"tract_geoid": "T2", "tract_vintage": "2020", "geometry": _square(20, 0, 30, 10)},
        ],
        geometry="geometry", crs=CRS,
    )

    out = build_school_tract_match(points, tracts)

    a = out[out["msid"] == "a"].iloc[0]
    assert a["tract_geoid"] == "T1"
    b = out[out["msid"] == "b"].iloc[0]
    assert b["tract_geoid"] == "T2"  # nearest, since "b" fell outside both squares


def test_build_school_tract_match_covers_both_vintages():
    points = _points([("a", 5, 5)])
    tracts = gpd.GeoDataFrame(
        [
            {"tract_geoid": "OLD1", "tract_vintage": "2010", "geometry": _square(0, 0, 10, 10)},
            {"tract_geoid": "NEW1", "tract_vintage": "2020", "geometry": _square(0, 0, 10, 10)},
        ],
        geometry="geometry", crs=CRS,
    )

    out = build_school_tract_match(points, tracts)
    assert len(out) == 2
    assert set(zip(out["tract_vintage"], out["tract_geoid"])) == {("2010", "OLD1"), ("2020", "NEW1")}


def test_build_school_tract_match_empty_inputs():
    out = build_school_tract_match(gpd.GeoDataFrame(columns=["msid", "geometry"]), gpd.GeoDataFrame(columns=["tract_geoid", "tract_vintage", "geometry"]))
    assert out.empty
    assert list(out.columns) == ["msid", "tract_vintage", "tract_geoid"]


def test_build_school_zip_match_within():
    points = _points([("a", 5, 5)])
    zctas = gpd.GeoDataFrame([{"zip_code": "32601", "geometry": _square(0, 0, 10, 10)}], geometry="geometry", crs=CRS)

    out = build_school_zip_match(points, zctas)
    assert out.iloc[0]["zip_code"] == "32601"


def test_build_school_acs_panel_picks_vintage_by_year():
    tract_match = pd.DataFrame(
        [
            {"msid": "a", "tract_vintage": "2010", "tract_geoid": "OLD1"},
            {"msid": "a", "tract_vintage": "2020", "tract_geoid": "NEW1"},
        ]
    )
    acs = pd.DataFrame(
        [
            {"tract_geoid": "OLD1", "year": 2015, "median_household_income": 40000.0, "poverty_rate": 0.2,
             "pct_owner_occupied": 0.6, "pct_bachelors_plus": 0.25, "pct_moved_last_year": 0.15},
            {"tract_geoid": "NEW1", "year": 2021, "median_household_income": 50000.0, "poverty_rate": 0.18,
             "pct_owner_occupied": 0.65, "pct_bachelors_plus": 0.3, "pct_moved_last_year": 0.12},
        ]
    )

    out = build_school_acs_panel(tract_match, acs)

    assert len(out) == 2
    row_2015 = out[out["year"] == 2015].iloc[0]
    assert row_2015["median_household_income"] == 40000.0
    row_2021 = out[out["year"] == 2021].iloc[0]
    assert row_2021["median_household_income"] == 50000.0


def test_build_school_acs_panel_empty_inputs():
    out = build_school_acs_panel(pd.DataFrame(columns=["msid", "tract_vintage", "tract_geoid"]), pd.DataFrame(columns=["tract_geoid", "year"]))
    assert out.empty


def test_build_school_zhvi_panel_joins_on_zip():
    zip_match = pd.DataFrame([{"msid": "a", "zip_code": "32601"}, {"msid": "b", "zip_code": "33101"}])
    zhvi = pd.DataFrame([{"zip_code": "32601", "year": 2020, "zhvi": 210000.0}])

    out = build_school_zhvi_panel(zip_match, zhvi)

    assert len(out) == 1
    assert out.iloc[0]["msid"] == "a"
    assert out.iloc[0]["zhvi"] == 210000.0


def test_build_school_zhvi_panel_empty_inputs():
    out = build_school_zhvi_panel(pd.DataFrame(columns=["msid", "zip_code"]), pd.DataFrame(columns=["zip_code", "year"]))
    assert out.empty


def test_placed_school_points_excludes_empty_geometry_not_just_null():
    # Regression test: geopandas 1.0+ changed `.notna()` to treat an EMPTY
    # geometry (e.g. `Point()`) as non-null, unlike a real `None` -- a plain
    # `cross_section["geometry"].notna()` filter silently let 1,220 unplaced
    # schools (empty points, not None) through as if they had a real
    # location, inflating "placed schools" from the real 5,984 to 7,204 in
    # the first real run of this module. Both must be excluded.
    cross_section = gpd.GeoDataFrame(
        [
            {"msid": "a", "geometry": Point(0, 0)},
            {"msid": "b", "geometry": GeometryCollection()},  # empty, not None
            {"msid": "c", "geometry": None},
        ],
        geometry="geometry", crs="EPSG:3087",
    )

    out = placed_school_points(cross_section)
    assert list(out["msid"]) == ["a"]
