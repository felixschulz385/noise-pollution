"""The sweden-schools specification, on a small synthetic long panel (no real data)."""
import numpy as np
import pandas as pd
import pytest

from noise_pollution.analysis import sweden_schools as se

T = se.MATCH_TIER
YEARS = range(2000, 2006)


def _school(sid, *, road=None, rail=None, road_unknown=False, rail_unknown=False, side_unknown=False):
    """One school's treatment columns. ``road``/``rail``: construction year, or None if untreated."""
    cols = {}
    for kind, year, unknown in (("road", road, road_unknown), ("rail", rail, rail_unknown)):
        cols[f"{kind}_ever_treated_{T}"] = year is not None
        cols[f"{kind}_timing_unknown_{T}"] = unknown
        cols[f"{kind}_first_treat_year_{T}"] = np.nan if year is None or unknown else float(year)
        cols[f"{kind}_{T}_unknown"] = side_unknown and kind == "road"
    return sid, cols


SCHOOLS = dict([
    _school(1),                               # never treated
    _school(2, road=2003),                    # road only
    _school(3, road=2004, rail=2002),         # both kinds: the earlier year counts
    _school(4, rail=2003, rail_unknown=True),  # treated, no construction year: dropped
    _school(5, side_unknown=True),            # untreated beside a barrier of unknown side: dropped
    _school(6, road=2003, rail=2001, rail_unknown=True),  # one usable kind: kept, road year
])


@pytest.fixture
def panel():
    rows = []
    for sid, cols in SCHOOLS.items():
        for y in YEARS:
            base = {"skolenhetskod": str(sid), "year": y, **cols, "traffic_max_adt_500m": 100.0 * sid,
                    "neighbourhood_mean_net_income_tkr": 300.0, "neighbourhood_share_eftergymnasial": np.nan}
            rows.append({**base, "outcome_name": se.OUTCOME_NAME, "value": sid + 0.1 * (y - 2000)})
            rows.append({**base, "outcome_name": "other", "value": -1.0})
            for col, name in se.BASELINE_OUTCOMES.items():
                value = {"parent_edu": 2.0 + 0.1 * sid, "born_abroad": 5.0, "foreign_parents": float(sid)}[col]
                rows.append({**base, "outcome_name": name, "value": value + (y - 2000)})
    return pd.DataFrame(rows)


def test_build_analysis_sample_and_treatment(panel, capsys):
    analysis = se.build_analysis(panel)
    assert list(analysis.columns) == ["id", "year", "gvar", se.OUTCOME_STATA, *se.COVARIATES.values()]
    gvar = analysis.groupby("id")["gvar"].first().to_dict()
    assert gvar == {1: 0.0, 2: 2003.0, 3: 2002.0, 6: 2003.0}
    assert analysis["id"].dtype == "int64"
    assert len(analysis) == 4 * len(YEARS)
    out = capsys.readouterr().out
    assert "dropping 6 rows (1 schools): ever-treated but every matching barrier's construction year is unknown" in out
    assert "dropping 6 rows (1 schools): not treated, but beside a barrier whose side is unknown" in out
    assert "3 with a usable combined treatment year" in out


def test_pull_outcome(panel):
    out = se.pull_outcome(panel, "other", "z")
    assert list(out.columns) == ["id", "year", "z"]
    assert out["id"].dtype == "int64" and (out["z"] == -1.0).all()
    assert len(out) == len(SCHOOLS) * len(YEARS)


def test_baselines_first_year_and_standardised(panel, capsys):
    analysis = se.build_analysis(panel)
    bl = se.baselines(panel, analysis)
    # the first observed year's values (2000): parent_edu 2.0 + 0.1 * id; foreign 5 + id
    assert bl.base.loc[2, "parent_edu_base"] == pytest.approx(2.2)
    assert bl.base.loc[3, "foreign_base"] == pytest.approx(8.0)
    assert (bl.base["parent_edu_base_year"] == 2000).all()
    for col in ("parent_edu_base_z", "foreign_base_z"):
        assert bl.base[col].mean() == pytest.approx(0) and bl.base[col].std() == pytest.approx(1)
    # treated schools observed before and after construction: 2, 3, 6
    assert sorted(bl.identifying.index) == [2, 3, 6]
    assert set(bl.heterogeneity.columns) >= {"edu_high", "foreign_high"}
    assert len(bl.heterogeneity) == len(analysis)
