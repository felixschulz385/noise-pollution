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
    attach_neighbourhood,
    attach_road_projects,
    attach_shocks,
    attach_staff,
    attach_traffic,
    build_event_study_panel,
    build_road_projects_year_panel,
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
    same_side_unknown=False, protected_unknown=False,
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


EMPTY_ROAD_PROJECTS = pd.DataFrame(
    columns=[
        "msid", "roadway_id", "fiscal_year", "start_date", "end_date",
        "description", "is_wall_project",
    ]
)


def _road_projects(rows):
    # rows: (msid, roadway_id, fiscal_year, start_date, end_date, description, is_wall_project)
    if not rows:
        return EMPTY_ROAD_PROJECTS.copy()
    out = pd.DataFrame(
        [
            {
                "msid": m, "roadway_id": r, "fiscal_year": fy,
                "start_date": pd.Timestamp(sd) if sd else pd.NaT,
                "end_date": pd.Timestamp(ed) if ed else pd.NaT,
                "description": desc, "is_wall_project": wall,
            }
            for m, r, fy, sd, ed, desc, wall in rows
        ]
    )
    out["fiscal_year"] = out["fiscal_year"].astype("Int64")
    return out


EMPTY_SHOCKS_PANEL = pd.DataFrame(
    columns=["county_name", "assessment_year", "n_declarations", "n_hurricane_declarations", "any_major_disaster"]
)


def _shocks_panel(rows):
    # rows: (county_name, assessment_year, n_declarations, n_hurricane_declarations, any_major_disaster)
    if not rows:
        return EMPTY_SHOCKS_PANEL.copy()
    return pd.DataFrame(
        [
            {
                "county_name": c, "assessment_year": y, "n_declarations": n,
                "n_hurricane_declarations": nh, "any_major_disaster": maj,
            }
            for c, y, n, nh, maj in rows
        ]
    )


EMPTY_DISTRICT_STAFF_PANEL = pd.DataFrame(
    columns=["district_name", "year", "avg_salary", "avg_years_experience", "median_salary", "per_pupil_expenditure"]
)
EMPTY_SCHOOL_STAFF_PANEL = pd.DataFrame(columns=["msid", "year", "pct_out_of_field", "n_classes_total"])


def _district_staff_panel(rows):
    # rows: (district_name, year, avg_salary, avg_years_experience, per_pupil_expenditure)
    if not rows:
        return EMPTY_DISTRICT_STAFF_PANEL.copy()
    return pd.DataFrame(
        [
            {
                "district_name": d, "year": y, "avg_salary": sal,
                "avg_years_experience": exp, "median_salary": np.nan, "per_pupil_expenditure": ppe,
            }
            for d, y, sal, exp, ppe in rows
        ]
    )


def _school_staff_panel(rows):
    # rows: (msid, year, pct_out_of_field, n_classes_total)
    if not rows:
        return EMPTY_SCHOOL_STAFF_PANEL.copy()
    return pd.DataFrame(
        [{"msid": m, "year": y, "pct_out_of_field": p, "n_classes_total": n} for m, y, p, n in rows]
    )


EMPTY_ACS_PANEL = pd.DataFrame(
    columns=["msid", "year", "median_household_income", "poverty_rate", "pct_owner_occupied", "pct_bachelors_plus", "pct_moved_last_year"]
)
EMPTY_ZHVI_PANEL = pd.DataFrame(columns=["msid", "year", "zhvi"])


def _acs_panel(rows):
    # rows: (msid, year, median_household_income, poverty_rate)
    if not rows:
        return EMPTY_ACS_PANEL.copy()
    return pd.DataFrame(
        [
            {
                "msid": m, "year": y, "median_household_income": inc, "poverty_rate": pov,
                "pct_owner_occupied": 0.6, "pct_bachelors_plus": 0.3, "pct_moved_last_year": 0.1,
            }
            for m, y, inc, pov in rows
        ]
    )


def _zhvi_panel(rows):
    # rows: (msid, year, zhvi)
    if not rows:
        return EMPTY_ZHVI_PANEL.copy()
    return pd.DataFrame([{"msid": m, "year": y, "zhvi": z} for m, y, z in rows])


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

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
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

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
    assert list(panel["msid"]) == ["a"]


