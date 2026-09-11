"""Preprocess step (stages 1a + 1b) for the Florida ``schools`` source.

Builds the school spine and operation panel from the raw ``msid``, ``edge`` and
CCD/CRDC/EDFacts pulls (written by ``fetch``). Crystallizes
``src/experiments/florida/schools.ipynb``. Two artifacts:

* **`school_cross_section.parquet`** — one row per ``msid``: identity, the
  ``NCESSCH`` crosswalk, MSID classification, coordinates.
* **`school_year_panel.parquet`** — one row per ``msid x year`` (spring year,
  1990-2026): the cross-section's identity + geometry, ``in_operation``, and
  every available Cluster-A covariate (``docs/data/florida/covariates.md``)
  from CCD / CRDC / EDFacts.

Stage 2 — the school <-> barrier match, which ``REQUIRES noise_barriers`` — is
``schools/assemble.py``, not here: the split matches the on-disk layout
(``processed/`` vs ``assembled/``) and means editing a covariate definition
never re-runs the expensive geospatial match.

Design decisions (``docs/data/florida/schools/README.md`` has the full list):

* **The `NCESSCH` crosswalk is embedded in MSID** — ``FEDERAL_DIST_NO`` (7
  digits) + ``FEDERAL_SCHL_NO`` (5 digits); a ``"0"`` in either part is a
  "no federal id" sentinel -> ``NA`` (~9.4% of rows). A composed id can land on
  more than one ``msid`` (school reconstitutions / program stubs sharing a
  federal id, ~0.5%) — ``ncessch_shared`` flags this; it is not deduplicated
  away because both rows are legitimate MSID entries.
* **Coordinates:** NCES EDGE (address-geocoded, joined via the crosswalk) wins
  over MSID's own ``LATITUDE``/``LONGITUDE`` on disagreement (``geom_disagree_m``
  records the gap); schools with neither are ``geocode_pending`` — geocoding
  ``PHYSICAL_ADDRESS`` is a deferred follow-up, not done here.
* **Grade span** comes from MSID ``GRADE_CODE`` via the authoritative FLDOE
  code table (``msid_codes``, Appendix B — resolves ~85% of rows). The
  remainder (codes ``00``/``99`` = not-yet-assigned/unassigned) fall back to
  CCD's ``lowest_grade_offered``/``highest_grade_offered`` where that is a
  plain grade 0-12 (CCD's own ``-1`` sentinel is ambiguous between "PK" and
  "not reported" in the raw export, so it is **not** used as a fallback value).
* **`in_operation`** is month-aware: ``open_spring = year(DATE_OPENED) +
  (month >= 7)``, mirrored for ``DATE_CLOSED``; a school operates in spring
  year ``Y`` iff ``open_spring <= Y <= close_spring``. On a 2015+ year where the
  school **appears in `assessments.parquet`** but the dates disagree, the
  assessment appearance wins (``in_operation = True``, ``in_operation_src =
  "conflict"``) — testing students is hard evidence a school was open.
* **CCD/CRDC/EDFacts** use Urban's ``-1``/``-2``/``-3`` sentinels for
  missing/not-applicable/suppressed; the value becomes ``NA`` and a
  ``<col>_missing`` companion records why. Year alignment to the panel's spring
  year: CCD directory & enrollment ``year + 1`` (fall of the school year);
  CRDC ``year + 1`` (confirmed against the Urban codebook — ``year`` there is
  also defined as "Academic year (fall semester)"); EDFacts **no offset**
  (already spring-year indexed).
* **Raw-pull deduplication.** ``crdc_2021.parquet`` was found to carry 50,592
  fully-duplicate rows (63% of the file — every ``disability in {1, 2}`` row
  doubled, ``disability == 99`` clean; almost certainly an overlapping page
  from the fetch's pagination on that year's unusually large pull), which
  silently doubled ``pct_swd`` for spring year 2022. ``_load_year_parquets``
  drops exact-duplicate rows for every CCD/CRDC/EDFacts source as a result —
  harmless where none exist, which is everywhere else.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.regions.florida.sources.assessments.shared import (
    processed_assessments_path as assessments_parquet_path,
)
from src.regions.florida.sources.schools import msid_codes as MC
from src.regions.florida.sources.schools.shared import (
    EDGE_DEFAULT_VINTAGE,
    FL_FIPS_STR,
    PANEL_YEARS_DEFAULT,
    edge_extract_dir,
    edge_raw_path,
    msid_raw_path,
    processed_cross_section_path,
    processed_metadata_path,
    processed_panel_path,
    schools_paths,
)

TARGET_EPSG = 3087
FL_BBOX = (-87.7, 24.3, -79.8, 31.1)  # lon, lat — generous
TESTED_GRADES = MC.TESTED_GRADES

# CCD sentinel codes (Urban Institute Education Data API convention).
CCD_SENTINELS = {-1: "missing", -2: "na", -3: "suppressed"}

# Raw ccd_directory column -> tidy column. The three money columns get a
# `<dst>_missing` companion (see `_clean_sentinel`); the rest pass through.
CCD_DIRECTORY_MAP = {
    "enrollment": "enrollment",
    "free_or_reduced_price_lunch": "frpl_n",
    "teachers_fte": "teachers_fte",
    "title_i_status": "title_i_status",
    "charter": "ccd_charter",
    "magnet": "ccd_magnet",
    "virtual": "ccd_virtual",
    "school_status": "ccd_status",
    "lowest_grade_offered": "ccd_grade_low",
    "highest_grade_offered": "ccd_grade_high",
}
CCD_DIRECTORY_SENTINEL_COLS = ("enrollment", "free_or_reduced_price_lunch", "teachers_fte")

CCD_RACE_LABEL = {1: "white", 2: "black", 3: "hispanic", 4: "asian",
                  5: "amerindian", 6: "pacific", 7: "multiracial"}

# The cross-section's final column order (each kept only if present).
CROSS_SECTION_COLUMNS = [
    "msid", "ncessch", "ncessch_shared", "district", "school", "district_name",
    "name", "activity", "school_type", "charter_kind", "func_setting",
    "serv_type", "magnet_kind", "grade_code", "grade_low", "grade_high",
    "grade_low_source", "serves_tested_grades", "is_regular", "is_alternative",
    "is_charter", "is_magnet", "is_virtual", "geom_source", "geom_disagree_m",
    "geocode_pending", "date_opened", "date_closed", "in_assessments_ever",
    "geometry",
]


# --------------------------------------------------------------------------- #
# stage 1a: spine                                                            #
# --------------------------------------------------------------------------- #

def load_msid(root: Path | None = None) -> pd.DataFrame:
    """Read the fetched ``MSID_all_schools.tsv``, stripped of the stray
    trailing-tab empty column."""
    path = msid_raw_path("all_schools", root)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — run `python -m src.cli florida data schools fetch --subsource msid` first."
        )
    df = pd.read_csv(path, sep="\t", dtype=str).rename(columns=str.strip)
    return df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]


def compose_ncessch(msid: pd.DataFrame) -> pd.DataFrame:
    """Add ``msid``, ``ncessch`` and ``ncessch_shared`` (the crosswalk is
    embedded in MSID's own federal-id fields — see the module docstring)."""
    out = msid.copy()
    out["district"] = out["DISTRICT"].str.strip().str.zfill(2)
    out["school"] = out["SCHOOL"].str.strip().str.zfill(4)
    out["msid"] = out["district"] + out["school"]
    if not out["msid"].is_unique:
        dupes = out.loc[out["msid"].duplicated(keep=False), "msid"].unique()
        raise ValueError(f"MSID export has duplicate msid values: {sorted(dupes)[:10]}")

    fed_dist = out["FEDERAL_DIST_NO"].str.strip()
    fed_school = out["FEDERAL_SCHL_NO"].str.strip()
    has_fed = fed_dist.ne("0") & fed_dist.ne("") & fed_school.ne("0") & fed_school.ne("")
    out["ncessch"] = np.where(has_fed, fed_dist.str.zfill(7) + fed_school.str.zfill(5), np.nan)

    dup_ncessch = out.loc[out["ncessch"].notna(), "ncessch"]
    shared_ids = set(dup_ncessch[dup_ncessch.duplicated(keep=False)])
    out["ncessch_shared"] = out["ncessch"].isin(shared_ids)
    return out


def decode_classification(msid: pd.DataFrame, ccd_directory: pd.DataFrame | None = None) -> pd.DataFrame:
    """Decode the MSID single-letter codes via :mod:`msid_codes`, resolve the
    grade span (MSID ``GRADE_CODE`` primary, a conservative CCD fallback), and
    derive the advisory ``is_*`` flags. ``serv_type == 'B'`` is *Alternative
    Education*, not "basic" — see ``msid_codes.SERV_TYPE``."""
    out = msid.copy()
    out["activity"] = out["ACTIVITY_CODE"].map(MC.ACTIVITY_CODE)
    out["school_type"] = out["TYPE"].str.strip().str.zfill(2).map(MC.SCHOOL_TYPE)
    out["charter_kind"] = out["CHARTER_SCHL_STAT"].map(MC.CHARTER_STATUS)
    out["func_setting"] = out["SCHL_FUNC_SETTING"].map(MC.FUNC_SETTING)
    out["serv_type"] = out["PRIMARY_SERV_TYPE"].map(MC.SERV_TYPE)
    out["magnet_kind"] = out["MAGNET_STATUS"].map(MC.MAGNET_STATUS)

    grade_code = out["GRADE_CODE"].fillna("")
    span = grade_code.map(MC.grade_code_span)
    out["grade_low"] = span.map(lambda t: t[0]).astype("Int64")
    out["grade_high"] = span.map(lambda t: t[1]).astype("Int64")
    out["grade_low_source"] = np.where(out["grade_low"].notna(), "msid_grade_code", "none")
    out["serves_tested_grades"] = pd.array(grade_code.map(MC.grade_code_serves_tested), dtype="boolean")

    if ccd_directory is not None:
        _fill_grade_span_from_ccd(out, ccd_directory)

    out["is_regular"] = out["serv_type"].eq("k12_general")
    out["is_alternative"] = out["serv_type"].eq("alternative_education")
    out["is_charter"] = out["charter_kind"].notna() & out["charter_kind"].ne("not_charter")
    out["is_magnet"] = out["magnet_kind"].isin(["magnet_schoolwide", "magnet_program"])
    out["is_virtual"] = out["func_setting"].eq("virtual")
    return out


def _fill_grade_span_from_ccd(out: pd.DataFrame, ccd_directory: pd.DataFrame) -> None:
    """Best-effort fallback for the ~15% of rows GRADE_CODE leaves unresolved
    (mutates ``out`` in place). Only CCD grades 0-12 are trusted — CCD's own
    ``-1`` sentinel is ambiguous between "PK" and "not reported" in this
    export, so it is skipped rather than guessed."""
    def plain_grade(series: pd.Series) -> pd.Series:
        v = pd.to_numeric(series, errors="coerce")
        return v.where(v.between(0, 12))

    latest = (
        ccd_directory.dropna(subset=["ncessch"])
        .assign(_lo=plain_grade(ccd_directory["ccd_grade_low"]),
                _hi=plain_grade(ccd_directory["ccd_grade_high"]))
        .dropna(subset=["_lo", "_hi"])
        .sort_values("year")
        .drop_duplicates("ncessch", keep="last")
        .set_index("ncessch")[["_lo", "_hi"]]
    )
    need = out["grade_low"].isna() & out["ncessch"].notna()
    lo = out.loc[need, "ncessch"].map(latest["_lo"])
    hi = out.loc[need, "ncessch"].map(latest["_hi"])
    filled = lo.notna() & hi.notna()
    idx = lo[filled].index
    out.loc[idx, "grade_low"] = lo[filled].astype("Int64")
    out.loc[idx, "grade_high"] = hi[filled].astype("Int64")
    out.loc[idx, "grade_low_source"] = "ccd_directory"
    out.loc[idx, "serves_tested_grades"] = [
        bool(TESTED_GRADES & set(range(int(a), int(b) + 1))) for a, b in zip(lo[filled], hi[filled])
    ]


def extract_edge_shapefile(vintage: str | None = None, root: Path | None = None) -> Path:
    """The EDGE download is a zip containing a zip (``Shapefile_SCH.zip``)
    containing the shapefile. Extract both layers into a cached directory
    under ``raw/_edge_extracted/<vintage>/`` and return the ``.shp`` path."""
    vintage = vintage or EDGE_DEFAULT_VINTAGE
    zip_path = edge_raw_path(vintage, root)
    if not zip_path.exists():
        raise FileNotFoundError(
            f"{zip_path} missing — run `... schools fetch --subsource edge` first."
        )
    dest = edge_extract_dir(vintage, root)
    shp_path = dest / "Shapefile_SCH" / f"EDGE_GEOCODE_PUBLICSCH_{vintage}.shp"
    if shp_path.exists() and shp_path.stat().st_mtime >= zip_path.stat().st_mtime:
        return shp_path

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as outer:
        inner_name = next((n for n in outer.namelist() if n.lower().endswith(".zip")), None)
        if inner_name is None:
            raise RuntimeError(f"{zip_path} has no nested shapefile zip; found {outer.namelist()}")
        inner_bytes = outer.read(inner_name)
    inner_dir = dest / Path(inner_name).stem
    inner_dir.mkdir(parents=True, exist_ok=True)
    import io
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
        inner.extractall(inner_dir)
    if not shp_path.exists():
        found = list(dest.rglob("*.shp"))
        if not found:
            raise RuntimeError(f"no .shp found after extracting {zip_path}")
        shp_path = found[0]
    return shp_path


def load_edge(vintage: str | None = None, root: Path | None = None) -> gpd.GeoDataFrame:
    """FL rows of the NCES EDGE public-school geocode, keyed on ``ncessch``."""
    shp_path = extract_edge_shapefile(vintage, root)
    edge = gpd.read_file(shp_path)
    edge["ncessch"] = edge["NCESSCH"].astype(str)
    if "STATE" in edge.columns:
        edge = edge[edge["STATE"].astype(str).eq("FL")]
    else:
        edge = edge[edge["ncessch"].str.startswith("12")]
    return edge


def resolve_coordinates(msid: pd.DataFrame, edge: gpd.GeoDataFrame) -> pd.DataFrame:
    """EDGE (address-geocoded) wins over MSID's own lat/lon on disagreement;
    ``geom_source`` records which; ``geocode_pending`` flags active schools
    with neither. Returns ``msid`` with ``lat``/``lon``/ladder columns added."""
    out = msid.copy()
    mlat = pd.to_numeric(out["LATITUDE"], errors="coerce")
    mlon = pd.to_numeric(out["LONGITUDE"], errors="coerce")
    msid_ok = mlat.between(FL_BBOX[1], FL_BBOX[3]) & mlon.between(FL_BBOX[0], FL_BBOX[2])
    out["msid_lat"] = mlat.where(msid_ok)
    out["msid_lon"] = mlon.where(msid_ok)

    elat = pd.to_numeric(edge.get("LAT"), errors="coerce")
    elon = pd.to_numeric(edge.get("LON"), errors="coerce")
    if elat is None or elat.isna().all():
        elat, elon = edge.geometry.y, edge.geometry.x
    edge_ll = (
        edge.assign(edge_lat=np.asarray(elat), edge_lon=np.asarray(elon))
        [["ncessch", "edge_lat", "edge_lon"]]
        .dropna(subset=["ncessch"])
        .drop_duplicates("ncessch")
    )
    out = out.merge(edge_ll, on="ncessch", how="left")

    out["lat"] = out["edge_lat"].fillna(out["msid_lat"])
    out["lon"] = out["edge_lon"].fillna(out["msid_lon"])
    out["geom_source"] = np.select(
        [out["edge_lat"].notna(), out["msid_lat"].notna()], ["edge", "msid"], default="none"
    )
    out["geocode_pending"] = (out["geom_source"] == "none") & out["ACTIVITY_CODE"].eq("A")

    both = out.dropna(subset=["edge_lat", "msid_lat"])
    out["geom_disagree_m"] = _haversine_m(
        both["edge_lat"], both["edge_lon"], both["msid_lat"], both["msid_lon"]
    ).reindex(out.index)
    return out


def _haversine_m(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    r = 6371000.0
    p1, p2 = np.radians(lat1.to_numpy()), np.radians(lat2.to_numpy())
    dphi = np.radians(lat2.to_numpy() - lat1.to_numpy())
    dlmb = np.radians(lon2.to_numpy() - lon1.to_numpy())
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return pd.Series((2 * r * np.arcsin(np.sqrt(a))).round(1), index=lat1.index)


def load_assessment_schools(root: Path | None = None) -> pd.DataFrame:
    """Non-state-total rows of ``assessments.parquet`` (MultiIndexed on
    ``msid, grade, subject, year`` — reset before use)."""
    path = assessments_parquet_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data assessments preprocess` first.")
    assess = pd.read_parquet(path).reset_index()
    assess["msid"] = assess["msid"].astype(str)
    assess["year"] = assess["year"].astype(int)
    return assess[~assess["is_state_total"]]


def build_cross_section(
    spine: pd.DataFrame, assess_school: pd.DataFrame
) -> gpd.GeoDataFrame:
    """Assemble the one-row-per-``msid`` :data:`CROSS_SECTION_COLUMNS` table
    from the classified, geocoded MSID spine."""
    d = spine.rename(columns={
        "DISTRICT_NAME": "district_name", "SCHOOL_NAME_LONG": "name",
        "GRADE_CODE": "grade_code", "DATE_OPENED": "date_opened", "DATE_CLOSED": "date_closed",
    })
    geometry = gpd.points_from_xy(d["lon"], d["lat"], crs=4326)
    xs = gpd.GeoDataFrame(d, geometry=geometry, crs=4326).to_crs(TARGET_EPSG)
    xs["in_assessments_ever"] = xs["msid"].isin(set(assess_school["msid"]))
    cols = [c for c in CROSS_SECTION_COLUMNS if c in xs.columns]
    return xs[cols].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# stage 1a: operation panel skeleton                                        #
# --------------------------------------------------------------------------- #

def build_operation_panel(
    spine: pd.DataFrame,
    assess_school: pd.DataFrame,
    panel_years: tuple[int, int] = PANEL_YEARS_DEFAULT,
) -> pd.DataFrame:
    """One row per ``msid x year``, spring years ``panel_years``, with the
    month-aware ``in_operation`` rule (see the module docstring)."""
    opened = pd.to_datetime(spine["DATE_OPENED"], errors="coerce")
    closed = pd.to_datetime(spine["DATE_CLOSED"], errors="coerce")
    open_spring = (opened.dt.year + (opened.dt.month >= 7).astype("Int64")).astype("float")
    close_spring = (closed.dt.year + (closed.dt.month >= 7).astype("Int64")).astype("float")
    open_spring = open_spring.fillna(-np.inf).to_numpy()[:, None]
    close_spring = close_spring.fillna(np.inf).to_numpy()[:, None]

    lo, hi = panel_years
    years = np.arange(lo, hi + 1)
    in_op = (open_spring <= years) & (close_spring >= years)

    skeleton = pd.DataFrame(
        in_op,
        index=pd.Index(spine["msid"].to_numpy(), name="msid"),
        columns=pd.Index(years, name="year"),
    )
    panel = skeleton.stack().rename("in_operation").reset_index()
    panel["year"] = panel["year"].astype(int)
    panel["in_operation"] = panel["in_operation"].astype("boolean")

    tested = assess_school[["msid", "year"]].drop_duplicates().assign(in_assessments=True)
    panel = panel.merge(tested, on=["msid", "year"], how="left")
    panel["in_assessments"] = panel["in_assessments"].fillna(False)

    conflict = panel["in_assessments"] & (panel["in_operation"] == False) & panel["year"].between(2015, hi)  # noqa: E712
    tested_and_open = panel["in_assessments"] & (panel["in_operation"] == True)  # noqa: E712
    panel["in_operation_src"] = np.select([conflict, tested_and_open], ["conflict", "dates+tested"], default="dates")
    panel.loc[conflict, "in_operation"] = True
    return panel


# --------------------------------------------------------------------------- #
# stage 1b: Cluster-A covariates                                            #
# --------------------------------------------------------------------------- #

def _clean_sentinel(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Urban's ``-1/-2/-3`` -> (value with sentinels blanked to NA, a
    companion ``ok``/``missing``/``na``/``suppressed`` flag)."""
    values = pd.to_numeric(series, errors="coerce")
    missing = values.map(CCD_SENTINELS)
    missing = missing.where(values.lt(0), "ok")
    return values.where(values.ge(0)), missing


def _load_year_parquets(root: Path | None, pattern: str) -> pd.DataFrame | None:
    """Concatenate the cached per-year raw pulls, dropping exact-duplicate rows.
    ``crdc_2021.parquet`` was found to carry 50,592 fully-duplicate rows (63% of
    the file, every ``disability in {1, 2}`` row present twice, ``disability ==
    99`` clean) — almost certainly an overlapping page from ``_get_all_pages``
    on that year's unusually large pull. Left uncorrected this doubles
    ``pct_swd`` for spring year 2022 (median 0.14 -> 0.29, 3.6% of rows > 1).
    Deduplicating here is defensive and harmless for every other file, which
    has none."""
    files = sorted(schools_paths(root)["raw"].glob(pattern))
    if not files:
        return None
    return pd.concat(
        [pd.read_parquet(f) for f in files], ignore_index=True
    ).drop_duplicates(ignore_index=True)


def tidy_ccd_directory(root: Path | None = None) -> pd.DataFrame | None:
    """``enrollment``, ``frpl_n``, ``teachers_fte``, ``pupil_teacher_ratio``,
    Title I / charter / magnet / virtual / status, grade span — spring-year
    indexed. ``None`` if `ccd_directory` was never fetched."""
    raw = _load_year_parquets(root, "ccd_directory_*.parquet")
    if raw is None:
        return None
    raw = raw[pd.to_numeric(raw["fips"], errors="coerce") == int(FL_FIPS_STR)].copy()
    raw["ncessch"] = raw["ncessch"].astype(str).str.zfill(12)
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce") + 1  # fall of school year -> spring

    out = raw[["ncessch", "year"]].copy()
    for src, dst in CCD_DIRECTORY_MAP.items():
        if src not in raw.columns:
            continue
        if src in CCD_DIRECTORY_SENTINEL_COLS:
            out[dst], out[f"{dst}_missing"] = _clean_sentinel(raw[src])
        else:
            out[dst] = raw[src]
    out["pupil_teacher_ratio"] = out["enrollment"] / out["teachers_fte"].replace(0, np.nan)
    return out


def tidy_ccd_enrollment_race(root: Path | None = None) -> pd.DataFrame | None:
    """Race/ethnicity shares from ``ccd_enrollment`` (``/race/`` disaggregation).
    ``None`` if never fetched."""
    raw = _load_year_parquets(root, "ccd_enrollment_*.parquet")
    if raw is None:
        return None
    raw = raw.copy()
    raw["ncessch"] = raw["ncessch"].astype(str).str.zfill(12)
    raw["enrollment"] = pd.to_numeric(raw["enrollment"], errors="coerce")
    raw.loc[raw["enrollment"] < 0, "enrollment"] = np.nan
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce") + 1

    total = raw.loc[raw["race"] == 99].groupby(["ncessch", "year"])["enrollment"].sum().rename("enr_total")
    wide = (
        raw[raw["race"].isin(CCD_RACE_LABEL)]
        .pivot_table(index=["ncessch", "year"], columns="race", values="enrollment", aggfunc="sum")
        .rename(columns=CCD_RACE_LABEL)
    )
    out = wide.join(total).reset_index()
    denom = out["enr_total"].where(out["enr_total"] > 0)  # avoid a 0/0 -> inf
    for race in CCD_RACE_LABEL.values():
        if race in out.columns:
            out[f"pct_{race}"] = out[race] / denom
    keep = ["ncessch", "year", "enr_total"] + [f"pct_{r}" for r in CCD_RACE_LABEL.values() if f"pct_{r}" in out]
    return out[keep]


def tidy_crdc_swd(root: Path | None = None) -> pd.DataFrame | None:
    """``pct_swd`` (IDEA-served students with disabilities) from ``crdc``
    (``/disability/sex/``, biennial). ``None`` if never fetched.

    2021 has a second, subtler duplication `_load_year_parquets`'s exact-row
    dedup doesn't catch: ~14% of schools carry two ``(ncessch, disability=1,
    sex=99, race=99)`` records with an identical ``enrollment_crdc`` (the K-12
    IDEA total) but a different ``psenrollment_crdc`` (preschool enrollment,
    unused here) — almost certainly a school + attached-preschool-program split
    in OCR's own collection. Deduplicating on the natural key before summing
    (not full-row) removes it regardless of which unused column differs.
    """
    raw = _load_year_parquets(root, "crdc_*.parquet")
    if raw is None:
        return None
    raw = raw.copy()
    raw["ncessch"] = raw["ncessch"].astype(str).str.zfill(12)
    raw["enrollment_crdc"] = pd.to_numeric(raw["enrollment_crdc"], errors="coerce")
    raw.loc[raw["enrollment_crdc"] < 0, "enrollment_crdc"] = np.nan
    # Urban's crdc codebook defines `year` as "Academic year (fall semester)" —
    # the same convention as CCD — so +1 is confirmed, not assumed.
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce") + 1

    key = ["ncessch", "year", "race", "sex", "disability"]
    sex_total = raw[raw["sex"] == 99].drop_duplicates(subset=key)
    idea = sex_total[sex_total["disability"] == 1].groupby(["ncessch", "year"])["enrollment_crdc"].sum().rename("swd_n")
    total = sex_total[sex_total["disability"] == 99].groupby(["ncessch", "year"])["enrollment_crdc"].sum().rename("crdc_total")
    out = pd.concat([idea, total], axis=1).reset_index()
    # a handful of school-years report a positive IDEA count against a 0 total
    # (an internally inconsistent source row) -> NA rather than +inf
    out["pct_swd"] = out["swd_n"] / out["crdc_total"].where(out["crdc_total"] > 0)
    return out


def tidy_crdc_lep(root: Path | None = None) -> pd.DataFrame | None:
    """``pct_ell`` (limited-English-proficient students) from ``crdc_lep``
    (``/lep/sex/``, biennial). ``None`` if never fetched.

    Same shape and provenance as :func:`tidy_crdc_swd` (same CRDC datasource,
    same biennial years, same "academic year (fall semester)" -> +1 spring
    offset) but disaggregated by ``lep`` (1 = LEP, 99 = total) instead of
    ``disability``. Deduplicated the same defensive way, on the natural key
    before summing, in case this endpoint carries the same kind of
    school+preschool split ``tidy_crdc_swd`` found in 2021."""
    raw = _load_year_parquets(root, "crdc_lep_*.parquet")
    if raw is None:
        return None
    raw = raw.copy()
    raw["ncessch"] = raw["ncessch"].astype(str).str.zfill(12)
    raw["enrollment_crdc"] = pd.to_numeric(raw["enrollment_crdc"], errors="coerce")
    raw.loc[raw["enrollment_crdc"] < 0, "enrollment_crdc"] = np.nan
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce") + 1

    key = ["ncessch", "year", "race", "sex", "lep"]
    sex_total = raw[raw["sex"] == 99].drop_duplicates(subset=key)
    ell = sex_total[sex_total["lep"] == 1].groupby(["ncessch", "year"])["enrollment_crdc"].sum().rename("ell_n")
    total = sex_total[sex_total["lep"] == 99].groupby(["ncessch", "year"])["enrollment_crdc"].sum().rename("crdc_lep_total")
    out = pd.concat([ell, total], axis=1).reset_index()
    out["pct_ell"] = out["ell_n"] / out["crdc_lep_total"].where(out["crdc_lep_total"] > 0)
    return out[["ncessch", "year", "pct_ell"]]


def tidy_edfacts(root: Path | None = None) -> pd.DataFrame | None:
    """``read_prof_midpt`` / ``math_prof_midpt`` — a robustness cross-check
    *outcome*, not a Cluster-A covariate. ``None`` if never fetched."""
    raw = _load_year_parquets(root, "edfacts_*.parquet")
    if raw is None:
        return None
    raw = raw.copy()
    raw["ncessch"] = raw["ncessch"].astype(str).str.zfill(12)
    for col in ("race", "sex", "lep", "disability", "econ_disadvantaged",
                "homeless", "migrant", "foster_care", "military_connected"):
        if col in raw.columns:
            raw = raw[pd.to_numeric(raw[col], errors="coerce").fillna(99) == 99]
    keep = [c for c in ("ncessch", "year", "read_test_pct_prof_midpt", "math_test_pct_prof_midpt")
            if c in raw.columns]
    out = raw[keep].rename(columns={
        "read_test_pct_prof_midpt": "read_prof_midpt", "math_test_pct_prof_midpt": "math_prof_midpt",
    })
    for col in ("read_prof_midpt", "math_prof_midpt"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def join_covariates(
    panel: pd.DataFrame,
    cross_section: pd.DataFrame,
    ccd_directory: pd.DataFrame | None,
    race_shares: pd.DataFrame | None,
    crdc_swd: pd.DataFrame | None,
    crdc_lep: pd.DataFrame | None,
    edfacts: pd.DataFrame | None,
) -> pd.DataFrame:
    """Left-join every available Cluster-A table onto the panel skeleton, keyed
    on ``(ncessch, year)``. Nothing is lagged here — t-1 lagging is an
    analysis-layer choice (``docs/data/florida/covariates.md``)."""
    out = panel.merge(cross_section[["msid", "ncessch"]], on="msid", how="left")
    for table in (ccd_directory, race_shares, crdc_swd, crdc_lep, edfacts):
        if table is not None:
            out = out.merge(table, on=["ncessch", "year"], how="left")
    return out


# --------------------------------------------------------------------------- #
# orchestrator                                                              #
# --------------------------------------------------------------------------- #

def save_processed(
    cross_section: gpd.GeoDataFrame,
    panel: gpd.GeoDataFrame,
    report: dict[str, object],
    root: Path | None = None,
) -> dict[str, str]:
    """Write the two parquets + the ``schools.json`` provenance/validation
    sidecar."""
    xs_path = processed_cross_section_path(root)
    pn_path = processed_panel_path(root)
    meta_path = processed_metadata_path(root)
    for path in (xs_path, pn_path, meta_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    cross_section.to_parquet(xs_path)
    panel.to_parquet(pn_path)
    meta_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"cross_section": str(xs_path), "panel": str(pn_path), "metadata": str(meta_path)}


def run_schools_preprocess(
    root: Path | None = None,
    panel_years: tuple[int, int] = PANEL_YEARS_DEFAULT,
    edge_vintage: str | None = None,
) -> dict[str, object]:
    """Load the raw ``msid``/``edge``/CCD/CRDC/EDFacts pulls, build the spine +
    operation panel, join every available Cluster-A covariate, validate, and
    persist ``school_cross_section.parquet`` / ``school_year_panel.parquet``."""
    msid_raw = load_msid(root)
    msid_id = compose_ncessch(msid_raw)

    ccd_directory = tidy_ccd_directory(root)
    msid_classified = decode_classification(msid_id, ccd_directory)

    edge = load_edge(edge_vintage, root)
    msid_geo = resolve_coordinates(msid_classified, edge)

    assess_school = load_assessment_schools(root)
    cross_section = build_cross_section(msid_geo, assess_school)
    panel_skeleton = build_operation_panel(msid_geo, assess_school, panel_years)

    race_shares = tidy_ccd_enrollment_race(root)
    crdc_swd = tidy_crdc_swd(root)
    crdc_lep = tidy_crdc_lep(root)
    edfacts = tidy_edfacts(root)
    panel = join_covariates(
        panel_skeleton, cross_section, ccd_directory, race_shares, crdc_swd, crdc_lep, edfacts
    )
    panel_geo = gpd.GeoDataFrame(
        panel.merge(cross_section[["msid", "geometry"]], on="msid", how="left"),
        geometry="geometry", crs=f"EPSG:{TARGET_EPSG}",
    )

    # --- validation gate ---
    if not cross_section["msid"].is_unique:
        raise ValueError("school_cross_section must be one row per msid")
    if panel_geo.duplicated(["msid", "year"]).any():
        raise ValueError("school_year_panel must be one row per (msid, year)")

    tested_msid = set(assess_school["msid"])
    missing_msid = tested_msid - set(cross_section["msid"])
    # districts 78/80 = state colleges (dual-enrolment EOCs), not PK-12 — expected absent
    known_exceptions = {m for m in missing_msid if m[:2] in ("78", "80")}
    unexplained_missing = sorted(missing_msid - known_exceptions)
    if unexplained_missing:
        raise ValueError(f"assessment msid missing from the spine, unexplained: {unexplained_missing}")

    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/schools/preprocess.py",
        "panel_years": list(panel_years),
        "crs": f"EPSG:{TARGET_EPSG}",
        "rows": {"cross_section": int(len(cross_section)), "panel": int(len(panel_geo))},
        "crosswalk": {
            "ncessch_sentinel_share": float(msid_id["ncessch"].isna().mean()),
            "ncessch_shared_rows": int(msid_id["ncessch_shared"].sum()),
            "assessment_msid_missing_state_colleges": sorted(known_exceptions),
        },
        "coordinates": {
            "geom_source": cross_section["geom_source"].value_counts().to_dict(),
            "geocode_pending": int(cross_section["geocode_pending"].sum()),
        },
        "grade_span": {
            "source": cross_section["grade_low_source"].value_counts().to_dict(),
            "unresolved": int(cross_section["grade_low"].isna().sum()),
        },
        "panel": {
            "operating_rows": int(panel_geo["in_operation"].sum()),
            "conflict_to_true": int((panel_geo["in_operation_src"] == "conflict").sum()),
        },
        "stage1b_sources_present": {
            "ccd_directory": ccd_directory is not None,
            "ccd_enrollment_race": race_shares is not None,
            "crdc_swd": crdc_swd is not None,
            "crdc_lep": crdc_lep is not None,
            "edfacts": edfacts is not None,
        },
        "panel_columns": list(panel_geo.columns),
    }
    report["saved"] = save_processed(cross_section, panel_geo, report, root)
    return report
