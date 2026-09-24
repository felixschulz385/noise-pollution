"""Paths and queries for the Sweden `osm_walls` source: OpenStreetMap walls
used as the one direct observation of which side of its road a noise barrier
stands on. Trafikverket's own barrier geometry is snapped onto the road/track
centreline and its `side` attribute carries no signal; see
`docs/data/sweden/barrier_matching.md`.

Two groups are fetched: ways tagged as noise barriers, and plain
`barrier=wall` ways with no `wall=` subtype. The untyped ones are kept
because, where they run parallel to a Trafikverket barrier, they agree with
the parallel-road side rule as often as the tagged ones do (checked
2026-09-23); `_barrier_reference.py` applies the parallel/offset/length
filters that screen out garden and retaining walls.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from src.regions.sweden.sources._layout import domain_dirs

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_SWEDEN = 'area["ISO3166-1"="SE"][admin_level=2]->.se;'
QUERIES = {
    "noise_barrier": (
        f"[out:json][timeout:600];{_SWEDEN}"
        '(way["wall"="noise_barrier"](area.se);way["barrier"="noise_barrier"](area.se);'
        'way["noise_barrier"](area.se);way["barrier"="fence"]["fence_type"="noise_barrier"](area.se););'
        "out tags geom;"
    ),
    "untyped_wall": f'[out:json][timeout:600];{_SWEDEN}way["barrier"="wall"][!"wall"](area.se);out tags geom;',
}


def osm_walls_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("osm_walls", root)


def raw_query_path(wall_type: str, root: Path | None = None) -> Path:
    return osm_walls_paths(root)["raw"] / f"{wall_type}.json"


def processed_osm_walls_path(root: Path | None = None) -> Path:
    return osm_walls_paths(root)["processed"] / "osm_walls.parquet"


def load_osm_walls(root: Path | None = None) -> gpd.GeoDataFrame:
    path = processed_osm_walls_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data osm-walls fetch` then `osm-walls preprocess` first.")
    return gpd.read_parquet(path)
