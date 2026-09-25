"""Tests for `src/core/barrier_geometry/linear_ref.py` -- the line-network geometry primitives behind
`_barrier_reference.py`. Synthetic geometry in EPSG:3006 with round-number
coordinates so expected results are exact."""
import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, Point

from src.core.barrier_geometry import linear_ref as lr


def test_position_and_side_projects_km_position_and_offset():
    line = LineString([(0, 0), (100, 0)])
    km_position, side, offset_m = lr.position_and_side(Point(50, 10), line, 0.0, 100.0)
    assert km_position == pytest.approx(50.0)
    assert offset_m == pytest.approx(10.0)
    assert side != 0.0


def test_position_and_side_opposite_offsets_get_opposite_signs():
    line = LineString([(0, 0), (100, 0)])
    _, above, _ = lr.position_and_side(Point(50, 10), line, 0.0, 100.0)
    _, below, _ = lr.position_and_side(Point(50, -10), line, 0.0, 100.0)
    assert above == -below


def test_position_and_side_uses_km_from_to_not_geometry_length():
    line = LineString([(0, 0), (100, 0)])
    km_position, _, _ = lr.position_and_side(Point(25, 0), line, 10000.0, 10500.0)
    assert km_position == pytest.approx(10125.0)


def test_signed_side_matches_position_and_side_and_is_zero_on_the_line():
    line = LineString([(0, 0), (100, 0)])
    sign, offset = lr.signed_side(line, [Point(50, 10), Point(50, -10), Point(50, 0)])
    assert list(sign) == [1.0, -1.0, 0.0]
    assert list(offset) == pytest.approx([10.0, 10.0, 0.0])


def test_signed_side_past_the_end_still_reflects_the_lateral_side():
    # Beyond the line's end the along-line component doesn't enter the
    # cross product -- a point ahead-and-left is still "left".
    line = LineString([(0, 0), (100, 0)])
    sign, _ = lr.signed_side(line, [Point(400, 5), Point(400, -5)])
    assert list(sign) == [1.0, -1.0]


def test_build_adjacency_links_segments_sharing_an_endpoint():
    net = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 0)])], crs="EPSG:3006")
    endpoints = lr.build_adjacency(net)
    assert set(endpoints[(100, 0)]) == {0, 1}
    assert endpoints[(0, 0)] == [0]


def test_nearest_segment_returns_the_closer_segment_and_its_geometry():
    net = gpd.GeoDataFrame(
        {"bandel": ["A", "B"]},
        geometry=[LineString([(0, 0), (100, 0)]), LineString([(0, 100), (100, 100)])],
        crs="EPSG:3006",
    )
    joined = lr.nearest_segment(gpd.GeoDataFrame(geometry=[Point(50, 5)], crs="EPSG:3006"), net)
    assert joined.iloc[0]["bandel"] == "A"
    assert joined.iloc[0]["dist_m"] == pytest.approx(5.0)
    assert joined.iloc[0]["segment_geometry"] == net.geometry.iloc[0]


def _network(geoms):
    net = gpd.GeoDataFrame(geometry=geoms, crs="EPSG:3006").reset_index(drop=True)
    return net.geometry.to_numpy(), net.geometry.length.to_numpy(), lr.build_adjacency(net), net.sindex


def _chain():
    return _network([LineString([(0, 0), (500, 0)]), LineString([(500, 0), (1000, 0)]), LineString([(1000, 0), (1500, 0)])])


def test_corridor_geometry_trims_the_seed_segment_to_the_budget():
    geoms, lengths, endpoints, _ = _chain()
    corridor = lr.corridor_geometry(0, Point(250, 0), geoms, lengths, endpoints, budget_m=100.0)
    assert corridor.length == pytest.approx(200.0)


def test_corridor_geometry_trims_a_neighbor_longer_than_the_remaining_budget():
    # 100m of budget is left at the first junction; the 500m neighbour is
    # cut to those 100m rather than dropped.
    geoms, lengths, endpoints, _ = _chain()
    corridor = lr.corridor_geometry(0, Point(0, 0), geoms, lengths, endpoints, budget_m=600.0)
    assert corridor.length == pytest.approx(600.0)
    assert corridor.intersects(Point(600, 0)) and not corridor.intersects(Point(650, 0))


def test_corridor_geometry_trims_a_neighbor_entered_at_its_far_end():
    # The neighbour is digitized pointing back towards the junction.
    geoms, lengths, endpoints, _ = _network([LineString([(0, 0), (500, 0)]), LineString([(1000, 0), (500, 0)])])
    corridor = lr.corridor_geometry(0, Point(0, 0), geoms, lengths, endpoints, budget_m=600.0)
    assert corridor.length == pytest.approx(600.0)
    assert corridor.intersects(Point(600, 0)) and not corridor.intersects(Point(900, 0))


def test_through_line_continues_straight_and_ignores_a_side_street():
    geoms, _, endpoints, _ = _network(
        [
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (200, 0)]),  # straight on
            LineString([(100, 0), (100, 100)]),  # side street, 90 degrees
            LineString([(-100, 0), (0, 0)]),  # straight on, backwards
        ]
    )
    line, used = lr.through_line(0, Point(50, 0), geoms, endpoints, budget_m=1000.0)
    assert used == {0, 1, 3}
    assert list(line.coords) == [(-100, 0), (0, 0), (100, 0), (200, 0)]


def _divided_road(extra=()):
    # carriageway A at y=0, carriageway B at y=20, split at x=500 like real
    # NVDB rows are; `extra` adds more rows.
    return _network(
        [
            LineString([(0, 0), (500, 0)]),
            LineString([(500, 0), (1000, 0)]),
            LineString([(0, 20), (500, 20)]),
            LineString([(500, 20), (1000, 20)]),
            *extra,
        ]
    )


