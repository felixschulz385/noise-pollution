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

TREATMENT_DEFINITIONS = ("point", "same_route", "same_side")

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


def build_event_study_panel(
    assessments: pd.DataFrame,
    school_year_panel: gpd.GeoDataFrame,
    cross_section: gpd.GeoDataFrame,
    rollup: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """One row per ``(msid, grade, subject, year)`` — the ``assessments``
    grain — with Cluster-A covariates, static school identity/filter fields,
    and all three treatment-timing definitions joined on."""
    panel = assessments.loc[~assessments["is_state_total"].fillna(False)].copy()

    panel = panel.merge(
        school_year_panel.drop(columns="geometry"), on=["msid", "year"], how="left", validate="m:1"
    )
    static_cols = cross_section[STATIC_SCHOOL_COLUMNS + ["geometry"]].rename(columns=STATIC_SCHOOL_RENAMES)
    panel = panel.merge(static_cols, on="msid", how="left", validate="m:1")
    panel = panel.merge(rollup[TREATMENT_COLUMNS], on="msid", how="left", validate="m:1")

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
    """Load the assessments + schools artifacts, join, validate, and
    persist."""
    assessments = load_assessments(root)
    school_year_panel = load_school_year_panel(root)
    cross_section = load_cross_section(root)
    rollup = load_treatment_rollup(root)

    panel = build_event_study_panel(assessments, school_year_panel, cross_section, rollup)

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
    }
    saved = save_panel(panel, report, root)
    report["saved"] = saved
    return report
