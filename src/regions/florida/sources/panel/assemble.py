"""Final assembly for the Florida barrier-construction event study: joins
the outcome (``assessments``), Cluster-A covariates + spine identity
(``schools``), and all three barrier-treatment-timing definitions
(``schools assemble``'s rollup) into one school x grade x subject x year
panel.

``REQUIRES`` ``assessments preprocess`` and ``schools {preprocess,assemble}``
to have already run — this module does no fetching or cleaning of its own,
only joining already-processed local artifacts. Kept as its own stage (not
folded into ``schools/assemble.py``) for the same isolation reason the
``schools`` source's own stages are split: editing an outcome-panel filter
should never re-run the geospatial barrier match, and vice versa.

Treatment timing is carried as **three parallel definitions**
(``_point`` / ``_same_route`` / ``_same_side`` — ``schools/assemble.py``'s
matching-rigour tiers, see ``docs/data/florida/schools/README.md``) rather
than collapsed to one — the analysis layer picks a baseline + robustness
checks downstream, nothing is decided here. A school with no nearby wall at
all gets ``ever_treated_* = False`` (a real, informative value), not a
missing row or NA — every join here is a LEFT join anchored on
``assessments``, so no outcome row is ever dropped for a missing covariate
or treatment match.

**Traffic (Cluster C) is joined by nearest available FGDL release year, not
an exact-year match.** ``traffic``'s ``school_aadt_panel.parquet`` only has
AADT for the years FGDL happened to publish a release (real gaps: no release
at all for 2005 or 2012-2015, see ``docs/data/florida/traffic/README.md``),
while ``assessments`` has one row per school-year every year. ``attach_traffic``
uses ``pd.merge_asof(..., direction="nearest", tolerance=MAX_TRAFFIC_YEAR_GAP)``
per ``msid`` to pick the closest release year within
:data:`MAX_TRAFFIC_YEAR_GAP` years — an assessment year further than that from
any release (e.g. deep inside the 2012-2015 hole) gets ``NA`` traffic columns
rather than a misleadingly stale match. ``traffic_aadt`` is the roadway-wide
mean; ``traffic_aadt_local`` (when present in ``school_aadt_panel.parquet``)
is the current-snapshot-scaled, school-specific estimate — see
``traffic/assemble.py``'s module docstring for what that scaling does and
does not assume.

**Road-works (Cluster D) is joined by year-interval overlap, not a
nearest-value match like traffic.** ``road_projects``'s
``school_road_projects.parquet`` rows carry a *timing interval*, not a
single year: a Work-Program row has one ``fiscal_year``, an
Active-Construction row has a ``[start_date, end_date]`` date range (real
data: median 2-year span, max 9). ``attach_road_projects`` first explodes
each pair into one row per calendar year the project actually spans
(``_project_active_years``), then does a plain exact-year left join onto
``(msid, year)`` — unlike ``merge_asof``'s nearest-match tolerance, a school
either had a logged project active in that specific assessment year or it
didn't. A school-year with no active project gets
``n_road_projects_active=0`` / the flag columns ``False``, not ``NA`` — this
is a real "no road work" value, not a missing one, mirroring the
``ever_treated_*`` convention above. The **164** ``is_wall_project``
keyword-flagged rows from ``preprocess.py`` and the ``is_widening_project``
scan (``road_projects.shared.tag_widening_keyword``, shared with
``road_projects/assemble.py``'s own per-school rollup rather than
duplicated) both roll up into per-school-year booleans.

**A malformed source row (``end_date`` earlier than ``start_date``) is
dropped from the year-level join, not just a missing one.** FDOT documents
``EstEndDate`` as an estimate that can be revised, so a future fetch could
plausibly land a reversed range; ``_project_active_years`` treats
``year_lo > year_hi`` the same as an unusable/missing interval (excluded
before exploding) rather than crashing on ``range(lo, hi + 1)`` producing an
empty span.

**Shocks (Cluster G) is joined by an exact ``(district_name, year)`` match —
the simplest join in this module.** ``shocks``' ``county_year_panel``
(``shocks/assemble.py``'s output, despite the ``school_shocks_panel.parquet``
filename — kept at ``county_name x assessment_year`` grain, not exploded per
school, since every school in a county sees the identical declaration
history) already carries ``assessment_year`` — ``shocks/preprocess.py``
derives it from each declaration's actual date via the same month-aware rule
``schools/preprocess.py`` uses for ``in_operation``. So ``attach_shocks``
needs no ``merge_asof`` tolerance or interval explosion: it renames
``county_name``/``assessment_year`` to ``district_name``/``year`` and does a
plain left join — ``assessments``' own ``district_name`` column already
upper-cases to the same county-name convention ``shocks`` normalizes to, no
extra crosswalk needed here. A school-year in a county with no declaration
that year (or in one of the ~20 special, non-county FLDOE districts) gets
``shock_n_declarations=0`` / ``shock_any_major_disaster=False`` — a real "no
shock" value, matching the ``ever_treated_*``/``n_road_projects_active``
convention, not ``NA``.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.florida.sources.assessments.shared import processed_assessments_path
from src.regions.florida.sources.panel.shared import assembled_metadata_path, assembled_panel_path
from src.regions.florida.sources.road_projects.shared import school_road_projects_path, tag_widening_keyword
from src.regions.florida.sources.schools.shared import (
    assembled_rollup_path,
    processed_cross_section_path,
    processed_panel_path,
)
from src.regions.florida.sources.shocks.shared import school_shocks_panel_path
from src.regions.florida.sources.traffic.shared import school_aadt_panel_path

TREATMENT_DEFINITIONS = ("point", "same_route", "same_side")

# How many years apart an assessment year and the nearest FGDL release year
# may be before the traffic match is dropped (NA) rather than used as a
# stale proxy -- deliberately smaller than the 2012-2015 gap (up to 5 years
# between releases) so an assessment year deep inside that hole is flagged
# untraceable rather than silently matched to a release several years away.
MAX_TRAFFIC_YEAR_GAP = 2

# Raw `school_aadt_panel.parquet` column -> panel column. `aadt_local` (the
# current-snapshot local-intensity-scaled estimate, see
# `traffic/assemble.py`'s module docstring) is optional -- older
# `school_aadt_panel.parquet` files, or synthetic test fixtures, may not
# carry it, so `attach_traffic` only selects/renames whichever of these are
# actually present.
TRAFFIC_RENAME = {
    "roadway_id": "traffic_roadway_id",
    "release_year": "traffic_release_year",
    "aadt": "traffic_aadt",
    "dist_m": "traffic_match_dist_m",
    "aadt_local": "traffic_aadt_local",
}
TRAFFIC_COLUMNS = list(TRAFFIC_RENAME.values())

# Static (msid-level, not year-varying) identity/filter fields from the MSID
# spine -- covariates.md calls for restricting the analysis sample to
# regular schools with a stable grade span; that decision belongs in the
# analysis layer, but the fields it needs have to be here to make it.
# `name`/`district_name` are renamed on the way in (below) since `assessments`
# already carries its own FLDOE-native `school_name`/`district_name` --
# without the rename these collide and pandas silently suffixes both to
# `_x`/`_y`, losing which one came from which source.
STATIC_SCHOOL_COLUMNS = [
    "msid", "name", "district_name", "school_type", "is_regular", "is_alternative",
    "is_charter", "is_magnet", "is_virtual", "grade_low", "grade_high", "serves_tested_grades",
]
STATIC_SCHOOL_RENAMES = {"name": "msid_school_name", "district_name": "msid_district_name"}

TREATMENT_COLUMNS = [
    "msid", "nearest_fdot_dist_m", "nearest_fdot_gcid",
    "n_walls_100m", "n_walls_200m", "n_walls_300m", "n_walls_500m", "n_walls_1000m",
    "wall_len_500m", "ever_near_wall_500m", "ever_near_wall_1000m",
] + [
    f"{stat}_{definition}"
    for definition in TREATMENT_DEFINITIONS
    for stat in ("first_treat_year", "ever_treated", "timing_unknown")
]


def load_assessments(root: Path | None = None) -> pd.DataFrame:
    """``assessments.parquet``, indexed on ``(msid, grade, subject, year)`` —
    reset to plain columns for joining."""
    path = processed_assessments_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data assessments preprocess` first.")
    return pd.read_parquet(path).reset_index()


def load_school_year_panel(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_panel_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    return gpd.read_parquet(path)


def load_cross_section(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    return gpd.read_parquet(path)


def load_treatment_rollup(root: Path | None = None) -> pd.DataFrame:
    path = assembled_rollup_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools assemble` first.")
    return pd.read_parquet(path)


def load_school_aadt_panel(root: Path | None = None) -> pd.DataFrame:
    path = school_aadt_panel_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data traffic assemble` first.")
    return pd.read_parquet(path)


def load_school_road_projects(root: Path | None = None) -> pd.DataFrame:
    path = school_road_projects_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data road-projects assemble` first.")
    return pd.read_parquet(path)


def load_shocks_county_year_panel(root: Path | None = None) -> pd.DataFrame:
    path = school_shocks_panel_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data shocks assemble` first.")
    return pd.read_parquet(path)


def attach_traffic(
    panel: pd.DataFrame,
    school_aadt_panel: pd.DataFrame,
    max_year_gap: int = MAX_TRAFFIC_YEAR_GAP,
) -> pd.DataFrame:
    """Left-join each ``(msid, year)`` row onto the nearest available FGDL
    release year for that school's matched roadway, within ``max_year_gap``
    years (see module docstring for why an exact-year match doesn't exist).
    A school with no traffic match at all (unmatched to a roadway, or every
    release too far from this assessment year) keeps its row with ``NA``
    traffic columns, same convention as every other join in this module."""
    present_source_columns = [c for c in TRAFFIC_RENAME if c in school_aadt_panel.columns]
    traffic = school_aadt_panel.dropna(subset=["release_year"])[["msid", *present_source_columns]].copy()
    traffic["release_year"] = traffic["release_year"].astype("int64")
    # `merge_asof`'s `by=` requires matching dtypes on both sides; `panel`'s
    # `msid` can be an Arrow-backed string dtype (from a parquet read) while
    # a freshly-built/empty traffic frame may be plain `object` -- cast both
    # to plain `str` for the merge key only, not the columns we return.
    traffic["_msid_key"] = traffic["msid"].astype(str)
    # `merge_asof` requires the `on` column sorted GLOBALLY (not just within
    # each `by` group) -- sorting by [msid, year] instead silently breaks
    # this the moment there's more than one msid, since `year` then resets
    # at each group boundary.
    traffic = traffic.drop(columns="msid").sort_values("release_year").reset_index(drop=True)

    out = panel.reset_index(drop=True)
    out["_traffic_row_order"] = out.index
    out["_msid_key"] = out["msid"].astype(str)
    left_sorted = out.sort_values("year").reset_index(drop=True)

    joined = pd.merge_asof(
        left_sorted,
        traffic,
        left_on="year",
        right_on="release_year",
        by="_msid_key",
        direction="nearest",
        tolerance=max_year_gap,
    )
    joined = joined.rename(columns=TRAFFIC_RENAME).drop(columns="_msid_key")
    return joined.sort_values("_traffic_row_order").drop(columns="_traffic_row_order").reset_index(drop=True)


ROAD_PROJECTS_COLUMNS = ["n_road_projects_active", "road_project_is_wall", "road_project_is_widening"]


def _project_active_years(school_road_projects: pd.DataFrame) -> pd.DataFrame:
    """One row per ``(school_road_projects row, calendar year that project
    spans)``. A Work-Program row's single ``fiscal_year`` becomes a
    one-year span; an Active-Construction row's ``[start_date, end_date]``
    becomes every calendar year from ``start_date.year`` to
    ``end_date.year`` inclusive (real data: median 2-year span, max 9 — see
    module docstring). A row with neither a usable ``fiscal_year`` nor any
    usable date (191 of 40,729 in the real run — some Active-Construction
    contracts log only one of start/end and it happens to also be NaT), or
    with ``end_date`` earlier than ``start_date`` (not observed in the real
    run, but ``EstEndDate`` is FDOT's own documented estimate and can be
    revised, so a reversed range is a plausible future data-quality issue,
    not just a hypothetical one), is dropped from this year-level join, not
    from ``school_road_projects.parquet`` itself."""
    start_year = school_road_projects["start_date"].dt.year
    end_year = school_road_projects["end_date"].dt.year
    year_lo = school_road_projects["fiscal_year"].where(
        school_road_projects["fiscal_year"].notna(), start_year.combine_first(end_year)
    )
    year_hi = school_road_projects["fiscal_year"].where(
        school_road_projects["fiscal_year"].notna(), end_year.combine_first(start_year)
    )

    out = school_road_projects.assign(year_lo=year_lo, year_hi=year_hi).dropna(subset=["year_lo", "year_hi"])
    out = out[out["year_lo"] <= out["year_hi"]]
    out["year_lo"] = out["year_lo"].astype(int)
    out["year_hi"] = out["year_hi"].astype(int)
    out["year"] = [list(range(lo, hi + 1)) for lo, hi in zip(out["year_lo"], out["year_hi"])]
    exploded = out.explode("year", ignore_index=True)
    exploded["year"] = exploded["year"].astype(int)
    return exploded


def build_road_projects_year_panel(school_road_projects: pd.DataFrame) -> pd.DataFrame:
    """Collapse ``school_road_projects.parquet`` to one row per
    ``(msid, year)`` with a project active that year: a count plus
    ``is_wall_project``/``is_widening_project`` keyword-flag summaries (the
    widening regex is the same one ``road_projects/assemble.py`` uses for its
    own per-school rollup, imported rather than duplicated)."""
    columns = ["msid", "year", *ROAD_PROJECTS_COLUMNS]
    if school_road_projects.empty:
        return pd.DataFrame(columns=columns)

    exploded = _project_active_years(school_road_projects)
    if exploded.empty:
        return pd.DataFrame(columns=columns)

    is_widening = tag_widening_keyword(exploded["description"])
    grouped = (
        exploded.assign(is_widening_project=is_widening)
        .groupby(["msid", "year"])
        .agg(
            n_road_projects_active=("roadway_id", "size"),
            road_project_is_wall=("is_wall_project", "any"),
            road_project_is_widening=("is_widening_project", "any"),
        )
        .reset_index()
    )
    return grouped[columns]


def attach_road_projects(panel: pd.DataFrame, school_road_projects: pd.DataFrame) -> pd.DataFrame:
    """Left-join each ``(msid, year)`` row onto the road-projects year panel
    (see :func:`build_road_projects_year_panel`) by exact ``(msid, year)`` —
    an interval-overlap join resolved ahead of time by exploding to
    calendar years, not a nearest-value match like :func:`attach_traffic`.
    A school-year with no active project gets ``n_road_projects_active=0``
    and the flag columns ``False`` — a real "no road work logged" value, not
    a missing one."""
    year_panel = build_road_projects_year_panel(school_road_projects)
    out = panel.merge(year_panel, on=["msid", "year"], how="left")
    out["n_road_projects_active"] = out["n_road_projects_active"].fillna(0).astype(int)
    out["road_project_is_wall"] = out["road_project_is_wall"].fillna(False).astype(bool)
    out["road_project_is_widening"] = out["road_project_is_widening"].fillna(False).astype(bool)
    return out


SHOCKS_RENAME = {
    "county_name": "district_name",
    "assessment_year": "year",
    "n_declarations": "shock_n_declarations",
    "n_hurricane_declarations": "shock_n_hurricane_declarations",
    "any_major_disaster": "shock_any_major_disaster",
}


def attach_shocks(panel: pd.DataFrame, shocks_county_year_panel: pd.DataFrame) -> pd.DataFrame:
    """Left-join each row onto the county-year shocks rollup by exact
    ``(district_name, year)`` — the simplest join in this module:
    ``assessment_year`` (derived in ``shocks/preprocess.py``) already
    resolves each declaration to one exact spring, and ``assessments``' own
    ``district_name`` already upper-cases to the same county-name convention
    ``shocks`` normalizes to, so no ``merge_asof`` tolerance or interval
    explosion is needed. A school-year in a county with no declaration (or
    in a special, non-county FLDOE district) gets ``shock_n_declarations=0``
    / ``shock_any_major_disaster=False`` — a real "no shock" value, not
    ``NA``."""
    renamed = shocks_county_year_panel.rename(columns=SHOCKS_RENAME)
    out = panel.merge(renamed, on=["district_name", "year"], how="left")
    out["shock_n_declarations"] = out["shock_n_declarations"].fillna(0).astype(int)
    out["shock_n_hurricane_declarations"] = out["shock_n_hurricane_declarations"].fillna(0).astype(int)
    out["shock_any_major_disaster"] = out["shock_any_major_disaster"].fillna(False).astype(bool)
    return out


def build_event_study_panel(
    assessments: pd.DataFrame,
    school_year_panel: gpd.GeoDataFrame,
    cross_section: gpd.GeoDataFrame,
    rollup: pd.DataFrame,
    school_aadt_panel: pd.DataFrame,
    school_road_projects: pd.DataFrame,
    shocks_county_year_panel: pd.DataFrame,
    max_traffic_year_gap: int = MAX_TRAFFIC_YEAR_GAP,
) -> gpd.GeoDataFrame:
    """One row per ``(msid, grade, subject, year)`` — the ``assessments``
    grain — with Cluster-A covariates, static school identity/filter fields,
    all three treatment-timing definitions, the nearest-year traffic (AADT)
    match, the road-projects year-interval match, and the shocks
    county-year match joined on."""
    panel = assessments.loc[~assessments["is_state_total"].fillna(False)].copy()

    panel = panel.merge(
        school_year_panel.drop(columns="geometry"), on=["msid", "year"], how="left", validate="m:1"
    )
    static_cols = cross_section[STATIC_SCHOOL_COLUMNS + ["geometry"]].rename(columns=STATIC_SCHOOL_RENAMES)
    panel = panel.merge(static_cols, on="msid", how="left", validate="m:1")
    panel = panel.merge(rollup[TREATMENT_COLUMNS], on="msid", how="left", validate="m:1")
    panel = attach_traffic(panel, school_aadt_panel, max_traffic_year_gap)
    panel = attach_road_projects(panel, school_road_projects)
    panel = attach_shocks(panel, shocks_county_year_panel)

    for definition in TREATMENT_DEFINITIONS:
        # No wall nearby -> genuinely never treated / no unknown-timing wall,
        # not a missing value: the rollup join leaves these NA only because
        # the school had no row in `rollup` to begin with.
        panel[f"ever_treated_{definition}"] = panel[f"ever_treated_{definition}"].fillna(False)
        panel[f"timing_unknown_{definition}"] = panel[f"timing_unknown_{definition}"].fillna(False)
        panel[f"event_time_{definition}"] = panel["year"] - panel[f"first_treat_year_{definition}"]

    return gpd.GeoDataFrame(panel, geometry="geometry", crs=cross_section.crs)


def save_panel(panel: gpd.GeoDataFrame, metadata: dict[str, object], root: Path | None = None) -> dict[str, str]:
    panel_path = assembled_panel_path(root)
    meta_path = assembled_metadata_path(root)
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(panel_path, index=False)
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"panel": str(panel_path), "metadata": str(meta_path)}


def run_panel_assemble(root: Path | None = None) -> dict[str, object]:
    """Load the assessments + schools + traffic + road-projects + shocks
    artifacts, join, validate, and persist."""
    assessments = load_assessments(root)
    school_year_panel = load_school_year_panel(root)
    cross_section = load_cross_section(root)
    rollup = load_treatment_rollup(root)
    school_aadt_panel = load_school_aadt_panel(root)
    school_road_projects = load_school_road_projects(root)
    shocks_county_year_panel = load_shocks_county_year_panel(root)

    panel = build_event_study_panel(
        assessments,
        school_year_panel,
        cross_section,
        rollup,
        school_aadt_panel,
        school_road_projects,
        shocks_county_year_panel,
    )

    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/panel/assemble.py",
        "grain": "msid x grade x subject x year",
        "rows": int(len(panel)),
        "distinct_schools": int(panel["msid"].nunique()),
        "year_range": [int(panel["year"].min()), int(panel["year"].max())],
        "treatment_definitions": {
            definition: {
                "ever_treated_schools": int(
                    panel.loc[panel[f"ever_treated_{definition}"], "msid"].nunique()
                ),
                "ever_treated_school_year_subject_grade_rows": int(panel[f"ever_treated_{definition}"].sum()),
            }
            for definition in TREATMENT_DEFINITIONS
        },
        "rows_missing_enrollment_covariate": int(panel["enrollment"].isna().sum()),
        "rows_missing_geometry": int(panel.geometry.isna().sum()),
        "max_traffic_year_gap": MAX_TRAFFIC_YEAR_GAP,
        "rows_with_traffic_match": int(panel["traffic_aadt"].notna().sum()),
        "rows_missing_traffic_match": int(panel["traffic_aadt"].isna().sum()),
        "rows_with_traffic_aadt_local": (
            int(panel["traffic_aadt_local"].notna().sum()) if "traffic_aadt_local" in panel.columns else 0
        ),
        "rows_with_road_project_active": int((panel["n_road_projects_active"] > 0).sum()),
        "rows_with_road_project_wall_keyword": int(panel["road_project_is_wall"].sum()),
        "rows_with_road_project_widening_keyword": int(panel["road_project_is_widening"].sum()),
        "rows_with_a_shock_declaration": int((panel["shock_n_declarations"] > 0).sum()),
        "rows_with_a_hurricane_shock": int((panel["shock_n_hurricane_declarations"] > 0).sum()),
        "rows_with_a_major_disaster_shock": int(panel["shock_any_major_disaster"].sum()),
    }
    saved = save_panel(panel, report, root)
    report["saved"] = saved
    return report
