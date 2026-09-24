"""Raw-stage fetch for the Florida `staff` source's three sub-sources.

`teacher_salary`/`out_of_field` try `_http.wayback_download` first (see
`shared.py`'s module docstring for why `www.fldoe.org` itself is a dead end
for a scripted client), falling back to the same manual `--from-file`/
`--file-url` import path `assessments/fetch.py` uses for a year that isn't
archived (or if the Internet Archive itself is briefly down). `district_finance`
is a plain, unblocked JSON API call — no fallback needed.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from src.regions.florida.sources._http import WaybackNotArchivedError, download_to_file, get_json, wayback_download
from src.regions.florida.sources.staff.shared import (
    CCD_FINANCE_FIRST_YEAR,
    CCD_FINANCE_LAST_YEAR,
    OUT_OF_FIELD_FILES,
    TEACHER_SALARY_FILES,
    ccd_finance_url,
    raw_district_finance_path,
    raw_out_of_field_path,
    raw_teacher_salary_path,
)


def _fetch_fldoe_workbook(
    registry: dict[int, str],
    dest_fn,
    *,
    years: list[int] | None,
    from_file: str | None,
    file_url: str | None,
    root: Path | None,
) -> dict[str, object]:
    target_years = sorted(years) if years else sorted(registry)
    unknown = [y for y in target_years if y not in registry]
    if unknown:
        raise ValueError(f"No known FLDOE workbook URL for assessment year(s) {unknown}.")

    if from_file:
        if len(target_years) != 1:
            raise ValueError("--from-file requires exactly one --year.")
        src = Path(from_file).expanduser()
        if not src.is_file():
            raise FileNotFoundError(f"--from-file not found: {src}")
        dest = dest_fn(target_years[0], root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return {"years_targeted": target_years, "imported": [str(dest)], "downloaded": [], "errors": []}

    if file_url:
        if len(target_years) != 1:
            raise ValueError("--file-url requires exactly one --year.")
        dest = dest_fn(target_years[0], root)
        try:
            download_to_file(file_url, dest)
            return {"years_targeted": target_years, "imported": [], "downloaded": [str(dest)], "errors": []}
        except RuntimeError as exc:
            return {"years_targeted": target_years, "imported": [], "downloaded": [], "errors": [str(exc)]}

    downloaded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for year in target_years:
        dest = dest_fn(year, root)
        if dest.exists():
            skipped.append(str(dest))
            continue
        try:
            wayback_download(registry[year], dest)
            downloaded.append(str(dest))
        except WaybackNotArchivedError as exc:
            errors.append(f"{year}: {exc}")
        except RuntimeError as exc:
            errors.append(f"{year}: {exc}  (retry later, or download {registry[year]} in a browser and use --from-file)")

    return {
        "years_targeted": target_years,
        "downloaded": downloaded,
        "already_cached": skipped,
        "errors": errors,
    }


def fetch_teacher_salary(
    years: list[int] | None = None,
    *,
    from_file: str | None = None,
    file_url: str | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    return _fetch_fldoe_workbook(
        TEACHER_SALARY_FILES, raw_teacher_salary_path, years=years, from_file=from_file, file_url=file_url, root=root
    )


def fetch_out_of_field(
    years: list[int] | None = None,
    *,
    from_file: str | None = None,
    file_url: str | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    return _fetch_fldoe_workbook(
        OUT_OF_FIELD_FILES, raw_out_of_field_path, years=years, from_file=from_file, file_url=file_url, root=root
    )


def fetch_district_finance(years: list[int] | None = None, *, root: Path | None = None) -> dict[str, object]:
    """One GET per year against the Urban Institute's CCD F-33 finance
    endpoint (`fips=12`) — confirmed live 2026-09 to return every FL district
    in a single unpaginated response (`"next": null`), so no pagination loop
    is needed, unlike `schools`' larger per-school CCD/CRDC/EDFacts pulls."""
    target_years = sorted(years) if years else list(range(CCD_FINANCE_FIRST_YEAR, CCD_FINANCE_LAST_YEAR + 1))
    fetched: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for year in target_years:
        dest = raw_district_finance_path(year, root)
        if dest.exists():
            skipped.append(str(dest))
            continue
        try:
            payload = get_json(ccd_finance_url(year))
        except RuntimeError as exc:
            errors.append(f"{year}: {exc}")
            continue
        results = payload.get("results", [])
        dest.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame.from_records(results).assign(year=year).to_parquet(dest, index=False)
        fetched.append(str(dest))

    return {"years_targeted": target_years, "fetched": fetched, "already_cached": skipped, "errors": errors}
