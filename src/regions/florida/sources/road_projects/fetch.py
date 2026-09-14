"""Fetch step for the Florida `road_projects` source.

Pulls two live FDOT ArcGIS REST FeatureServer extracts into
`data/florida/road_projects/raw/`, attributes only (`returnGeometry=false`):

* `Work_Program_Current` layers 2 (Construction Phase) and 13 (PD&E Phase) --
  current 5-year Work Program window only (a live query for `FISCALYR<2020`
  returns zero rows -- confirmed empirically, see
  `docs/data/florida/road_projects/README.md` Open Question 1).
* `Active_Construction_Projects` layer 1 ("Construction Projects", Site
  Manager extract) -- NOT current-only despite the name: `StartDate` spans
  2009-03-03 to 2026-04-16 (2,428 rows total, confirmed via `outStatistics`),
  the only usable pre-2020 signal from either live service.

Geometry is skipped: `road_projects/README.md`'s join strategy is
`roadway_id` + milepost-overlap against `road_network`, not spatial nearest-
line matching (both services share `road_network.roadway_id`'s id format),
so geometry isn't needed for the join -- mirrors `traffic/fetch.py`'s
`ignore_geometry=True` choice for the same reason.

Pagination follows the ArcGIS REST convention (`resultOffset` /
`resultRecordCount`, stop once a page returns fewer features than requested)
rather than the Urban Institute API's `next`-URL convention `schools/fetch.py`
uses -- a different upstream, a different pagination contract. The retry/
backoff GET itself (`_http.get_json`) is shared with `schools/fetch.py`,
which was the only other caller before this source pulled it out of both.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from src.regions.florida.sources._http import USER_AGENT, get_json
from src.regions.florida.sources.road_projects.shared import (
    ACTIVE_CONSTRUCTION_LAYER_ID,
    ACTIVE_CONSTRUCTION_SERVICE,
    WORK_PROGRAM_LAYERS,
    WORK_PROGRAM_SERVICE,
    raw_active_construction_path,
    raw_work_program_path,
    road_projects_paths,
)

_PAGE_SIZE = 1000
_PAGE_CAP = 500


def _fetch_layer_records(layer_url: str, *, where: str = "1=1", page_size: int = _PAGE_SIZE) -> list[dict]:
    """Page an ArcGIS REST FeatureServer layer's `/query` endpoint via
    `resultOffset`, attributes only."""
    records: list[dict] = []
    offset = 0
    for _ in range(_PAGE_CAP):
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "false",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
            "orderByFields": "OBJECTID",
            "f": "json",
        }
        payload = get_json(f"{layer_url}/query?{urlencode(params)}", user_agent=USER_AGENT)
        if "error" in payload:
            raise RuntimeError(f"{layer_url}: {payload['error']}")
        features = payload.get("features", [])
        records.extend(feature["attributes"] for feature in features)
        if len(features) < page_size:
            return records
        offset += page_size
    raise RuntimeError(f"{layer_url}: exceeded {_PAGE_CAP} pages")


def fetch_work_program_layer(name: str, *, root: Path | None = None, force: bool = False) -> dict[str, object]:
    """Fetch one `Work_Program_Current` sublayer (`"construction"` or
    `"pde"`) and save its attribute table."""
    import pandas as pd  # heavy; only needed to write parquet

    destination = raw_work_program_path(name, root)
    if destination.exists() and not force:
        return {"layer": name, "status": "cached", "path": str(destination)}

    layer_url = f"{WORK_PROGRAM_SERVICE}/{WORK_PROGRAM_LAYERS[name]}"
    records = _fetch_layer_records(layer_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_parquet(destination, index=False)
    return {"layer": name, "status": "fetched", "path": str(destination), "rows": len(records)}


def fetch_active_construction_projects(*, root: Path | None = None, force: bool = False) -> dict[str, object]:
    """Fetch the `Active_Construction_Projects` extract and save its
    attribute table."""
    import pandas as pd

    destination = raw_active_construction_path(root)
    if destination.exists() and not force:
        return {"layer": "active_construction", "status": "cached", "path": str(destination)}

    layer_url = f"{ACTIVE_CONSTRUCTION_SERVICE}/{ACTIVE_CONSTRUCTION_LAYER_ID}"
    records = _fetch_layer_records(layer_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_parquet(destination, index=False)
    return {"layer": "active_construction", "status": "fetched", "path": str(destination), "rows": len(records)}


def fetch_road_projects(*, root: Path | None = None, force: bool = False) -> dict[str, object]:
    """Fetch all three raw extracts (Work Program Construction + PD&E,
    Active Construction Projects) into `raw/`."""
    road_projects_paths(root)  # ensures raw/processed/assembled exist

    results = {
        name: fetch_work_program_layer(name, root=root, force=force) for name in WORK_PROGRAM_LAYERS
    }
    results["active_construction"] = fetch_active_construction_projects(root=root, force=force)

    return {
        "layers": results,
        "fetched": sum(1 for r in results.values() if r["status"] == "fetched"),
        "cached": sum(1 for r in results.values() if r["status"] == "cached"),
    }
