"""The florida-schools specification, on a small synthetic panel (no real data)."""
import numpy as np
import pandas as pd
import pytest

from noise_pollution.analysis import florida_schools as fl

T = fl.MATCH_TIER
YEARS = range(2005, 2010)
# msid: (ever treated, construction year, timing unknown, side unknown, lateral m, regular)
SCHOOLS = {
    101: (False, np.nan, False, False, np.nan, True),   # control
    102: (True, 2007.0, False, False, 120.0, True),     # near (<= 300 m), bin 1
    103: (True, 2006.0, False, False, 450.0, True),     # far, bin 3
    104: (True, np.nan, True, False, 200.0, True),      # timing unknown: dropped
    105: (False, np.nan, False, True, np.nan, True),    # side unknown: dropped
    106: (False, np.nan, False, False, np.nan, False),  # not a regular school: dropped
}
CELLS = [("3", "ELA", 10.0, 0.0), ("4", "MATH", 30.0, 1.0), ("EOC", "ALG", 20.0, 2.0)]


@pytest.fixture
def panel():
    rows = []
    for msid, (ever, year, unknown, side_unknown, lateral, regular) in SCHOOLS.items():
        for y in YEARS:
            for grade, subject, n, z in CELLS:
                rows.append({
                    "msid": msid, "year": y, "grade": grade, "subject": subject, "is_regular": regular,
                    "z_mss_w": z + 0.01 * msid, "n_students": n,
                    f"ever_treated_{T}": ever, f"first_treat_year_{T}": year, f"timing_unknown_{T}": unknown,
                    f"{T}_unknown": side_unknown, "proposed_protected": msid == 101, "protected_lateral_m": lateral,
                    "traffic_max_aadt_500m": 1000.0, "n_road_projects_active": 0, "shock_any_major_disaster": False,
                    "nbhd_median_household_income": np.nan if y < 2007 else 50_000.0 + msid,
                    "nbhd_poverty_rate": 0.1, "nbhd_pct_bachelors_plus": 0.3, "nbhd_pct_owner_occupied": 0.6,
                    "frpl_n": 10.0 * (msid - 100) + (y - 2005), "enrollment": 100.0, "pct_black": 0.2,
                    "district_number": str(msid % 2 + 1),
                })
    return pd.DataFrame(rows)


def test_build_datasets(panel, capsys):
    d = fl.build_datasets(panel)
    a = d.analysis.set_index(["id", "year"])
    # the n_students-weighted collapse: (10*0 + 30*1 + 20*2) / 60, plus the school offset
    assert a.loc[(102, 2005), "z_mss_w"] == pytest.approx(70 / 60 + 1.02)
    assert sorted(d.analysis["id"].unique()) == [101, 102, 103]
    gvar = d.analysis.groupby("id")["gvar"].first().to_dict()
    assert gvar == {101: 0.0, 102: 2007.0, 103: 2006.0}
    near = d.analysis.groupby("id")[["lat_near", "lat_far", "lat_bin"]].first()
    assert near.loc[102].tolist() == [1, 0, 1] and near.loc[103].tolist() == [0, 1, 3] and near.loc[101].tolist() == [0, 0, 0]
    assert d.analysis.groupby("id")["proposed_ctrl"].first().to_dict() == {101: 1, 102: 0, 103: 0}
    # SES from the earliest vintage with data (2007), logged; FRPL from the first year
    assert a.loc[(102, 2005), "ses_log_income"] == pytest.approx(np.log(50_102.0))
    assert a.loc[(103, 2009), "frpl_base"] == pytest.approx(0.3)
    assert d.analysis["frpl_base_z"].groupby(d.analysis["id"]).first().mean() == pytest.approx(0)
    assert d.analysis["shock_major"].dtype == "float64"
    # cells: one per grade x subject x year, weights sum to 1 per school-year, no cohort for EOC
    assert len(d.cells) == 3 * len(YEARS) * len(CELLS)
    assert d.cells.groupby(["id", "year"])["cell_w"].sum().to_numpy() == pytest.approx(1.0)
    eoc = d.cells["n_students"] == 20  # the EOC cell
    assert d.cells.loc[eoc, "cohort"].isna().all()
    grade = d.cells["year"] - d.cells["cohort"]
    assert (grade[d.cells["n_students"] == 10] == 3).all() and (grade[d.cells["n_students"] == 30] == 4).all()
    out = capsys.readouterr().out
    assert "dropping 5 rows (1 schools): ever-treated but construction year unknown" in out
    assert "dropping 5 rows (1 schools): not treated, but beside a wall whose side is unknown" in out


def test_steps_equal_build_datasets(panel):
    rows, school_year, merged = fl.build_school_year(panel)
    merged, comp, analysis = fl.add_school_baselines(merged, school_year)
    d = fl.build_datasets(panel)
    pd.testing.assert_frame_equal(analysis, d.analysis)
    pd.testing.assert_frame_equal(fl.build_cells(rows, analysis), d.cells)


def test_district_and_control_sets(panel):
    d = fl.build_datasets(panel)
    district = fl.district_by_school(d.school_year)
    assert district.index.dtype == "int64" and district.loc[102] == 1
    assert set(fl.CONTROL_SETS["SES"]) == set(fl.SES_COLS.values())
    for cols in fl.CONTROL_SETS.values():
        assert set(cols) <= set(d.analysis.columns)
