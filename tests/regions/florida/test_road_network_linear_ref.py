"""Nearest-road matching, linear referencing, and the network-distance-bounded
corridor flood-fill, exercised on synthetic geometry — no local data needed."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.florida.sources.road_network.linear_ref import (
    arterial_subset,
    build_adjacency,
    corridor_geometry,
    milepost_and_side,
    nearest_road,
)

CRS = "EPSG:3087"


def _roads(rows):
    # rows: (roadway_id, x0, y0, x1, y1, funclass)
    return gpd.GeoDataFrame(
        [{"roadway_id": rid, "begin_post": 0.0, "end_post": ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 1609.344,
          "funclass": fc, "geometry": LineString([(x0, y0), (x1, y1)])}
         for rid, x0, y0, x1, y1, fc in rows],
        geometry="geometry", crs=CRS,
    )


def test_arterial_subset_filters_and_resets_index():
    roads = _roads([
        ("a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other"),
        ("b", 0, 10, 100, 10, "URBAN: Local"),
        ("c", 0, 20, 100, 20, "URBAN: Minor Collector (Fed Aid)"),
    ]).iloc[[1, 0, 2]]  # deliberately out of order / non-default index

    major = arterial_subset(roads)
    assert list(major["roadway_id"]) == ["a", "c"]
    assert list(major.index) == [0, 1]  # reset


def test_nearest_road_pulls_road_geometry_not_point_geometry():
    roads = _roads([("a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other")])
    points = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(50, 30)], crs=CRS)

    joined = nearest_road(points, roads)
    assert joined["dist_m"].iloc[0] == pytest.approx(30.0)
    # the gotcha this function exists to avoid: road_geometry must be the
    # matched ROAD's line, not the point itself.
    assert joined["road_geometry"].iloc[0].equals(roads.geometry.iloc[0])
    assert joined["point_geometry"].iloc[0].equals(points.geometry.iloc[0])


def test_milepost_and_side_opposite_signs_across_the_line():
    line = LineString([(0, 0), (100, 0)])
    above = Point(50, 10)
    below = Point(50, -10)

    mp_a, side_a, off_a = milepost_and_side(above, line, begin_post=0.0, end_post=1.0)
    mp_b, side_b, off_b = milepost_and_side(below, line, begin_post=0.0, end_post=1.0)

    assert mp_a == pytest.approx(0.5, abs=1e-6)
    assert mp_b == pytest.approx(0.5, abs=1e-6)
    assert off_a == pytest.approx(10.0)
    assert off_b == pytest.approx(10.0)
    assert side_a == -side_b
    assert side_a != 0.0


def test_milepost_and_side_on_the_line_has_zero_side():
    line = LineString([(0, 0), (100, 0)])
    on_line = Point(25, 0)
    mp, side, off = milepost_and_side(on_line, line, begin_post=10.0, end_post=20.0)
    assert mp == pytest.approx(12.5)
    assert side == 0.0
    assert off == pytest.approx(0.0, abs=1e-9)


def test_build_adjacency_connects_only_shared_endpoints():
    roads = _roads([
        ("a", 0, 0, 100, 0, "x"),
        ("b", 100, 0, 200, 0, "x"),   # shares (100, 0) with "a"
        ("c", 500, 500, 600, 500, "x"),  # disjoint
    ])
    adj = build_adjacency(roads)
    assert adj[(100, 0)] == [0, 1]
    assert (500, 500) in adj and adj[(500, 500)] == [2]
    assert (600, 500) in adj and adj[(600, 500)] == [2]


def test_corridor_geometry_stays_within_budget_on_a_long_chain():
    # Five 100 m segments end-to-end; origin at the middle of the 3rd.
    roads = _roads([(str(i), i * 100, 0, (i + 1) * 100, 0, "x") for i in range(5)])
    geoms = roads.geometry.to_numpy()
    lengths = roads.geometry.length.to_numpy()
    endpoints = build_adjacency(roads)

    origin = Point(250, 0)  # middle of segment index 2 ([200, 300])
    corridor = corridor_geometry(2, origin, geoms, lengths, endpoints, budget_m=120.0)

    minx, miny, maxx, maxy = corridor.bounds
    # 120 m budget from x=250 should reach at most [130, 370], comfortably
    # inside segment 1 and segment 3 but nowhere near segments 0 or 4.
    assert minx >= 125.0
    assert maxx <= 375.0


def test_corridor_geometry_trims_an_oversized_seed_segment():
    # A single 10 km segment (mirrors rciroads' occasional 30-57 km
    # unsegmented stretches) -- the corridor must NOT be the whole segment.
    roads = _roads([("huge", 0, 0, 10_000, 0, "x")])
    geoms = roads.geometry.to_numpy()
    lengths = roads.geometry.length.to_numpy()
    endpoints = build_adjacency(roads)

    origin = Point(5_000, 0)
    corridor = corridor_geometry(0, origin, geoms, lengths, endpoints, budget_m=500.0)

    minx, miny, maxx, maxy = corridor.bounds
    assert minx == pytest.approx(4_500.0, abs=1.0)
    assert maxx == pytest.approx(5_500.0, abs=1.0)
    assert corridor.length < 2_000.0  # nowhere close to the 10 km seed


def test_corridor_geometry_does_not_cross_a_gap():
    roads = _roads([
        ("a", 0, 0, 100, 0, "x"),
        ("b", 200, 0, 300, 0, "x"),  # 100 m gap from "a" -- no shared endpoint
    ])
    geoms = roads.geometry.to_numpy()
    lengths = roads.geometry.length.to_numpy()
    endpoints = build_adjacency(roads)

    origin = Point(50, 0)
    corridor = corridor_geometry(0, origin, geoms, lengths, endpoints, budget_m=1000.0)
    minx, miny, maxx, maxy = corridor.bounds
    assert maxx <= 100.0  # never reaches segment "b" despite a generous budget
