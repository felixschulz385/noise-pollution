"""Stage 3 for the Florida `traffic` source: match schools to a roadway and
attach that roadway's AADT panel.

`REQUIRES` `schools preprocess` (`school_cross_section.parquet`),
`road_network preprocess` (`road_network.parquet`), and this source's own
`fetch` + `preprocess` (`aadt_panel.parquet`) to already exist.

Reuses `road_network/linear_ref.py`'s `arterial_subset`/`nearest_road` — the
same nearest-road matching `schools/assemble.py`'s `match_barriers_road`
already uses for walls — pointed at school points instead. Not a new
algorithm, just the existing one applied to a different set of points (this
is algorithm 3, `road_gated`, from the schools rigour ladder, but on the
school side of the match rather than the wall side; `schools/assemble.py`
never needed to persist that half on its own).

Two outputs, kept at their natural grain rather than one exploded table:

* **`school_road_match.parquet`** — one row per placed `msid`: nearest
  arterial `roadway_id` + `dist_m`, plus the **local-intensity scaling**
  columns described below. `roadway_id` is `NA` for a school beyond
  `MAX_MATCH_DIST_M` of any arterial road (kept, not dropped — a school with
  no traffic covariate should still show up as `NA`, not vanish).
* **`school_aadt_panel.parquet`** — `msid x release_year`: every FGDL
  release year's AADT for that school's matched roadway (a left join of
  `school_road_match` onto `aadt_panel.parquet` by `roadway_id`), plus
  `aadt_local` (see below). Left at `release_year` grain deliberately,
  **not** exploded to assessment years — matching a school-year in
  `assessments.parquet` to the nearest available `release_year` (the
  archive's 2005/2012-2015 gaps, see `docs/data/florida/traffic/README.md`,
  mean that's not always the same year) is the final event-study panel's job
  (`panel/assemble.py`), not this module's. A school with no roadway match,
  or a roadway with no AADT some release, keeps its row with `NA` traffic
  columns rather than being dropped.

**Local-intensity scaling (`aadt_local`).** `aadt` (the roadway-wide,
length-weighted mean from `traffic/preprocess.py`) can be a coarse proxy for
a specific school's exposure — a `roadway_id` can span a short urban block
or a 57 km stretch (`road_network`'s Open Question 7), and AADT genuinely
varies along it. **True segment-level history isn't available**: FGDL
re-segments each `ROADWAY` differently release to release (see
`traffic/preprocess.py`'s module docstring), so there is no single "the
segment near this school" that exists consistently across all 57 releases —
only within one release's own snapshot. What *is* available is
`road_network.parquet` itself: one snapshot (whichever version it was last
preprocessed from) that already carries per-segment `aadt`. So
`compute_local_intensity` computes, from that one snapshot only, each
matched school's **local-intensity ratio** — its nearest segment's own AADT
divided by that roadway's `aadt_panel` mean for the *same* release year —
and `build_school_aadt_panel` applies that ratio to every release year's
roadway mean to produce `aadt_local`, a school-specific estimate. This is a
deliberate approximation, not true history: it assumes a school's position
*relative to* its roadway's own average (busier or quieter than the
roadway typically is) is roughly stable over time, which is a much weaker
assumption than assuming the roadway-wide *level* is stable — but it is an
assumption, and `aadt` (the unscaled roadway mean) is kept alongside
`aadt_local` rather than replaced, so a consumer can use either or compare.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.florida.sources.road_network.linear_ref import arterial_subset, nearest_road
from src.regions.florida.sources.road_network.shared import (
    load_road_network,
    processed_metadata_path as road_network_metadata_path,
)
from src.regions.florida.sources.schools.shared import processed_cross_section_path
from src.regions.florida.sources.traffic.shared import (
    processed_aadt_panel_path,
    release_year,
    school_aadt_panel_path,
    school_nearby_aadt_path,
    school_road_match_path,
)

MAX_MATCH_DIST_M = 1000.0


def load_placed_schools(root: Path | None = None) -> gpd.GeoDataFrame:
    """The `schools preprocess` cross-section, restricted to schools that got
    a real coordinate (`geom_source != 'none'`) — same filter
    `schools/assemble.py` applies."""
    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    xs = gpd.read_parquet(path)
    return xs[xs["geom_source"] != "none"].reset_index(drop=True)


def load_aadt_panel(root: Path | None = None) -> pd.DataFrame:
    path = processed_aadt_panel_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data traffic preprocess` first.")
    return pd.read_parquet(path)


def load_road_network_reference_version(root: Path | None = None) -> str:
    """The FGDL version `road_network.parquet` was built from — read from
    its own provenance sidecar rather than assumed, since a user may have
    preprocessed a non-default version. This is the single snapshot
    `compute_local_intensity` anchors the local-intensity ratio to."""
    path = road_network_metadata_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data road-network preprocess` first.")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    version = metadata.get("version")
    if not version:
        raise ValueError(f"{path} has no 'version' field — is it a road_network provenance sidecar?")
    return version


def match_schools_to_roadway(
    placed: gpd.GeoDataFrame,
    road_network: gpd.GeoDataFrame,
    max_dist: float = MAX_MATCH_DIST_M,
) -> pd.DataFrame:
    """Nearest arterial `roadway_id` for every placed school, plus that
    matched segment's own AADT from this snapshot (`nearest_segment_aadt`,
    non-positive values treated as missing like everywhere else in this
    source) — the input `compute_local_intensity` scales into a ratio."""
    major = arterial_subset(road_network)
    sj = nearest_road(placed[["geometry"]], major)
    segment_aadt = pd.to_numeric(
        pd.Series(major["aadt"].to_numpy()[sj["index_right"].to_numpy()]), errors="coerce"
    )
    segment_aadt = segment_aadt.where(segment_aadt > 0)

    out = pd.DataFrame(
        {
            "msid": placed["msid"].to_numpy(),
            "roadway_id": major["roadway_id"].to_numpy()[sj["index_right"].to_numpy()],
            "dist_m": sj["dist_m"].to_numpy(),
            "nearest_segment_aadt": segment_aadt.to_numpy(),
        }
    )
    too_far = out["dist_m"] > max_dist
    out.loc[too_far, ["roadway_id", "nearest_segment_aadt"]] = pd.NA
    return out


def compute_local_intensity(
    school_road_match: pd.DataFrame,
    aadt_panel: pd.DataFrame,
    reference_release_year: int,
) -> pd.DataFrame:
    """Add the local-intensity ratio (see module docstring) to
    `school_road_match`: each matched school's `nearest_segment_aadt`
    (from the one road-network snapshot) divided by that same roadway's
    `aadt_panel` mean for `reference_release_year` — the same year the
    snapshot itself is from."""
    reference = aadt_panel.loc[
        aadt_panel["release_year"] == reference_release_year, ["roadway_id", "aadt"]
    ].rename(columns={"aadt": "roadway_mean_aadt_reference"})

    out = school_road_match.merge(reference, on="roadway_id", how="left")
    out["local_reference_release_year"] = reference_release_year
    ratio = out["nearest_segment_aadt"] / out["roadway_mean_aadt_reference"]
    out["local_intensity_ratio"] = ratio.where(out["roadway_mean_aadt_reference"] > 0)
    return out


def build_school_aadt_panel(school_road_match: pd.DataFrame, aadt_panel: pd.DataFrame) -> pd.DataFrame:
    """Left join of every matched school onto its roadway's AADT time
    series; an unmatched school (no roadway within `max_dist`) keeps one row
    with `NA` traffic columns instead of being dropped. Also adds
    `aadt_local = aadt * local_intensity_ratio` when `school_road_match`
    carries that ratio (see `compute_local_intensity`)."""
    matched = school_road_match.dropna(subset=["roadway_id"])
    joined = matched.merge(aadt_panel, on="roadway_id", how="left")

    unmatched = school_road_match[school_road_match["roadway_id"].isna()].copy()
    for column in aadt_panel.columns:
        if column not in unmatched.columns:
            unmatched[column] = pd.NA

    out = pd.concat([joined, unmatched], ignore_index=True)
    if "local_intensity_ratio" in out.columns and "aadt" in out.columns:
        out["aadt_local"] = out["aadt"] * out["local_intensity_ratio"]
    return out.sort_values(["msid", "release_year"], na_position="last").reset_index(drop=True)


NEARBY_RADII_M = (250, 500)


def match_schools_to_nearby_roadways(
    placed: gpd.GeoDataFrame, road_network: gpd.GeoDataFrame, radius: float = max(NEARBY_RADII_M)
) -> pd.DataFrame:
    """Every RCI `roadway_id` passing within `radius` of each school (any road
    class, not just arterials), with its closest distance: `msid`,
    `roadway_id`, `dist_m`."""
    roads = road_network[["roadway_id", "geometry"]].dropna(subset=["roadway_id"]).reset_index(drop=True)
    points = placed.to_crs(roads.crs).reset_index(drop=True)
    school_idx, road_idx = roads.sindex.query(points.geometry.values, predicate="dwithin", distance=radius)
    pairs = pd.DataFrame(
        {
            "msid": points["msid"].to_numpy()[school_idx],
            "roadway_id": roads["roadway_id"].to_numpy()[road_idx],
            "dist_m": roads.geometry.values[road_idx].distance(points.geometry.values[school_idx]),
        }
    )
    return pairs.groupby(["msid", "roadway_id"], as_index=False)["dist_m"].min()


def build_school_nearby_aadt(nearby: pd.DataFrame, aadt_panel: pd.DataFrame) -> pd.DataFrame:
    """`msid x release_year`: `traffic_max_aadt_{R}m`, the highest roadway AADT
    among roads within R metres of the school. Unlike `school_aadt_panel`'s
    single nearest arterial, this catches the busy highway a few hundred
    metres away rather than the nearer quiet road (for schools protected by
    a wall, the nearest arterial is the wall's own road only ~52% of the
    time)."""
    joined = nearby.merge(aadt_panel[["roadway_id", "release_year", "aadt"]], on="roadway_id")
    frames = []
    for radius in NEARBY_RADII_M:
        frames.append(
            joined[joined["dist_m"] <= radius]
            .groupby(["msid", "release_year"])["aadt"]
            .max()
            .rename(f"traffic_max_aadt_{radius}m")
        )
    return pd.concat(frames, axis=1).reset_index()


def save_assembled(
    school_road_match: pd.DataFrame, school_aadt_panel: pd.DataFrame, root: Path | None = None
) -> dict[str, str]:
    road_match_path = school_road_match_path(root)
    aadt_panel_path_out = school_aadt_panel_path(root)
    for path in (road_match_path, aadt_panel_path_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    school_road_match.to_parquet(road_match_path, index=False)
    school_aadt_panel.to_parquet(aadt_panel_path_out, index=False)
    return {"school_road_match": str(road_match_path), "school_aadt_panel": str(aadt_panel_path_out)}


def run_traffic_assemble(root: Path | None = None, max_dist: float = MAX_MATCH_DIST_M) -> dict[str, object]:
    """Load the school, road-network and AADT-panel layers, match, compute
    the local-intensity scaling, and persist."""
    placed = load_placed_schools(root)
    road_network = load_road_network(root)
    aadt_panel = load_aadt_panel(root)
    reference_version = load_road_network_reference_version(root)
    reference_release_year = release_year(reference_version)

    school_road_match = match_schools_to_roadway(placed, road_network, max_dist)
    school_road_match = compute_local_intensity(school_road_match, aadt_panel, reference_release_year)
    school_aadt_panel = build_school_aadt_panel(school_road_match, aadt_panel)
    saved = save_assembled(school_road_match, school_aadt_panel, root)
    nearby_aadt = build_school_nearby_aadt(match_schools_to_nearby_roadways(placed, road_network), aadt_panel)
    nearby_path = school_nearby_aadt_path(root)
    nearby_aadt.to_parquet(nearby_path, index=False)
    saved["school_nearby_aadt"] = str(nearby_path)

    matched = school_road_match["roadway_id"].notna()
    has_ratio = school_road_match["local_intensity_ratio"].notna()
    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/traffic/assemble.py",
        "max_dist_m": max_dist,
        "reference_version": reference_version,
        "reference_release_year": reference_release_year,
        "schools_placed": int(len(placed)),
        "schools_matched": int(matched.sum()),
        "schools_unmatched": int((~matched).sum()),
        "schools_with_local_intensity_ratio": int(has_ratio.sum()),
        "school_aadt_panel_rows": int(len(school_aadt_panel)),
        "aadt_known_rows": (
            int(school_aadt_panel["aadt"].notna().sum()) if "aadt" in school_aadt_panel.columns else 0
        ),
        "aadt_local_known_rows": (
            int(school_aadt_panel["aadt_local"].notna().sum()) if "aadt_local" in school_aadt_panel.columns else 0
        ),
        "schools_with_nearby_aadt": int(nearby_aadt["msid"].nunique()),
        "saved": saved,
    }
