"""Match schools to their nearest `Trafik` segment and attach that
segment's **full historical `[valid_from, valid_to)` window history** --
Covariate Cluster C (`docs/data/sweden/covariates.md`), the core
traffic-growth confounder for the barrier event study.

`REQUIRES` `schools preprocess` (`schools.geojson`) and this source's own
`preprocess` (`traffic.parquet`, now unioned across every `Trafik` order
under `raw/`) to already exist.

**Two-step design, split because they're genuinely different concerns**:
1. `match_schools_to_element` -- a SPATIAL nearest-neighbour match (which
   segment is physically closest to this school), using only each
   element's most-current row (preferring `valid_to == 99991231`, else the
   latest `valid_from`) so `sjoin_nearest` sees one clean geometry per
   element rather than several historical duplicates of the same
   location. Static, not year-dependent: one row per school
   (`skolenhetskod`, `element_id`, `dist_m`).
2. `build_school_traffic_history` -- a plain attribute join of that
   matched `element_id` against `traffic.parquet`'s FULL historical
   window table (every `[valid_from, valid_to)` row for that element, not
   just the current one). Output is one row per **(school, historical
   window)** -- a school with 3 recovered historical windows for its
   matched segment gets 3 rows, not 1.

This got corrected 2026-09-16 from an earlier, wrong v1 that only ever
kept the current-vintage row -- see `preprocess.py`'s module docstring and
`docs/data/sweden/traffic/README.md`'s "Correction" section for the full
story (a same-session test wrongly concluded `Betraktelsedatum` doesn't
give real historical data; a real user-provided example proved it does).
`panel/assemble.py::attach_traffic` is responsible for picking, per
outcome row, whichever of a school's historical windows actually covers
that row's `year` (an interval-overlap join, not a flat broadcast) --
this module just makes every real window available to join against.

Reuses `src/core/barrier_geometry/linear_ref.py::nearest_segment` -- the same nearest-segment
spatial-index join `schools/assemble.py`'s algorithms 4/5 use against
`road_network`/`network`, just pointed at the `traffic` layer directly."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.core.barrier_geometry.linear_ref import nearest_segment
from src.regions.sweden.sources.schools.assemble import load_geocoded_schools
from src.regions.sweden.sources.traffic.shared import assembled_school_traffic_path, processed_traffic_path

METRIC_CRS = "EPSG:3006"  # SWEREF99 TM
MAX_MATCH_DIST_M = 1000.0
IS_CURRENT_SENTINEL = 99991231

TRAFFIC_COLUMNS = [
    "valid_from",
    "valid_to",
    "direction",
    "role",
    "adt_samtliga_fordon",
    "adt_tunga_fordon",
    "adt_axelpar",
    "adt_latta_fordon_06_18",
    "adt_latta_fordon_18_22",
    "adt_latta_fordon_22_06",
    "adt_medeltunga_fordon_06_18",
    "adt_medeltunga_fordon_18_22",
    "adt_medeltunga_fordon_22_06",
    "adt_tunga_fordon_06_18",
    "adt_tunga_fordon_18_22",
    "adt_tunga_fordon_22_06",
    "matarsperiod",
    "matmetod",
    "osakerhet_samtliga_fordon",
    "osakerhet_tunga_fordon",
    "osakerhet_axelpar",
]


def load_processed_traffic(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_traffic_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data traffic preprocess` first.")
    return gpd.read_parquet(path)


def most_current_rows(traffic_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per `element_id` -- its currently-open window
    (`valid_to == 99991231`) if it has one, else its most recent
    `valid_from`. Used only for the spatial match (geometry shouldn't
    meaningfully differ across one element's historical windows, but
    `sjoin_nearest` needs exactly one candidate row per element, not
    several)."""
    is_current = traffic_gdf["valid_to"].eq(IS_CURRENT_SENTINEL)
    current = traffic_gdf[is_current]
    still_missing = set(traffic_gdf["element_id"]) - set(current["element_id"])
    fallback = (
        traffic_gdf[traffic_gdf["element_id"].isin(still_missing)]
        .sort_values("valid_from")
        .drop_duplicates(subset="element_id", keep="last")
    )
    return pd.concat([current, fallback], ignore_index=True)


