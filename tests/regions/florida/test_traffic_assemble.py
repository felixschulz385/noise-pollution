"""`match_schools_to_roadway` (nearest-arterial matching, reused from
`road_network/linear_ref.py`), `compute_local_intensity` (the current-
snapshot local-intensity scaling ratio), and `build_school_aadt_panel` (the
left join onto a roadway's AADT time series), exercised on synthetic
geometry/tables — no local data needed."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.florida.sources.traffic.assemble import (
    build_school_aadt_panel,
    build_school_nearby_aadt,
    compute_local_intensity,
    match_schools_to_nearby_roadways,
    match_schools_to_roadway,
)

CRS = "EPSG:3087"


def _road_row(rid, x0, y0, x1, y1, fc, aadt=0.0):
    return {
        "roadway_id": rid,
        "begin_post": 0.0,
        "end_post": 1.0,
        "funclass": fc,
        "aadt": aadt,
        "geometry": LineString([(x0, y0), (x1, y1)]),
    }


def _roads(rows):
    # rows: (roadway_id, x0, y0, x1, y1, funclass) or (..., funclass, aadt)
    return gpd.GeoDataFrame([_road_row(*row) for row in rows], geometry="geometry", crs=CRS)


def _schools(rows):
    # rows: (msid, x, y)
    return gpd.GeoDataFrame(
        {"msid": [r[0] for r in rows]},
        geometry=[Point(r[1], r[2]) for r in rows],
        crs=CRS,
    )


def test_match_schools_to_roadway_picks_nearest_arterial():
    roads = _roads(
        [
            ("road_a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other", 15000.0),
            ("road_b", 0, 50, 100, 50, "URBAN: Principal Arterial - Other", 8000.0),
            ("road_local", 0, 5, 100, 5, "URBAN: Local", 99999.0),  # closer, but not arterial
        ]
    )
    schools = _schools([("s1", 50, 10), ("s2", 50, 45)])

    out = match_schools_to_roadway(schools, roads)

    assert list(out["msid"]) == ["s1", "s2"]
    assert list(out["roadway_id"]) == ["road_a", "road_b"]
    assert out.loc[out["msid"] == "s1", "dist_m"].iloc[0] == pytest.approx(10.0)
    assert list(out["nearest_segment_aadt"]) == [15000.0, 8000.0]


def test_match_schools_to_roadway_beyond_max_dist_is_na():
    roads = _roads([("road_a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other", 15000.0)])
    schools = _schools([("far", 50, 2000)])

    out = match_schools_to_roadway(schools, roads, max_dist=1000.0)

    assert pd.isna(out.loc[out["msid"] == "far", "roadway_id"].iloc[0])
    assert pd.isna(out.loc[out["msid"] == "far", "nearest_segment_aadt"].iloc[0])
    # dist_m itself is kept even when the match is dropped, for diagnostics
    assert out.loc[out["msid"] == "far", "dist_m"].iloc[0] == pytest.approx(2000.0)


def test_match_schools_to_roadway_treats_non_positive_segment_aadt_as_missing():
    roads = _roads([("road_a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other", 0.0)])
    schools = _schools([("s1", 50, 10)])

    out = match_schools_to_roadway(schools, roads)
    assert pd.isna(out.loc[0, "nearest_segment_aadt"])


def test_compute_local_intensity_ratio():
    school_road_match = pd.DataFrame(
        {
            "msid": ["s1", "s2"],
            "roadway_id": ["road_a", "road_a"],
            "dist_m": [10.0, 20.0],
            "nearest_segment_aadt": [30000.0, 10000.0],  # s1's segment is busier than s2's
        }
    )
    aadt_panel = pd.DataFrame(
        {"roadway_id": ["road_a", "road_a"], "release_year": [2019, 2026], "aadt": [20000.0, 20000.0]}
    )

    out = compute_local_intensity(school_road_match, aadt_panel, reference_release_year=2026)

    assert out.loc[out["msid"] == "s1", "local_intensity_ratio"].iloc[0] == pytest.approx(1.5)
    assert out.loc[out["msid"] == "s2", "local_intensity_ratio"].iloc[0] == pytest.approx(0.5)
    assert (out["local_reference_release_year"] == 2026).all()


def test_compute_local_intensity_na_when_roadway_has_no_reference_aadt():
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_unknown"], "dist_m": [10.0], "nearest_segment_aadt": [30000.0]}
    )
    aadt_panel = pd.DataFrame({"roadway_id": ["road_a"], "release_year": [2026], "aadt": [20000.0]})

    out = compute_local_intensity(school_road_match, aadt_panel, reference_release_year=2026)
    assert pd.isna(out.loc[0, "local_intensity_ratio"])


def test_build_school_aadt_panel_left_joins_by_roadway():
    school_road_match = pd.DataFrame(
        {"msid": ["s1", "s2"], "roadway_id": ["road_a", "road_b"], "dist_m": [10.0, 20.0]}
    )
    aadt_panel = pd.DataFrame(
        {
            "roadway_id": ["road_a", "road_a", "road_b"],
            "release_year": [2019, 2026, 2019],
            "aadt": [10000.0, 12000.0, 5000.0],
        }
    )

    out = build_school_aadt_panel(school_road_match, aadt_panel)

    s1_years = out.loc[out["msid"] == "s1", "release_year"].tolist()
    assert s1_years == [2019, 2026]
    assert out.loc[(out["msid"] == "s2") & (out["release_year"] == 2019), "aadt"].iloc[0] == 5000.0


def test_build_school_aadt_panel_computes_aadt_local_from_ratio():
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_a"], "dist_m": [10.0], "local_intensity_ratio": [1.5]}
    )
    aadt_panel = pd.DataFrame(
        {"roadway_id": ["road_a", "road_a"], "release_year": [2019, 2026], "aadt": [10000.0, 20000.0]}
    )

    out = build_school_aadt_panel(school_road_match, aadt_panel)
    assert out.loc[out["release_year"] == 2019, "aadt_local"].iloc[0] == pytest.approx(15000.0)
    assert out.loc[out["release_year"] == 2026, "aadt_local"].iloc[0] == pytest.approx(30000.0)


def test_build_school_aadt_panel_keeps_unmatched_school_with_na_row():
    school_road_match = pd.DataFrame({"msid": ["s1", "orphan"], "roadway_id": ["road_a", pd.NA], "dist_m": [10.0, 5000.0]})
    aadt_panel = pd.DataFrame({"roadway_id": ["road_a"], "release_year": [2019], "aadt": [10000.0]})

    out = build_school_aadt_panel(school_road_match, aadt_panel)

    assert "orphan" in set(out["msid"])
    orphan_row = out[out["msid"] == "orphan"]
    assert len(orphan_row) == 1
    assert pd.isna(orphan_row["aadt"].iloc[0])
    assert pd.isna(orphan_row["release_year"].iloc[0])


def test_nearby_roadways_include_every_road_within_the_radius_with_its_closest_distance():
    roads = _roads([
        ("LOCAL", -500, 100, 500, 100, "URBAN: Local"),
        ("HWY", -500, 400, 500, 400, "URBAN: Principal Arterial - Interstate"),
        ("HWY", 500, 400, 900, 450, "URBAN: Principal Arterial - Interstate"),
        ("FAR", -500, 900, 500, 900, "URBAN: Principal Arterial - Other"),
    ])
    nearby = match_schools_to_nearby_roadways(_schools([("s", 0, 0)]), roads, radius=500).set_index("roadway_id")
    assert sorted(nearby.index) == ["HWY", "LOCAL"]  # FAR is beyond 500m
    assert nearby.loc["HWY", "dist_m"] == pytest.approx(400.0)


def test_nearby_aadt_is_the_busiest_road_within_each_radius():
    nearby = pd.DataFrame({"msid": ["s", "s"], "roadway_id": ["LOCAL", "HWY"], "dist_m": [100.0, 400.0]})
    aadt = pd.DataFrame(
        {"roadway_id": ["LOCAL", "HWY", "HWY"], "release_year": [2015, 2015, 2016], "aadt": [4000.0, 90000.0, 95000.0]}
    )
    out = build_school_nearby_aadt(nearby, aadt).set_index("release_year")
    assert out.loc[2015, "traffic_max_aadt_250m"] == 4000.0
    assert out.loc[2015, "traffic_max_aadt_500m"] == 90000.0
    assert out.loc[2016, "traffic_max_aadt_500m"] == 95000.0
    assert pd.isna(out.loc[2016, "traffic_max_aadt_250m"])
