"""Download the OSM wall queries in `shared.QUERIES` from the public Overpass
API. The server answers 406 to requests without a User-Agent, and 504 when
busy; a busy server is retried a few times before giving up."""
from __future__ import annotations

import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.regions.sweden.sources.osm_walls.shared import OVERPASS_URL, QUERIES, raw_query_path

USER_AGENT = "noise-pollution-research/1.0"


def _post_overpass(query: str, *, attempts: int = 3, wait_s: int = 30, timeout: int = 660) -> bytes:
    body = urlencode({"data": query}).encode()
    request = Request(OVERPASS_URL, data=body, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in (429, 504) or attempt == attempts:
                raise RuntimeError(f"Overpass HTTP {exc.code}") from exc
        except URLError as exc:
            if attempt == attempts:
                raise RuntimeError(f"Overpass request failed: {exc}") from exc
        time.sleep(wait_s)


def run_osm_walls_fetch(root: Path | None = None) -> dict:
    saved = {}
    for wall_type, query in QUERIES.items():
        payload = _post_overpass(query)
        path = raw_query_path(wall_type, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        saved[wall_type] = {"bytes": len(payload), "saved": str(path)}
    return {"queries": saved}
