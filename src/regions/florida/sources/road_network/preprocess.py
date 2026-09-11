"""Preprocess step for the Florida road-network source.

Turns one raw FGDL release (``rciroads_<version>.shp``, written by ``fetch``)
into a single tidy GeoParquet layer of roadway centerline segments, ready to
be joined to ``noise_barriers`` and school points in the ``schools`` source
(algorithms 3-5, see ``docs/data/florida/schools/README.md``'s "Stage 2").

Design decisions (see ``docs/data/florida/road_network/README.md`` and the
exploratory notebook ``src/experiments/florida/road_network.ipynb`` this
crystallizes):

* **No row filtering.** Unlike ``noise_barriers`` (which drops
  ``RECOMMENDED``/``PLANNED``/``REMOVED`` rows), every ``rciroads`` row is
  kept — there is no analogous "not really built" status here, and the
  layer has no nulls to drop either.
* **``MultiLineString`` flattened to ``LineString``.** 37 of 40,357 segments
  are non-contiguous multi-part geometries that ``shapely``'s
  ``.project()``/``.interpolate()`` refuse to run on directly (needed for
  the linear-referencing / side-of-centerline logic downstream). Flattened
  once here (``linemerge``, or the longest part if the pieces don't merge
  into one line) rather than handled per lookup in every consumer.
* **``YEAR_``'s ``0`` sentinel (≈16% of rows) becomes ``NA``** — mirrors
  ``noise_barriers``' sentinel handling for ``FED_YRCON``.
* **``DESCRIPT`` is dropped** — confirmed (notebook §2) to duplicate
  ``FUNCLASS`` exactly on every row; not a route name, carries no
  information ``funclass`` doesn't already have.
* **CRS EPSG:3087** (Florida GDL Albers, metres) is preserved, so downstream
  distance / linear-referencing work needs no reprojection.
"""
from __future__ import annotations

import datetime as dt
import json
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString
from shapely.ops import linemerge

from src.regions.florida.sources.road_network.shared import (
    DEFAULT_VERSION,
    processed_metadata_path,
    processed_road_network_path,
    raw_metadata_path,
    raw_shapefile_path,
    validate_version,
)

TARGET_EPSG = 3087

# Data-currency-year sentinel; anything else is a real year (rciroads_jul26's
# only non-sentinel value is 2025 — no plausible-range filter needed the way
# noise_barriers' FED_YRCON needs one).
YEAR_SENTINEL = 0

# Raw column -> tidy name. Only those present in the given release are used.
COLUMN_RENAMES = {
    "ROADWAY": "roadway_id",
    "SEGMENTID": "segmentid",
    "BEGIN_POST": "begin_post",
    "END_POST": "end_post",
    "YEAR_": "year",
    "FUNCLASSCO": "funclassco",
    "FUNCLASS": "funclass",
    "LANE_CNT": "lane_cnt",
    "AADT": "aadt",
    "RTLENGTH": "rtlength_m",
    "RCILENGTH": "rcilength_m",
    "ARCLENGTH": "arclength_m",
    "SHAPE_LEN": "shape_len_m",
    "AUTOID": "autoid",
    "FGDLAQDATE": "fgdlaqdate",
}

# Final column order (each kept only if present).
OUTPUT_COLUMNS = [
    "roadway_id",
    "segmentid",
    "begin_post",
    "end_post",
    "year",
    "funclassco",
    "funclass",
    "lane_cnt",
    "aadt",
    "rtlength_m",
    "rcilength_m",
    "arclength_m",
    "shape_len_m",
    "autoid",
    "fgdlaqdate",
    "geometry",
]


def _flatten_multilinestring(geometry):
    """A plain ``LineString`` unchanged; a ``MultiLineString`` merged into one
    ``LineString`` where its parts are contiguous, else its longest part."""
    if not isinstance(geometry, MultiLineString):
        return geometry
    merged = linemerge(geometry)
    if merged.geom_type == "LineString":
        return merged
    return max(geometry.geoms, key=lambda part: part.length)


def _fgdl_date(value: str | None) -> str | None:
    """Normalise an FGDL/ArcGIS date string to ``YYYY-MM-DD`` where possible."""
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text or None


def parse_fgdl_metadata(xml_path: Path) -> dict[str, str] | None:
    """Best-effort pull of title / publication date / last-modified from the
    ArcGIS-Pro-style FGDL metadata XML. Returns ``None`` if the file is absent
    or unparseable — provenance is a nice-to-have, never fatal."""
    if not xml_path.exists():
        return None
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None

    def first(path: str) -> str | None:
        el = root.find(path)
        return el.text.strip() if el is not None and el.text else None

    info = {
        "title": first(".//resTitle"),
        "publication_date": _fgdl_date(first(".//idCitation/date/pubDate") or first(".//pubDate")),
        "last_modified": _fgdl_date(first("./Esri/ModDate")),
    }
    return {key: value for key, value in info.items() if value} or None


