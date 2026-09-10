"""Raw-stage handling for the FLDOE assessment-results source.

`www.fldoe.org` blocks scripted downloads, so there is no unattended fetch. This
module (1) reports the results-page registry and what is already in raw/,
(2) can import a workbook you downloaded in a browser (`--from-file`), and
(3) will make a best-effort HTTP attempt if you paste a direct file URL
(`--file-url`) — expect it to 403 unless your network is exempt.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from src.regions.florida.sources._http import download_to_file
from src.regions.florida.sources.assessments.shared import (
    ARCHIVE_PAGES,
    MANUAL_DOWNLOAD_STEPS,
    NO_SPRING_TESTING,
    RESULTS_PAGES,
    assessments_paths,
    scan_raw,
    validate_year,
    year_raw_dir,
)


def _sanitize(name: str) -> str:
    cleaned = name.strip().replace("/", "_").replace("\\", "_")
    return cleaned or "download.bin"


def list_years(root: Path | None = None) -> dict[str, object]:
    present = scan_raw(root)
    return {
        "results_pages": RESULTS_PAGES,
        "archive_pages": ARCHIVE_PAGES,
        "no_spring_testing": sorted(NO_SPRING_TESTING),
        "raw_dir": str(assessments_paths(root)["raw"]),
        "downloaded": {str(y): present.get(y, []) for y in sorted(present)},
        "missing": [y for y in sorted(RESULTS_PAGES) if not present.get(y)],
    }


def fetch_assessments(
    years: list[int] | None = None,
    *,
    from_files: list[str] | None = None,
    file_url: str | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    target_years = [validate_year(y) for y in years] if years else sorted(RESULTS_PAGES)
    imported: list[str] = []
    downloaded: list[str] = []
    errors: list[str] = []

    # Ensure the per-year folders exist so the manual drop target is obvious.
    for year in target_years:
        year_raw_dir(year, root).mkdir(parents=True, exist_ok=True)

    if from_files:
        if len(target_years) != 1:
            raise ValueError("--from-file requires exactly one --year.")
        dest_dir = year_raw_dir(target_years[0], root)
        for src in from_files:
            src_path = Path(src).expanduser()
            if not src_path.is_file():
                errors.append(f"--from-file not found: {src_path}")
                continue
            dest = dest_dir / _sanitize(src_path.name)
            shutil.copy2(src_path, dest)
            imported.append(str(dest))

    if file_url:
        if len(target_years) != 1:
            raise ValueError("--file-url requires exactly one --year.")
        dest = year_raw_dir(target_years[0], root) / _sanitize(file_url.split("?")[0].split("/")[-1] or "download.bin")
        try:
            download_to_file(file_url, dest)
            downloaded.append(str(dest))
        except RuntimeError as exc:
            errors.append(f"{exc}  (download in a browser and use --from-file instead)")

    present = scan_raw(root)
    return {
        "years_targeted": target_years,
        "imported": imported,
        "downloaded": downloaded,
        "errors": errors,
        "status": {
            str(y): {
                "page": RESULTS_PAGES.get(y),
                "files": present.get(y, []),
                "state": "present" if present.get(y) else "missing",
            }
            for y in target_years
        },
        "instructions": MANUAL_DOWNLOAD_STEPS,
    }
