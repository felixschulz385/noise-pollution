"""`match_schools_to_roadway` (nearest-arterial + milepost, reusing
`road_network/linear_ref.py`), `match_school_projects` (milepost-overlap join
against `road_projects.parquet`), and `build_summary` (always-present
per-school rollup), exercised on synthetic geometry/tables -- no local data
needed."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.florida.sources.road_projects.assemble import (
    build_summary,
    match_school_projects,
    match_schools_to_roadway,
)

CRS = "EPSG:3087"


def _road_row(rid, x0, y0, x1, y1, fc, begin_post=10.0, end_post=20.0):
    return {
        "roadway_id": rid,
        "begin_post": begin_post,
        "end_post": end_post,
        "funclass": fc,
        "geometry": LineString([(x0, y0), (x1, y1)]),
    }


def _roads(rows):
    return gpd.GeoDataFrame([_road_row(*row) for row in rows], geometry="geometry", crs=CRS)


def _schools(rows):
    return gpd.GeoDataFrame(
        {"msid": [r[0] for r in rows]},
        geometry=[Point(r[1], r[2]) for r in rows],
        crs=CRS,
    )


def _project(roadway_id, begin_post, end_post, description="", is_wall=False, **overrides):
    row = {
        "source": "work_program_construction",
        "roadway_id": roadway_id,
        "begin_post": begin_post,
        "end_post": end_post,
        "fiscal_year": pd.NA,
        "start_date": pd.NaT,
        "end_date": pd.NaT,
        "description": description,
        "is_wall_project": is_wall,
        "cost": pd.NA,
    }
    row.update(overrides)
    return row


def test_match_schools_to_roadway_computes_milepost():
    # road_a: 100m long, milepost 10 -> 20; school at x=25 -> frac 0.25 -> milepost 12.5
    roads = _roads([("road_a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other", 10.0, 20.0)])
    schools = _schools([("s1", 25, 5)])

    out = match_schools_to_roadway(schools, roads)

    assert out.loc[0, "roadway_id"] == "road_a"
    assert out.loc[0, "milepost"] == pytest.approx(12.5, abs=1e-3)


def test_match_schools_to_roadway_beyond_max_dist_is_na():
    roads = _roads([("road_a", 0, 0, 100, 0, "URBAN: Principal Arterial - Other")])
    schools = _schools([("far", 50, 2000)])

    out = match_schools_to_roadway(schools, roads, max_dist=1000.0)

    assert pd.isna(out.loc[0, "roadway_id"])
    assert pd.isna(out.loc[0, "milepost"])


def test_match_school_projects_within_tolerance():
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_a"], "dist_m": [10.0], "milepost": [12.5]}
    )
    projects = pd.DataFrame([_project("road_a", 12.0, 13.0, description="resurfacing")])

    out = match_school_projects(school_road_match, projects, tolerance_mi=0.25)

    assert len(out) == 1
    assert out.loc[0, "msid"] == "s1"


def test_match_school_projects_outside_tolerance_excluded():
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_a"], "dist_m": [10.0], "milepost": [12.5]}
    )
    projects = pd.DataFrame([_project("road_a", 15.0, 16.0, description="far-away job")])

    out = match_school_projects(school_road_match, projects, tolerance_mi=0.25)

    assert len(out) == 0


def test_match_school_projects_boundary_within_tolerance_included():
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_a"], "dist_m": [10.0], "milepost": [12.5]}
    )
    # begin_post 12.75, tolerance 0.25 -> effective start 12.5 -> boundary inclusive
    projects = pd.DataFrame([_project("road_a", 12.75, 13.0, description="boundary job")])

    out = match_school_projects(school_road_match, projects, tolerance_mi=0.25)

    assert len(out) == 1


def test_match_school_projects_different_roadway_excluded():
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_a"], "dist_m": [10.0], "milepost": [12.5]}
    )
    projects = pd.DataFrame([_project("road_b", 12.0, 13.0, description="different road")])

    out = match_school_projects(school_road_match, projects, tolerance_mi=0.25)

    assert len(out) == 0


def test_match_school_projects_unmatched_school_contributes_no_rows():
    school_road_match = pd.DataFrame(
        {"msid": ["orphan"], "roadway_id": [pd.NA], "dist_m": [5000.0], "milepost": [pd.NA]}
    )
    projects = pd.DataFrame([_project("road_a", 12.0, 13.0)])

    out = match_school_projects(school_road_match, projects, tolerance_mi=0.25)

    assert len(out) == 0


def test_build_summary_counts_and_flags():
    placed = _schools([("s1", 25, 5), ("s2", 25, 5)])
    school_road_match = pd.DataFrame(
        {
            "msid": ["s1", "s2"],
            "roadway_id": ["road_a", "road_a"],
            "dist_m": [10.0, 10.0],
            "milepost": [12.5, 12.5],
        }
    )
    school_road_projects = pd.DataFrame(
        [
            {**_project("road_a", 12.0, 13.0, description="ADD LANES & RECONSTR", is_wall=False), "msid": "s1"},
            {**_project("road_a", 12.0, 13.0, description="Perimeter Wall", is_wall=True), "msid": "s1"},
        ]
    )

    out = build_summary(placed, school_road_match, school_road_projects)

    s1 = out[out["msid"] == "s1"].iloc[0]
    s2 = out[out["msid"] == "s2"].iloc[0]
    assert s1["n_projects_nearby"] == 2
    assert s1["n_wall_projects_nearby"] == 1
    assert s1["n_widening_projects_nearby"] == 1
    assert s2["n_projects_nearby"] == 0
    assert s2["n_wall_projects_nearby"] == 0


def test_build_summary_always_has_one_row_per_placed_school_even_with_no_projects():
    placed = _schools([("s1", 25, 5)])
    school_road_match = pd.DataFrame(
        {"msid": ["s1"], "roadway_id": ["road_a"], "dist_m": [10.0], "milepost": [12.5]}
    )
    empty_projects = pd.DataFrame(columns=["msid", "roadway_id", "description", "is_wall_project"])

    out = build_summary(placed, school_road_match, empty_projects)

    assert len(out) == 1
    assert out.loc[0, "n_projects_nearby"] == 0
