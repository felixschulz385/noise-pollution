"""`schools preprocess` (stage 1a/1b) pipeline functions, exercised on small
synthetic frames shaped like the raw MSID / CCD pulls — no local data needed."""
import numpy as np
import pandas as pd
import pytest

from src.regions.florida.sources.schools.preprocess import (
    _clean_sentinel,
    _fill_grade_span_from_ccd,
    _haversine_m,
    build_operation_panel,
    compose_ncessch,
    decode_classification,
    join_covariates,
    tidy_crdc_lep,
)


def _msid_row(district, school, fed_dist="0", fed_school="0", **overrides):
    row = {
        "DISTRICT": district, "SCHOOL": school,
        "FEDERAL_DIST_NO": fed_dist, "FEDERAL_SCHL_NO": fed_school,
        "ACTIVITY_CODE": "A", "TYPE": "1", "CHARTER_SCHL_STAT": "Z",
        "SCHL_FUNC_SETTING": "Z", "PRIMARY_SERV_TYPE": "R", "MAGNET_STATUS": "Z",
        "GRADE_CODE": "08", "DATE_OPENED": None, "DATE_CLOSED": None,
        "LATITUDE": "0.0", "LONGITUDE": "0.0",
        "SCHOOL_NAME_LONG": f"SCHOOL {district}{school}", "DISTRICT_NAME": "TEST",
    }
    row.update(overrides)
    return row


def _msid(rows):
    return pd.DataFrame(rows)


# --- compose_ncessch --------------------------------------------------------

def test_compose_ncessch_pads_and_sentinels():
    df = compose_ncessch(_msid([
        _msid_row("1", "21", fed_dist="1200030", fed_school="1"),   # -> 120003000001
        _msid_row("1", "22", fed_dist="0", fed_school="0"),         # sentinel -> NA
        _msid_row("1", "23", fed_dist="1200030", fed_school="0"),   # partial sentinel -> NA
    ]))
    df = df.set_index("msid")
    assert df.loc["010021", "ncessch"] == "120003000001"
    assert pd.isna(df.loc["010022", "ncessch"])
    assert pd.isna(df.loc["010023", "ncessch"])
    assert df["msid"].is_unique if "msid" in df.columns else True


def test_compose_ncessch_flags_shared_ids():
    df = compose_ncessch(_msid([
        _msid_row("1", "0101", fed_dist="1200030", fed_school="1"),
        _msid_row("2", "0101", fed_dist="1200030", fed_school="1"),  # same composed ncessch
        _msid_row("3", "0101", fed_dist="1200030", fed_school="2"),  # distinct
    ]))
    shared = dict(zip(df["msid"], df["ncessch_shared"]))
    assert shared["010101"] is True and shared["020101"] is True
    assert shared["030101"] is False


def test_compose_ncessch_rejects_duplicate_msid():
    with pytest.raises(ValueError, match="duplicate msid"):
        compose_ncessch(_msid([_msid_row("1", "01"), _msid_row("1", "01")]))


# --- decode_classification ---------------------------------------------------

def test_decode_classification_serv_type_b_is_alternative_not_basic():
    df = decode_classification(compose_ncessch(_msid([
        _msid_row("1", "0101", PRIMARY_SERV_TYPE="B"),
        _msid_row("1", "0102", PRIMARY_SERV_TYPE="R"),
    ])))
    df = df.set_index("msid")
    assert df.loc["010101", "serv_type"] == "alternative_education"
    assert bool(df.loc["010101", "is_regular"]) is False
    assert bool(df.loc["010101", "is_alternative"]) is True
    assert df.loc["010102", "serv_type"] == "k12_general"
    assert bool(df.loc["010102", "is_regular"]) is True


def test_decode_classification_grade_span_from_grade_code():
    df = decode_classification(compose_ncessch(_msid([
        _msid_row("1", "0101", GRADE_CODE="113"),   # 3-10
        _msid_row("1", "0102", GRADE_CODE="99"),    # Unassigned -> NA
    ]))).set_index("msid")
    assert (df.loc["010101", "grade_low"], df.loc["010101", "grade_high"]) == (3, 10)
    assert df.loc["010101", "serves_tested_grades"] == True  # noqa: E712
    assert pd.isna(df.loc["010102", "grade_low"])
    assert df.loc["010102", "grade_low_source"] == "none"


