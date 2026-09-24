"""Tests for `grid/side.py` -- wiring grid cells to their nearest barrier,
and to every barrier that protects them, through `_barrier_reference.py`
(whose side methods are tested in `test_barrier_reference.py`). Synthetic
geometry in EPSG:3006."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.regions.sweden.sources._barrier_reference import build_barrier_references
from src.regions.sweden.sources.grid.side import NEAREST_COLUMNS, match_grid_protection, match_grid_side

CRS = "EPSG:3006"


def _cells(points: dict[str, tuple[float, float]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"cell_id": list(points)}, geometry=gpd.points_from_xy(*zip(*points.values())), crs=CRS)


def _network():
    # Divided road: carriageway A (y=0) and B (y=20).
    return gpd.GeoDataFrame(
        {"element_id": ["A", "B"], "start_measure": [0.0, 0.0], "end_measure": [1.0, 1.0]},
        geometry=[LineString([(0, 0), (2000, 0)]), LineString([(0, 20), (2000, 20)])],
        crs=CRS,
    )


def _barriers():
    # b_a on A near x=450; b_b on B far away near x=1650.
    return gpd.GeoDataFrame(
        {"element_id": ["A", "B"], "start_measure": [0.20, 0.80], "end_measure": [0.25, 0.85]},
        geometry=[LineString([(400, 0), (500, 0)]), LineString([(1600, 20), (1700, 20)])],
        crs=CRS,
    )


def test_each_cell_is_judged_against_its_nearest_barrier():
    cells = _cells({"a_outer": (450, -40), "a_median": (450, 10), "b_outer": (1650, 60), "far": (450, 5000)})
    refs = build_barrier_references(_barriers(), _network(), kind="road", osm_walls=None)
    out = match_grid_side(cells, _barriers(), refs).set_index("cell_id")

    assert list(out.columns) == NEAREST_COLUMNS
    assert out.loc["a_outer", "same_side"] and out.loc["a_outer", "side_method"] == "parallel_road"
    assert not out.loc["a_median", "same_side"]
    assert out.loc["b_outer", "same_side"]  # B's outer side is +y, judged against b_b
    assert not out.loc["far", "same_route"] and not out.loc["far", "same_side"]


def test_rail_never_uses_a_neighbouring_track_so_snapped_barriers_are_unknown():
    cells = _cells({"c": (450, -40)})
    refs = build_barrier_references(_barriers(), _network(), kind="rail", osm_walls=None)
    out = match_grid_side(cells, _barriers(), refs).set_index("cell_id")
    assert out.loc["c", "same_route"]
    assert out.loc["c", "same_side_unknown"] and not out.loc["c", "same_side"]


def _two_roads():
    # Road A (y=0) and road D (y=-100), 100m apart -- too far apart to be
    # each other's parallel road. b0's wall stands south of A, b1's south of
    # D (both genuinely offset 3m, so `geometric_offset`).
    network = gpd.GeoDataFrame(
        {"element_id": ["A", "D"], "start_measure": [0.0, 0.0], "end_measure": [1.0, 1.0]},
        geometry=[LineString([(0, 0), (2000, 0)]), LineString([(0, -100), (2000, -100)])],
        crs=CRS,
    )
    barriers = gpd.GeoDataFrame(
        {
            "element_id": ["A", "D"],
            "start_measure": [0.20, 0.235],
            "end_measure": [0.25, 0.245],
            "built_year": pd.array([2010, pd.NA], dtype="Int64"),
        },
        geometry=[LineString([(400, -3), (500, -3)]), LineString([(470, -103), (490, -103)])],
        crs=CRS,
    )
    return network, barriers


def test_a_cell_protected_by_a_barrier_that_is_not_its_nearest():
    # The cell sits between the roads: 57m from b0 (it's on b0's protected,
    # south side) and 37m from b1 (on b1's unprotected, north side).
    network, barriers = _two_roads()
    cells = _cells({"between": (480, -60), "past_both": (1500, -60)})
    refs = build_barrier_references(barriers, network, kind="road", osm_walls=None)
    nearest = match_grid_side(cells, barriers, refs).set_index("cell_id")
    assert not nearest.loc["between", "same_side"]  # judged against b1, the nearest

    out = match_grid_protection(cells, barriers, refs).set_index("cell_id")
    assert out.loc["between", "protected"] and out.loc["between", "n_protecting_barriers"] == 1
    assert out.loc["between", "protected_barrier_row"] == 0
    assert out.loc["between", "protected_side_method"] == "geometric_offset"
    assert out.loc["between", "treat_year_protected"] == 2010
    assert not out.loc["between", "protected_undated"]
    assert not out.loc["past_both", "protected"] and out.loc["past_both", "n_protecting_barriers"] == 0


def test_protection_by_an_unknown_side_barrier_is_flagged_not_counted():
    network, barriers = _two_roads()
    barriers = barriers.assign(geometry=[LineString([(400, 0), (500, 0)]), LineString([(470, -100), (490, -100)])])
    cells = _cells({"beside_b0": (450, 40)})
    refs = build_barrier_references(barriers, network, kind="road", osm_walls=None)
    out = match_grid_protection(cells, barriers, refs).set_index("cell_id")
    assert not out.loc["beside_b0", "protected"] and out.loc["beside_b0", "protected_unknown"]
