"""The shared DiD helpers, on small hand-built panels (no real data)."""
import numpy as np
import pandas as pd
import pytest

from noise_pollution.analysis import did


def _panel(values: dict[int, list[float]], gvar: dict[int, float], years=(2000, 2001, 2002)) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": i, "year": y, "gvar": gvar[i], "y": v} for i, vs in values.items() for y, v in zip(years, vs)]
    )


def test_cs_simple_att_matches_hand_computation():
    # A treated 2001, C treated 2002, B never treated
    df = _panel({1: [0.0, 1.0, 3.0], 2: [0.0, 0.5, 1.0], 3: [0.0, 0.0, 2.0]}, {1: 2001, 2: 0, 3: 2002})
    # g=2001, t=2001: A +1.0 vs. mean(B +0.5, C +0.0) = 0.25 -> 0.75
    # g=2001, t=2002: A +3.0 vs. B +1.0 (C treated by then)    -> 2.0
    # g=2002, t=2002: C +2.0 (from 2001) vs. B +0.5             -> 1.5
    assert did.cs_simple_att(df, "y") == pytest.approx((0.75 + 2.0 + 1.5) / 3)


def test_cs_simple_att_recovers_a_constant_effect():
    rng = np.random.default_rng(0)
    years = np.arange(2000, 2010)
    rows = []
    for i in range(60):
        g = [0, 2004, 2006][i % 3]
        level, trend = rng.normal(), 0.1
        for y in years:
            rows.append({"id": i, "year": y, "gvar": g, "y": level + trend * (y - 2000) + (0.4 if g and y >= g else 0)})
    assert did.cs_simple_att(pd.DataFrame(rows), "y") == pytest.approx(0.4)


def test_cs_simple_att_skips_cohorts_without_a_base_year():
    df = _panel({1: [0.0, 1.0, 3.0], 2: [0.0, 0.5, 1.0], 3: [0.0, 0.0, 2.0]}, {1: 2001, 2: 0, 3: 2000})
    # cohort 2000 has no 1999 in the data, so only cohort 2001 counts; C is then never "not yet"
    assert did.cs_simple_att(df, "y") == pytest.approx(((1.0 - 0.5) + (3.0 - 1.0)) / 2)


def test_ri_cs_is_reproducible_and_bounded():
    df = _panel({i: [0.0, float(i % 2), 1.0] for i in range(8)}, {i: (2001 if i < 3 else 0) for i in range(8)})
    first = did.ri_cs(df, "y", draws=99, seed=1)
    assert first == did.ri_cs(df, "y", draws=99, seed=1)
    assert first[0] == pytest.approx(did.cs_simple_att(df, "y"))
    assert 1 / 100 <= first[1] <= 1


def test_identifying_schools_needs_a_pre_and_a_post_period():
    per = pd.DataFrame(
        {"gvar": [0, 2005, 2005, 2005, 2010], "first_year": [2000, 2000, 2005, 2000, 2000],
         "last_year": [2010, 2010, 2010, 2004, 2010]},
        index=[1, 2, 3, 4, 5],
    )
    assert list(did.identifying_schools(per).index) == [2, 5]


def test_stata_text():
    assert did.stata_globals({"SES": ["a", "b"], "T": ("c",)}) == "global SES a b\nglobal T c"
    for program in ("cs_att", "cs_row", "twfe_setup"):
        assert f"program define {program}" in did.STATA_PROGRAMS
    assert did.STATA_PROGRAMS.count("program define") == did.STATA_PROGRAMS.count("\nend\n")