def load_raw_road_network(version: str | None = None) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Read one local FGDL release's shapefile plus its metadata sidecar."""
    resolved = validate_version(version or DEFAULT_VERSION)
    shp_path = raw_shapefile_path(resolved)
    if not shp_path.exists():
        raise FileNotFoundError(
            f"{shp_path} missing — run "
            f"`python -m src.cli florida data road-network fetch --version {resolved}` first."
        )
    with warnings.catch_warnings():
        # The shapefile stores measured (M) geometries; pyogrio drops the M
        # values with a warning. We do not use M (BEGIN_POST/END_POST carry
        # the linear reference as ordinary attributes instead).
        warnings.filterwarnings("ignore", message="Measured .* geometry types are not supported")
        gdf = gpd.read_file(shp_path)

    xml_path = raw_metadata_path(resolved)
    metadata: dict[str, object] = {
        "version": resolved,
        "raw_shapefile": str(shp_path),
        "raw_metadata_xml": str(xml_path) if xml_path.exists() else None,
        "raw_crs": str(gdf.crs),
        "raw_rows": int(len(gdf)),
        "fgdl_metadata": parse_fgdl_metadata(xml_path),
    }
    return gdf, metadata


def preprocess_road_network(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Tidy the columns and flatten ``MultiLineString`` geometries, returning
    a GeoDataFrame in EPSG:3087 with the :data:`OUTPUT_COLUMNS` schema."""
    if gdf.crs is not None and gdf.crs.to_epsg() != TARGET_EPSG:
        gdf = gdf.to_crs(TARGET_EPSG)

    flattened = gdf.geometry.apply(_flatten_multilinestring)
    out = gpd.GeoDataFrame({"geometry": flattened.to_numpy()}, geometry="geometry", crs=gdf.crs)
    for src, dst in COLUMN_RENAMES.items():
        if src in gdf.columns:
            out[dst] = gdf[src].to_numpy()

    if "year" in out.columns:
        year = pd.to_numeric(out["year"], errors="coerce")
        year = year.where(year != YEAR_SENTINEL)
        out["year"] = pd.array(year.to_numpy(), dtype="Int64")
    if "lane_cnt" in out.columns:
        out["lane_cnt"] = pd.array(out["lane_cnt"].round().to_numpy(), dtype="Int64")

    ordered = [column for column in OUTPUT_COLUMNS if column in out.columns]
    remaining = [column for column in out.columns if column not in ordered]
    out = out[ordered + remaining]
    if {"roadway_id", "segmentid"}.issubset(out.columns):
        out = out.sort_values(["roadway_id", "segmentid"]).reset_index(drop=True)
    else:
        out = out.reset_index(drop=True)
    return out


def save_processed_road_network(
    gdf: gpd.GeoDataFrame, metadata: dict[str, object]
) -> dict[str, str]:
    """Write ``road_network.parquet`` and its ``road_network.json`` provenance
    sidecar."""
    parquet_path = processed_road_network_path()
    meta_path = processed_metadata_path()
    gdf.to_parquet(parquet_path, index=False)

    provenance = {
        "source": "fdot_rciroads_fgdl",
        "version": metadata.get("version"),
        "raw_shapefile": metadata.get("raw_shapefile"),
        "raw_metadata_xml": metadata.get("raw_metadata_xml"),
        "fgdl_metadata": metadata.get("fgdl_metadata"),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "crs": f"EPSG:{TARGET_EPSG}",
        "raw_rows": metadata.get("raw_rows"),
        "rows": int(len(gdf)),
        "distinct_roadway_ids": int(gdf["roadway_id"].nunique()) if "roadway_id" in gdf.columns else None,
        "multilinestring_flattened": metadata.get("multilinestring_flattened"),
        "year_known": int(gdf["year"].notna().sum()) if "year" in gdf.columns else 0,
        "columns": list(gdf.columns),
        "parquet": str(parquet_path),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"parquet": str(parquet_path), "metadata": str(meta_path)}


def run_road_network_preprocess(version: str | None = None) -> dict[str, object]:
    """Load one raw release, clean it, and persist the tidy layer + sidecar."""
    raw_gdf, metadata = load_raw_road_network(version)

    metadata["multilinestring_flattened"] = int((raw_gdf.geom_type == "MultiLineString").sum())
    processed = preprocess_road_network(raw_gdf)
    saved = save_processed_road_network(processed, metadata)

    return {
        "version": metadata["version"],
        "raw_shapefile": metadata["raw_shapefile"],
        "raw_rows": metadata["raw_rows"],
        "rows": int(len(processed)),
        "distinct_roadway_ids": int(processed["roadway_id"].nunique()),
        "multilinestring_flattened": metadata["multilinestring_flattened"],
        "year_known": int(processed["year"].notna().sum()) if "year" in processed.columns else 0,
        "crs": f"EPSG:{TARGET_EPSG}",
        "columns": list(processed.columns),
        "fgdl_metadata": metadata["fgdl_metadata"],
        "saved": saved,
    }
