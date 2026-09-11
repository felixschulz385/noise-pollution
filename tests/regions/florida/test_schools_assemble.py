"""`schools assemble` (stage 2, the point-only barrier match), exercised on
synthetic school points + wall lines — no local data needed."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.florida.sources.schools.assemble import (
    PENDING_ROAD_COLUMNS,
    add_road_treatment_definitions,
    match_barriers_point,
    match_barriers_road,
)

CRS = "EPSG:3087"


def _schools(rows):
    return gpd.GeoDataFrame(
        [{"msid": m, "ncessch": n, "geometry": Point(x, y)} for m, n, x, y in rows],
        geometry="geometry", crs=CRS,
    )


def _barriers(rows):
    # rows: (gcid, category, built_year, x0, x1, y)
    return gpd.GeoDataFrame(
        [{"gcid": g, "category": cat, "built_year": by, "seg_len_m": 10.0,
          "geometry": LineString([(x0, y), (x1, y)])} for g, cat, by, x0, x1, y in rows],
        geometry="geometry", crs=CRS,
    )


def _road_network(rows):
    # rows: (roadway_id, x0, x1, y)
    return gpd.GeoDataFrame(
        [{"roadway_id": rid, "segmentid": i, "begin_post": 0.0,
          "end_post": abs(x1 - x0) / 1609.344, "funclass": "URBAN: Principal Arterial - Other",
          "geometry": LineString([(x0, y), (x1, y)])}
         for i, (rid, x0, x1, y) in enumerate(rows)],
        geometry="geometry", crs=CRS,
    )


def test_pairs_within_max_dist_and_placeholder_columns():
    schools = _schools([("near", "N1", 0, 0), ("far", "N2", 10_000, 10_000)])
    barriers = _barriers([("w1", "fdot_barrier", 2010, -50, 50, 50)])  # 50 m from "near"
    pair, rollup = match_barriers_point(schools, barriers, max_dist=1000)

    assert set(pair["msid"]) == {"near"}  # "far" has nothing within 1000 m
    assert rollup.set_index("msid").loc["near", "nearest_fdot_dist_m"] == pytest.approx(50.0)
    assert rollup.set_index("msid").loc["far", "nearest_fdot_dist_m"] > 1000
    for col in PENDING_ROAD_COLUMNS:
        assert col in pair.columns and pair[col].isna().all()


def test_treat_year_rules():
    schools = _schools([("s", "N1", 0, 0)])
    barriers = _barriers([
        ("fdot_dated", "fdot_barrier", 2005, -10, 10, 10),
        ("fdot_undated", "fdot_barrier", None, -10, 10, 20),
        ("other", "other_wall", 1999, -10, 10, 30),
    ])
    pair = match_barriers_point(schools, barriers, max_dist=1000)[0].set_index("gcid")

    assert pair.loc["fdot_dated", "treat_year"] == 2005
    assert pair.loc["fdot_dated", "timing_unknown"] == False  # noqa: E712
    assert pd.isna(pair.loc["fdot_undated", "treat_year"])
    assert pair.loc["fdot_undated", "timing_unknown"] == True  # noqa: E712
    # other_wall is never treatment, regardless of its own date
    assert pd.isna(pair.loc["other", "treat_year"])
    assert pair.loc["other", "timing_unknown"] == False  # noqa: E712


def test_is_nearest_fdot_flags_only_the_closest_fdot_wall():
    schools = _schools([("s", "N1", 0, 0)])
    barriers = _barriers([
        ("close", "fdot_barrier", 2010, -5, 5, 5),
        ("mid", "fdot_barrier", 2015, -5, 5, 50),
        ("other_close", "other_wall", 2010, -5, 5, 1),  # closer, but not fdot
    ])
    pair = match_barriers_point(schools, barriers, max_dist=1000)[0].set_index("gcid")
    assert pair.loc["close", "is_nearest_fdot"] == True   # noqa: E712
    assert pair.loc["mid", "is_nearest_fdot"] == False     # noqa: E712
    assert pair.loc["other_close", "is_nearest_fdot"] == False  # noqa: E712


def test_rollup_buffer_counts_and_first_treat_year():
    schools = _schools([("s", "N1", 0, 0)])
    barriers = _barriers([
        ("a", "fdot_barrier", 2012, -5, 5, 50),
        ("b", "fdot_barrier", 2008, -5, 5, 400),
        ("c", "fdot_barrier", 2018, -5, 5, 900),
    ])
    rollup = match_barriers_point(schools, barriers, max_dist=1000)[1].set_index("msid")
    row = rollup.loc["s"]
    assert row["n_walls_100m"] == 1
    assert row["n_walls_500m"] == 2
    assert row["n_walls_1000m"] == 3
    assert row["ever_near_wall_500m"] == True   # noqa: E712
    assert row["first_treat_year_point"] == 2008
    assert row["ever_treated_point"] == True    # noqa: E712
    assert row["timing_unknown_point"] == False   # noqa: E712


def test_crs_mismatch_raises():
    schools = _schools([("s", "N1", 0, 0)]).set_crs("EPSG:4326", allow_override=True)
    barriers = _barriers([("a", "fdot_barrier", 2010, -5, 5, 5)])
    with pytest.raises(ValueError, match="CRS mismatch"):
        match_barriers_point(schools, barriers)


def test_match_barriers_road_fills_pending_columns():
    # A wall just north (y=5) of a 2 km road; one school north (same side),
    # one south (opposite side), one far down the road (out of corridor
    # reach at the small budget/buffer used here).
    schools = _schools([
        ("same_side", "N1", 500, 30),
        ("opp_side", "N2", 500, -30),
        ("far", "N3", 1500, 30),
    ])
    barriers = _barriers([("w1", "fdot_barrier", 2010, 495, 505, 5)])
    road_network = _road_network([("r1", 0, 2000, 0)])

    pair, _ = match_barriers_point(schools, barriers, max_dist=1500)
    assert set(pair["msid"]) == {"same_side", "opp_side", "far"}

    out = match_barriers_road(pair, schools, barriers, road_network, budget_m=200.0, buffer_m=50.0)
    out = out.set_index("msid")

    assert out.loc["same_side", "road_id"] == "r1"
    assert out.loc["same_side", "same_route"] == True  # noqa: E712
    assert out.loc["same_side", "school_side"] == out.loc["same_side", "wall_side"]

    assert out.loc["opp_side", "same_route"] == True  # noqa: E712
    assert out.loc["opp_side", "school_side"] == -out.loc["opp_side", "wall_side"]

    assert out.loc["far", "same_route"] == False  # noqa: E712
    assert pd.isna(out.loc["far", "school_side"])
    assert pd.isna(out.loc["far", "wall_side"])
    # road_id / wall_side still populate even when the school is out of reach
    # -- only the school-dependent columns go NA.
    assert out.loc["far", "road_id"] == "r1"


def test_add_road_treatment_definitions_three_tiers_diverge():
    # Same setup: point-only treats all three as "near an fdot wall"; the
    # same_route tier drops "far" (outside corridor reach); the same_side
    # tier further drops "opp_side" (opposite carriageway) -- three
    # definitions kept side by side, not collapsed to one.
    schools = _schools([
        ("same_side", "N1", 500, 30),
        ("opp_side", "N2", 500, -30),
        ("far", "N3", 1500, 30),
    ])
    barriers = _barriers([("w1", "fdot_barrier", 2010, 495, 505, 5)])
    road_network = _road_network([("r1", 0, 2000, 0)])

    pair, rollup = match_barriers_point(schools, barriers, max_dist=1500)
    pair = match_barriers_road(pair, schools, barriers, road_network, budget_m=200.0, buffer_m=50.0)
    rollup = add_road_treatment_definitions(pair, rollup).set_index("msid")

    assert rollup.loc["same_side", "ever_treated_point"] == True   # noqa: E712
    assert rollup.loc["opp_side", "ever_treated_point"] == True    # noqa: E712
    assert rollup.loc["far", "ever_treated_point"] == True         # noqa: E712

    assert rollup.loc["same_side", "ever_treated_same_route"] == True   # noqa: E712
    assert rollup.loc["opp_side", "ever_treated_same_route"] == True    # noqa: E712
    assert rollup.loc["far", "ever_treated_same_route"] == False        # noqa: E712

    assert rollup.loc["same_side", "ever_treated_same_side"] == True    # noqa: E712
    assert rollup.loc["opp_side", "ever_treated_same_side"] == False    # noqa: E712
    assert rollup.loc["far", "ever_treated_same_side"] == False         # noqa: E712

    assert rollup.loc["same_side", "first_treat_year_same_side"] == 2010
    assert pd.isna(rollup.loc["opp_side", "first_treat_year_same_side"])


def test_match_barriers_road_covers_other_wall_category_too():
    schools = _schools([("s", "N1", 500, 30)])
    barriers = _barriers([("priv", "other_wall", None, 495, 505, 5)])
    road_network = _road_network([("r1", 0, 2000, 0)])

    pair, _ = match_barriers_point(schools, barriers, max_dist=1500)
    out = match_barriers_road(pair, schools, barriers, road_network, budget_m=200.0, buffer_m=50.0)

    assert out.iloc[0]["road_id"] == "r1"
    assert out.iloc[0]["same_route"] == True  # noqa: E712
