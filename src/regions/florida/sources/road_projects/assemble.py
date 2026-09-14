"""Stage 3 for the Florida `road_projects` source: match schools to a
roadway + milepost, then attach every nearby project from
`road_projects.parquet`.

`REQUIRES` `schools preprocess` (`school_cross_section.parquet`),
`road_network preprocess` (`road_network.parquet`), and this source's own
`fetch` + `preprocess` (`road_projects.parquet`).

**Milepost, not just `roadway_id`, is the point of this module** —
`traffic/assemble.py`'s `match_schools_to_roadway` already gives a school its
nearest `roadway_id`, but `road_projects` rows carry `[begin_post, end_post]`
ranges that can be a short stretch of a `roadway_id` spanning many
kilometres (`road_network`'s Open Question 7); matching by `roadway_id`
alone would attach every project ever logged anywhere on that roadway to
every school near it, including ones many miles away. So this module
recomputes its own school<->roadway match (reusing
`road_network/linear_ref.py`'s `arterial_subset`/`nearest_road`, same as
`traffic/assemble.py`) and additionally projects each school onto its
matched segment for a `milepost` (`linear_ref.milepost_and_side`, algorithm
4's `same_segment` linear referencing — already validated code, not new).

**The milepost reference frames were checked, not assumed, before relying on
this join**: for the 115,375 `road_projects` rows whose `roadway_id` exists
in `road_network` (97.8% of all rows), 99.96% have `[begin_post, end_post]`
falling within that roadway's own milepost extent (±0.25 mi tolerance) —
confirms FDOT really does use one shared linear-referencing system across
`rciroads` and the Work Program / Site Manager extracts (as the README's
source description implied but hadn't independently verified), so a direct
milepost-overlap join is sound. `MILEPOST_TOLERANCE_MI` uses that same
0.25 mi (~400 m) buffer.

Three outputs, kept at their natural grain (mirrors `traffic/assemble.py`'s
"grain over pre-aggregation" choice, and `schools/assemble.py`'s
pair-then-rollup pattern):

* **`school_road_match.parquet`** — one row per placed `msid`: `roadway_id`,
  `dist_m`, `milepost`. `NA` for a school beyond `MAX_MATCH_DIST_M` of any
  arterial road, same convention as `traffic/assemble.py`.
* **`school_road_projects.parquet`** — one row per `(msid, road_projects
  row)` pair where the school's `milepost` falls within that project's
  `[begin_post - tol, end_post + tol]` on the matched `roadway_id`. A school
  with no nearby project keeps no rows here (unlike the `NA`-row convention
  elsewhere) — see `school_road_projects_summary.parquet` for a per-school
  row that always exists.
* **`school_road_projects_summary.parquet`** — one row per placed `msid`:
  project counts, the `is_wall_project`/`is_widening_project` keyword-flag
  counts, and the earliest/latest `fiscal_year`/`start_date` among nearby
  projects. A standalone per-school inspection/QA artifact — `panel`'s own
  event-study join (below) works from `school_road_projects.parquet`
  directly, not from this file.

`panel/assemble.py`'s `attach_road_projects` joins `school_road_projects.parquet`
into `event_study_panel.parquet` — a project's timing is an interval
(`fiscal_year` or `[start_date, end_date]`), not a single nearest-year value
like `traffic`'s AADT, so that join first explodes each pair to one row per
calendar year the project spans, then does a plain exact `(msid, year)` left
join rather than `traffic`'s `merge_asof`; see that module's docstring for
the real numbers.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.florida.sources.road_network.linear_ref import arterial_subset, milepost_and_side, nearest_road
from src.regions.florida.sources.road_network.shared import processed_road_network_path
from src.regions.florida.sources.road_projects.shared import (
    processed_projects_path,
    school_road_match_path,
    school_road_projects_path,
    school_road_projects_summary_path,
    tag_widening_keyword,
)
from src.regions.florida.sources.schools.shared import processed_cross_section_path

MAX_MATCH_DIST_M = 1000.0
MILEPOST_TOLERANCE_MI = 0.25


def load_placed_schools(root: Path | None = None) -> gpd.GeoDataFrame:
    """Same filter `traffic/assemble.py`/`schools/assemble.py` apply: only
    schools that resolved a real coordinate."""
    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    xs = gpd.read_parquet(path)
    return xs[xs["geom_source"] != "none"].reset_index(drop=True)


def load_road_network(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_road_network_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data road-network preprocess` first.")
    return gpd.read_parquet(path)


def load_road_projects(root: Path | None = None) -> pd.DataFrame:
    path = processed_projects_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data road-projects preprocess` first.")
    return pd.read_parquet(path)


def match_schools_to_roadway(
    placed: gpd.GeoDataFrame,
    road_network: gpd.GeoDataFrame,
    max_dist: float = MAX_MATCH_DIST_M,
) -> pd.DataFrame:
    """Nearest arterial `roadway_id` + `milepost` for every placed school.
    `milepost` comes from projecting the school onto its matched segment's
    centerline via `linear_ref.milepost_and_side` (the `same_segment`
    linear-referencing algorithm `road_network` already validated), using
    that segment's own `begin_post`/`end_post` -- not the whole roadway's
    extent, since a `roadway_id` can be made of many segments."""
    major = arterial_subset(road_network)
    sj = nearest_road(placed[["geometry"]], major)
    idx = sj["index_right"].to_numpy()

    mileposts = [
        milepost_and_side(point, line, begin_post, end_post)[0]
        for point, line, begin_post, end_post in zip(
            sj["point_geometry"],
            major["geometry"].to_numpy()[idx],
            major["begin_post"].to_numpy()[idx],
            major["end_post"].to_numpy()[idx],
        )
    ]

    out = pd.DataFrame(
        {
            "msid": placed["msid"].to_numpy(),
            "roadway_id": major["roadway_id"].to_numpy()[idx],
            "dist_m": sj["dist_m"].to_numpy(),
            "milepost": mileposts,
        }
    )
    too_far = out["dist_m"] > max_dist
    out.loc[too_far, ["roadway_id", "milepost"]] = pd.NA
    return out


def match_school_projects(
    school_road_match: pd.DataFrame,
    road_projects: pd.DataFrame,
    tolerance_mi: float = MILEPOST_TOLERANCE_MI,
) -> pd.DataFrame:
    """`(msid, road_projects row)` pairs: same `roadway_id`, and the
    school's `milepost` within `[begin_post - tolerance, end_post +
    tolerance]`. A school with no roadway match, or no project overlapping
    its milepost, contributes no rows here (see
    `school_road_projects_summary.parquet` for a per-school row that always
    exists)."""
    matched = school_road_match.dropna(subset=["roadway_id", "milepost"]).copy()
    matched["roadway_id"] = matched["roadway_id"].astype(str)

    projects = road_projects.dropna(subset=["roadway_id", "begin_post", "end_post"]).copy()
    projects["roadway_id"] = projects["roadway_id"].astype(str)
    projects = projects.reset_index(drop=True).rename_axis("project_row").reset_index()

    pairs = matched.merge(projects, on="roadway_id", how="inner", suffixes=("", "_project"))
    within = (pairs["milepost"] >= pairs["begin_post"] - tolerance_mi) & (
        pairs["milepost"] <= pairs["end_post"] + tolerance_mi
    )
    out = pairs[within].drop(columns=["project_row"]).reset_index(drop=True)
    return out


def build_summary(
    placed: gpd.GeoDataFrame, school_road_match: pd.DataFrame, school_road_projects: pd.DataFrame
) -> pd.DataFrame:
    """One row per placed `msid` -- always present, unlike
    `school_road_projects.parquet` -- with nearby-project counts, keyword
    flags, and the earliest/latest timing found."""
    base = pd.DataFrame({"msid": placed["msid"].to_numpy()}).merge(
        school_road_match[["msid", "roadway_id", "dist_m"]], on="msid", how="left"
    )

    if school_road_projects.empty:
        base["n_projects_nearby"] = 0
        base["n_wall_projects_nearby"] = 0
        base["n_widening_projects_nearby"] = 0
        for col in ("fiscal_year_min", "fiscal_year_max", "start_date_min", "start_date_max"):
            base[col] = pd.NA
        return base

    is_widening = tag_widening_keyword(school_road_projects["description"])
    scored = school_road_projects.assign(is_widening_project=is_widening)

    grouped = scored.groupby("msid").agg(
        n_projects_nearby=("roadway_id", "size"),
        n_wall_projects_nearby=("is_wall_project", "sum"),
        n_widening_projects_nearby=("is_widening_project", "sum"),
        fiscal_year_min=("fiscal_year", "min"),
        fiscal_year_max=("fiscal_year", "max"),
        start_date_min=("start_date", "min"),
        start_date_max=("start_date", "max"),
    )

    out = base.merge(grouped, on="msid", how="left")
    out["n_projects_nearby"] = out["n_projects_nearby"].fillna(0).astype(int)
    out["n_wall_projects_nearby"] = out["n_wall_projects_nearby"].fillna(0).astype(int)
    out["n_widening_projects_nearby"] = out["n_widening_projects_nearby"].fillna(0).astype(int)
    return out


def save_assembled(
    school_road_match: pd.DataFrame,
    school_road_projects: pd.DataFrame,
    summary: pd.DataFrame,
    root: Path | None = None,
) -> dict[str, str]:
    paths = {
        "school_road_match": school_road_match_path(root),
        "school_road_projects": school_road_projects_path(root),
        "school_road_projects_summary": school_road_projects_summary_path(root),
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    school_road_match.to_parquet(paths["school_road_match"], index=False)
    school_road_projects.to_parquet(paths["school_road_projects"], index=False)
    summary.to_parquet(paths["school_road_projects_summary"], index=False)
    return {name: str(path) for name, path in paths.items()}


def run_road_projects_assemble(
    root: Path | None = None,
    max_dist: float = MAX_MATCH_DIST_M,
    tolerance_mi: float = MILEPOST_TOLERANCE_MI,
) -> dict[str, object]:
    placed = load_placed_schools(root)
    road_network = load_road_network(root)
    road_projects = load_road_projects(root)

    school_road_match = match_schools_to_roadway(placed, road_network, max_dist)
    school_road_projects = match_school_projects(school_road_match, road_projects, tolerance_mi)
    summary = build_summary(placed, school_road_match, school_road_projects)
    saved = save_assembled(school_road_match, school_road_projects, summary, root)

    matched = school_road_match["roadway_id"].notna()
    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/road_projects/assemble.py",
        "max_dist_m": max_dist,
        "milepost_tolerance_mi": tolerance_mi,
        "schools_placed": int(len(placed)),
        "schools_matched": int(matched.sum()),
        "schools_unmatched": int((~matched).sum()),
        "school_road_projects_pairs": int(len(school_road_projects)),
        "schools_with_a_nearby_project": int((summary["n_projects_nearby"] > 0).sum()),
        "schools_with_a_nearby_wall_project": int((summary["n_wall_projects_nearby"] > 0).sum()),
        "saved": saved,
    }
