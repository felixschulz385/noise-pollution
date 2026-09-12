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
  ``n_students``-weighted), which differences the FCAT 2.0 -> FSA, FSA -> FAST
  and FSA -> B.E.S.T. scale breaks out.

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

# The z-score is comparable only within a regime x subject x grade. FCAT ->
# FCAT 2.0 rescales at 2011 (new Next Generation Sunshine State Standards,
# NGSSS); FCAT 2.0 -> FSA rescales again at 2015; FSA -> FAST (ELA, Math) and
# FSA -> B.E.S.T. (Algebra 1, Geometry) rescale a third time at 2023. EOCs
# (Algebra 1, Geometry, Biology 1, Civics, U.S. History) didn't exist before
# 2011 (FCAT had no EOCs) and the NGSSS ones were never rescaled through the
# FCAT 2.0/FSA boundary.
FIRST_FCAT2_YEAR = 2011
FIRST_FSA_YEAR = 2015
FIRST_MODERN_REGIME_YEAR = 2023


def regime(year: int, subject: str) -> str:
    if subject in ("ELA", "MATH"):
        if year < FIRST_FCAT2_YEAR:
            return "FCAT"
        if year < FIRST_FSA_YEAR:
            return "FCAT 2.0"
        return "FSA" if year < FIRST_MODERN_REGIME_YEAR else "FAST"
    if subject in ("ALG1", "GEO"):
        if year < FIRST_FSA_YEAR:
            return "NGSSS EOC"
        return "FSA" if year < FIRST_MODERN_REGIME_YEAR else "B.E.S.T."
    if subject == "SCI":
        return "SSS Science" if year < FIRST_FCAT2_YEAR else "NGSSS Science"
    return "NGSSS EOC"  # BIO1, CIVICS, USHIST


def _norm_col(value) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = re.sub(r"\s+", " ", str(value)).strip().lower()
    if not s:
        return None
    if "district number" in s:
        return "district_number"
    if s in ("district name", "district"):   # 2003 G04-10 labels this column just "District"
        return "district_name"
    if "school number" in s:
        return "school_number"
    if s in ("school name", "school"):   # 2004-07 FCAT labels this column just "School"
        return "school_name"
    if s == "grade":
        return "grade_raw"
    if "number of students" in s:
        return "n_students"
    if "mean" in s and "scale score" in s:
        # 2012-14 FCAT 2.0 ELA/Math report only "Mean Developmental Scale
        # Score" (the within-grade score, despite the name) -- that's the
        # usable column there. 2011 uniquely reports BOTH that column and a
        # separate "... Scale Score (100-500)" (a one-year legacy-linking
        # column back to old FCAT); when both exist, prefer the (100-500)
        # one, tagged separately so `parse_sheet` can pick a winner.
        return "mean_scale_score_dev" if "developmental" in s else "mean_scale_score"
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
    # 2003 grades 4-10: the District/School NUMBER columns carry no header
    # text at all -- only bare "District" / "School" labels (meaning the
    # NAME columns, one position to their right). Detect via those two exact
    # cells co-occurring with a scale-score label, to avoid false positives.
    for i in range(min(16, len(raw))):
        cells = [re.sub(r"\s+", " ", str(v)).strip().lower() for v in raw.iloc[i]]
        if "district" in cells and "school" in cells and any("scale score" in c for c in cells):
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
    header_cells = [re.sub(r"\s+", " ", str(v)).strip().lower() for v in raw.iloc[h]]
    names = [_norm_col(v) for v in raw.iloc[h]]
    body = raw.iloc[h + 1:].reset_index(drop=True)

    cols: dict[str, pd.Series] = {}
    for j, name in enumerate(names):
        if name and name not in cols:
            cols[name] = body.iloc[:, j]

    # 2003 grades 4-10: the District/School NUMBER columns have no header
    # text at all -- only bare "District"/"School" (name) labels -- and
    # merged header cells shift where that text lands column-to-column
    # inconsistently across files, so its position can't be trusted. The
    # underlying data is always laid out
    # [district_number, district_name, school_number, school_name] in the
    # first 4 columns regardless, confirmed across multiple files -- use that
    # fixed positional layout instead of hunting for the label.
    if "district" in header_cells and "school" in header_cells:
        cols["district_number"] = body.iloc[:, 0]
        cols["district_name"] = body.iloc[:, 1]
        cols["school_number"] = body.iloc[:, 2]
        cols["school_name"] = body.iloc[:, 3]

    df = pd.DataFrame(cols)

    if "mean_scale_score" not in df.columns and "mean_scale_score_dev" in df.columns:
        df = df.rename(columns={"mean_scale_score_dev": "mean_scale_score"})
    else:
        df = df.drop(columns=["mean_scale_score_dev"], errors="ignore")

    df["district_number"] = df["district_number"].map(lambda v: _to_id(v, 2))
    df["school_number"] = df["school_number"].map(lambda v: _to_id(v, 4))
    for c in ("district_name", "school_name"):
        df[c] = df[c].astype("string").str.strip()
    # Some pre-2011 FCAT files leave the STATE TOTALS row's school-name cell
    # blank (no "RESULTS FOR GRADE"-style placeholder), and a few (e.g.
    # 2006-08 Math grade 3) leave district_number/school_number blank there
    # too, not even "00"/"0000" -- don't drop that row for missing IDs, or
    # the file's single provenance total row is silently lost. No real
    # Florida county name contains "state", so this text match is safe.
    is_totals_row = df["district_name"].str.upper().str.contains("STATE", na=False)
    keep = is_totals_row | (df["district_number"].notna() & df["school_number"].notna()
                            & df["school_name"].notna())
    df = df[keep].copy()
    is_totals_row = is_totals_row.loc[df.index]
    df.loc[is_totals_row & df["district_number"].isna(), "district_number"] = "00"
    df.loc[is_totals_row & df["school_number"].isna(), "school_number"] = "0000"

    df["msid"] = df["district_number"] + df["school_number"]
    df["is_state_total"] = (df["msid"].eq("000000")
                            | df["district_name"].str.upper().eq("STATE TOTALS"))

    # FL2011_MATH_G07_school.xls (and maybe others) appends a second, partial
    # pass over a handful of districts after the main body — a late-district
    # resubmission FLDOE appended instead of replacing in place, not a parser
    # artifact (confirmed: only districts near the end of the sheet repeat,
    # each with different Number of Students / scores the second time). Keep
    # the later row, which is the resubmission, same convention as
    # `schools/preprocess.py`'s `drop_duplicates(..., keep="last")`.
    df = df.drop_duplicates(subset="msid", keep="last")

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


OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def parse_workbook(path: Path, year: int, subject: str, grade: str) -> pd.DataFrame:
    """Read one raw ``.xls`` workbook and parse it to the canonical long schema.

    2004-05 Science school reports are SAS-generated "Excel HTML" exports, not
    real OLE2 binaries, despite the ``.xls`` extension (Excel opens them fine
    either way). ``pd.read_html`` happens to produce the same header-less grid
    shape as ``pd.ExcelFile(...).parse(0, header=None)``, so the rest of the
    pipeline (header detection, column mapping) is unchanged either way.
    """
    with path.open("rb") as f:
        head = f.read(8)
    if head == OLE2_MAGIC:
        raw = pd.ExcelFile(path).parse(0, header=None, dtype=object)
    else:
        raw = pd.read_html(path, header=None)[0]
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
    "subject_label", "regime", "retrofitted_2015", "fcat_equivalent_2011",
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
    # 2011 ELA/Math school reports carry only "FCAT Equivalent" scores -- a
    # crosswalk onto the legacy (pre-2.0) FCAT scale for transition-year
    # continuity, not FCAT 2.0's own native per-grade scale that 2012-14
    # report directly as "Mean Developmental Scale Score". Flagged (not
    # dropped) the same way as `retrofitted_2015`: the within-year z-score is
    # unaffected, but raw `mean_scale_score` should not be trended against
    # 2012-14 as if on the same scale.
    df["fcat_equivalent_2011"] = (df["year"] == 2011) & df["subject"].isin(["ELA", "MATH"])

    cell = df["year"].astype(str) + "|" + df["subject"] + "|" + df["grade"]
    scored = df[~df["is_state_total"] & ~df["suppressed"]]
    z = scored.groupby(cell[scored.index], group_keys=False).apply(_zscores)
    df = df.join(z)

    # nullable dtypes so NaNs (suppression / state totals) round-trip through parquet
    for c in SCORE_COLS:
        df[c] = df[c].astype("Int64")
    for c in ("z_mss", "z_mss_w"):
        df[c] = df[c].astype("Float64")
    for c in ("is_state_total", "suppressed", "retrofitted_2015", "fcat_equivalent_2011"):
        df[c] = df[c].astype("boolean")

    out = (df.set_index(INDEX_COLS)[OUTPUT_COLS]
           .sort_index())
    if out.index.duplicated().any():
        dupes = out.index[out.index.duplicated()].tolist()[:5]
        raise ValueError(f"non-unique (msid, grade, subject, year) index, e.g. {dupes}")

    school = out[~out["is_state_total"].fillna(False)]
    ok = school[~school["suppressed"].fillna(False)]
    level_cols = ["pct_l1", "pct_l2", "pct_l3", "pct_l4", "pct_l5"]
    # 2003-05 Science reports predate FLDOE finalizing Science achievement
    # levels ("Science Achievement Levels have not been determined" is the
    # sheet's own footnote) -- those rows carry no level percentages at all,
    # not a suppression or parsing gap, so exclude them from these two
    # consistency checks rather than count an all-NaN row as a violation.
    has_levels = ok[level_cols].notna().any(axis=1)
    scored = ok[has_levels]
    lv_sum = scored[level_cols].sum(axis=1)
    l3p_gap = (scored["pct_l3"] + scored["pct_l4"] + scored["pct_l5"] - scored["pct_level3_plus"]).abs()
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
