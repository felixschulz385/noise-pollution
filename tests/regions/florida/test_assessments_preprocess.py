"""`parse_sheet` (both FLDOE layouts), the regime map and `_to_id`, plus the
within-cell z-score in `build_assessments_table` — exercised on synthetic
in-memory sheet frames, no local `.xls` needed."""
import numpy as np
import pandas as pd
import pytest

from src.regions.florida.sources.assessments.preprocess import (
    _to_id,
    build_assessments_table,
    parse_sheet,
    regime,
)

# --- wide-standard layout: ELA / Math grade files, all EOC files, Science 2024+
WIDE_HEADER = ["District Number", "District Name", "School Number", "School Name",
               "Grade", "Number of Students", "Mean  Scale Score ",
               "Percentage in Level 3 or Above", "1", "2", "3", "4", "5"]


def _wide_sheet(rows):
    data = [["Spring 2019 Florida Standards Assessments ELA Grade 5"] + [None] * 12,
            [None, "Notes: suppressed as *"] + [None] * 11,
            [None] * 13,
            [None] * 8 + ["Percentage in Each Achievement Level", None, None, None, None],
            WIDE_HEADER]
    return pd.DataFrame(data + rows)


def test_wide_layout_parses_state_total_and_schools_and_suppression():
    out = parse_sheet(_wide_sheet([
        ["00", "STATE TOTALS", "0000", "GRADE 05", "05", 210000, 320, 53, 22, 25, 25, 19, 9],
        ["01", "ALACHUA", "0031", "FINLEY ELEM", "05", 92, 328, 66, 21, 13, 20, 29, 17],
        ["01", "ALACHUA", "0081", "SIDNEY LANIER CENTER", "05", 3, "*", "*", "*", "*", "*", "*", "*"],
        [None, "Footnote line that must be dropped", None, None, None, None, None, None, None, None, None, None, None],
    ]), year=2019, subject="ELA", grade="05")

    assert len(out) == 3                                  # footnote row dropped
    assert out["is_state_total"].tolist() == [True, False, False]
    assert out["msid"].tolist() == ["000000", "010031", "010081"]
    finley = out[out.msid == "010031"].iloc[0]
    assert finley["mean_scale_score"] == 328 and finley["pct_l5"] == 17
    lanier = out[out.msid == "010081"].iloc[0]
    assert bool(lanier["suppressed"]) is True
    assert pd.isna(lanier["mean_scale_score"]) and lanier["n_students"] == 3


def test_science_legacy_layout_column_order_is_mapped_by_name():
    # Grade first; the 1..5 columns come BEFORE the "% level 3+" column; a
    # "Number of Points Possible" row sits under the header; trailing content
    # areas must be ignored.
    header = ["Grade", "District Number", "District Name", "School Number", "School Name",
             "Number of Students", "Mean  Scale Score", "1", "2", "3", "4", "5",
             "Percentage Passing (Achievement Levels 3 and Above)",
             "Nature of Science", "Earth and Space Science", "Physical Science", None]
    data = [["2015 STATEWIDE SCIENCE ASSESSMENT"] + [None] * 16,
            [None] * 17, [None] * 17, [None] * 17,
            [None, None, "Notes: ..."] + [None] * 14,
            [None] * 17,
            [None] * 5 + ["Total Test Scores"] + [None] * 6 + ["Mean Points Earned", None, None, None],
            [None] * 6 + [None, "% in each Achievement Level"] + [None] * 9,
            header,
            ["5", "Number of Points Possible", None, None, None, None, None, None, None,
             None, None, None, 10, 16, 16, 14, None],
            ["05", "00", "STATE TOTALS", "0000", "GRADE 05", 198519, 200, 22, 25, 27, 13, 12,
             53, 7, 11, 11, 10],
            ["05", "01", "ALACHUA", "0031", "FINLEY ELEM", 96, 208, 18, 22, 15, 19, 27,
             60, 8, 11, 12, 10]]
    out = parse_sheet(pd.DataFrame(data), year=2015, subject="SCI", grade="05")

    assert len(out) == 2                                     # points-possible row dropped
    finley = out[out.msid == "010031"].iloc[0]
    assert finley["mean_scale_score"] == 208
    assert finley["pct_l1"] == 18 and finley["pct_l5"] == 27   # not the content-area cols
    assert finley["pct_level3_plus"] == 60
    assert out[out.msid == "010031"]["is_state_total"].iloc[0] == False  # noqa: E712


FCAT_EQUIV_HEADER = ["Grade", "District Number", "District Name", "School Number",
                     "School Name", "Number of Students",
                     "Mean FCAT Equivalent Developmental Scale Score",
                     "Mean FCAT Equivalent Scale Score (100-500)",
                     "1", "2", "3", "4", "5", "Percentage in Achievement Levels 3 and Above"]


def test_2011_dual_scale_score_columns_prefers_non_developmental():
    # 2011 FCAT 2.0 ELA/Math uniquely carries both a Developmental Scale Score
    # (vertical, ~1000-2000 range) and an "FCAT Equivalent (100-500)" column;
    # the latter is the one comparable in magnitude to every other year.
    data = [["FLORIDA COMPREHENSIVE ASSESSMENT TEST 2.0 (FCAT 2.0) 2011"] + [None] * 13,
            FCAT_EQUIV_HEADER,
            ["05", "01", "ALACHUA", "0031", "FINLEY ELEM", 92, 1830, 328, 21, 13, 20, 29, 17, 66]]
    out = parse_sheet(pd.DataFrame(data), year=2011, subject="ELA", grade="05")
    assert out.iloc[0]["mean_scale_score"] == 328   # the (100-500) column, not 1830


