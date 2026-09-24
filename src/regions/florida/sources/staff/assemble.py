"""Stage 3 for the Florida `staff` source: build the `district -> leaid`
crosswalk needed only for the CCD fiscal join, then join all three
sub-sources into the two panels `panel/assemble.py` consumes.

`REQUIRES` `schools preprocess` (`school_cross_section.parquet`) and this
source's own `fetch` + `preprocess`.

**Why a crosswalk is needed at all, and only for one of three sub-sources.**
`teacher_salary`/`out_of_field` are FLDOE's own workbooks, keyed by FLDOE's
own `DISTRICT #`/`SCHOOL #` numbering -- confirmed empirically (see
`shared.py`'s module docstring) to match `school_cross_section.parquet`'s
`district`/`school` fields exactly, so those two need no crosswalk at all.
`district_finance` comes from the Urban Institute's CCD API instead, which
keys by NCES `leaid` (`FEDERAL_DIST_NO`, the first 7 digits of `ncessch`) --
a different id system.

**The `district -> leaid` mapping is a MODAL join, not a strict 1:1 one.**
Checked empirically before committing (real `school_cross_section.parquet`,
2026-09): 83 of 84 FLDOE districts map to exactly one `leaid` among their
schools; district `01` (Alachua) has 9 distinct `leaid`s because several
individual charter schools got their OWN NCES leaid despite reporting
through the county district for FLDOE's own accounting (a known, general CCD
quirk, not a Florida-specific bug). The MODAL `leaid` per district still
captures the large majority of each district's schools (min 88.5%, median
100%, across all 84 districts) -- `build_district_leaid_crosswalk` picks
that modal id and reports the coverage fraction rather than silently
assuming a clean 1:1 map, the same "verify, don't assume" bar `shocks
/assemble.py` set for its own county-name join.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from src.regions.florida.sources.schools.shared import processed_cross_section_path
from src.regions.florida.sources.staff.shared import (
    district_staff_panel_path,
    processed_district_finance_path,
    processed_out_of_field_path,
    processed_teacher_salary_path,
    school_staff_panel_path,
)


def load_school_cross_section(root: Path | None = None) -> pd.DataFrame:
    import geopandas as gpd

    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    return pd.DataFrame(gpd.read_parquet(path)[["msid", "district", "district_name", "ncessch"]])


def load_processed_teacher_salary(root: Path | None = None) -> pd.DataFrame:
    path = processed_teacher_salary_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data staff preprocess` first.")
    return pd.read_parquet(path)


def load_processed_out_of_field(root: Path | None = None) -> pd.DataFrame:
    path = processed_out_of_field_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data staff preprocess` first.")
    return pd.read_parquet(path)


def load_processed_district_finance(root: Path | None = None) -> pd.DataFrame:
    path = processed_district_finance_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data staff preprocess` first.")
    return pd.read_parquet(path)


def build_district_leaid_crosswalk(cross_section: pd.DataFrame) -> pd.DataFrame:
    """One row per FLDOE `district`: its modal NCES `leaid` (the first 7
    digits of `ncessch`, i.e. `FEDERAL_DIST_NO`) among its own schools, plus
    `leaid_coverage_frac` — the share of that district's `ncessch`-bearing
    schools the modal `leaid` actually covers (see module docstring)."""
    columns = ["district", "district_name", "leaid", "leaid_coverage_frac", "n_schools_with_leaid"]
    have_leaid = cross_section[cross_section["ncessch"].notna()].copy()
    if have_leaid.empty:
        return pd.DataFrame(columns=columns)

    have_leaid["leaid"] = have_leaid["ncessch"].astype(str).str[:7]

    rows = []
    for district, group in have_leaid.groupby("district"):
        counts = group["leaid"].value_counts()
        modal_leaid = counts.index[0]
        rows.append(
            {
                "district": district,
                "district_name": group["district_name"].iloc[0],
                "leaid": modal_leaid,
                "leaid_coverage_frac": float(counts.iloc[0] / counts.sum()),
                "n_schools_with_leaid": int(counts.sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("district").reset_index(drop=True)


def build_district_staff_panel(
    teacher_salary: pd.DataFrame, district_finance: pd.DataFrame, crosswalk: pd.DataFrame
) -> pd.DataFrame:
    """`district x assessment_year`: `teacher_salary`'s own numbering merged
    with `district_finance` via the crosswalk's `leaid`. Outer-joined so a
    district-year present in only one sub-source still keeps its row (with
    the other sub-source's columns `NA`) — a genuine "not available", not
    dropped. `district_name` always comes from the crosswalk (authoritative,
    from `schools`' own spine), not from `teacher_salary` — `district_finance`
    predates `teacher_salary`'s 2013-14 start (back to 1995), so a
    finance-only district-year would otherwise have no name to join
    `panel/assemble.py`'s `(district_name, year)` key on."""
    salary = teacher_salary.drop(columns=["district_name"], errors="ignore").copy()
    salary["district"] = salary["district_number"].astype("Int64").astype(str).str.zfill(2)

    finance_with_district = district_finance.merge(
        crosswalk[["district", "leaid"]], on="leaid", how="inner"
    )
    finance_by_district_year = finance_with_district[
        ["district", "year", "per_pupil_expenditure"]
    ].drop_duplicates(subset=["district", "year"])

    out = salary.merge(finance_by_district_year, on=["district", "year"], how="outer")
    out = out.merge(crosswalk[["district", "district_name"]], on="district", how="left")
    out["district_number"] = pd.to_numeric(out["district"], errors="coerce").astype("Int64")
    return out.sort_values(["district", "year"]).reset_index(drop=True)


def build_school_staff_panel(out_of_field: pd.DataFrame) -> pd.DataFrame:
    """`msid x assessment_year`, already at the right join grain — `msid` is
    composed exactly like `schools/preprocess.py`'s `compose_ncessch`
    (`district.zfill(2) + school.zfill(4)`)."""
    columns = ["msid", "year", "pct_out_of_field", "n_classes_total", "n_classes_in_field", "n_classes_out_of_field"]
    if out_of_field.empty:
        return pd.DataFrame(columns=columns)

    out = out_of_field.copy()
    out["msid"] = (
        out["district_number"].astype("Int64").astype(str).str.zfill(2)
        + out["school_number"].astype("Int64").astype(str).str.zfill(4)
    )
    return out[columns].reset_index(drop=True)


def save_assembled(
    district_staff_panel: pd.DataFrame, school_staff_panel: pd.DataFrame, root: Path | None = None
) -> dict[str, str]:
    district_path = district_staff_panel_path(root)
    school_path = school_staff_panel_path(root)
    district_path.parent.mkdir(parents=True, exist_ok=True)
    district_staff_panel.to_parquet(district_path, index=False)
    school_staff_panel.to_parquet(school_path, index=False)
    return {"district_staff_panel": str(district_path), "school_staff_panel": str(school_path)}


def run_staff_assemble(root: Path | None = None) -> dict[str, object]:
    cross_section = load_school_cross_section(root)
    teacher_salary = load_processed_teacher_salary(root)
    out_of_field = load_processed_out_of_field(root)
    district_finance = load_processed_district_finance(root)

    crosswalk = build_district_leaid_crosswalk(cross_section)
    district_panel = build_district_staff_panel(teacher_salary, district_finance, crosswalk)
    school_panel = build_school_staff_panel(out_of_field)
    saved = save_assembled(district_panel, school_panel, root)

    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/staff/assemble.py",
        "distinct_districts_with_leaid": int(len(crosswalk)),
        "min_leaid_coverage_frac": float(crosswalk["leaid_coverage_frac"].min()) if not crosswalk.empty else None,
        "district_staff_panel_rows": int(len(district_panel)),
        "district_staff_panel_rows_with_per_pupil_expenditure": int(district_panel["per_pupil_expenditure"].notna().sum()),
        "school_staff_panel_rows": int(len(school_panel)),
        "saved": saved,
    }
