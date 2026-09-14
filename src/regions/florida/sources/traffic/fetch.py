"""Download step for the Florida `traffic` (AADT panel) source.

Turns FGDL `rciroads` releases -- already fetchable wholesale by
`road_network.fetch.fetch_road_network` -- into a per-release attribute-only
table (`roadway_id`, `segmentid`, `aadt`, ...), dropping the multi-MB
centerline geometry this source has no use for. Fetching many releases (the
archive holds 57 as of `jul26`, `jun04` -> `jul26`, ~3/year -- see
`road_network.fetch.list_versions`) is what turns `road_network`'s `AADT`
field -- a single cross-section on its own -- into the time-varying traffic
covariate the event study needs; see `docs/data/florida/traffic/README.md`.

`fetch_traffic_version` is idempotent (skips a version whose attribute table
already exists unless `force=True`) and, by default, deletes the extracted
`road_network` shapefile again after pulling the columns this source needs --
each release is ~34 MB of geometry for a few numeric columns, and keeping 57
copies around (~2 GB) would only be useful to `road_network` itself, which
already keeps its own default-version snapshot separately. If a version was
already on disk before this call (e.g. `road_network`'s own default `jul26`),
it is left alone either way.
"""
from __future__ import annotations

import shutil

import geopandas as gpd

from src.regions.florida.sources.road_network.fetch import fetch_road_network
from src.regions.florida.sources.road_network.fetch import list_versions as _list_road_network_versions
from src.regions.florida.sources.road_network.shared import (
    raw_metadata_path,
    raw_shapefile_dir,
    raw_shapefile_path,
    validate_version,
)
from src.regions.florida.sources.traffic.shared import raw_aadt_path, release_year

# Attribute columns to keep from the road_network shapefile -- everything
# `traffic` needs, none of the geometry. Matches road_network/preprocess.py's
# COLUMN_RENAMES subset relevant to traffic.
_KEEP_COLUMNS = [
    "ROADWAY",
    "SEGMENTID",
    "BEGIN_POST",
    "END_POST",
    "YEAR_",
    "FUNCLASSCO",
    "FUNCLASS",
    "LANE_CNT",
    "AADT",
    "FGDLAQDATE",
]

_RENAME = {
    "ROADWAY": "roadway_id",
    "SEGMENTID": "segmentid",
    "BEGIN_POST": "begin_post",
    "END_POST": "end_post",
    "YEAR_": "year",
    "FUNCLASSCO": "funclassco",
    "FUNCLASS": "funclass",
    "LANE_CNT": "lane_cnt",
    "AADT": "aadt",
    "FGDLAQDATE": "fgdlaqdate",
}


def list_versions() -> dict[str, object]:
    """The same FGDL `rciroads` archive index `road_network` reads -- every
    release listed there is a candidate AADT-panel year."""
    return _list_road_network_versions()


def _extract_attributes(version: str) -> gpd.GeoDataFrame:
    shp_path = raw_shapefile_path(version)
    gdf = gpd.read_file(shp_path, ignore_geometry=True)
    present = [c for c in _KEEP_COLUMNS if c in gdf.columns]
    out = gdf[present].rename(columns=_RENAME)
    out["version"] = version
    out["release_year"] = release_year(version)
    return out


def fetch_traffic_version(
    version: str,
    *,
    force: bool = False,
    keep_road_network_raw: bool = False,
) -> dict[str, object]:
    """Fetch one FGDL release and save its attribute-only AADT table."""
    resolved = validate_version(version)
    out_path = raw_aadt_path(resolved)
    if out_path.exists() and not force:
        return {"version": resolved, "status": "cached", "path": str(out_path)}

    already_on_disk = raw_shapefile_path(resolved).exists()
    road_network_fetch_result: dict[str, object] | None = None
    if not already_on_disk:
        road_network_fetch_result = fetch_road_network(resolved, keep_zip=False, with_metadata=False)

    table = _extract_attributes(resolved)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)

    cleaned_road_network_raw = False
    if not keep_road_network_raw and not already_on_disk:
        shutil.rmtree(raw_shapefile_dir(resolved), ignore_errors=True)
        meta_path = raw_metadata_path(resolved)
        if meta_path.exists():
            meta_path.unlink()
        cleaned_road_network_raw = True

    return {
        "version": resolved,
        "status": "fetched",
        "path": str(out_path),
        "rows": int(len(table)),
        "release_year": release_year(resolved),
        "road_network_raw_cleaned": cleaned_road_network_raw,
        "road_network_fetch": road_network_fetch_result,
    }


def fetch_traffic_panel(
    versions: list[str] | None = None,
    *,
    limit: int | None = None,
    force: bool = False,
    keep_road_network_raw: bool = False,
) -> dict[str, object]:
    """Fetch attribute tables for many FGDL releases at once.

    ``versions=None`` fetches every release the archive lists (57 as of
    ``jul26``, newest first); ``limit`` takes only the N most recent instead
    -- useful for a quick smoke test before committing to the full archive
    (each release is a real network download).
    """
    resolved_versions = versions if versions is not None else list(list_versions()["versions"])
    if limit is not None:
        resolved_versions = resolved_versions[:limit]

    results = [
        fetch_traffic_version(version, force=force, keep_road_network_raw=keep_road_network_raw)
        for version in resolved_versions
    ]

    return {
        "versions_requested": len(resolved_versions),
        "versions": [r["version"] for r in results],
        "fetched": sum(1 for r in results if r["status"] == "fetched"),
        "cached": sum(1 for r in results if r["status"] == "cached"),
        "results": results,
    }
