"""`staff` preprocess -- exercised on synthetic workbooks shaped like the
real FLDOE exports (verified live against the real 2024-25 `TeacherSalaryData
.xlsx`/`IFOFFTeach2425.xlsx`, see `docs/data/florida/staff/README.md`) and a
synthetic CCD finance table. No local data or network needed."""
from pathlib import Path

import pandas as pd
import pytest

from src.regions.florida.sources.staff.preprocess import (
    preprocess_district_finance,
    preprocess_out_of_field,
    preprocess_teacher_salary,
)


def _write_teacher_salary_workbook(path: Path) -> None:
    """Mirrors the real workbook: `Teachers` has a 2-row header (a merged
    `TEACHER` cell over 3 sub-columns), `Average Yrs Experience` and
    `Median Salary` each have a single header row -- three different
    header shapes in one workbook, on purpose."""
    teachers = pd.DataFrame(
        [
            ["AVERAGE SALARIES FOR TEACHERS\n2024-25, FINAL SURVEY 3", None, None, None, None],
            ["Note: ...", None, None, None, None],
            ["DISTRICT #", "DISTRICT NAME", "TEACHER", None, None],
            [None, None, "AVERAGE SALARY", "NUMBER \nEMPLOYED", "EMPLOYMENT LENGTH \n(in Months)"],
            [0, "FLORIDA", 56663.17, 172444, 10.03],
            [1, "ALACHUA", 51629.48, 1664, 10.02],
            [2, "BAKER", 51652.52, 300, 10.01],
        ]
    )
    experience = pd.DataFrame(
        [
            ["Teachers Average Years' Experience", None, None, None],
            ["Note: ...", None, None, None],
            ["DISTRICT #", "DISTRICT NAME", "NUMBER OF TEACHERS", "AVERAGE YEARS' EXPERIENCE"],
            [0, "FLORIDA", 167784, 11.86],
            [1, "ALACHUA", 1661, 11.58],
            [2, "BAKER", 300, 11.88],
        ]
    )
    median = pd.DataFrame(
        [
            ["Median Teacher Salaries", None, None, None],
            ["Note: ...", None, None, None],
            ["DISTRICT #", "DISTRICT NAME", "NUMBER OF TEACHERS", "MEDIAN SALARY"],
            [0, "FLORIDA", 172444, 54025.04],
            [1, "ALACHUA", 1664, 50369.50],
            [2, "BAKER", 300, 48515.08],
        ]
    )
    with pd.ExcelWriter(path) as writer:
        teachers.to_excel(writer, sheet_name="Teachers", header=False, index=False)
        experience.to_excel(writer, sheet_name="Average Yrs Experience", header=False, index=False)
        median.to_excel(writer, sheet_name="Median Salary", header=False, index=False)


def _write_out_of_field_workbook(path: Path) -> None:
    rows = pd.DataFrame(
        [
            ["Total Number and Percent of Classes...", None, None, None, None, None, None, None, None],
            ["Notes: ...", None, None, None, None, None, None, None, None],
            [
                "District #", "District Name", "School #", "School Name",
                "Total Classes Taught by In-Field and Out-of-Field",
                "# of In-Field Classes", "# of Out-of-Field Classes", "% In-\nField", "% Out-of-Field",
            ],
            [0, "FLORIDA", 0, "STATE TOTALS", 1622103, 1390464, 231639, 0.857198, 0.142802],
            [1, "ALACHUA", 0, "DISTRICT TOTALS", 16862, 16336, 526, 0.968806, 0.031194],
            [1, "ALACHUA", 22, "EARLY LEARNING ACADEMY AT DUVAL", 17, 17, 0, 1.0, 0.0],
        ]
    )
    with pd.ExcelWriter(path) as writer:
        rows.to_excel(writer, sheet_name="Sheet1", header=False, index=False)


def test_preprocess_teacher_salary_merges_three_sheets(tmp_path):
    path = tmp_path / "salary_2025.xlsx"
    _write_teacher_salary_workbook(path)

    out = preprocess_teacher_salary({2025: path})

    assert set(out["district_number"]) == {0, 1, 2}
    assert len(out) == 3
    alachua = out[out["district_number"] == 1].iloc[0]
    assert alachua["district_name"] == "ALACHUA"
    assert alachua["year"] == 2025
    assert alachua["avg_salary"] == pytest.approx(51629.48)
    assert alachua["n_teachers_salary"] == 1664
    assert alachua["avg_years_experience"] == pytest.approx(11.58)
    assert alachua["median_salary"] == pytest.approx(50369.50)
    assert bool(alachua["is_real_county_district"]) is True
    florida_total = out[out["district_number"] == 0].iloc[0]
    assert bool(florida_total["is_real_county_district"]) is False


def test_preprocess_teacher_salary_empty_when_no_files():
    out = preprocess_teacher_salary({})
    assert out.empty
    assert "avg_salary" in out.columns


def test_preprocess_out_of_field_drops_state_and_district_totals(tmp_path):
    path = tmp_path / "ifoff_2025.xlsx"
    _write_out_of_field_workbook(path)

    out = preprocess_out_of_field({2025: path})

    assert len(out) == 1
    row = out.iloc[0]
    assert row["district_number"] == 1
    assert row["school_number"] == 22
    assert row["n_classes_total"] == 17
    assert row["pct_out_of_field"] == 0.0


def test_preprocess_district_finance_computes_per_pupil(tmp_path):
    raw = pd.DataFrame(
        [
            {"leaid": "1200030", "year": 2020, "exp_current_elsec_total": 307903000, "enrollment_fall_responsible": 28300},
            {"leaid": "1200002", "year": 2020, "exp_current_elsec_total": -1, "enrollment_fall_responsible": -1},
        ]
    )
    path = tmp_path / "finance_2020.parquet"
    raw.to_parquet(path, index=False)

    out = preprocess_district_finance({2020: path})

    real = out[out["leaid"] == "1200030"].iloc[0]
    assert real["per_pupil_expenditure"] == pytest.approx(307903000 / 28300)
    suppressed = out[out["leaid"] == "1200002"].iloc[0]
    assert pd.isna(suppressed["per_pupil_expenditure"])


def test_preprocess_district_finance_empty_when_no_files():
    out = preprocess_district_finance({})
    assert out.empty
    assert "per_pupil_expenditure" in out.columns