def test_parallel_neighbor_finds_the_other_carriageway():
    geoms, _, endpoints, sindex = _divided_road()
    anchor = Point(250, 0)
    line, used = lr.through_line(0, anchor, geoms, endpoints)
    assert lr.parallel_neighbor(anchor, line, used, geoms, sindex, endpoints) in {2, 3}


def test_parallel_neighbor_rejects_a_short_frontage_road_that_doesnt_stay_alongside():
    # A 60m parallel stub 5m away is nearer than carriageway B but doesn't
    # run alongside for +-200m, so B wins.
    geoms, _, endpoints, sindex = _divided_road(extra=(LineString([(220, -5), (280, -5)]),))
    anchor = Point(250, 0)
    line, used = lr.through_line(0, anchor, geoms, endpoints)
    assert lr.parallel_neighbor(anchor, line, used, geoms, sindex, endpoints) in {2, 3}


def test_parallel_neighbor_ignores_the_roads_own_continuation_and_cross_streets():
    geoms, _, endpoints, sindex = _network(
        [
            LineString([(0, 0), (500, 0)]),
            LineString([(560, 0), (1000, 0)]),  # collinear continuation after a gap
            LineString([(300, -50), (300, 50)]),  # cross street
        ]
    )
    anchor = Point(470, 0)
    line, used = lr.through_line(0, anchor, geoms, endpoints)
    assert lr.parallel_neighbor(anchor, line, used, geoms, sindex, endpoints) is None


def test_local_tangent_is_a_unit_vector_along_the_line():
    assert np.allclose(lr.local_tangent(LineString([(0, 0), (0, 10)]), Point(1, 5)), [0.0, 1.0])


def test_through_line_stops_before_a_segment_that_heads_back():
    # A hook: every junction turns < 45 degrees (so the per-junction rule
    # alone would follow it), but the last segment heads back against the
    # seed's direction -- it must not be followed.
    geoms, _, endpoints, _ = _network(
        [
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (160, 40)]),  # 34 degrees
            LineString([(160, 40), (180, 100)]),  # another 38
            LineString([(180, 100), (170, 160)]),  # another 28 -- now heading -x
        ]
    )
    line, used = lr.through_line(0, Point(50, 0), geoms, endpoints, budget_m=1000.0)
    assert used == {0, 1, 2}
    assert list(line.coords)[-1] == (180, 100)


def _ramp_off_a_mainline():
    # Mainline M: one row (0,0)-(2000,0). Ramp R starts ON M at x=1000 with
    # no shared node (as NVDB often digitizes it) and bends away southwards.
    return _network([LineString([(0, 0), (2000, 0)]), LineString([(1000, 0), (1300, -60), (1600, -60)])])


def test_through_line_stops_at_a_ramp_end_that_meets_a_row_mid_way_without_sindex():
    geoms, _, endpoints, _ = _ramp_off_a_mainline()
    line, used = lr.through_line(1, Point(1450, -60), geoms, endpoints)
    assert used == {1}
    assert list(line.coords)[0] == (1000, 0)


def test_through_line_bridges_onto_the_row_a_ramp_starts_from():
    geoms, _, endpoints, sindex = _ramp_off_a_mainline()
    line, used = lr.through_line(1, Point(1450, -60), geoms, endpoints, sindex=sindex)
    assert used == {0, 1}
    # Continues back along the mainline, away from the ramp -- not forward
    # along the mainline beside it.
    assert list(line.coords)[0][0] < 1000
    assert line.distance(Point(1500, 0)) > 50


def test_chain_lines_joins_pieces_end_to_end_and_orients_them():
    pieces = [
        LineString([(0, 0), (100, 0)]),
        LineString([(101, 0), (200, 0)]),  # a 1 m gap: still one wall
        LineString([(300, 0), (201, 0)]),  # digitised the other way
        LineString([(300, 0), (300, 100)]),  # turns 90 degrees: another wall
        LineString([(5000, 0), (5100, 0)]),
    ]
    chains = lr.chain_lines(pieces)
    assert chains["chain_id"].tolist()[:3] == [0, 0, 0] and chains["chain_size"].tolist() == [3, 3, 3, 1, 1]
    assert chains["chain_pos"].tolist()[:3] == [0, 1, 2]
    assert chains["chain_orient"].tolist()[:3] == [1, 1, -1]
    assert len(set(chains["chain_id"])) == 3
    joined = lr.join_chain(pieces[:3], chains["chain_orient"].tolist()[:3])
    assert joined.coords[0] == (0, 0) and joined.coords[-1] == (300, 0)
    assert joined.length == pytest.approx(300)


def test_chain_lines_runs_the_way_most_of_the_wall_is_digitised():
    pieces = [LineString([(100, 0), (0, 0)]), LineString([(300, 0), (100, 0)]), LineString([(300, 0), (320, 0)])]
    chains = lr.chain_lines(pieces)
    # 300 of 320 m run towards -x, so the chain does too: from piece 2 to piece 0.
    assert chains["chain_pos"].tolist() == [2, 1, 0]
    assert chains["chain_orient"].tolist() == [1, 1, -1]


def test_chain_lines_leaves_branches_apart():
    # Two co-located records meet the same end: not a simple path.
    pieces = [LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 0)]), LineString([(100, 0.5), (200, 0.5)])]
    assert lr.chain_lines(pieces)["chain_size"].tolist() == [1, 1, 1]