def test_grade_span_ccd_fallback_only_trusts_plain_0_12():
    msid = decode_classification(compose_ncessch(_msid([
        _msid_row("1", "0101", GRADE_CODE="99", fed_dist="1200030", fed_school="1"),  # unresolved
        _msid_row("1", "0102", GRADE_CODE="99", fed_dist="1200030", fed_school="2"),  # unresolved, sentinel ccd
    ])))
    ccd = pd.DataFrame({
        "ncessch": ["120003000001", "120003000002"],
        "year": [2020, 2020],
        "ccd_grade_low": ["3", "-1"],     # second is CCD's ambiguous sentinel
        "ccd_grade_high": ["5", "-1"],
    })
    _fill_grade_span_from_ccd(msid, ccd)
    msid = msid.set_index("msid")
    assert (msid.loc["010101", "grade_low"], msid.loc["010101", "grade_high"]) == (3, 5)
    assert msid.loc["010101", "grade_low_source"] == "ccd_directory"
    assert bool(msid.loc["010101", "serves_tested_grades"]) is True
    assert pd.isna(msid.loc["010102", "grade_low"])  # -1 not trusted, stays unresolved


# --- coordinates -------------------------------------------------------------

def test_haversine_zero_for_identical_points():
    lat = pd.Series([25.0, 30.0])
    lon = pd.Series([-80.0, -82.0])
    out = _haversine_m(lat, lon, lat, lon)
    assert (out == 0).all()


def test_haversine_matches_known_distance():
    # two points ~1 degree of latitude apart -> ~111 km
    out = _haversine_m(pd.Series([25.0]), pd.Series([-80.0]), pd.Series([26.0]), pd.Series([-80.0]))
    assert out.iloc[0] == pytest.approx(111_195, rel=0.01)


# --- sentinel cleaning ---------------------------------------------------

def test_clean_sentinel_maps_negatives_and_keeps_ok():
    values, missing = _clean_sentinel(pd.Series(["100", "-1", "-2", "-3", None]))
    assert values.tolist()[:1] == [100.0]
    assert values.isna().tolist() == [False, True, True, True, True]
    assert missing.tolist() == ["ok", "missing", "na", "suppressed", "ok"]


# --- operation panel -----------------------------------------------------

def _spine(rows):
    return pd.DataFrame(rows)


def test_operation_panel_month_aware_open_close():
    spine = _spine([
        {"msid": "010101", "DATE_OPENED": "08/15/2015", "DATE_CLOSED": None},   # fall open -> spring 2016+
        {"msid": "010102", "DATE_OPENED": None, "DATE_CLOSED": "06/30/2016"},   # closes end of SY2015-16
    ])
    assess = pd.DataFrame({"msid": pd.Series(dtype=str), "year": pd.Series(dtype=int)})
    panel = build_operation_panel(spine, assess, panel_years=(2014, 2017)).set_index(["msid", "year"])

    assert panel.loc[("010101", 2015), "in_operation"] == False  # noqa: E712  (opened fall 2015, not yet spring 2015)
    assert panel.loc[("010101", 2016), "in_operation"] == True   # noqa: E712
    assert panel.loc[("010102", 2016), "in_operation"] == True   # noqa: E712  (closes at end of spring 2016)
    assert panel.loc[("010102", 2017), "in_operation"] == False  # noqa: E712


def test_operation_panel_assessment_appearance_overrides_dates_on_conflict():
    # dates say this school closed before 2016, but it appears in assessments that year
    spine = _spine([{"msid": "010101", "DATE_OPENED": None, "DATE_CLOSED": "06/30/2010"}])
    assess = pd.DataFrame({"msid": ["010101"], "year": [2016]})
    panel = build_operation_panel(spine, assess, panel_years=(2015, 2017)).set_index(["msid", "year"])

    assert panel.loc[("010101", 2016), "in_operation"] == True  # noqa: E712
    assert panel.loc[("010101", 2016), "in_operation_src"] == "conflict"
    assert panel.loc[("010101", 2015), "in_operation"] == False  # noqa: E712
    assert panel.loc[("010101", 2015), "in_operation_src"] == "dates"


