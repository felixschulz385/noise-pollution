"""Preprocess step for the Florida `traffic` (AADT panel) source.

Stacks the per-release attribute tables `fetch.py` wrote (one parquet per
FGDL `rciroads` version) into a single `roadway_id x release_year` AADT
panel.

**Row grain is `roadway_id x release_year`, not `roadway_id x segmentid`.**
That was the original design (matching `road_network.parquet`'s own grain),
but verified against two real releases (`jul26` vs `jan19`) and rejected:
FGDL re-segments each `ROADWAY` differently release to release -- of the
~40k `jul26` segments, only 5 shared a `(roadway_id, segmentid)` pair with
`jan19`, and even `begin_post`/`end_post` breakpoints for the same stretch of
road differ between releases (one sampled roadway had 2 segments in `jul26`
vs 1 in `jan19`, with different boundaries). `roadway_id` itself, by
contrast, is stable (84% overlap between those two releases), so this module
aggregates every release's segments within a `roadway_id` into one row: AADT
as the length-weighted mean (weight = `end_post - begin_post`, i.e. a
roadway carrying 35,000 AADT for 3 miles and 5,000 for 1 mile averages
closer to 35,000 than a plain segment mean would), alongside `aadt_min`/
`aadt_max`/`segment_count`/`length_mi` so a consumer can judge how much
within-roadway heterogeneity the average is smoothing over. Verified this
still carries real time variation once aggregated: `jul26` vs `jan19`
(2026 vs 2019) shows a +10% median AADT change across the ~15.5k shared
roadways, ~51/49 up/down -- consistent with traffic growth, not noise.

**Fixed 2026-09-14: FGDL releases more than once a year, so grouping by
`version` (in addition to `roadway_id`/`release_year`) was silently
producing one row per *version*, not per *year* as documented.** Recent
years (2016 on) have 3-4 releases each (e.g. `jan26`/`apr26`/`jul26` all
map to `release_year=2026`); checked against the real fetched archive and
found 231,906 of 272,656 `(roadway_id, release_year)` groups (85%) had 2-4
duplicate rows. A downstream consumer joining on `release_year` alone (as
`panel/assemble.py`'s `attach_traffic` does) would silently pick one via
whatever tie-break its merge happened to use -- for most roadway-years the
within-year releases are nearly identical (median ratio 1.03 across
releases), but a real ~10% tail differs by >20%, some by much more. Fixed
by aggregating directly to `[roadway_id, release_year]` (not
`..., version`), pooling every segment from every release in that calendar
year into one length-weighted mean -- statistically cleaner than averaging
several already-computed per-version means, and it also matches the
existing "aggregate now, keep spread diagnostics alongside" philosophy this
module already uses for the segment-level pooling. `version` (singular) is
no longer a meaningful per-row value once multiple versions are pooled, so
the output carries `release_count` (how many distinct FGDL versions
contributed to that row) instead.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

from src.regions.florida.sources.traffic.shared import (
    processed_aadt_panel_path,
    processed_metadata_path,
    traffic_paths,
)

# Same YEAR_ data-currency sentinel road_network/preprocess.py handles.
YEAR_SENTINEL = 0

# Segments with a zero/negative post-mile span (bad data, not a real
# zero-length road) get this floor as their weight instead of being dropped
# or given zero weight (which would erase their AADT from the average).
MIN_SEGMENT_LENGTH_MI = 0.01

OUTPUT_COLUMNS = [
    "roadway_id",
    "release_year",
    "release_count",
    "aadt",
    "aadt_min",
    "aadt_max",
    "segment_count",
    "length_mi",
    "lane_cnt",
    "funclass",
    "fgdlaqdate",
]


def load_raw_traffic_tables() -> pd.DataFrame:
    """Read and concatenate every per-version attribute parquet `fetch.py`
    wrote."""
    raw_dir = traffic_paths()["raw"]
    files = sorted(raw_dir.glob("aadt_*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"no 'aadt_<version>.parquet' files in {raw_dir} -- run "
            "`python -m src.cli florida data traffic fetch` first."
        )
    frames = [pd.read_parquet(path) for path in files]
    return pd.concat(frames, ignore_index=True)


def _clean_segments(raw: pd.DataFrame) -> pd.DataFrame:
    """Sentinel/dtype cleanup at the raw segment grain, before aggregation."""
    out = raw.copy()

    if "year" in out.columns:
        year = pd.to_numeric(out["year"], errors="coerce")
        out["year"] = year.where(year != YEAR_SENTINEL)
    if "aadt" in out.columns:
        # AADT is a traffic count; treat non-positive values as missing
        # rather than a real zero (an unmeasured/placeholder segment, not a
        # road with no traffic).
        aadt = pd.to_numeric(out["aadt"], errors="coerce")
        out["aadt"] = aadt.where(aadt > 0)
    if {"begin_post", "end_post"}.issubset(out.columns):
        out["length_mi"] = (out["end_post"] - out["begin_post"]).clip(lower=MIN_SEGMENT_LENGTH_MI)
    return out


def _weighted_mean_aadt(group: pd.DataFrame) -> float:
    """Length-weighted mean AADT across a roadway's segments in one release,
    ignoring segments with unknown AADT rather than treating them as 0."""
    known = group[group["aadt"].notna()]
    total_length = known["length_mi"].sum()
    if total_length <= 0:
        return np.nan
    return float((known["aadt"] * known["length_mi"]).sum() / total_length)


def _aggregate_group(group: pd.DataFrame) -> pd.Series:
    funclass = group["funclass"].dropna()
    return pd.Series(
        {
            "aadt": _weighted_mean_aadt(group),
            "aadt_min": group["aadt"].min(),
            "aadt_max": group["aadt"].max(),
            "segment_count": len(group),
            "release_count": group["version"].nunique(),
            "length_mi": group["length_mi"].sum(),
            "lane_cnt": group["lane_cnt"].mean(),
            "funclass": funclass.mode().iloc[0] if not funclass.empty else pd.NA,
            "fgdlaqdate": group["fgdlaqdate"].max(),
        }
    )


def _aggregate_to_roadway(segments: pd.DataFrame) -> pd.DataFrame:
    """Collapse every segment row -- across every FGDL release that shares a
    `release_year`, not just one release's own `roadway_id x segmentid`
    rows -- into one row per `roadway_id x release_year` (length-weighted
    mean AADT; see module docstring for why segment-level rows can't be kept
    across releases, and why grouping by `version` too would silently split
    a year with several releases back into one row per release)."""
    grouped = segments.groupby(["roadway_id", "release_year"]).apply(_aggregate_group)
    out = grouped.reset_index()
    out["lane_cnt"] = pd.array(out["lane_cnt"].round().to_numpy(), dtype="Int64")
    out["segment_count"] = out["segment_count"].astype(int)
    out["release_count"] = out["release_count"].astype(int)
    return out


def preprocess_traffic(raw: pd.DataFrame) -> pd.DataFrame:
    """Tidy sentinels/dtypes and aggregate to one row per
    `roadway_id x release_year`, pooling every FGDL release that shares a
    calendar year."""
    segments = _clean_segments(raw)
    out = _aggregate_to_roadway(segments)

    ordered = [column for column in OUTPUT_COLUMNS if column in out.columns]
    remaining = [column for column in out.columns if column not in ordered]
    out = out[ordered + remaining]
    out = out.sort_values(["roadway_id", "release_year"]).reset_index(drop=True)
    return out


def save_processed_traffic(df: pd.DataFrame, versions: list[str] | None = None) -> dict[str, str]:
    """Write `aadt_panel.parquet` and its `traffic.json` provenance
    sidecar. `versions` is the raw (pre-aggregation) list of FGDL release
    tags that went into `df` -- captured before aggregation since `version`
    is no longer a per-row column once multiple releases pool into one
    `release_year` row (see `release_count` on `df` itself for the per-row
    count)."""
    parquet_path = processed_aadt_panel_path()
    meta_path = processed_metadata_path()
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)

    provenance = {
        "source": "fdot_rciroads_fgdl_multi_vintage",
        "grain": "roadway_id x release_year (length-weighted mean AADT across every segment of every FGDL release sharing that year)",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "distinct_roadway_ids": int(df["roadway_id"].nunique()) if "roadway_id" in df.columns else None,
        "release_years": (
            sorted(int(y) for y in df["release_year"].dropna().unique())
            if "release_year" in df.columns
            else []
        ),
        "versions": sorted(versions) if versions else [],
        "aadt_known": int(df["aadt"].notna().sum()) if "aadt" in df.columns else 0,
        "columns": list(df.columns),
        "parquet": str(parquet_path),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"parquet": str(parquet_path), "metadata": str(meta_path)}


def run_traffic_preprocess() -> dict[str, object]:
    """Load every fetched release's attribute table, aggregate it, and
    persist the stacked panel + sidecar."""
    raw = load_raw_traffic_tables()
    versions = sorted(raw["version"].dropna().unique().tolist()) if "version" in raw.columns else []
    processed = preprocess_traffic(raw)
    saved = save_processed_traffic(processed, versions)

    return {
        "raw_rows": int(len(raw)),
        "rows": int(len(processed)),
        "distinct_roadway_ids": int(processed["roadway_id"].nunique()),
        "release_years": sorted(int(y) for y in processed["release_year"].dropna().unique()),
        "versions": versions,
        "aadt_known": int(processed["aadt"].notna().sum()),
        "columns": list(processed.columns),
        "saved": saved,
    }