def test_2012_single_developmental_column_is_still_the_usable_score():
    # 2012-14 report ONLY "Mean Developmental Scale Score" (no (100-500)
    # sibling) -- despite the name, that lone column is the real score there.
    header = ["Grade", "District Number", "District Name", "School Number",
              "School Name", "Number of Students", "Mean Developmental Scale Score",
              "1", "2", "3", "4", "5", "Percentage in Achievement Levels 3 and Above"]
    data = [["FCAT 2.0 2012"] + [None] * 12,
            header,
            ["05", "01", "ALACHUA", "0031", "FINLEY ELEM", 92, 219, 21, 13, 20, 29, 17, 66]]
    out = parse_sheet(pd.DataFrame(data), year=2012, subject="ELA", grade="05")
    assert out.iloc[0]["mean_scale_score"] == 219


def test_appended_late_district_resubmission_keeps_the_later_row():
    # FL2011_MATH_G07_school.xls appends a second, partial pass over a tail
    # of districts after the main body -- a late resubmission, not identical
    # duplicate rows. The later (corrected) row should win.
    out = parse_sheet(_wide_sheet([
        ["59", "SEMINOLE", "0541", "TUSKAWILLA MIDDLE SCHOOL", "05", 357, 1830, 64, 16, 20, 33, 23, 8],
        ["01", "ALACHUA", "0031", "FINLEY ELEM", "05", 92, 328, 66, 21, 13, 20, 29, 17],
        ["59", "SEMINOLE", "0541", "TUSKAWILLA MIDDLE SCHOOL", "05", 329, 1715, 59, 25, 16, 25, 24, 9],
    ]), year=2011, subject="MATH", grade="05")

    assert len(out) == 2   # the stale first pass for 590541 is dropped
    tusk = out[out.msid == "590541"].iloc[0]
    assert tusk["n_students"] == 329 and tusk["mean_scale_score"] == 1715


def test_to_id_zero_pads_strings_and_numeric_cells():
    assert _to_id("1", 2) == "01" and _to_id("0031", 4) == "0031"
    assert _to_id(1, 2) == "01" and _to_id(31.0, 4) == "0031"   # numeric-stored IDs
    assert _to_id("STATE TOTALS", 2) is pd.NA
    assert _to_id(None, 2) is pd.NA and _to_id(np.nan, 4) is pd.NA


@pytest.mark.parametrize("year, subject, expected", [
    (2019, "ELA", "FSA"), (2023, "ELA", "FAST"), (2022, "MATH", "FSA"),
    (2019, "ALG1", "FSA"), (2024, "GEO", "B.E.S.T."),
    (2015, "SCI", "NGSSS Science"), (2026, "SCI", "NGSSS Science"),
    (2016, "BIO1", "NGSSS EOC"), (2025, "USHIST", "NGSSS EOC"),
    (2011, "ELA", "FCAT 2.0"), (2014, "MATH", "FCAT 2.0"),
    (2011, "ALG1", "NGSSS EOC"), (2013, "GEO", "NGSSS EOC"),
])
def test_regime_map(year, subject, expected):
    assert regime(year, subject) == expected


def test_build_table_indexes_and_zscores(tmp_path, monkeypatch):
    import src.regions.florida.sources.assessments.preprocess as pp

    # 2022 on the FSA scale (~300), 2023 rescaled to FAST (~200); the three
    # schools keep the same spacing (-20, 0, +20 about the mean) across the break.
    sheets = {
        yr: _wide_sheet([
            ["00", "STATE TOTALS", "0000", "G5", "05", 1000, base, 50, 20, 20, 30, 20, 10],
            ["01", "A", "0011", "LOW", "05", 40, base - 20, 30, 40, 30, 20, 8, 2],
            ["01", "A", "0012", "MID", "05", 60, base, 50, 20, 20, 30, 20, 10],
            ["02", "B", "0013", "HIGH", "05", 50, base + 20, 70, 10, 10, 30, 30, 20],
        ])
        for yr, base in ((2022, 300), (2023, 200))
    }
    monkeypatch.setattr(pp, "iter_raw_files", lambda years=None, root=None: [
        (pp.Path(f"FL{yr}_ELA_G05_school.xls"), yr, "ELA", "05") for yr in (2022, 2023)])
    monkeypatch.setattr(pp, "parse_workbook",
                        lambda path, y, s, g: pp.parse_sheet(sheets[y], y, s, g, path.name))

    table, stats = build_assessments_table(root=tmp_path)

    assert list(table.index.names) == ["msid", "grade", "subject", "year"]
    assert not table.index.duplicated().any()
    assert stats["n_files"] == 2 and stats["state_total_rows"] == 2 and stats["school_rows"] == 6
    assert table.xs(2022, level="year")["regime"].iloc[0] == "FSA"
    assert table.xs(2023, level="year")["regime"].iloc[0] == "FAST"

    schools = table[~table["is_state_total"].fillna(False)]
    for yr in (2022, 2023):
        z = schools.xs(yr, level="year")["z_mss"].astype(float)
        assert z.mean() == pytest.approx(0.0, abs=1e-9)
    z22 = sorted(table.xs(2022, level="year")["z_mss"].astype(float).dropna())
    z23 = sorted(table.xs(2023, level="year")["z_mss"].astype(float).dropna())
    assert np.allclose(z22, [-1.0, 0.0, 1.0]) and np.allclose(z22, z23)
