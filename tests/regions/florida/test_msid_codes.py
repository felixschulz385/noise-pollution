"""MSID code tables (from the FLDOE MSID Application Guidelines, Appendices A/B)
and the grade-code → grade-span helpers."""
import pytest

from src.regions.florida.sources.schools import msid_codes as mc


def test_single_value_tables_cover_the_observed_file_codes():
    # values seen in data/florida/schools/raw/MSID_all_schools.tsv
    assert set("ACF") <= set(mc.ACTIVITY_CODE)
    assert set("ZRCHBT") <= set(mc.CHARTER_STATUS)
    assert set("ZDVBPTNHJML") <= set(mc.FUNC_SETTING)
    assert set("RBOSAV") <= set(mc.SERV_TYPE)
    assert set("ZPS") <= set(mc.MAGNET_STATUS)
    # the meaning that matters for the sample filter
    assert mc.SERV_TYPE["R"] == "k12_general"
    assert mc.SERV_TYPE["B"] == "alternative_education"  # not "basic"
    assert mc.FUNC_SETTING["V"] == "virtual"


@pytest.mark.parametrize(
    "code, span, tested",
    [
        ("08", (-1, 5), True),    # PK-5
        ("8", (-1, 5), True),      # unpadded form also occurs in the file
        ("67", (6, 8), True),      # 6-8
        ("85", (9, 12), True),     # 9-12
        ("113", (3, 10), True),    # 3-10
        ("50", (4, 4), True),      # single grade 4
        ("119", (-1, 12), True),   # PK-2, 9-12 -> serves 9,10 so tested
        ("04", (-1, 2), False),    # PK-2 -> no tested grade
        ("87", (11, 12), False),   # 11-12
        ("90", (13, 13), False),   # Adult
        ("99", (None, None), None),  # Unassigned
        ("112", (None, None), None),  # Not in use
        ("", (None, None), None),
    ],
)
def test_grade_code_span_and_tested(code, span, tested):
    assert mc.grade_code_span(code) == span
    assert mc.grade_code_serves_tested(code) is tested


def test_grade_code_set_is_explicit_not_just_a_range():
    # "KG, 3-5" covers K and 3,4,5 but NOT 1,2
    assert mc.grade_code_to_set("09") == {0, 3, 4, 5}


def test_normalize_grade_code():
    assert mc.normalize_grade_code("8") == "08"
    assert mc.normalize_grade_code("113") == "113"
    assert mc.normalize_grade_code(None) == ""
    assert mc.normalize_grade_code("nan") == ""
