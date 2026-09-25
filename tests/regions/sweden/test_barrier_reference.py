"""Tests for `_barrier_reference.py` -- which road stretch a barrier covers
(linear-reference key join) and which side of it the barrier stands on.
Synthetic network in EPSG:3006; like the real layers, a barrier's
`element_id` is the road link it is registered on and its measures are
fractions along that link, and its geometry sits ON the road line."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point
from shapely.ops import substring as substring_line

from src.core.barrier_geometry import protection as pr
from src.regions.sweden.sources import _barrier_reference as br

CRS = "EPSG:3006"


def _road(rows):
    """rows: (element_id, start_measure, end_measure, geometry)."""
    return gpd.GeoDataFrame(
        {"element_id": [r[0] for r in rows], "start_measure": [r[1] for r in rows], "end_measure": [r[2] for r in rows]},
        geometry=[r[3] for r in rows],
        crs=CRS,
    )


def _divided_road():
    # Link A: carriageway at y=0 (digitized +x), split into two rows at
    # x=1000. Link B: the other carriageway, 20m to the left (y=20).
    return _road(
        [
            ("A", 0.0, 0.5, LineString([(0, 0), (1000, 0)])),
            ("A", 0.5, 1.0, LineString([(1000, 0), (2000, 0)])),
            ("B", 0.0, 1.0, LineString([(0, 20), (2000, 20)])),
        ]
    )


def _barrier(element_id, start, end, geometry):
    return gpd.GeoDataFrame(
        {"element_id": [element_id], "start_measure": [start], "end_measure": [end]}, geometry=[geometry], crs=CRS
    )


def _osm(lines, wall_type="noise_barrier"):
    return gpd.GeoDataFrame(
        {"osm_id": list(range(1, len(lines) + 1)), "wall_type": [wall_type] * len(lines)}, geometry=lines, crs=CRS
    )


def test_primary_rows_uses_the_key_join_and_keeps_every_covered_row():
    network = _divided_road()
    # Measures 0.45-0.55 of link A: straddles both of A's rows, mostly the second.
    barriers = _barrier("A", 0.44, 0.56, LineString([(880, 0), (1120, 0)]))
    primary, covered = br.primary_rows(barriers, network)
    assert set(covered[0]) == {0, 1}
    assert primary.iat[0] in {0, 1}


def test_primary_rows_falls_back_to_the_nearest_row_without_a_key_match():
    barriers = _barrier("not-in-network", 0.0, 1.0, LineString([(900, 19), (950, 19)]))
    primary, covered = br.primary_rows(barriers, _divided_road())
    assert primary.iat[0] == 2
    assert covered[0] == [2]


def test_divided_road_barrier_protects_the_side_away_from_the_other_carriageway():
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=None, kind="road")
    assert refs.table.loc[0, "side_method"] == "parallel_road"

    points = [Point(450, -40), Point(450, 10), Point(450, 60), Point(450, 5000)]
    out = pr.classify_points(points, np.zeros(4, dtype=int), refs)
    assert out["same_side"].tolist() == [True, False, False, False]  # outer side / median / beyond B / far away
    assert out["same_route"].tolist() == [True, True, True, False]
    assert not out["same_side_unknown"].any()


def test_undivided_road_is_unknown_never_same_side():
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))])
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    assert refs.table.loc[0, "side_method"] == "unknown"

    out = pr.classify_points([Point(450, -40), Point(450, 40)], np.zeros(2, dtype=int), refs)
    assert out["same_route"].all()
    assert not out["same_side"].any()
    assert out["same_side_unknown"].all()


def test_osm_wall_beside_the_barrier_decides_the_side_and_beats_the_parallel_road_rule():
    # OSM puts the wall 8m to the LEFT of A (inside the median) -- direct
    # observation wins over the parallel-road inference.
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    osm = _osm([LineString([(390, 8), (510, 8)])])
    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=osm, kind="road")
    assert refs.table.loc[0, "side_method"] == "osm_offset"
    assert refs.table.loc[0, "osm_id"] == 1
    out = pr.classify_points([Point(450, 5), Point(450, -40)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].tolist() == [True, False]


def test_osm_wall_nearer_the_other_carriageway_is_not_this_barriers_wall():
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    osm = _osm([LineString([(390, 28), (510, 28)])])  # outside carriageway B
    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=osm, kind="road")
    assert refs.table.loc[0, "side_method"] == "parallel_road"


def test_osm_candidates_must_be_parallel_long_enough_and_offset():
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))])
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    osm = _osm(
        [
            LineString([(450, -30), (450, 30)]),  # perpendicular
            LineString([(440, 10), (455, 10)]),  # too short
            LineString([(390, 0.5), (510, 0.5)]),  # on the road itself
        ]
    )
    refs = br.build_barrier_references(barriers, network, osm_walls=osm, kind="road")
    assert refs.table.loc[0, "side_method"] == "unknown"


def test_rail_barrier_with_a_real_offset_uses_it_and_snapped_rail_stays_unknown():
    # Rail never infers a side from a neighbouring track.
    tracks = _road(
        [
            ("T1", 0.0, 1.0, LineString([(0, 0), (2000, 0)])),
            ("T2", 0.0, 1.0, LineString([(0, 5), (2000, 5)])),
        ]
    )
    offset = _barrier("T1", 0.20, 0.25, LineString([(400, -6), (500, -6)]))
    snapped = _barrier("T1", 0.30, 0.35, LineString([(600, 0), (700, 0)]))
    barriers = pd.concat([offset, snapped], ignore_index=True)
    refs = br.build_barrier_references(barriers, tracks, osm_walls=None, kind="rail")
    assert refs.table["side_method"].tolist() == ["geometric_offset", "unknown"]
    out = pr.classify_points([Point(450, -30), Point(450, 30)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].tolist() == [True, False]


def test_route_column_is_carried_from_the_primary_row():
    tracks = _road([("T1", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))]).assign(bandel="100")
    barriers = _barrier("T1", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, tracks, osm_walls=None, kind="rail", route_column="bandel")
    assert refs.table.loc[0, "route"] == "100"


def test_points_beyond_the_end_of_the_barriers_road_have_an_unknown_side():
    # The road ends at x=1000 (no continuation); a point past its end is in
    # the buffered corridor but not beside the road, so its side is undefined.
    network = _road(
        [
            ("A", 0.0, 1.0, LineString([(0, 0), (1000, 0)])),
            ("B", 0.0, 1.0, LineString([(0, 20), (1000, 20)])),
        ]
    )
    barriers = _barrier("A", 0.90, 0.95, LineString([(900, 0), (950, 0)]))
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    assert refs.table.loc[0, "side_method"] == "parallel_road"
    out = pr.classify_points([Point(930, -40), Point(1100, -40)], np.zeros(2, dtype=int), refs)
    assert out["same_route"].tolist() == [True, True]
    assert out["same_side"].tolist() == [True, False]
    assert out["same_side_unknown"].tolist() == [False, True]


def test_a_ramp_barriers_side_reference_continues_onto_the_mainline_it_leaves():
    # Ramp R starts mid-way along mainline M (no shared node). Without the
    # bridge, a point beside M before the ramp is beyond the end of R's
    # line and unknown; with it, it is judged against M.
    network = _road(
        [
            ("M", 0.0, 1.0, LineString([(0, 0), (2000, 0)])),
            ("R", 0.0, 1.0, LineString([(1000, 0), (1300, -60), (1600, -60)])),
        ]
    )
    barriers = _barrier("R", 0.6, 0.9, LineString([(1300, -70), (1500, -70)]))  # 10m south of R
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="rail")
    assert refs.table.loc[0, "side_method"] == "geometric_offset"
    out = pr.classify_points([Point(700, -50), Point(700, 50)], np.zeros(2, dtype=int), refs)
    assert out["same_route"].all()
    assert out["same_side"].tolist() == [True, False]
    assert not out["same_side_unknown"].any()


def test_left_and_right_barriers_on_the_same_stretch_protect_both_sides():
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))])
    geom = LineString([(400, 0), (500, 0)])
    barriers = gpd.GeoDataFrame(
        {
            "element_id": ["A", "A", "A"],
            "start_measure": [0.20, 0.205, 0.60],
            "end_measure": [0.25, 0.25, 0.65],
            "side": ["left", "right", "left"],
        },
        geometry=[geom, geom, LineString([(1200, 0), (1300, 0)])],
        crs=CRS,
    )
    assert br.both_sides_rows(barriers) == {0, 1}
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    assert refs.table["side_method"].tolist() == ["both_sides", "both_sides", "unknown"]
    out = pr.classify_points([Point(450, -40), Point(450, 40)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].all()
    assert not out["same_side_unknown"].any()


def test_overlapping_barriers_with_the_same_side_label_are_not_both_sides():
    geom = LineString([(400, 0), (500, 0)])
    barriers = gpd.GeoDataFrame(
        {"element_id": ["A", "A"], "start_measure": [0.2, 0.2], "end_measure": [0.25, 0.25], "side": ["right", "right"]},
        geometry=[geom, geom],
        crs=CRS,
    )
    assert br.both_sides_rows(barriers) == set()


def _double_track():
    return _road(
        [
            ("T1", 0.0, 1.0, LineString([(0, 0), (2000, 0)])),
            ("T2", 0.0, 1.0, LineString([(0, 5), (2000, 5)])),
        ]
    )


def _rail_barrier(distance_m):
    return _barrier("T1", 0.20, 0.25, LineString([(400, 0), (500, 0)])).assign(distance_from_track_center_m=distance_m)


def test_rail_barrier_with_a_recorded_distance_stands_away_from_the_other_track():
    refs = br.build_barrier_references(_rail_barrier(4.0), _double_track(), osm_walls=None, kind="rail")
    assert refs.table.loc[0, "side_method"] == "track_offset"
    out = pr.classify_points([Point(450, -30), Point(450, 30)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].tolist() == [True, False]


def test_rail_barrier_without_a_recorded_distance_stays_unknown_beside_another_track():
    refs = br.build_barrier_references(_rail_barrier(np.nan), _double_track(), osm_walls=None, kind="rail")
    assert refs.table.loc[0, "side_method"] == "unknown"


def test_rail_osm_wall_must_lie_at_the_recorded_distance():
    # Recorded 4m; the only OSM wall is 15m out on the other side -- not
    # this barrier's wall, so the recorded distance + other track decide.
    osm = _osm([LineString([(390, 15), (510, 15)])])
    refs = br.build_barrier_references(_rail_barrier(4.0), _double_track(), osm_walls=osm, kind="rail")
    assert refs.table.loc[0, "side_method"] == "track_offset"
    at_distance = _osm([LineString([(390, -4), (510, -4)])])
    refs = br.build_barrier_references(_rail_barrier(4.0), _double_track(), osm_walls=at_distance, kind="rail")
    assert refs.table.loc[0, "side_method"] == "osm_offset"


def test_osm_wall_past_the_barriers_end_is_not_its_wall():
    # The wall starts 5m past the barrier's end: inside a round-capped 40m
    # buffer for 35m, but never beside the barrier.
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))])
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, network, osm_walls=_osm([LineString([(505, -8), (600, -8)])]), kind="road")
    assert refs.table.loc[0, "side_method"] == "unknown"


def test_osm_walls_on_both_sides_protect_both_sides():
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))])
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    osm = _osm([LineString([(390, 8), (510, 8)]), LineString([(390, -8), (510, -8)])])
    refs = br.build_barrier_references(barriers, network, osm_walls=osm, kind="road")
    assert refs.table.loc[0, "side_method"] == "osm_both_sides"
    out = pr.classify_points([Point(450, 30), Point(450, -30)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].tolist() == [True, True]


def test_double_track_twin_records_each_take_the_wall_beside_their_own_track():
    # One record per track (T1 at y=0, T2 at y=5), no recorded distance; a
    # wall outside each track. The longer wall is T2's: T1 must not claim it.
    barriers = pd.concat(
        [
            _barrier("T1", 0.20, 0.25, LineString([(400, 0), (500, 0)])),
            _barrier("T2", 0.20, 0.25, LineString([(400, 5), (500, 5)])),
        ],
        ignore_index=True,
    ).assign(distance_from_track_center_m=np.nan)
    osm = _osm([LineString([(390, -4), (510, -4)]), LineString([(380, 9), (520, 9)])])
    refs = br.build_barrier_references(barriers, _double_track(), osm_walls=osm, kind="rail")
    assert refs.table["side_method"].tolist() == ["osm_offset", "osm_offset"]
    assert refs.table["osm_id"].tolist() == [1, 2]
    assert refs.table["barrier_sign"].tolist() == [-1.0, 1.0]


def test_outer_track_sign_points_away_from_the_other_tracks_and_is_not_a_side_method():
    refs = br.build_barrier_references(_rail_barrier(np.nan), _double_track(), osm_walls=None, kind="rail")
    assert refs.table.loc[0, "side_method"] == "unknown"
    assert refs.table.loc[0, "outer_track_sign"] == -1.0
    three = pd.concat([_double_track(), _road([("T0", 0.0, 1.0, LineString([(0, -5), (2000, -5)]))])], ignore_index=True)
    refs = br.build_barrier_references(_rail_barrier(np.nan), three, osm_walls=None, kind="rail")
    assert np.isnan(refs.table.loc[0, "outer_track_sign"])  # a middle track
    road = br.build_barrier_references(_barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)])), _divided_road(), osm_walls=None, kind="road")
    assert np.isnan(road.table.loc[0, "outer_track_sign"])


def test_protected_is_same_side_beside_the_barriers_own_stretch():
    # Barrier covers x=400-500. Points on its protected side: beside it,
    # 30m past its end (within the 50m margin), and 200m past it.
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=None, kind="road")
    assert refs.table.loc[0, ["span_start_m", "span_end_m"]].tolist() == pytest.approx([400.0, 500.0], abs=1e-6)
    points = [Point(450, -40), Point(530, -40), Point(700, -40), Point(450, 10)]
    out = pr.classify_points(points, np.zeros(4, dtype=int), refs)
    assert out["same_side"].tolist() == [True, True, True, False]
    assert out["along_offset_m"].tolist() == pytest.approx([0.0, 30.0, 200.0, 0.0])
    assert out["lateral_m"].tolist() == pytest.approx([40.0, 40.0, 40.0, 10.0])
    assert out["protected"].tolist() == [True, True, False, False]
    assert not out["protected_unknown"].any()


def test_unknown_side_only_leaves_protection_unknown_beside_the_stretch():
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (2000, 0)]))])
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    out = pr.classify_points([Point(450, -40), Point(900, -40), Point(450, 5000)], np.zeros(3, dtype=int), refs)
    assert out["same_side_unknown"].tolist() == [True, True, False]
    assert out["protected_unknown"].tolist() == [True, False, False]
    assert not out["protected"].any()
    assert np.isnan(out["along_offset_m"].iat[2])  # outside the corridor


def test_span_margin_is_configurable():
    barriers = _barrier("A", 0.20, 0.25, LineString([(400, 0), (500, 0)]))
    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=None, kind="road")
    out = pr.classify_points([Point(530, -40)], np.zeros(1, dtype=int), refs, span_margin_m=0.0)
    assert not out["protected"].iat[0]


def test_a_point_far_past_the_end_of_a_short_line_is_not_beside_the_stretch():
    # The line ends at x=1000, 50m past the barrier's end (x=950). A point
    # at x=1400 must not be clamped to the line's end and count as beside.
    network = _road(
        [
            ("A", 0.0, 1.0, LineString([(0, 0), (1000, 0)])),
            ("B", 0.0, 1.0, LineString([(0, 20), (1000, 20)])),
        ]
    )
    barriers = _barrier("A", 0.85, 0.95, LineString([(850, 0), (950, 0)]))
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    out = pr.classify_points([Point(1400, -40), Point(990, -40)], np.zeros(2, dtype=int), refs)
    assert out["along_offset_m"].tolist() == pytest.approx([450.0, 40.0])
    assert out["same_side_unknown"].tolist() == [True, False]
    assert out["protected_unknown"].tolist() == [False, False]
    assert out["protected"].tolist() == [False, True]


def _arc(radius, start_deg, end_deg, n=60, offset=0.0):
    angles = np.radians(np.linspace(start_deg, end_deg, n))
    return LineString([((radius + offset) * np.cos(a), (radius + offset) * np.sin(a)) for a in angles])


@pytest.mark.parametrize("inward", [True, False])
def test_protection_zone_matches_the_point_test_on_a_tight_bend(inward):
    # A road bending around (0,0) with radius 300m -- tighter than the
    # zone's 600m reach. The wall at the top of the bend stands 3m inside or
    # outside it. Points inside the bend beyond its centre are nearer other
    # parts of the road, so neither the zone nor the point test protects them.
    network = _road([("A", 0.0, 1.0, _arc(300, 180, 0))])
    wall = _arc(300, 100, 80, n=10, offset=-3.0 if inward else 3.0)
    barriers = _barrier("A", 0.45, 0.55, wall)
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    assert refs.table.loc[0, "side_method"] == "geometric_offset"
    zone = pr.protection_zones(refs).geometry.iloc[0]

    xs, ys = np.meshgrid(np.arange(-700, 701, 20.0), np.arange(-500, 1001, 20.0))
    points = [Point(x, y) for x, y in zip(xs.ravel(), ys.ravel())]
    protected = pr.classify_points(points, np.zeros(len(points), dtype=int), refs)["protected"].to_numpy()
    in_zone = np.array([zone.covers(p) for p in points])
    near_edge = np.array([zone.boundary.distance(p) <= pr.ZONE_STEP_M for p in points])
    assert protected.sum() > 20
    assert not ((in_zone != protected) & ~near_edge).any()


def test_protection_zone_ignores_a_tiny_oddly_angled_end_segment():
    # The road's line ends in a 0.5m jog -- NVDB digitization noise. A point
    # 150m beside the barrier must still be in its zone.
    network = _road([("A", 0.0, 1.0, LineString([(0, 0), (1000, 0), (1000.3, 0.4)]))])
    barriers = _barrier("A", 0.80, 0.95, LineString([(800, -3), (950, -3)]))
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    zone = pr.protection_zones(refs).geometry.iloc[0]
    points = [Point(990, -150), Point(900, -150), Point(1100, -150)]
    protected = pr.classify_points(points, np.zeros(3, dtype=int), refs)["protected"].tolist()
    assert protected == [True, True, False]
    assert [zone.covers(p) for p in points] == protected


def test_a_barrier_on_a_roundabout_has_no_beyond_the_end():
    # The barrier's through-line closes on itself (a roundabout): nothing is
    # beyond an end, and the zone isn't cut at the closing point.
    arc = list(_arc(100, 0, 360, n=73).coords)
    ring = LineString(arc[:-1] + [arc[0]])
    network = _road([("R", 0.0, 1.0, ring)])
    barriers = _barrier("R", 0.0, 0.1, _arc(97, 0, 36, n=8))  # 3m inside, starting at the closing point
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    assert refs.lines[0].is_closed
    inside, outside = Point(80, 10), Point(130, 20)
    out = pr.classify_points([inside, outside], np.zeros(2, dtype=int), refs)
    assert out["protected"].tolist() == [True, False]
    assert not out["same_side_unknown"].any()
    assert pr.protection_zones(refs).geometry.iloc[0].covers(inside)


def test_zone_is_only_cut_beyond_the_roads_end_not_beside_a_curve_after_it():
    # The road starts at (0,0) heading +x, bends left through a quarter
    # circle and heads north. The barrier covers it from its start round the
    # bend. A point west of the northbound part is beside the barrier's
    # stretch even though it lies "behind" the road's start (x < 0).
    bend = [(100 + 100 * np.sin(t), 100 - 100 * np.cos(t)) for t in np.linspace(0, np.pi / 2, 12)]
    road = LineString([(0, 0), *bend, (200, 700)])
    network = _road([("A", 0.0, 1.0, road)])
    barrier_geom = substring_line(road, 0.0, 600.0)
    barriers = _barrier("A", 0.0, 600.0 / road.length, barrier_geom)
    refs = br.build_barrier_references(barriers, network, osm_walls=None, kind="road")
    assert refs.table.loc[0, "side_method"] == "unknown"
    beside, behind_start = Point(-50, 400), Point(-100, -5)
    out = pr.classify_points([beside, behind_start], np.zeros(2, dtype=int), refs)
    assert out["protected_unknown"].tolist() == [True, False]
    zone = pr.protection_zones(refs).geometry.iloc[0]
    assert zone.covers(beside) and not zone.covers(behind_start)


def _stub_track():
    # T1 is digitised +x up to x=1000 and -x beyond it (T1b), so the stub's
    # through-line runs against its sibling's; T2 runs alongside at y=5.
    return _road(
        [
            ("T1a", 0.0, 1.0, LineString([(0, 0), (1000, 0)])),
            ("T1b", 0.0, 1.0, LineString([(2000, 0), (1000, 0)])),
            ("T2", 0.0, 1.0, LineString([(0, 5), (2000, 5)])),
        ]
    )


def _bis_barriers(rows):
    """rows: (element_id, start, end, geometry, bis_object_number, recorded distance)."""
    return gpd.GeoDataFrame(
        {
            "element_id": [r[0] for r in rows], "start_measure": [r[1] for r in rows], "end_measure": [r[2] for r in rows],
            "bis_object_number": [r[4] for r in rows], "distance_from_track_center_m": [r[5] for r in rows],
        },
        geometry=[r[3] for r in rows],
        crs=CRS,
    )


STUB = ("T1b", 0.989, 0.98901, LineString([(1011, 0), (1011.02, 0)]), 7, np.nan)


def test_stub_takes_the_side_of_its_bis_objects_other_records():
    # The sibling stands right of +x (away from T2, y<0); the stub, on a
    # link digitised the other way, must protect the same y<0 side.
    sibling = ("T1a", 0.9, 1.0, LineString([(900, 0), (1000, 0)]), 7, 4.0)
    refs = br.build_barrier_references(_bis_barriers([sibling, STUB]), _stub_track(), osm_walls=None, kind="rail")
    assert refs.table["side_method"].tolist() == ["track_offset", "bis_sibling"]
    out = pr.classify_points([Point(1011, -30), Point(1011, 30)], np.array([1, 1]), refs)
    assert out["same_side"].tolist() == [True, False]


@pytest.mark.parametrize(
    "others",
    [
        # Two records of the object disagree.
        [("T1a", 0.9, 1.0, LineString([(900, 0), (1000, 0)]), 7, 4.0),
         ("T2", 0.45, 0.5, LineString([(900, 5), (1000, 5)]), 7, 4.0)],
        # The only record is another object's.
        [("T1a", 0.9, 1.0, LineString([(900, 0), (1000, 0)]), 8, 4.0)],
        # The object's record lies more than 50 m away.
        [("T1a", 0.8, 0.9, LineString([(800, 0), (900, 0)]), 7, 4.0)],
    ],
)
def test_stub_stays_unknown_without_one_agreeing_record_nearby(others):
    refs = br.build_barrier_references(_bis_barriers([*others, STUB]), _stub_track(), osm_walls=None, kind="rail")
    assert refs.table["side_method"].iat[-1] == "unknown"
