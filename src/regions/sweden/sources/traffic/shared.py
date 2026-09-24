"""Paths for the Sweden `traffic` source: NVDB's `Trafik` data product
(ÅDT -- traffic flow, CNOSSOS-EU-ready time-of-day x vehicle-class splits),
Covariate Cluster C. Manually downloaded via Lastkajen (a custom Sverigefiler
order) -- no automated `fetch`, same "place the file under `raw/`" pattern
as `road_network`/`network`'s own manual downloads. See
`docs/data/sweden/traffic/README.md`.

**Multiple orders under `raw/` are expected and meaningful, not an
ambiguity to reject.** Each `Trafik` order at a different `Betraktelsedatum`
returns a genuinely different historical slice of NVDB's per-segment
`[VALID_FROM, VALID_TO)`-windowed measurement history -- confirmed live
2026-09-16 (an earlier same-session test wrongly concluded otherwise from a
biased comparison, see `traffic/README.md`'s "Correction" section). So
`preprocess` unions every `.gpkg` found, rather than requiring exactly one.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs


def traffic_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("traffic", root)


def all_traffic_gpkgs(root: Path | None = None) -> list[Path]:
    """Every manually-downloaded `Trafik` GeoPackage under `raw/` -- found
    by glob, since Lastkajen bakes a per-order id into the name (e.g.
    `Traffic_260916_653409.gpkg`). Each is a legitimate, different
    historical `Betraktelsedatum` slice -- `preprocess` unions all of
    them, not just the most recent."""
    raw_dir = traffic_paths(root)["raw"]
    matches = sorted(raw_dir.glob("**/*.gpkg"))
    if not matches:
        raise FileNotFoundError(
            f"No .gpkg found under {raw_dir} -- download the NVDB Trafik "
            "GeoPackage from Lastkajen and place it (zipped or already extracted) there."
        )
    return matches


def processed_traffic_path(root: Path | None = None) -> Path:
    return traffic_paths(root)["processed"] / "traffic.parquet"


def assembled_school_traffic_path(root: Path | None = None) -> Path:
    return traffic_paths(root)["assembled"] / "school_traffic.parquet"
