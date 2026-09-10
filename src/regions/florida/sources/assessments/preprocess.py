"""Preprocess step for the FLDOE assessment-results source.

Merges every raw workbook under ``data/florida/assessments/raw/<year>/`` (written
by ``fetch``) into one tidy table indexed on **school x grade x subject x year**
and writes it to ``data/florida/assessments/processed/assessments.parquet`` with
a ``assessments.json`` provenance sidecar.

This crystallizes ``src/experiments/florida/assessments.ipynb``. Design:

* **Two on-disk layouts** are absorbed by locating the header row
  (``District Number`` + ``School Number``) and mapping cells by name, not
  position: *wide-standard* (ELA / Math grade files, every EOC file, Statewide
  Science 2024+) and *science-legacy* (Statewide Science 2015-2023 — ``Grade``
  first, ``1..5`` before the "% level 3+" column, trailing content-area columns,
  a "Number of Points Possible" row under the header).
* **One ``STATE TOTALS`` row per file** is kept and flagged
  (``is_state_total``, ``msid == "000000"``) as the statewide reference line;
  it is excluded from the z-score moments.
* **Suppression** (small-cell rule, ``n < 10``) blanks the score columns; the
  ``suppressed`` flag is kept and those rows get ``NaN`` scores / z-scores.
* **Primary outcome:** ``z_mss`` / ``z_mss_w`` — the school mean scale score
  standardised within each ``year x subject x grade`` cell (unweighted and
  ``n_students``-weighted), which differences the FSA -> FAST / FSA -> B.E.S.T.
  scale breaks out.

No geocoding, no ``NCESSCH`` crosswalk, no school-directory join — the key is the
FLDOE District + School number (``msid``); turning it into coordinates and an
open/close panel filter is the ``schools`` source's work.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.regions.florida.sources.assessments.shared import (
    assessments_paths,
    processed_assessments_path,
    processed_metadata_path,
    validate_year,
)

# --- parsing ---------------------------------------------------------------

SUPPRESSED_TOKENS = {"*", "**", "***", "", "n/a", "na", ".", "nan", "none"}
_INT_RE = re.compile(r"^(\d+)(?:\.0+)?$")
_FILE_RE = re.compile(r"FL(\d{4})_([A-Z0-9]+)_(?:G(\d\d)|EOC)_")

SCORE_COLS = ["n_students", "mean_scale_score", "pct_level3_plus",
              "pct_l1", "pct_l2", "pct_l3", "pct_l4", "pct_l5"]

SUBJECT_LABEL = {
    "ELA": "English Language Arts", "MATH": "Mathematics",
    "SCI": "Statewide Science", "ALG1": "Algebra 1 EOC", "GEO": "Geometry EOC",
    "BIO1": "Biology 1 EOC", "CIVICS": "Civics EOC", "USHIST": "U.S. History EOC",
}

# The z-score is comparable only within a regime x subject x grade. FSA -> FAST
# (ELA, Math) and FSA -> B.E.S.T. (Algebra 1, Geometry) rescale at 2023; the
# NGSSS EOCs and Statewide Science were never rescaled.
FIRST_MODERN_REGIME_YEAR = 2023


def regime(year: int, subject: str) -> str:
    if subject in ("ELA", "MATH"):
        return "FSA" if year < FIRST_MODERN_REGIME_YEAR else "FAST"
    if subject in ("ALG1", "GEO"):
        return "FSA" if year < FIRST_MODERN_REGIME_YEAR else "B.E.S.T."
    if subject == "SCI":
        return "NGSSS Science"
    return "NGSSS EOC"  # BIO1, CIVICS, USHIST


def _norm_col(value) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = re.sub(r"\s+", " ", str(value)).strip().lower()
    if not s:
        return None
    if "district number" in s:
        return "district_number"
    if s == "district name":
        return "district_name"
    if "school number" in s:
        return "school_number"
    if s == "school name":
        return "school_name"
    if s == "grade":
        return "grade_raw"
    if "number of students" in s:
        return "n_students"
    if "mean" in s and "scale score" in s:
        return "mean_scale_score"
    if "points earned" in s or "points possible" in s:
        return None
    if "percent" in s and ("level 3" in s or "levels 3" in s) and "content" not in s:
        return "pct_level3_plus"
    if s in {"1", "2", "3", "4", "5"}:
        return f"pct_l{s}"
    return None


def _header_row(raw: pd.DataFrame) -> int:
    for i in range(min(16, len(raw))):
        joined = " | ".join(re.sub(r"\s+", " ", str(v)).strip().lower() for v in raw.iloc[i])
        if "district number" in joined and "school number" in joined:
            return i
    raise ValueError("header row (District Number + School Number) not found in first 16 rows")


def _to_id(value, width: int):
    match = _INT_RE.match(str(value).strip()) if value is not None else None
    return match.group(1).zfill(width) if match else pd.NA


def parse_sheet(raw: pd.DataFrame, year: int, subject: str, grade: str,
                source_file: str = "") -> pd.DataFrame:
    """Turn one raw, header-less sheet frame into the canonical long schema (one
    row per school, plus the file's single ``STATE TOTALS`` row). Split out from
    :func:`parse_workbook` so it can be unit-tested without an ``.xls`` file."""
    h = _header_row(raw)
    names = [_norm_col(v) for v in raw.iloc[h]]
    body = raw.iloc[h + 1:].reset_index(drop=True)

    cols: dict[str, pd.Series] = {}
    for j, name in enumerate(names):
        if name and name not in cols:
            cols[name] = body.iloc[:, j]
    df = pd.DataFrame(cols)

    df["district_number"] = df["district_number"].map(lambda v: _to_id(v, 2))
    df["school_number"] = df["school_number"].map(lambda v: _to_id(v, 4))
    for c in ("district_name", "school_name"):
        df[c] = df[c].astype("string").str.strip()
    df = df[df["district_number"].notna() & df["school_number"].notna()
            & df["school_name"].notna()].copy()

    df["msid"] = df["district_number"] + df["school_number"]
    df["is_state_total"] = (df["msid"].eq("000000")
                            | df["district_name"].str.upper().eq("STATE TOTALS"))

    mss = df["mean_scale_score"].astype("string").str.strip().str.lower()
    df["suppressed"] = mss.isna() | mss.isin(SUPPRESSED_TOKENS)
    for c in SCORE_COLS:
        if c not in df:
            df[c] = np.nan
        s = df[c].astype("string").str.strip()
        df[c] = pd.to_numeric(s.where(~s.str.lower().isin(SUPPRESSED_TOKENS)), errors="coerce")

    df["year"], df["subject"], df["grade"] = year, subject, grade
    df["source_file"] = source_file
    return df[["year", "subject", "grade", "district_number", "district_name",
               "school_number", "school_name", "msid", "is_state_total",
               "suppressed", *SCORE_COLS, "source_file"]]


def parse_workbook(path: Path, year: int, subject: str, grade: str) -> pd.DataFrame:
    """Read one raw ``.xls`` workbook and parse it to the canonical long schema."""
    raw = pd.ExcelFile(path).parse(0, header=None, dtype=object)
    return parse_sheet(raw, year, subject, grade, source_file=path.name)


def iter_raw_files(years: list[int] | None = None, root: Path | None = None):
    """Yield ``(path, year, subject, grade)`` for every ``FL<year>_<SUBJECT>_...``
    workbook under ``raw/<year>/``, optionally restricted to ``years``."""
    raw = assessments_paths(root)["raw"]
    wanted = {int(y) for y in years} if years else None
    for ydir in sorted(raw.glob("[0-9][0-9][0-9][0-9]")) if raw.exists() else []:
        year = int(ydir.name)
        if wanted is not None and year not in wanted:
            continue
        for path in sorted(ydir.glob("*.xls")):
            m = _FILE_RE.match(path.name)
            if m:
                yield path, int(m.group(1)), m.group(2), (m.group(3) or "EOC")


# --- assembly ------------------------------------------------------------------

INDEX_COLS = ["msid", "grade", "subject", "year"]
OUTPUT_COLS = [
    "subject_label", "regime", "retrofitted_2015",
    "district_number", "district_name", "school_number", "school_name",
    "is_state_total", "suppressed",
    "n_students", "mean_scale_score", "pct_level3_plus",
    "pct_l1", "pct_l2", "pct_l3", "pct_l4", "pct_l5",
    "z_mss", "z_mss_w", "source_file",
]


def _zscores(group: pd.DataFrame) -> pd.DataFrame:
    x = group["mean_scale_score"]
    z = (x - x.mean()) / x.std()
    w = group["n_students"]
    ok = w.notna() & x.notna()
    if ok.any() and w[ok].sum() > 0:
        mu = np.average(x[ok], weights=w[ok])
        sd = float(np.sqrt(np.average((x[ok] - mu) ** 2, weights=w[ok])))
        zw = (x - mu) / sd if sd > 0 else pd.Series(np.nan, index=group.index)
    else:
        zw = pd.Series(np.nan, index=group.index)
    return pd.DataFrame({"z_mss": z, "z_mss_w": zw})


def build_assessments_table(
    years: list[int] | None = None, root: Path | None = None
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Parse and merge every raw workbook into one tidy frame indexed on
    ``(msid, grade, subject, year)``, with the within-cell z-score."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frames = [parse_workbook(p, y, s, g) for p, y, s, g in iter_raw_files(years, root)]
    if not frames:
        raise FileNotFoundError(
            "No assessment workbooks found under "
            f"{assessments_paths(root)['raw']} — run "
            "`python -m src.cli florida data assessments fetch` (and drop the "
            "downloaded .xls files into raw/<year>/) first."
        )

    df = pd.concat(frames, ignore_index=True)
    df["subject_label"] = df["subject"].map(SUBJECT_LABEL)
    df["regime"] = [regime(y, s) for y, s in zip(df["year"], df["subject"])]
    df["retrofitted_2015"] = (df["year"] == 2015) & df["subject"].isin(["ELA", "MATH", "ALG1", "GEO"])

    cell = df["year"].astype(str) + "|" + df["subject"] + "|" + df["grade"]
    scored = df[~df["is_state_total"] & ~df["suppressed"]]
    z = scored.groupby(cell[scored.index], group_keys=False).apply(_zscores)
    df = df.join(z)

    # nullable dtypes so NaNs (suppression / state totals) round-trip through parquet
    for c in SCORE_COLS:
        df[c] = df[c].astype("Int64")
    for c in ("z_mss", "z_mss_w"):
        df[c] = df[c].astype("Float64")
    for c in ("is_state_total", "suppressed", "retrofitted_2015"):
        df[c] = df[c].astype("boolean")

    out = (df.set_index(INDEX_COLS)[OUTPUT_COLS]
           .sort_index())
    if out.index.duplicated().any():
        dupes = out.index[out.index.duplicated()].tolist()[:5]
        raise ValueError(f"non-unique (msid, grade, subject, year) index, e.g. {dupes}")

    school = out[~out["is_state_total"].fillna(False)]
    ok = school[~school["suppressed"].fillna(False)]
    lv_sum = ok[["pct_l1", "pct_l2", "pct_l3", "pct_l4", "pct_l5"]].sum(axis=1)
    l3p_gap = (ok["pct_l3"] + ok["pct_l4"] + ok["pct_l5"] - ok["pct_level3_plus"]).abs()
    stats = {
        "years": sorted(int(y) for y in df["year"].unique()),
        "n_files": int(df["source_file"].nunique()),
        "rows": int(len(out)),
        "school_rows": int(len(school)),
        "state_total_rows": int(out["is_state_total"].fillna(False).sum()),
        "distinct_schools": int(school.index.get_level_values("msid").nunique()),
        "rows_by_subject": {k: int(v) for k, v in
                            out.reset_index().groupby("subject").size().items()},
        "suppressed_share": round(float(school["suppressed"].fillna(False).mean()), 4),
        "levels_sum_within_2pp": round(float(lv_sum.between(98, 102).mean()), 4),
        "level3plus_consistent": round(float((l3p_gap <= 1).mean()), 4),
        "columns": INDEX_COLS + OUTPUT_COLS,
    }
    return out, stats


def save_processed(df: pd.DataFrame, stats: dict[str, object],
                   root: Path | None = None) -> dict[str, str]:
    parquet_path = processed_assessments_path(root)
    meta_path = processed_metadata_path(root)
    df.to_parquet(parquet_path, index=True)

    provenance = {
        "source": "fldoe_k12_assessment_results",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "raw_dir": str(assessments_paths(root)["raw"]),
        "index": INDEX_COLS,
        "outcome": "z_mss / z_mss_w — school mean scale score standardised within "
                   "year x subject x grade (unweighted / n_students-weighted)",
        **stats,
        "parquet": str(parquet_path),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"parquet": str(parquet_path), "metadata": str(meta_path)}


def run_assessment_preprocess(
    years: list[int] | None = None, root: Path | None = None
) -> dict[str, object]:
    """Merge the raw workbooks into the tidy table and persist it + its sidecar."""
    target_years = [validate_year(y) for y in years] if years else None
    table, stats = build_assessments_table(target_years, root)
    saved = save_processed(table, stats, root)
    return {**stats, "saved": saved}
