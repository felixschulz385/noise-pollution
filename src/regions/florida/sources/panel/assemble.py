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
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.florida.sources.assessments.shared import processed_assessments_path
from src.regions.florida.sources.panel.shared import assembled_metadata_path, assembled_panel_path
from src.regions.florida.sources.schools.shared import (
    assembled_rollup_path,
    processed_cross_section_path,
    processed_panel_path,
)
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


def build_event_study_panel(
    assessments: pd.DataFrame,
    school_year_panel: gpd.GeoDataFrame,
    cross_section: gpd.GeoDataFrame,
    rollup: pd.DataFrame,
    school_aadt_panel: pd.DataFrame,
    max_traffic_year_gap: int = MAX_TRAFFIC_YEAR_GAP,
) -> gpd.GeoDataFrame:
    """One row per ``(msid, grade, subject, year)`` — the ``assessments``
    grain — with Cluster-A covariates, static school identity/filter fields,
    all three treatment-timing definitions, and the nearest-year traffic
    (AADT) match joined on."""
    panel = assessments.loc[~assessments["is_state_total"].fillna(False)].copy()

    panel = panel.merge(
        school_year_panel.drop(columns="geometry"), on=["msid", "year"], how="left", validate="m:1"
    )
    static_cols = cross_section[STATIC_SCHOOL_COLUMNS + ["geometry"]].rename(columns=STATIC_SCHOOL_RENAMES)
    panel = panel.merge(static_cols, on="msid", how="left", validate="m:1")
    panel = panel.merge(rollup[TREATMENT_COLUMNS], on="msid", how="left", validate="m:1")
    panel = attach_traffic(panel, school_aadt_panel, max_traffic_year_gap)

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
    """Load the assessments + schools + traffic artifacts, join, validate,
    and persist."""
    assessments = load_assessments(root)
    school_year_panel = load_school_year_panel(root)
    cross_section = load_cross_section(root)
    rollup = load_treatment_rollup(root)
    school_aadt_panel = load_school_aadt_panel(root)

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup, school_aadt_panel)

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
    }
    saved = save_panel(panel, report, root)
    report["saved"] = saved
    return report