def test_operation_panel_pre_2015_conflict_not_checked():
    # a "tested" row before 2015 shouldn't be possible from real data, but the
    # rule is explicitly scoped to 2015+ -- verify it doesn't fire earlier
    spine = _spine([{"msid": "010101", "DATE_OPENED": None, "DATE_CLOSED": "06/30/2000"}])
    assess = pd.DataFrame({"msid": ["010101"], "year": [2005]})
    panel = build_operation_panel(spine, assess, panel_years=(2000, 2006)).set_index(["msid", "year"])
    assert panel.loc[("010101", 2005), "in_operation"] == False  # noqa: E712
    assert panel.loc[("010101", 2005), "in_operation_src"] == "dates"


# --- covariate join --------------------------------------------------------

def test_join_covariates_keys_on_ncessch_and_year():
    panel = pd.DataFrame({"msid": ["010101", "010102"], "year": [2020, 2020]})
    xs = pd.DataFrame({"msid": ["010101", "010102"], "ncessch": ["A", "B"]})
    ccd = pd.DataFrame({"ncessch": ["A"], "year": [2020], "enrollment": [500]})
    out = join_covariates(panel, xs, ccd, None, None, None, None)
    out = out.set_index("msid")
    assert out.loc["010101", "enrollment"] == 500
    assert pd.isna(out.loc["010102", "enrollment"])


# --- crdc_lep (pct_ell) -----------------------------------------------------

def _crdc_lep_raw_row(ncessch, year, sex, lep, enrollment_crdc):
    return {
        "ncessch": ncessch, "year": year, "race": 99, "sex": sex, "disability": 99,
        "lep": lep, "enrollment_crdc": enrollment_crdc, "psenrollment_crdc": -2,
    }


def test_tidy_crdc_lep_computes_pct_ell(monkeypatch):
    raw = pd.DataFrame([
        _crdc_lep_raw_row("A" * 12, 2016, 99, 1, 20),   # ELL count
        _crdc_lep_raw_row("A" * 12, 2016, 99, 99, 100),  # total
    ])
    monkeypatch.setattr(
        "src.regions.florida.sources.schools.preprocess._load_year_parquets",
        lambda root, pattern: raw if pattern == "crdc_lep_*.parquet" else None,
    )
    out = tidy_crdc_lep(None).set_index(["ncessch", "year"])
    # crdc year is fall-of-academic-year -> +1 to the spring panel year
    assert out.loc[("A" * 12, 2017), "pct_ell"] == pytest.approx(0.2)


def test_tidy_crdc_lep_dedupes_natural_key_before_summing(monkeypatch):
    """Same shape of bug `tidy_crdc_swd` was fixed for: a duplicated record
    sharing every dimension but an unused column must not double-count."""
    ncessch = "B" * 12
    dup_row = _crdc_lep_raw_row(ncessch, 2020, 99, 1, 10)
    dup_row_diff_unused = {**dup_row, "psenrollment_crdc": 5}  # differs only here
    total_row = _crdc_lep_raw_row(ncessch, 2020, 99, 99, 50)
    raw = pd.DataFrame([dup_row, dup_row_diff_unused, total_row])
    monkeypatch.setattr(
        "src.regions.florida.sources.schools.preprocess._load_year_parquets",
        lambda root, pattern: raw if pattern == "crdc_lep_*.parquet" else None,
    )
    out = tidy_crdc_lep(None).set_index(["ncessch", "year"])
    assert out.loc[(ncessch, 2021), "pct_ell"] == pytest.approx(0.2)  # 10/50, not 20/50


def test_tidy_crdc_lep_returns_none_when_never_fetched(monkeypatch):
    monkeypatch.setattr(
        "src.regions.florida.sources.schools.preprocess._load_year_parquets",
        lambda root, pattern: None,
    )
    assert tidy_crdc_lep(None) is None
