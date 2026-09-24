"""Parse the fetched Overpass JSON into one GeoParquet of wall lines in
SWEREF 99 TM: `osm_id`, `wall_type` (`noise_barrier` / `untyped_wall`),
`material`, geometry. Ways with fewer than two nodes are dropped; a way
present in both queries keeps its `noise_barrier` row."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.regions.sweden.sources._linear_ref import METRIC_CRS
from src.regions.sweden.sources.osm_walls.shared import QUERIES, processed_osm_walls_path, raw_query_path


def parse_overpass_ways(payload: dict, wall_type: str) -> gpd.GeoDataFrame:
    rows = [
        {
            "osm_id": int(element["id"]),
            "wall_type": wall_type,
            "material": element.get("tags", {}).get("material"),
            "geometry": LineString([(node["lon"], node["lat"]) for node in element["geometry"]]),
        }
        for element in payload["elements"]
        if element.get("type") == "way" and len(element.get("geometry", [])) >= 2
    ]
    frame = pd.DataFrame(rows, columns=["osm_id", "wall_type", "material", "geometry"])
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=4326).to_crs(METRIC_CRS)


def run_osm_walls_preprocess(root: Path | None = None) -> dict:
    frames = []
    for wall_type in QUERIES:
        path = raw_query_path(wall_type, root)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing -- run `sweden data osm-walls fetch` first.")
        frames.append(parse_overpass_ways(json.loads(path.read_text()), wall_type))
    walls = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=METRIC_CRS)
    walls = walls.drop_duplicates("osm_id", keep="first").reset_index(drop=True)

    out_path = processed_osm_walls_path(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    walls.to_parquet(out_path, index=False)
    return {
        "n_walls": int(len(walls)),
        "by_type": {k: int(v) for k, v in walls["wall_type"].value_counts().items()},
        "total_km": round(float(walls.length.sum()) / 1000, 1),
        "saved": str(out_path),
    }
