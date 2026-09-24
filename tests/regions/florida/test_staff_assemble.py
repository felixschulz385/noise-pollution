"""`build_district_leaid_crosswalk` (the modal-leaid-per-district join,
including the charter-noise case), `build_district_staff_panel`, and
`build_school_staff_panel` -- exercised on synthetic tables, no local data
needed."""
import pandas as pd
import pytest

from src.regions.florida.sources.staff.assemble import (
    build_district_leaid_crosswalk,
    build_district_staff_panel,
    build_school_staff_panel,
)


def _cross_section_row(msid, district, district_name, ncessch):
    return {"msid": msid, "district": district, "district_name": district_name, "ncessch": ncessch}


def test_crosswalk_picks_modal_leaid_and_reports_coverage():
    # District 01 has 3 schools sharing leaid 1200030 and 1 charter-only outlier.
    rows = [
        _cross_section_row("010010", "01", "ALACHUA", "1200030" + "00010"),
        _cross_section_row("010020", "01", "ALACHUA", "1200030" + "00020"),
        _cross_section_row("010030", "01", "ALACHUA", "1200030" + "00030"),
        _cross_section_row("010040", "01", "ALACHUA", "1201740" + "00001"),  # charter, own leaid
        _cross_section_row("020010", "02", "BAKER", "1200060" + "00010"),
    ]
    cross_section = pd.DataFrame(rows)

    out = build_district_leaid_crosswalk(cross_section)

    alachua = out[out["district"] == "01"].iloc[0]
    assert alachua["leaid"] == "1200030"
    assert alachua["leaid_coverage_frac"] == pytest.approx(0.75)
    baker = out[out["district"] == "02"].iloc[0]
    assert baker["leaid"] == "1200060"
    assert baker["leaid_coverage_frac"] == pytest.approx(1.0)


def test_crosswalk_empty_when_no_ncessch():
    cross_section = pd.DataFrame([_cross_section_row("010010", "01", "ALACHUA", None)])
    out = build_district_leaid_crosswalk(cross_section)
    assert out.empty


def test_build_district_staff_panel_joins_finance_via_crosswalk():
    teacher_salary = pd.DataFrame(
        [{"district_number": 1, "district_name": "ALACHUA", "year": 2020, "avg_salary": 51000.0}]
    )
    district_finance = pd.DataFrame(
        [{"leaid": "1200030", "year": 2020, "per_pupil_expenditure": 10361.9}]
    )
    crosswalk = pd.DataFrame([{"district": "01", "district_name": "ALACHUA", "leaid": "1200030", "leaid_coverage_frac": 1.0}])

    out = build_district_staff_panel(teacher_salary, district_finance, crosswalk)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["avg_salary"] == 51000.0
    assert row["per_pupil_expenditure"] == pytest.approx(10361.9)


def test_build_district_staff_panel_outer_join_keeps_salary_only_rows():
    teacher_salary = pd.DataFrame(
        [{"district_number": 1, "district_name": "ALACHUA", "year": 2005, "avg_salary": 40000.0}]
    )
    district_finance = pd.DataFrame(columns=["leaid", "year", "per_pupil_expenditure"])
    crosswalk = pd.DataFrame(columns=["district", "district_name", "leaid", "leaid_coverage_frac"])

    out = build_district_staff_panel(teacher_salary, district_finance, crosswalk)

    assert len(out) == 1
    assert out.iloc[0]["avg_salary"] == 40000.0
    assert pd.isna(out.iloc[0]["per_pupil_expenditure"])


def test_build_school_staff_panel_composes_msid():
    out_of_field = pd.DataFrame(
        [
            {
                "district_number": 1, "district_name": "ALACHUA", "school_number": 22, "year": 2025,
                "n_classes_total": 17, "n_classes_in_field": 17, "n_classes_out_of_field": 0,
                "pct_in_field": 1.0, "pct_out_of_field": 0.0,
            }
        ]
    )
    out = build_school_staff_panel(out_of_field)
    assert out.iloc[0]["msid"] == "010022"


def test_build_school_staff_panel_empty_when_no_rows():
    out = build_school_staff_panel(pd.DataFrame(columns=["district_number", "school_number", "year"]))
    assert out.empty
    assert "pct_out_of_field" in out.columns