def match_schools_to_element(
    schools_gdf: gpd.GeoDataFrame,
    traffic_gdf: gpd.GeoDataFrame,
    *,
    max_dist: float = MAX_MATCH_DIST_M,
    metric_crs: str = METRIC_CRS,
) -> pd.DataFrame:
    """One row per school: its nearest `Trafik` element's id + `dist_m`.
    Static (not year-dependent) -- a school beyond `max_dist` of any
    segment gets `NA` (kept, not dropped), same "no match is a real
    value" convention used throughout this pipeline."""
    schools_m = schools_gdf.to_crs(metric_crs)
    candidates = gpd.GeoDataFrame(most_current_rows(traffic_gdf), geometry="geometry", crs=traffic_gdf.crs).to_crs(
        metric_crs
    )

    joined = nearest_segment(schools_m[["geometry"]], candidates)
    joined = joined.reset_index(drop=True)
    joined["skolenhetskod"] = schools_m["skolenhetskod"].to_numpy()

    out = joined[["skolenhetskod", "dist_m", "element_id"]].copy()
    beyond_max = out["dist_m"] > max_dist
    out.loc[beyond_max, ["dist_m", "element_id"]] = pd.NA
    return out


def build_school_traffic_history(school_element_match: pd.DataFrame, traffic_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Broadcast each matched element's FULL historical window table onto
    its school -- one output row per (school, historical window). A
    school with no element match keeps exactly one row with `NA` traffic
    columns; a matched school gets one row per real window its element
    has (e.g. 3 rows if 3 distinct `[valid_from, valid_to)` periods were
    recovered across however many `Trafik` orders `preprocess` unioned)."""
    matched = school_element_match.dropna(subset=["element_id"])
    unmatched = school_element_match[school_element_match["element_id"].isna()]

    history_cols = ["element_id", *TRAFFIC_COLUMNS]
    joined = matched.merge(pd.DataFrame(traffic_gdf)[history_cols], on="element_id", how="left")

    if not unmatched.empty:
        for col in TRAFFIC_COLUMNS:
            unmatched = unmatched.assign(**{col: pd.NA})
        joined = pd.concat([joined, unmatched[["skolenhetskod", "dist_m", "element_id", *TRAFFIC_COLUMNS]]])

    return joined.reset_index(drop=True)


def save_school_traffic(school_traffic: pd.DataFrame, root: Path | None = None) -> str:
    path = assembled_school_traffic_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    school_traffic.to_parquet(path, index=False)
    return str(path)


def run_traffic_assemble(*, max_dist: float = MAX_MATCH_DIST_M, root: Path | None = None) -> dict[str, object]:
    schools_gdf = load_geocoded_schools(root)
    traffic_gdf = load_processed_traffic(root)

    school_element_match = match_schools_to_element(schools_gdf, traffic_gdf, max_dist=max_dist)
    school_traffic = build_school_traffic_history(school_element_match, traffic_gdf)
    saved_path = save_school_traffic(school_traffic, root)

    matched_schools = school_element_match["element_id"].notna()
    windows_per_school = school_traffic.dropna(subset=["element_id"]).groupby("skolenhetskod").size()
    return {
        "n_schools": int(len(school_element_match)),
        "n_matched": int(matched_schools.sum()),
        "n_unmatched_beyond_max_dist": int((~matched_schools).sum()),
        "median_dist_m": (
            float(school_element_match.loc[matched_schools, "dist_m"].median()) if matched_schools.any() else None
        ),
        "n_history_rows": int(len(school_traffic)),
        "median_windows_per_matched_school": float(windows_per_school.median()) if len(windows_per_school) else None,
        "saved": saved_path,
    }
