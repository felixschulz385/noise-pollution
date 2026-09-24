"""Preprocess step for the Florida `staff` source's three sub-sources.

Every FLDOE workbook (`teacher_salary`, `out_of_field`) shares the same
layout quirk: 2-3 free-text title/note rows, then a header row whose first
cell is literally `"DISTRICT #"` (sometimes `"District #"` — FLDOE isn't
consistent on case), sometimes followed by ONE more sub-header row (e.g. the
`Teachers` sheet's `AVERAGE SALARY` / `NUMBER EMPLOYED` / `EMPLOYMENT
LENGTH` sit one row below the merged `TEACHER` header cell), then data rows
whose first cell is a real district number. `_locate_header_row` +
`_numeric_first_column_rows` key off that shape (find the `"DISTRICT #"`
row, then take every row below it whose first cell parses as a number) —
robust to the exact header wording/row-count varying by sheet or by year,
since actual column names are assigned *positionally*, not by matching
header text (confirmed stable across the one workbook layout inspected
directly, `2024-25`; see `docs/data/florida/staff/README.md`).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from src.regions.florida.sources.staff.shared import (
    OUT_OF_FIELD_FILES,
    TEACHER_SALARY_FILES,
    processed_district_finance_path,
    processed_metadata_path,
    processed_out_of_field_path,
    processed_teacher_salary_path,
    raw_district_finance_path,
    raw_out_of_field_path,
    raw_teacher_salary_path,
)

# Districts 0 (Florida state total) and 68+ (special entities -- lab
# schools, DJJ, charter consortiums, virtual schools -- see
# `shocks/assemble.py`'s identical `MAX_COUNTY_DISTRICT_NUMBER` cutoff) are
# kept in the tidy output (a state total is a real, useful row) but flagged
# via `is_real_county_district` rather than silently mixed in with the 67
# real county districts.
MAX_COUNTY_DISTRICT_NUMBER = 67


def _locate_header_row(sheet: pd.DataFrame) -> int:
    first_col = sheet.iloc[:, 0].astype("string").str.strip().str.upper()
    matches = first_col[first_col == "DISTRICT #"]
    if matches.empty:
        raise ValueError('No "DISTRICT #" header row found in sheet.')
    return int(matches.index[0])


def _numeric_first_column_rows(sheet: pd.DataFrame, header_row: int) -> pd.DataFrame:
    body = sheet.iloc[header_row + 1 :].copy()
    numeric_first = pd.to_numeric(body.iloc[:, 0], errors="coerce")
    data = body.loc[numeric_first.notna()].reset_index(drop=True)
    # Value columns are located positionally, counting from the LAST column
    # (see the module docstring) -- an entirely-empty trailing column (some
    # FLDOE exports pad a wider sheet than the visible data) would otherwise
    # shift that count off the real value columns, so drop those first.
    return data.dropna(axis=1, how="all")


def _read_district_sheet(path: Path, sheet_keyword: str, value_names: list[str]) -> pd.DataFrame:
    """Read one sheet of a district-level workbook (`DISTRICT #`,
    `DISTRICT NAME`, then `len(value_names)` value columns) — matches the
    sheet by a case-insensitive substring of its name (year-to-year FLDOE
    sheet-name wording drifts slightly) rather than an exact name."""
    xl = pd.ExcelFile(path)
    candidates = [s for s in xl.sheet_names if sheet_keyword.lower() in s.lower()]
    if not candidates:
        raise ValueError(f"No sheet matching {sheet_keyword!r} in {path} (sheets: {xl.sheet_names}).")
    raw = xl.parse(candidates[0], header=None)
    header_row = _locate_header_row(raw)
    rows = _numeric_first_column_rows(raw, header_row)

    n_value_cols = len(value_names)
    out = pd.DataFrame(
        {
            "district_number": pd.to_numeric(rows.iloc[:, 0], errors="coerce").astype("Int64"),
            "district_name": rows.iloc[:, 1].astype("string").str.strip(),
        }
    )
    for i, name in enumerate(value_names):
        col_idx = rows.shape[1] - n_value_cols + i
        out[name] = pd.to_numeric(rows.iloc[:, col_idx], errors="coerce")
    return out


def load_raw_teacher_salary_files(root: Path | None = None) -> dict[int, Path]:
    return {year: p for year in TEACHER_SALARY_FILES if (p := raw_teacher_salary_path(year, root)).exists()}


def preprocess_teacher_salary(files: dict[int, Path]) -> pd.DataFrame:
    """One row per `(district_number, assessment_year)`: average salary /
    # employed / employment length (`Teachers` sheet), average years'
    experience (`Average Yrs Experience` sheet), and median salary
    (`Median Salary` sheet), joined on `district_number` within each year."""
    if not files:
        return pd.DataFrame(
            columns=[
                "district_number", "district_name", "year", "is_real_county_district",
                "avg_salary", "n_teachers_salary", "avg_employment_length_months",
                "avg_years_experience", "n_teachers_experience", "median_salary",
            ]
        )

    frames = []
    for year, path in sorted(files.items()):
        salary = _read_district_sheet(path, "Teacher", ["avg_salary", "n_teachers_salary", "avg_employment_length_months"])
        experience = _read_district_sheet(path, "Experience", ["n_teachers_experience", "avg_years_experience"])
        median = _read_district_sheet(path, "Median", ["n_teachers_median", "median_salary"])

        merged = salary.merge(
            experience[["district_number", "n_teachers_experience", "avg_years_experience"]],
            on="district_number", how="outer",
        ).merge(
            median[["district_number", "median_salary"]], on="district_number", how="outer",
        )
        merged["year"] = year
        frames.append(merged)

    out = pd.concat(frames, ignore_index=True)
    out["is_real_county_district"] = out["district_number"].between(1, MAX_COUNTY_DISTRICT_NUMBER)
    ordered = [
        "district_number", "district_name", "year", "is_real_county_district",
        "avg_salary", "n_teachers_salary", "avg_employment_length_months",
        "avg_years_experience", "n_teachers_experience", "median_salary",
    ]
    return out[ordered].sort_values(["district_number", "year"]).reset_index(drop=True)


def load_raw_out_of_field_files(root: Path | None = None) -> dict[int, Path]:
    return {year: p for year in OUT_OF_FIELD_FILES if (p := raw_out_of_field_path(year, root)).exists()}


def preprocess_out_of_field(files: dict[int, Path]) -> pd.DataFrame:
    """One row per `(district_number, school_number, assessment_year)` —
    real schools only (`school_number > 0`; the workbook's own `"STATE
    TOTALS"`/`"DISTRICT TOTALS"` rows use `school_number == 0` and are
    dropped here, not carried into a school-grain table)."""
    columns = [
        "district_number", "district_name", "school_number", "year",
        "n_classes_total", "n_classes_in_field", "n_classes_out_of_field",
        "pct_in_field", "pct_out_of_field",
    ]
    if not files:
        return pd.DataFrame(columns=columns)

    frames = []
    for year, path in sorted(files.items()):
        xl = pd.ExcelFile(path)
        raw = xl.parse(xl.sheet_names[0], header=None)
        header_row = _locate_header_row(raw)
        rows = _numeric_first_column_rows(raw, header_row)

        out = pd.DataFrame(
            {
                "district_number": pd.to_numeric(rows.iloc[:, 0], errors="coerce").astype("Int64"),
                "district_name": rows.iloc[:, 1].astype("string").str.strip(),
                "school_number": pd.to_numeric(rows.iloc[:, 2], errors="coerce").astype("Int64"),
                "n_classes_total": pd.to_numeric(rows.iloc[:, 4], errors="coerce"),
                "n_classes_in_field": pd.to_numeric(rows.iloc[:, 5], errors="coerce"),
                "n_classes_out_of_field": pd.to_numeric(rows.iloc[:, 6], errors="coerce"),
                "pct_in_field": pd.to_numeric(rows.iloc[:, 7], errors="coerce"),
                "pct_out_of_field": pd.to_numeric(rows.iloc[:, 8], errors="coerce"),
            }
        )
        out["year"] = year
        frames.append(out[out["school_number"] > 0])

    return pd.concat(frames, ignore_index=True)[columns].sort_values(
        ["district_number", "school_number", "year"]
    ).reset_index(drop=True)


def load_raw_district_finance_files(root: Path | None = None) -> dict[int, Path]:
    from src.regions.florida.sources.staff.shared import CCD_FINANCE_FIRST_YEAR, CCD_FINANCE_LAST_YEAR

    years = range(CCD_FINANCE_FIRST_YEAR, CCD_FINANCE_LAST_YEAR + 1)
    return {year: p for year in years if (p := raw_district_finance_path(year, root)).exists()}


def preprocess_district_finance(files: dict[int, Path]) -> pd.DataFrame:
    """One row per `(leaid, assessment_year)`: `per_pupil_expenditure` =
    `exp_current_elsec_total / enrollment_fall_responsible` (current
    elementary-secondary expenditure over fall enrollment — the standard
    NCES per-pupil definition, excludes capital outlay/debt service).
    `assessment_year == ccd_finance_year` directly, no `+1` offset — see
    `shared.py`'s module docstring for why F-33's fiscal-year label already
    is the spring/ending calendar year, unlike CCD's fall-semester surveys.
    A district-year with a suppressed/negative CCD sentinel value (`-1`,
    `-2`, ...) or zero enrollment gets `per_pupil_expenditure = NA`, not a
    nonsensical negative or infinite ratio."""
    columns = ["leaid", "year", "exp_current_elsec_total", "enrollment_fall_responsible", "per_pupil_expenditure"]
    if not files:
        return pd.DataFrame(columns=columns)

    frames = [pd.read_parquet(path) for _, path in sorted(files.items())]
    raw = pd.concat(frames, ignore_index=True)

    out = raw[["leaid", "year"]].copy()
    exp = pd.to_numeric(raw.get("exp_current_elsec_total"), errors="coerce")
    enrollment = pd.to_numeric(raw.get("enrollment_fall_responsible"), errors="coerce")
    out["exp_current_elsec_total"] = exp.where(exp > 0)
    out["enrollment_fall_responsible"] = enrollment.where(enrollment > 0)
    out["per_pupil_expenditure"] = out["exp_current_elsec_total"] / out["enrollment_fall_responsible"]
    return out[columns].sort_values(["leaid", "year"]).reset_index(drop=True)


def save_processed(
    teacher_salary: pd.DataFrame, out_of_field: pd.DataFrame, district_finance: pd.DataFrame, root: Path | None = None
) -> dict[str, str]:
    teacher_salary_path = processed_teacher_salary_path(root)
    out_of_field_path = processed_out_of_field_path(root)
    district_finance_path = processed_district_finance_path(root)
    meta_path = processed_metadata_path(root)
    for path in (teacher_salary_path, out_of_field_path, district_finance_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    teacher_salary.to_parquet(teacher_salary_path, index=False)
    out_of_field.to_parquet(out_of_field_path, index=False)
    district_finance.to_parquet(district_finance_path, index=False)

    provenance = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "teacher_salary_rows": int(len(teacher_salary)),
        "teacher_salary_years": sorted(int(y) for y in teacher_salary["year"].dropna().unique()),
        "out_of_field_rows": int(len(out_of_field)),
        "out_of_field_years": sorted(int(y) for y in out_of_field["year"].dropna().unique()),
        "district_finance_rows": int(len(district_finance)),
        "district_finance_years": sorted(int(y) for y in district_finance["year"].dropna().unique()),
        "parquet": {
            "teacher_salary": str(teacher_salary_path),
            "out_of_field": str(out_of_field_path),
            "district_finance": str(district_finance_path),
        },
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "teacher_salary": str(teacher_salary_path),
        "out_of_field": str(out_of_field_path),
        "district_finance": str(district_finance_path),
        "metadata": str(meta_path),
    }


def run_staff_preprocess(root: Path | None = None) -> dict[str, object]:
    teacher_salary = preprocess_teacher_salary(load_raw_teacher_salary_files(root))
    out_of_field = preprocess_out_of_field(load_raw_out_of_field_files(root))
    district_finance = preprocess_district_finance(load_raw_district_finance_files(root))
    saved = save_processed(teacher_salary, out_of_field, district_finance, root)

    return {
        "teacher_salary_rows": int(len(teacher_salary)),
        "out_of_field_rows": int(len(out_of_field)),
        "district_finance_rows": int(len(district_finance)),
        "saved": saved,
    }
