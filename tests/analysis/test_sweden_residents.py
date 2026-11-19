"""Group sizes and the MDE of the sweden-residents design, on hand-built inputs (no real data)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from noise_pollution.analysis import sweden_residents as sr
from noise_pollution.core.barrier_geometry.linear_ref import signed_side
from noise_pollution.core.barrier_geometry.protection import BarrierReferences


def test_the_short_window_step_has_variance_seven_sixths_of_one_cohort():
    # post mean of 3 cohorts (1/3) + level at e=-2 fitted with a trend through e=-4..-2 (5/6)
    assert sr.variance_factor(sr.DESIGNS["short"], "delta_SR") == pytest.approx(7 / 6)


def test_the_windows_follow_the_grade_years():
    assert sr.WINDOWS == {"short": (2000, 2019), "full": (2000, 2005)}


def test_mde_of_one_stack_matches_the_formula():
    sizes = pd.DataFrame({"protected": [100.0], "opposite": [100.0], "band": [0.0], "tau": [2010]})
    out = sr.mde(sizes, "opposite", sr.DESIGNS["short"], "delta_SR")
    se = np.sqrt(7 / 6 * (1 / 100 + 1 / 100))
    assert out["mde_sd"] == pytest.approx((sr.Z_ALPHA + sr.Z_POWER) * se)
    assert out["mde_sd_inverse_variance"] == pytest.approx(out["mde_sd"])
    assert out["mde_percentile_points"] == pytest.approx(out["mde_sd"] * 100 / np.sqrt(12))


def test_mde_drops_stacks_without_enough_comparison_children_and_reports_the_loss():
    sizes = pd.DataFrame({"protected": [30.0, 10.0], "opposite": [50.0, 0.5], "band": [0.0, 20.0], "tau": [2010, 2011]})
    out = sr.mde(sizes, "opposite", sr.DESIGNS["short"], "delta_SR")
    assert out["stacks"] == 1 and out["protected_lost_share"] == pytest.approx(0.25)
    both = sr.mde(sizes, "both", sr.DESIGNS["short"], "delta_SR")
    assert both["stacks"] == 2


def test_an_icc_floors_the_variance():
    sizes = pd.DataFrame({"protected": [1e9], "opposite": [1e9], "band": [0.0], "tau": [2010]})
    out = sr.mde(sizes, "opposite", sr.DESIGNS["short"], "delta_SR", icc=0.02)
    assert out["mde_sd"] == pytest.approx((sr.Z_ALPHA + sr.Z_POWER) * np.sqrt(7 / 6 * 0.04), rel=1e-6)


def test_interpolate_ghs_is_linear_between_epochs_and_flat_outside():
    ghs = pd.DataFrame({"cell_id": ["a"], "pop_2000": [10.0], "pop_2005": [20.0]})
    assert sr.interpolate_ghs(ghs, 2002)[0] == pytest.approx(14.0)
    assert sr.interpolate_ghs(ghs, 1990)[0] == pytest.approx(10.0)
    assert sr.interpolate_ghs(ghs, 2030)[0] == pytest.approx(20.0)


def test_children_per_cohort_uses_the_cell_share_or_the_national_one():
    ghs = pd.DataFrame({"cell_id": ["a", "b"], "pop_2015": [100.0, 100.0]})
    scb = pd.DataFrame(
        {"cell_id": ["a", "c"], "year": [2015, 2015], "pop": [10.0, 30.0], "age_0_4": [2.0, 3.0], "age_5_9": [2.0, 0.0],
         "age_10_14": [0.0, 0.0], "age_15_19": [0.0, 0.0]}
    )
    out = sr.children_per_cohort(ghs, scb, [2010])
    # a: 40% aged 0-19; b: none in SCB -> national 7/40
    assert out[2010].tolist() == pytest.approx([100 * 0.4 / 20, 100 * 7 / 40 / 20])


def test_stack_cells_keeps_clean_comparisons_and_protected_cells_of_the_barriers_year():
    # cells: 0 protected by b (2010), 1 protected earlier by another barrier, 2 clean opposite,
    # 3 opposite but protected in 2012 (inside the short window), 4 opposite protected 2020
    # (after it), 5 opposite of unknown side, 6 opposite, a barrier dated 1990 (outside)
    pairs = pd.DataFrame(
        {
            "cell": [0, 1, 2, 3, 4, 5, 6],
            "barrier_row": [0, 0, 0, 0, 0, 0, 1],
            "group": ["protected", "protected", "opposite", "opposite", "opposite", "opposite", "opposite"],
            "lateral_m": [50.0] * 7,
        }
    )
    status = pd.DataFrame(
        {
            "treated": [True, True, False, True, True, False, False],
            "treat_year": pd.array([2010, 2004, None, 2012, 2020, None, None], dtype="Int16"),
            "timing_unknown": [False] * 7,
            "side_unknown": [False, False, False, False, False, True, False],
        }
    )
    out = sr.stack_cells(pairs, status, np.array([2010.0, 1990.0]), "short")
    assert sorted(out["cell"].tolist()) == [0, 2, 4]
    assert set(out["rho"]) == {2007}


def test_stack_sizes_sums_children_at_rho():
    cells = pd.DataFrame({"cell": [0, 1, 1], "barrier_row": [0, 0, 1], "group": ["protected", "opposite", "band"], "tau": [2010, 2010, 2012], "rho": [2007, 2007, 2009]})
    children = pd.DataFrame({2007: [2.0, 3.0], 2009: [5.0, 7.0]})
    out = sr.stack_sizes(cells, children)
    assert out.loc[0, ["protected", "opposite", "band"]].tolist() == [2.0, 3.0, 0.0]
    assert out.loc[1, ["protected", "opposite", "band"]].tolist() == [0.0, 0.0, 7.0]


def test_barrier_cell_pairs_finds_the_three_groups():
    line = LineString([(0, 0), (4000, 0)])
    sign = float(signed_side(line, [Point(2150, 100)])[0][0])
    table = pd.DataFrame([{"side_method": "geometric_offset", "barrier_sign": sign, "span_start_m": 2000.0, "span_end_m": 2300.0}])
    refs = BarrierReferences(table=table, corridors={0: line}, lines={0: line}, buffer_m=600.0, crs="EPSG:3006")
    barriers = gpd.GeoDataFrame(geometry=[LineString([(2000, 10), (2300, 10)])], crs="EPSG:3006")
    points = np.array([Point(2150, 300), Point(2150, -300), Point(2150, 1000), Point(3500, 300)], dtype=object)
    out = sr.barrier_cell_pairs(points, barriers, refs)
    assert dict(zip(out["cell"], out["group"])) == {0: "protected", 1: "opposite", 2: "band"}
    assert out.set_index("cell").loc[2, "lateral_m"] == pytest.approx(1000.0)


def test_mde_without_usable_stacks_is_missing():
    sizes = pd.DataFrame({"protected": [5.0], "opposite": [0.2], "band": [0.0], "tau": [2010]})
    out = sr.mde(sizes, "opposite", sr.DESIGNS["short"], "delta_SR")
    assert out["stacks"] == 0 and np.isnan(out["mde_sd"])


def test_date_bounds_read_the_register_entry():
    road = pd.DataFrame({"valid_from": ["2006-02-01", "2018-05-01", None]})
    upper, vintage = sr.date_bounds(road, "road")
    assert np.isnan(upper[2]) and list(upper[:2]) == [2006, 2018]
    assert list(vintage) == ["nvdb-2006", "later", "later"]
    rail = pd.DataFrame({"connection_date": ["2019-04-05", "2022-09-29"], "connection_date_is_before_flag": [True, False]})
    upper, vintage = sr.date_bounds(rail, "rail")
    assert list(upper) == [2019, 2022] and list(vintage) == ["before-2019", "later"]


def test_impute_keeps_dated_years_and_respects_the_bound():
    built = np.array([1995.0, 2003.0, 2015.0, np.nan, np.nan])
    upper = np.array([2006, 2006, 2018, 2006, 2018], dtype=float)
    vintage = np.array(["a", "a", "b", "a", "b"])
    rng = np.random.default_rng(0)
    assert np.array_equal(sr.impute_built_years(built, upper, vintage, "current", rng), built, equal_nan=True)
    for _ in range(50):
        exp = sr.impute_built_years(built, upper, vintage, "expected", rng)
        assert list(exp[:3]) == [1995, 2003, 2015]
        assert exp[3] in (1995, 2003) and exp[4] == 2015
        ceil = sr.impute_built_years(built, upper, vintage, "ceiling", rng, window="short")
        assert 2000 <= ceil[3] <= 2006 and 2000 <= ceil[4] <= 2018


def test_impute_ceiling_puts_an_early_bound_in_the_first_window_year():
    out = sr.impute_built_years(np.array([np.nan]), np.array([1998.0]), np.array(["a"]), "ceiling",
                                np.random.default_rng(0), window="full")
    assert out[0] == 2000


def test_protected_status_takes_the_earliest_protecting_barrier():
    pairs = pd.DataFrame({
        "cell": [0, 0, 1, 2, 3],
        "barrier_row": [0, 1, 1, 2, 0],
        "group": ["protected", "protected", "protected", "protected", "band"],
    })
    built = np.array([2010.0, 2004.0, np.nan])
    st = sr.protected_status(pairs, np.array([True, True, True, False]), np.zeros(4, bool), built)
    assert st.loc[0, "treat_year"] == 2004 and not st.loc[0, "timing_unknown"]
    assert st.loc[1, "treat_year"] == 2004
    assert np.isnan(st.loc[2, "treat_year"]) and st.loc[2, "timing_unknown"]
    assert np.isnan(st.loc[3, "treat_year"]) and not st.loc[3, "timing_unknown"]
