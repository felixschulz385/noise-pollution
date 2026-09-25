"""Tests for Florida's `barrier_protection` stage: the reference-road choice,
the side (wall geometry first, `BLOC_SIDE` as fallback and check), line
trimming, and zones against the point test. Synthetic geometry in EPSG:3087."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.core.barrier_geometry.protection import ZONE_STEP_M, classify_points, protection_zones
from src.regions.florida.sources.barrier_protection import build as bpb
from src.regions.florida.sources.barrier_protection import reference as ref
from src.regions.florida.sources.barrier_protection import shared as bps

CRS = "EPSG:3087"


def _roads(rows):
    # rows: (roadway_id, geometry)
    return gpd.GeoDataFrame(
        [{"roadway_id": rid, "segmentid": i, "begin_post": 0.0, "end_post": 1.0,
          "funclass": "URBAN: Principal Arterial - Other", "geometry": g} for i, (rid, g) in enumerate(rows)],
        geometry="geometry", crs=CRS,
    )


def _walls(rows):
    # rows: (gcid, geometry, bloc_side)
    return gpd.GeoDataFrame(
        [{"gcid": g, "category": "fdot_barrier", "built_year": 2010, "is_programmed": False,
          "bloc_side": side, "geometry": geom} for g, geom, side in rows],
        geometry="geometry", crs=CRS,
    )


def _east_west_road():
    return _roads([("EW", LineString([(0, 0), (3000, 0)]))])


def test_side_comes_from_the_walls_own_geometry_and_is_checked_against_bloc_side():
    walls = _walls([
        ("north", LineString([(1000, 30), (1300, 30)]), "NORTH"),
        ("south", LineString([(1000, -30), (1300, -30)]), "NORTH"),  # label contradicts the geometry
    ])
    refs = ref.build_barrier_references(walls, _east_west_road())
    table = refs.table.set_index("gcid")
    assert table["side_method"].tolist() == ["geometric_offset", "geometric_offset"]
    assert table.loc["north", "side_check"] == "agrees"
    assert table.loc["south", "side_check"] == "disagrees"
    out = classify_points([Point(1150, 200), Point(1150, -200)], np.zeros(2, dtype=int), refs)
    assert out["protected"].tolist() == [True, False]


def test_a_wall_drawn_on_the_road_falls_back_to_bloc_side():
    walls = _walls([("on_road", LineString([(1000, 0.5), (1300, 0.5)]), "SOUTH")])
    refs = ref.build_barrier_references(walls, _east_west_road())
    assert refs.table.loc[0, "side_method"] == "bloc_side"
    out = classify_points([Point(1150, -200), Point(1150, 200)], np.zeros(2, dtype=int), refs)
    assert out["protected"].tolist() == [True, False]


def test_a_compass_label_along_the_road_leaves_the_side_undecided():
    # NORTH on a north-south road says nothing about east vs west. (On a
    # diagonal road it would still decide: north of a SW-NE road is its
    # north-west side.)
    north_south = _roads([("NS", LineString([(0, 0), (0, 3000)]))])
    walls = _walls([("w", LineString([(0.5, 1000), (0.5, 1300)]), "NORTH")])
    refs = ref.build_barrier_references(walls, north_south)
    assert refs.table.loc[0, "side_method"] == "unknown"


def test_the_reference_road_is_the_parallel_one_not_a_nearer_cross_street():
    # A north-south cross street passes 10m from the wall's midpoint; the
    # east-west arterial the wall runs along is 30m away.
    roads = _roads([
        ("EW", LineString([(0, 0), (3000, 0)])),
        ("NS", LineString([(1160, -500), (1160, 500)])),
    ])
    walls = _walls([("w", LineString([(1000, 30), (1300, 30)]), "NORTH")])
    refs = ref.build_barrier_references(walls, roads)
    assert refs.table.loc[0, "roadway_id"] == "EW"
    assert refs.table.loc[0, "reference_parallel"]


def test_a_long_rci_row_is_trimmed_around_the_wall():
    long_road = _roads([("LONG", LineString([(0, 0), (50_000, 0)]))])
    walls = _walls([("w", LineString([(25_000, 30), (25_300, 30)]), "NORTH")])
    refs = ref.build_barrier_references(walls, long_road)
    assert refs.lines[0].length == pytest.approx(300 + 2 * ref.LINE_TRIM_M, abs=1.0)
    assert refs.table.loc[0, "span_start_m"] == pytest.approx(ref.LINE_TRIM_M, abs=1.0)
    # The same_route corridor stays bounded too (budget past each wall end).
    out = classify_points([Point(25_150, 200), Point(40_000, 200)], np.zeros(2, dtype=int), refs)
    assert out["same_route"].tolist() == [True, False]


def test_zones_match_the_point_test():
    walls = _walls([("w", LineString([(1000, 30), (1300, 30)]), "NORTH")])
    refs = ref.build_barrier_references(walls, _east_west_road())
    zone = protection_zones(refs).geometry.iloc[0]
    xs, ys = np.meshgrid(np.arange(700, 1601, 25.0), np.arange(-700, 701, 25.0))
    points = [Point(x, y) for x, y in zip(xs.ravel(), ys.ravel())]
    protected = classify_points(points, np.zeros(len(points), dtype=int), refs)["protected"].to_numpy()
    in_zone = np.array([zone.covers(p) for p in points])
    near_edge = np.array([zone.boundary.distance(p) <= ZONE_STEP_M for p in points])
    assert protected.sum() > 50
    assert not ((in_zone != protected) & ~near_edge).any()


def test_build_saves_references_that_load_back_and_refuses_a_stale_file(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    monkeypatch.setattr(bps, "barrier_protection_paths", lambda root=None: paths)
    walls = _walls([("w", LineString([(1000, 30), (1300, 30)]), "NORTH")])
    monkeypatch.setattr(bpb, "load_barriers", lambda root=None: walls)
    monkeypatch.setattr(bpb, "load_road_network", lambda root=None: _east_west_road())
    report = bpb.run_barrier_protection_build()
    assert report["side_method"] == {"geometric_offset": 1}

    loaded = bps.load_barrier_references(barriers_gdf=walls)
    fresh = ref.build_barrier_references(walls, _east_west_road())
    pd.testing.assert_frame_equal(
        classify_points([Point(1150, 200)], np.zeros(1, dtype=int), loaded),
        classify_points([Point(1150, 200)], np.zeros(1, dtype=int), fresh),
    )
    zones = bps.load_protection_zones()
    assert zones[["gcid", "zone_status", "built_year"]].iloc[0].tolist() == ["w", "protected", 2010]
    with pytest.raises(ValueError, match="barrier-protection build"):
        bps.load_barrier_references(barriers_gdf=walls.assign(gcid=["other"]))
