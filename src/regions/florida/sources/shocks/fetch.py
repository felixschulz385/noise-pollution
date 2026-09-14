"""Fetch step for the Florida `shocks` source.

Pulls the entire Florida disaster-declaration history from OpenFEMA's
`DisasterDeclarationsSummaries` v2 API in **one request** -- confirmed live
2026-09-14: `$filter=state eq 'FL'&$top=5000` returns all 2,794 FL rows in a
single response (no `$skip` pagination loop needed, unlike every other
Florida source's archive). No auth required.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from src.regions.florida.sources._http import USER_AGENT, get_json
from src.regions.florida.sources.shocks.shared import (
    DISASTER_DECLARATIONS_URL,
    FETCH_TOP,
    raw_disaster_declarations_path,
)


def fetch_disaster_declarations(*, root: Path | None = None, force: bool = False) -> dict[str, object]:
    """Fetch every Florida `DisasterDeclarationsSummaries` row and save it."""
    import pandas as pd  # heavy; only needed to write parquet

    destination = raw_disaster_declarations_path(root)
    if destination.exists() and not force:
        return {"status": "cached", "path": str(destination)}

    params = {"$filter": "state eq 'FL'", "$top": str(FETCH_TOP)}
    payload = get_json(f"{DISASTER_DECLARATIONS_URL}?{urlencode(params)}", user_agent=USER_AGENT)
    records = payload.get("DisasterDeclarationsSummaries", [])
    if len(records) >= FETCH_TOP:
        raise RuntimeError(
            f"{DISASTER_DECLARATIONS_URL}: returned {len(records)} rows, at or above FETCH_TOP="
            f"{FETCH_TOP} -- the archive may have grown past a single page; raise FETCH_TOP or add pagination."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_parquet(destination, index=False)
    return {"status": "fetched", "path": str(destination), "rows": len(records)}
