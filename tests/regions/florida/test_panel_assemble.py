"""`panel assemble` (the final event-study join), exercised on tiny synthetic
assessments/schools/rollup frames — no local data needed."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from src.regions.florida.sources.panel.assemble import (
    STATIC_SCHOOL_COLUMNS,
    TREATMENT_COLUMNS,
    TREATMENT_DEFINITIONS,
    attach_traffic,
    build_event_study_panel,
)

CRS = "EPSG:3087"

ASSESSMENT_BASE = dict(
    subject_label="Mathematics", regime="FSA", retrofitted_2015=False,
    district_number="01", school_name="Test School", is_state_total=False,
    suppressed=False, n_students=100, mean_scale_score=300,
    pct_level3_plus=50, pct_l1=10, pct_l2=10, pct_l3=20, pct_l4=30, pct_l5=30,
    z_mss=0.1, z_mss_w=0.1, source_file="x.xls",
)


def _assessments(rows):
    # rows: (msid, grade, subject, year, **overrides)
    out = []
    for msid, grade, subject, year, overrides in rows:
        row = {"msid": msid, "grade": grade, "subject": subject, "year": year,
               "district_name": "Test District", **ASSESSMENT_BASE}
        row.update(overrides)
        out.append(row)
    return pd.DataFrame(out)


def _school_year_panel(rows):
    # rows: (msid, year, enrollment)
    return gpd.GeoDataFrame(
        [{"msid": m, "year": y, "enrollment": e, "geometry": Point(0, 0)} for m, y, e in rows],
        geometry="geometry", crs=CRS,
    )


CROSS_SECTION_BASE = dict(
    name="MSID Name", district_name="MSID District", school_type="Public",
    is_regular=True, is_alternative=False, is_charter=False, is_magnet=False,
    is_virtual=False, grade_low="KG", grade_high="12", serves_tested_grades=True,
)


def _cross_section(rows):
    # rows: (msid, x, y)
    return gpd.GeoDataFrame(
        [{"msid": m, **CROSS_SECTION_BASE, "geometry": Point(x, y)} for m, x, y in rows],
        geometry="geometry", crs=CRS,
    )


ROLLUP_BASE = dict(
    nearest_fdot_dist_m=np.nan, nearest_fdot_gcid=pd.NA,
    n_walls_100m=0, n_walls_200m=0, n_walls_300m=0, n_walls_500m=0, n_walls_1000m=0,
    wall_len_500m=0.0, ever_near_wall_500m=False, ever_near_wall_1000m=False,
    **{f"{stat}_{d}": (np.nan if stat == "first_treat_year" else False)
       for d in TREATMENT_DEFINITIONS for stat in ("first_treat_year", "ever_treated", "timing_unknown")},
)


def _rollup(rows):
    # rows: (msid, overrides dict)
    out = []
    for msid, overrides in rows:
        row = {"msid": msid, **ROLLUP_BASE}
        row.update(overrides)
        out.append(row)
    return pd.DataFrame(out)


EMPTY_AADT_PANEL = pd.DataFrame(columns=["msid", "roadway_id", "release_year", "aadt", "dist_m"])


def _aadt_panel(rows):
    # rows: (msid, roadway_id, release_year, aadt, dist_m)
    if not rows:
        return EMPTY_AADT_PANEL.copy()
    return pd.DataFrame(
        [
            {"msid": m, "roadway_id": r, "release_year": ry, "aadt": a, "dist_m": d}
            for m, r, ry, a, d in rows
        ]
    )


def test_grain_is_one_row_per_assessment_row_no_duplication():
    assessments = _assessments([
        ("a", "03", "ELA", 2020, {}),
        ("a", "03", "MATH", 2020, {}),
        ("a", "04", "ELA", 2020, {}),
        ("b", "03", "ELA", 2020, {}),
    ])
    school_year_panel = _school_year_panel([("a", 2020, 500), ("b", 2020, 300)])
    cross_section = _cross_section([("a", 0, 0), ("b", 100, 0)])
    rollup = _rollup([("a", {}), ("b", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL)
    assert len(panel) == 4
    assert panel.drop_duplicates(["msid", "grade", "subject", "year"]).shape[0] == 4


def test_state_total_rows_are_dropped():
    assessments = _assessments([
        ("000000", "03", "ELA", 2020, {"is_state_total": True}),
        ("a", "03", "ELA", 2020, {}),
    ])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL)
    assert list(panel["msid"]) == ["a"]


def test_school_missing_from_rollup_is_never_treated_not_missing():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    # "a" has no wall anywhere near it -> no rollup row for it (only an
    # unrelated school "z" is in the rollup at all).
    rollup = _rollup([("z", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL)
    row = panel.iloc[0]
    for definition in TREATMENT_DEFINITIONS:
        assert row[f"ever_treated_{definition}"] == False   # noqa: E712 -- not NaN
        assert row[f"timing_unknown_{definition}"] == False  # noqa: E712
        assert pd.isna(row[f"first_treat_year_{definition}"])


def test_event_time_is_year_minus_first_treat_year():
    assessments = _assessments([
        ("a", "03", "ELA", 2015, {}),
        ("a", "03", "ELA", 2020, {}),
    ])
    school_year_panel = _school_year_panel([("a", 2015, 500), ("a", 2020, 520)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {"first_treat_year_same_side": 2018.0, "ever_treated_same_side": True})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL).set_index("year")
    assert panel.loc[2015, "event_time_same_side"] == pytest.approx(-3.0)
    assert panel.loc[2020, "event_time_same_side"] == pytest.approx(2.0)


def test_static_columns_renamed_to_avoid_collision_with_assessments():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL)
    assert "msid_school_name" in panel.columns and "msid_district_name" in panel.columns
    assert panel.iloc[0]["msid_school_name"] == "MSID Name"
    # assessments' own district_name / school_name survive un-suffixed.
    assert panel.iloc[0]["district_name"] == "Test District"
    assert panel.iloc[0]["school_name"] == "Test School"
    assert not any(c.endswith(("_x", "_y")) for c in panel.columns)


def test_missing_covariate_row_keeps_the_assessment_row():
    # "b" has an assessment row for 2021 but no school_year_panel row that
    # year -- the outcome row must survive with NaN covariates, not vanish.
    assessments = _assessments([("b", "03", "ELA", 2021, {})])
    school_year_panel = _school_year_panel([("z", 1999, 1.0)])  # unrelated school/year only
    cross_section = _cross_section([("b", 0, 0)])
    rollup = _rollup([("b", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL)
    assert len(panel) == 1
    assert pd.isna(panel.iloc[0]["enrollment"])


def test_treatment_and_static_columns_present():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL)
    for col in TREATMENT_COLUMNS:
        if col == "msid":
            continue
        assert col in panel.columns
    for col in STATIC_SCHOOL_COLUMNS:
        if col in ("msid", "name", "district_name"):
            continue
        assert col in panel.columns


def test_attach_traffic_picks_nearest_release_year_within_tolerance():
    panel = pd.DataFrame({"msid": ["a", "a"], "year": [2013, 2019]})
    aadt = _aadt_panel(
        [
            ("a", "r1", 2011, 8000.0, 10.0),
            ("a", "r1", 2016, 9000.0, 10.0),
            ("a", "r1", 2019, 12000.0, 10.0),
        ]
    )

    out = attach_traffic(panel, aadt, max_year_gap=2).set_index("year")
    # 2013 is 2 away from 2011 and 3 away from 2016 -> matches 2011.
    assert out.loc[2013, "traffic_release_year"] == 2011
    assert out.loc[2013, "traffic_aadt"] == 8000.0
    # exact match
    assert out.loc[2019, "traffic_release_year"] == 2019
    assert out.loc[2019, "traffic_aadt"] == 12000.0


def test_attach_traffic_drops_match_beyond_tolerance():
    # 2013 is 2 years from the nearest release (2011) -- beyond a tolerance
    # of 1, so it must come back NA, not a stale match.
    panel = pd.DataFrame({"msid": ["a"], "year": [2013]})
    aadt = _aadt_panel([("a", "r1", 2011, 8000.0, 10.0), ("a", "r1", 2016, 9000.0, 10.0)])

    out = attach_traffic(panel, aadt, max_year_gap=1)
    assert pd.isna(out.loc[0, "traffic_aadt"])
    assert pd.isna(out.loc[0, "traffic_release_year"])


def test_attach_traffic_preserves_row_order_and_keeps_unmatched_school():
    panel = pd.DataFrame({"msid": ["b", "a", "b"], "year": [2019, 2019, 2020]})
    aadt = _aadt_panel([("a", "r1", 2019, 12000.0, 10.0)])  # nothing for "b"

    out = attach_traffic(panel, aadt, max_year_gap=2)
    assert list(out["msid"]) == ["b", "a", "b"]
    assert list(out["year"]) == [2019, 2019, 2020]
    assert pd.isna(out.loc[out["msid"] == "b", "traffic_aadt"]).all()
    assert out.loc[out["msid"] == "a", "traffic_aadt"].iloc[0] == 12000.0


def test_build_event_study_panel_includes_traffic_columns():
    assessments = _assessments([("a", "03", "ELA", 2019, {})])
    school_year_panel = _school_year_panel([("a", 2019, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])
    aadt = _aadt_panel([("a", "r1", 2019, 12000.0, 10.0)])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, aadt)
    assert panel.iloc[0]["traffic_aadt"] == 12000.0
    assert panel.iloc[0]["traffic_roadway_id"] == "r1"
