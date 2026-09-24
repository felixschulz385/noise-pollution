"""Tests for the schools `assemble` (school <-> barrier match) stage --
synthetic geometries built directly in EPSG:3006 (SWEREF99 TM) with
round-number coordinates so the expected distances are exact, no network."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.sweden.sources._barrier_reference import build_barrier_references
from src.regions.sweden.sources.barrier_protection.shared import ROUTE_COLUMNS
from src.regions.sweden.sources.noise_barriers.shared import load_noise_barriers
from src.regions.sweden.sources.schools import assemble as sa


def _schools_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"skolenhetskod": ["s1", "s2"]},
        geometry=[Point(0, 0), Point(0, 2000)],
        crs="EPSG:3006",
    )


def _barriers_gdf() -> gpd.GeoDataFrame:
    # b1: vertical segment at x=50, y in [-10,10] -> distance from (0,0) is
    # exactly 50 (perpendicular), from (0,2000) is the distance to the
    # nearest endpoint (50,10).
    # b2: vertical segment at x=0, y in [-1200,-1000] -> distance from
    # (0,0) is exactly 1000 (nearest endpoint (0,-1000)), from (0,2000) is
    # 3000.
    return gpd.GeoDataFrame(
        {
            "element_id": ["b1", "b2"],
            "built_year": pd.array([2010, pd.NA], dtype="Int64"),
        },
        geometry=[
            LineString([(50, -10), (50, 10)]),
            LineString([(0, -1200), (0, -1000)]),
        ],
        crs="EPSG:3006",
    )


def test_match_barriers_point_rollup_reports_nearest_distance_unconditionally():
    pair, rollup = sa.match_barriers_point(_schools_gdf(), _barriers_gdf(), max_dist=1000.0)

    s1 = rollup.set_index("skolenhetskod").loc["s1"]
    assert s1["nearest_dist_m"] == pytest.approx(50.0)
    assert s1["nearest_element_id"] == "b1"

    s2 = rollup.set_index("skolenhetskod").loc["s2"]
    # Nearest barrier point-to-point distance from (0,2000) to segment
    # endpoint (50,10): sqrt(50^2 + 1990^2).
    assert s2["nearest_dist_m"] == pytest.approx(((50**2 + 1990**2) ** 0.5), abs=0.1)


def test_match_barriers_point_pair_table_only_keeps_within_max_dist():
    pair, _ = sa.match_barriers_point(_schools_gdf(), _barriers_gdf(), max_dist=1000.0)
    # s1 is within 1000m of both b1 (50m) and b2 (exactly 1000m, inclusive);
    # s2 is beyond 1000m of everything.
    assert set(pair["skolenhetskod"]) == {"s1"}
    assert set(pair["element_id"]) == {"b1", "b2"}


def test_match_barriers_point_buffer_flags():
    pair, rollup = sa.match_barriers_point(_schools_gdf(), _barriers_gdf(), max_dist=1000.0, buffers=(100, 1000))
    s1 = rollup.set_index("skolenhetskod").loc["s1"]
    assert s1["n_barriers_100m"] == 1  # only b1 (50m) is within 100m
    assert s1["n_barriers_1000m"] == 2  # both b1 (50m) and b2 (1000m)
    assert s1["ever_near_100m"] and s1["ever_near_1000m"]

    s2 = rollup.set_index("skolenhetskod").loc["s2"]
    assert s2["n_barriers_1000m"] == 0
    assert not s2["ever_near_1000m"]


def test_match_barriers_point_treatment_timing_uses_built_year():
    pair, rollup = sa.match_barriers_point(_schools_gdf(), _barriers_gdf(), max_dist=1000.0)
    s1 = rollup.set_index("skolenhetskod").loc["s1"]
    assert s1["ever_treated"] is True or s1["ever_treated"] == True  # noqa: E712
    assert s1["first_treat_year"] == 2010  # min over b1=2010 and b2=NaN, NaN skipped
    # b2's own timing is unknown even though b1 DOES have a valid year --
    # marks the school `timing_unknown=True` alongside a valid
    # `first_treat_year`, same "any unknown-timing nearby barrier" semantics
    # as Florida's `timing_unknown_point`.
    assert bool(s1["timing_unknown"]) is True

    s2 = rollup.set_index("skolenhetskod").loc["s2"]
    assert pd.isna(s2["first_treat_year"])
    assert bool(s2["ever_treated"]) is False


def test_match_barriers_point_is_nearest_flag():
    pair, _ = sa.match_barriers_point(_schools_gdf(), _barriers_gdf(), max_dist=1000.0)
    s1_pairs = pair[pair["skolenhetskod"] == "s1"].set_index("element_id")
    assert s1_pairs.loc["b1", "is_nearest"] == True  # noqa: E712
    assert s1_pairs.loc["b2", "is_nearest"] == False  # noqa: E712


def test_build_combined_rollup_fills_untreated_schools_with_false_not_na():
    schools_gdf = _schools_gdf()
    _, road_rollup = sa.match_barriers_point(schools_gdf, _barriers_gdf(), max_dist=1000.0)
    empty_rail = pd.DataFrame(
        {"skolenhetskod": [], "ever_treated": [], "timing_unknown": [], "nearest_dist_m": [], "nearest_element_id": [], "first_treat_year": []}
    )

    combined = sa.build_combined_rollup(schools_gdf, {"road": road_rollup, "rail": empty_rail})

    assert list(combined["skolenhetskod"]) == ["s1", "s2"]
    assert combined["rail_ever_treated"].tolist() == [False, False]
    assert combined["rail_timing_unknown"].tolist() == [False, False]
    assert combined["road_ever_treated"].tolist() == [True, False]


def test_load_geocoded_schools_raises_a_clear_error_when_missing(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sa, "schools_paths", lambda root=None: paths)

    with pytest.raises(FileNotFoundError, match="schools preprocess"):
        sa.load_geocoded_schools()


def test_load_noise_barriers_rejects_unknown_kind():
    with pytest.raises(ValueError):
        load_noise_barriers("water")


# --- algorithms 4+5 (same_route / same_side) ------------------------------
#
# Like the real layers: a barrier's `element_id` is the road/track link it is
# registered on, its measures are fractions along that link, and its geometry
# sits on the link's line unless stated. Tight budget/buffer (50/60) keep
# corridor membership unambiguous at this toy scale.


def _links(rows, **extra):
    """rows: (element_id, geometry) -- one row per link, measures 0-1."""
    return gpd.GeoDataFrame(
        {"element_id": [r[0] for r in rows], "start_measure": 0.0, "end_measure": 1.0, **extra},
        geometry=[r[1] for r in rows],
        crs="EPSG:3006",
    )


def _barriers(rows):
    """rows: (element_id, start, end, geometry, built_year)."""
    return gpd.GeoDataFrame(
        {
            "element_id": [r[0] for r in rows],
            "start_measure": [r[1] for r in rows],
            "end_measure": [r[2] for r in rows],
            "built_year": pd.array([r[4] for r in rows], dtype="Int64"),
        },
        geometry=[r[3] for r in rows],
        crs="EPSG:3006",
    )


def _refs(barriers_gdf, network_gdf, kind, osm_walls=None):
    return build_barrier_references(
        barriers_gdf,
        network_gdf,
        kind=kind,
        osm_walls=osm_walls,
        route_column=ROUTE_COLUMNS[kind],
        budget_m=50.0,
        buffer_m=60.0,
    )


def _annotate(schools_gdf, barriers_gdf, network_gdf, kind, osm_walls=None):
    pair, rollup = sa.match_barriers_point(schools_gdf, barriers_gdf, max_dist=1000.0)
    refs = _refs(barriers_gdf, network_gdf, kind, osm_walls)
    annotated = sa.match_barriers_network(pair, schools_gdf, refs, kind=kind)
    return annotated.set_index("barrier_row"), rollup


def _school(x, y):
    return gpd.GeoDataFrame({"skolenhetskod": ["s1"]}, geometry=[Point(x, y)], crs="EPSG:3006")


def _rail():
    tracks = _links(
        [("T100", LineString([(0, 0), (2000, 0)])), ("T200", LineString([(600, 300), (700, 300)]))], bandel=["100", "200"]
    )
    barriers = _barriers(
        [
            ("T100", 0.2525, 0.2550, LineString([(505, 6), (510, 6)]), 2015),  # genuinely offset +6m
            ("T100", 0.2500, 0.2525, LineString([(500, -6), (505, -6)]), 2018),  # genuinely offset -6m
            ("T200", 0.4, 0.6, LineString([(640, 300), (660, 300)]), 2020),  # separate, isolated track
        ]
    )
    return tracks, barriers


def test_rail_same_route_follows_the_barriers_own_track_and_carries_the_bandel():
    tracks, barriers = _rail()
    out, _ = _annotate(_school(500, 5), barriers, tracks, "rail")
    assert out.loc[0, "same_route"] and out.loc[1, "same_route"]
    assert not out.loc[2, "same_route"]
    assert out.loc[0, "bandel"] == "100"


def test_rail_same_side_uses_a_genuine_offset():
    tracks, barriers = _rail()
    out, _ = _annotate(_school(500, 5), barriers, tracks, "rail")
    assert out.loc[0, "side_method"] == "geometric_offset" and out.loc[0, "same_side"]
    assert out.loc[1, "side_method"] == "geometric_offset" and not out.loc[1, "same_side"]


def _divided_road():
    return _links([("A", LineString([(0, 0), (2000, 0)])), ("B", LineString([(0, 20), (2000, 20)]))])


def test_road_same_side_is_the_outer_side_of_the_walls_own_carriageway():
    barriers = _barriers(
        [
            ("A", 0.25, 0.255, LineString([(500, 0), (510, 0)]), 2015),  # on carriageway A
            ("B", 0.25, 0.255, LineString([(500, 20), (510, 20)]), 2018),  # on carriageway B
        ]
    )
    # The school is outside carriageway A (y=-30): protected by A's wall,
    # not by B's (B's wall stands outside B, at y>20).
    out, _ = _annotate(_school(505, -30), barriers, _divided_road(), "road")
    assert out.loc[0, "same_route"] and out.loc[1, "same_route"]
    assert out.loc[0, "side_method"] == "parallel_road" and out.loc[0, "same_side"]
    assert not out.loc[1, "same_side"]


def test_road_undivided_is_unknown_and_never_counted_as_same_side():
    road = _links([("A", LineString([(0, 0), (2000, 0)]))])
    barriers = _barriers([("A", 0.25, 0.255, LineString([(500, 0), (510, 0)]), 2015)])
    schools_gdf = _school(505, -30)
    pair, rollup = sa.match_barriers_point(schools_gdf, barriers, max_dist=1000.0)
    annotated = sa.match_barriers_network(pair, schools_gdf, _refs(barriers, road, "road"), kind="road")
    assert annotated.loc[0, "side_method"] == "unknown"
    assert bool(annotated.loc[0, "same_side_unknown"]) and not annotated.loc[0, "same_side"]

    out = sa.add_network_treatment_definitions(annotated, rollup).set_index("skolenhetskod").loc["s1"]
    assert bool(out["ever_treated_same_route"]) and not bool(out["ever_treated_same_side"])
    assert bool(out["same_side_unknown"])


def test_road_osm_wall_decides_the_side_on_an_undivided_road():
    road = _links([("A", LineString([(0, 0), (2000, 0)]))])
    barriers = _barriers([("A", 0.25, 0.255, LineString([(500, 0), (510, 0)]), 2015)])
    osm = gpd.GeoDataFrame({"osm_id": [7], "wall_type": ["noise_barrier"]}, geometry=[LineString([(470, -8), (540, -8)])], crs="EPSG:3006")
    out, _ = _annotate(_school(505, -30), barriers, road, "road", osm_walls=osm)
    assert out.loc[0, "side_method"] == "osm_offset" and out.loc[0, "osm_id"] == 7
    assert out.loc[0, "same_side"]


def test_add_network_treatment_definitions_same_side_is_a_subset_of_same_route():
    tracks, barriers = _rail()
    schools_gdf = _school(500, 5)
    pair, rollup = sa.match_barriers_point(schools_gdf, barriers, max_dist=1000.0)
    annotated = sa.match_barriers_network(pair, schools_gdf, _refs(barriers, tracks, "rail"), kind="rail")
    out = sa.add_network_treatment_definitions(annotated, rollup).set_index("skolenhetskod").loc["s1"]
    assert out["first_treat_year_same_route"] == 2015 and out["first_treat_year_same_side"] == 2015
    assert set(annotated.loc[annotated["same_side"], "barrier_row"]) < set(annotated.loc[annotated["same_route"], "barrier_row"])
    assert not bool(out["same_side_unknown"])


def test_run_schools_assemble_network_requires_schools_preprocess_to_have_run_first(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sa, "schools_paths", lambda root=None: paths)

    with pytest.raises(FileNotFoundError, match="schools preprocess"):
        sa.run_schools_assemble_network("road")