def test_school_missing_from_rollup_is_never_treated_not_missing():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    # "a" has no wall anywhere near it -> no rollup row for it (only an
    # unrelated school "z" is in the rollup at all).
    rollup = _rollup([("z", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
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

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL).set_index("year")
    assert panel.loc[2015, "event_time_same_side"] == pytest.approx(-3.0)
    assert panel.loc[2020, "event_time_same_side"] == pytest.approx(2.0)


def test_static_columns_renamed_to_avoid_collision_with_assessments():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
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

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
    assert len(panel) == 1
    assert pd.isna(panel.iloc[0]["enrollment"])


def test_treatment_and_static_columns_present():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
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

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, aadt, EMPTY_ROAD_PROJECTS, EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL)
    assert panel.iloc[0]["traffic_aadt"] == 12000.0
    assert panel.iloc[0]["traffic_roadway_id"] == "r1"


def test_build_road_projects_year_panel_explodes_fiscal_year_to_one_row():
    projects = _road_projects([("a", "r1", 2024, None, None, "resurfacing", False)])
    out = build_road_projects_year_panel(projects)
    assert list(out[["msid", "year", "n_road_projects_active"]].itertuples(index=False)) == [("a", 2024, 1)]


def test_build_road_projects_year_panel_explodes_date_range_to_every_year():
    # 2016-07 -> 2018-03 spans calendar years 2016, 2017, 2018.
    projects = _road_projects([("a", "r1", None, "2016-07-01", "2018-03-01", "widening job", False)])
    out = build_road_projects_year_panel(projects)
    assert sorted(out["year"].tolist()) == [2016, 2017, 2018]
    assert (out["n_road_projects_active"] == 1).all()


def test_build_road_projects_year_panel_flags_wall_and_widening_keywords():
    projects = _road_projects(
        [
            ("a", "r1", 2024, None, None, "Perimeter Wall retrofit", True),
            ("a", "r1", 2024, None, None, "ADD LANES & RECONSTR", False),
        ]
    )
    out = build_road_projects_year_panel(projects)
    row = out[(out["msid"] == "a") & (out["year"] == 2024)].iloc[0]
    assert row["n_road_projects_active"] == 2
    assert bool(row["road_project_is_wall"]) is True
    assert bool(row["road_project_is_widening"]) is True


def test_build_road_projects_year_panel_drops_rows_with_no_usable_timing():
    projects = _road_projects([("a", "r1", None, None, None, "unknown timing", False)])
    out = build_road_projects_year_panel(projects)
    assert out.empty


def test_build_road_projects_year_panel_drops_reversed_date_range_without_crashing():
    # EstEndDate is FDOT's own documented estimate and can be revised earlier
    # than StartDate; this must be treated as unusable timing, not crash
    # range(lo, hi + 1) / .astype(int) on an empty exploded span.
    projects = _road_projects(
        [("a", "r1", None, "2021-06-01", "2019-01-01", "reversed dates", False)]
    )
    out = build_road_projects_year_panel(projects)
    assert out.empty


def test_build_road_projects_year_panel_empty_input_returns_empty_frame():
    out = build_road_projects_year_panel(EMPTY_ROAD_PROJECTS)
    assert out.empty
    assert list(out.columns) == ["msid", "year", "n_road_projects_active", "road_project_is_wall", "road_project_is_widening"]


def test_attach_road_projects_exact_year_no_active_project_is_zero_not_na():
    panel = pd.DataFrame({"msid": ["a"], "year": [2020]})
    projects = _road_projects([("a", "r1", 2024, None, None, "unrelated future job", False)])

    out = attach_road_projects(panel, projects)
    assert out.loc[0, "n_road_projects_active"] == 0
    assert out.loc[0, "road_project_is_wall"] is np.False_ or out.loc[0, "road_project_is_wall"] is False
    assert out.loc[0, "road_project_is_widening"] is np.False_ or out.loc[0, "road_project_is_widening"] is False


def test_attach_road_projects_matches_exact_year():
    panel = pd.DataFrame({"msid": ["a", "a"], "year": [2023, 2024]})
    projects = _road_projects([("a", "r1", 2024, None, None, "Perimeter Wall", True)])

    out = attach_road_projects(panel, projects).set_index("year")
    assert out.loc[2023, "n_road_projects_active"] == 0
    assert out.loc[2024, "n_road_projects_active"] == 1
    assert bool(out.loc[2024, "road_project_is_wall"]) is True


def test_attach_road_projects_preserves_row_order():
    panel = pd.DataFrame({"msid": ["b", "a", "b"], "year": [2019, 2019, 2020]})
    projects = _road_projects([("a", "r1", 2019, None, None, "job", False)])

    out = attach_road_projects(panel, projects)
    assert list(out["msid"]) == ["b", "a", "b"]
    assert list(out["year"]) == [2019, 2019, 2020]
    assert list(out["n_road_projects_active"]) == [0, 1, 0]


def test_build_event_study_panel_includes_road_project_columns():
    assessments = _assessments([("a", "03", "ELA", 2024, {})])
    school_year_panel = _school_year_panel([("a", 2024, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])
    projects = _road_projects([("a", "r1", 2024, None, None, "ADD LANES & RECONSTR", False)])

    panel = build_event_study_panel(
        assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, projects, EMPTY_SHOCKS_PANEL,
        EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL,
    )
    assert panel.iloc[0]["n_road_projects_active"] == 1
    assert bool(panel.iloc[0]["road_project_is_widening"]) is True


def test_attach_shocks_matches_exact_district_and_year():
    panel = pd.DataFrame({"district_name": ["BROWARD", "BROWARD"], "year": [2017, 2018]})
    shocks_panel = _shocks_panel([("BROWARD", 2018, 2, 1, True)])

    out = attach_shocks(panel, shocks_panel).set_index("year")
    assert out.loc[2017, "shock_n_declarations"] == 0
    assert bool(out.loc[2017, "shock_any_major_disaster"]) is False
    assert out.loc[2018, "shock_n_declarations"] == 2
    assert out.loc[2018, "shock_n_hurricane_declarations"] == 1
    assert bool(out.loc[2018, "shock_any_major_disaster"]) is True


def test_attach_shocks_unmatched_district_gets_zero_not_na():
    panel = pd.DataFrame({"district_name": ["FSU LAB SCHOOL"], "year": [2018]})
    shocks_panel = _shocks_panel([("BROWARD", 2018, 2, 1, True)])

    out = attach_shocks(panel, shocks_panel)
    assert out.loc[0, "shock_n_declarations"] == 0
    assert bool(out.loc[0, "shock_any_major_disaster"]) is False


def test_attach_shocks_preserves_row_order():
    panel = pd.DataFrame({"district_name": ["BROWARD", "ALACHUA", "BROWARD"], "year": [2018, 2018, 2019]})
    shocks_panel = _shocks_panel([("BROWARD", 2018, 1, 1, False)])

    out = attach_shocks(panel, shocks_panel)
    assert list(out["district_name"]) == ["BROWARD", "ALACHUA", "BROWARD"]
    assert list(out["year"]) == [2018, 2018, 2019]
    assert list(out["shock_n_declarations"]) == [1, 0, 0]


def test_build_event_study_panel_includes_shock_columns():
    assessments = _assessments([("a", "03", "ELA", 2018, {"district_name": "BROWARD"})])
    school_year_panel = _school_year_panel([("a", 2018, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])
    shocks_panel = _shocks_panel([("BROWARD", 2018, 1, 1, True)])

    panel = build_event_study_panel(
        assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS, shocks_panel,
        EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL,
    )
    assert panel.iloc[0]["shock_n_declarations"] == 1
    assert bool(panel.iloc[0]["shock_any_major_disaster"]) is True


def test_attach_staff_district_broadcast_and_school_exact_match():
    panel = pd.DataFrame({"msid": ["a", "b"], "district_name": ["BROWARD", "BROWARD"], "year": [2018, 2018]})
    district_panel = _district_staff_panel([("BROWARD", 2018, 55000.0, 12.0, 9500.0)])
    school_panel = _school_staff_panel([("a", 2018, 0.1, 100)])

    out = attach_staff(panel, district_panel, school_panel)

    # both schools in the district get the same salary/per-pupil figures...
    assert (out["staff_avg_teacher_salary"] == 55000.0).all()
    assert (out["staff_per_pupil_expenditure"] == 9500.0).all()
    # ...but only "a" has its own out-of-field match; "b" is NA, not zeroed.
    a_row = out[out["msid"] == "a"].iloc[0]
    b_row = out[out["msid"] == "b"].iloc[0]
    assert a_row["staff_pct_out_of_field_classes"] == 0.1
    assert pd.isna(b_row["staff_pct_out_of_field_classes"])


def test_attach_staff_unmatched_district_and_school_are_na():
    panel = pd.DataFrame({"msid": ["z"], "district_name": ["FSU LAB SCHOOL"], "year": [2018]})
    district_panel = _district_staff_panel([("BROWARD", 2018, 55000.0, 12.0, 9500.0)])
    school_panel = _school_staff_panel([("a", 2018, 0.1, 100)])

    out = attach_staff(panel, district_panel, school_panel)
    assert pd.isna(out.loc[0, "staff_avg_teacher_salary"])
    assert pd.isna(out.loc[0, "staff_pct_out_of_field_classes"])


def test_build_event_study_panel_includes_staff_columns():
    assessments = _assessments([("a", "03", "ELA", 2018, {"district_name": "BROWARD"})])
    school_year_panel = _school_year_panel([("a", 2018, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])
    district_panel = _district_staff_panel([("BROWARD", 2018, 55000.0, 12.0, 9500.0)])
    school_panel = _school_staff_panel([("a", 2018, 0.1, 100)])

    panel = build_event_study_panel(
        assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS,
        EMPTY_SHOCKS_PANEL, district_panel, school_panel, EMPTY_ACS_PANEL, EMPTY_ZHVI_PANEL,
    )
    assert panel.iloc[0]["staff_avg_teacher_salary"] == 55000.0
    assert panel.iloc[0]["staff_pct_out_of_field_classes"] == 0.1


def test_attach_neighbourhood_exact_msid_year_match():
    panel = pd.DataFrame({"msid": ["a", "b"], "year": [2020, 2020]})
    acs_panel = _acs_panel([("a", 2020, 55000.0, 0.15)])
    zhvi_panel = _zhvi_panel([("a", 2020, 210000.0)])

    out = attach_neighbourhood(panel, acs_panel, zhvi_panel)

    a_row = out[out["msid"] == "a"].iloc[0]
    assert a_row["nbhd_median_household_income"] == 55000.0
    assert a_row["nbhd_poverty_rate"] == 0.15
    assert a_row["nbhd_zhvi"] == 210000.0
    b_row = out[out["msid"] == "b"].iloc[0]
    assert pd.isna(b_row["nbhd_median_household_income"])
    assert pd.isna(b_row["nbhd_zhvi"])


def test_build_event_study_panel_includes_neighbourhood_columns():
    assessments = _assessments([("a", "03", "ELA", 2020, {})])
    school_year_panel = _school_year_panel([("a", 2020, 500)])
    cross_section = _cross_section([("a", 0, 0)])
    rollup = _rollup([("a", {})])
    acs_panel = _acs_panel([("a", 2020, 55000.0, 0.15)])
    zhvi_panel = _zhvi_panel([("a", 2020, 210000.0)])

    panel = build_event_study_panel(
        assessments, school_year_panel, cross_section, rollup, EMPTY_AADT_PANEL, EMPTY_ROAD_PROJECTS,
        EMPTY_SHOCKS_PANEL, EMPTY_DISTRICT_STAFF_PANEL, EMPTY_SCHOOL_STAFF_PANEL, acs_panel, zhvi_panel,
    )
    assert panel.iloc[0]["nbhd_median_household_income"] == 55000.0
    assert panel.iloc[0]["nbhd_zhvi"] == 210000.0


def test_attach_nearby_traffic_takes_the_nearest_release_year():
    from src.regions.florida.sources.panel.assemble import attach_nearby_traffic

    panel = pd.DataFrame({"msid": ["a", "a", "b"], "year": [2010, 2020, 2010]})
    nearby = pd.DataFrame(
        {
            "msid": ["a", "a", "b"],
            "release_year": [2009, 2021, 2009],
            "traffic_max_aadt_250m": [1000.0, 1200.0, np.nan],
            "traffic_max_aadt_500m": [50000.0, 60000.0, 8000.0],
        }
    )
    out = attach_nearby_traffic(panel, nearby, max_year_gap=2).set_index(["msid", "year"])
    assert out.loc[("a", 2010), "traffic_max_aadt_500m"] == 50000.0
    assert out.loc[("a", 2020), "traffic_max_aadt_500m"] == 60000.0
    assert pd.isna(out.loc[("b", 2010), "traffic_max_aadt_250m"])
    assert "release_year" not in out.columns


def test_attach_protected_road_traffic_uses_the_protecting_walls_roadway():
    from src.regions.florida.sources.panel.assemble import attach_protected_road_traffic

    panel = pd.DataFrame({"msid": ["a", "b"], "year": [2015, 2015], "protected_road_id": ["R1", None]})
    aadt = pd.DataFrame({"roadway_id": ["R1", "R2"], "release_year": [2015, 2015], "aadt": [90000.0, 3000.0]})
    out = attach_protected_road_traffic(panel, aadt, max_year_gap=2).set_index("msid")
    assert out.loc["a", "traffic_protected_road_aadt"] == 90000.0
    assert pd.isna(out.loc["b", "traffic_protected_road_aadt"])
