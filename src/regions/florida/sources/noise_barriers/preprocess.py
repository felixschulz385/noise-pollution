"""Preprocess step for the Florida noise-barrier source.

Turns one raw FGDL release (``noise_barriers_<version>.gdb``, written by
``fetch``) into a single tidy GeoParquet layer of *physically-present* walls,
ready to be joined to school metadata and the street network in the ``schools``
source to derive per-school barrier treatment timing.

Design decisions (see ``docs/data/florida/README.md`` and the exploratory
notebook ``src/experiments/florida/barriers.ipynb`` this crystallizes):

* **One snapshot, construction year as the event date.** Treatment timing comes
  from ``FED_YRCON`` on a single release, not from diffing successive FGDL
  snapshots. Walls with a sentinel / out-of-range year are kept with
  ``built_year = NA``; dating them is left to the downstream step. Multi-release
  diffing is a possible later robustness check, not done here.
* **Physically-present walls only.** ``TYPE in {CONSTRUCTED, REPLACED}`` becomes
  ``category = "fdot_barrier"``; ``PRIVATE WALL`` / ``PERIMETER WALL`` are kept
  in the same file as ``category = "other_wall"`` (potential noise-shielding
  confounders); ``RECOMMENDED`` / ``PLANNED`` / ``REMOVED`` are dropped.
* **CRS EPSG:3087** (Florida GDL Albers, metres) is preserved, so downstream
  distance / buffer / network work needs no reprojection.
* **Schema drift between releases is tolerated** — only columns present in the
  given release are carried through.
"""
from __future__ import annotations

import datetime as dt
import json
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.florida.sources.noise_barriers.shared import (
    DEFAULT_VERSION,
    processed_barriers_path,
    processed_metadata_path,
    raw_gdb_path,
    raw_metadata_path,
    validate_version,
)

TARGET_EPSG = 3087
FT_TO_M = 0.3048

# Plausible construction-year window; anything outside it (including the 9999 /
# 0 sentinels) becomes NA. Fixed rather than ``now()``-derived so runs are
# reproducible.
BUILT_YEAR_MIN = 1990
BUILT_YEAR_MAX = 2026

# TYPE -> category. Any TYPE not listed here is dropped.
FDOT_BARRIER_TYPES = ("CONSTRUCTED BARRIERS", "REPLACED BARRIERS")
OTHER_WALL_TYPES = ("PRIVATE WALL", "PERIMETER WALL")

# FLAG value marking a programmed / under-construction wall at snapshot time.
PROGRAMMED_FLAG = "FNV"

# Raw column -> tidy name. Only those present in the given release are used.
COLUMN_RENAMES = {
    "GCID": "gcid",
    "TYPE": "type",
    "FLAG": "flag",
    "FDOT_DISTR": "fdot_distr",
    "FED_ROUTE": "fed_route",
    "FED_COUNTY": "fed_county",
    "BLOC_SIDE": "bloc_side",
    "BLOC_BND": "bloc_bnd",
    "BLOC_ONRTE": "bloc_onrte",
    "FED_NAC": "fed_nac",
    "FED_ANR": "fed_anr",
    "BEN_RCPTRS": "ben_rcptrs",
    "TOT_RCPTRS": "tot_rcptrs",
    "FED_MATERL": "fed_materl",
    "FHWA_SUB_NOTES": "fhwa_sub_notes",
}

# Final column order (each kept only if present).
OUTPUT_COLUMNS = [
    "gcid",
    "category",
    "type",
    "flag",
    "is_programmed",
    "built_year",
    "fdot_distr",
    "fed_route",
    "fed_county",
    "bloc_side",
    "bloc_bnd",
    "bloc_onrte",
    "fed_nac",
    "fed_anr",
    "ben_rcptrs",
    "tot_rcptrs",
    "fed_materl",
    "fhwa_sub_notes",
    "height_m",
    "length_m",
    "seg_len_m",
    "geometry",
]


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


def load_raw_barriers(version: str | None = None) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Read one local FGDL release's geodatabase plus its metadata sidecar."""
    resolved = validate_version(version or DEFAULT_VERSION)
    gdb_path = raw_gdb_path(resolved)
    if not gdb_path.exists():
        raise FileNotFoundError(
            f"{gdb_path} missing — run "
            f"`python -m src.cli florida data noise-barriers fetch --version {resolved}` first."
        )
    with warnings.catch_warnings():
        # The GDB stores measured (M) geometries; pyogrio drops the M values
        # with a warning. We do not use M.
        warnings.filterwarnings("ignore", message="Measured .* geometry types are not supported")
        gdf = gpd.read_file(gdb_path)

    xml_path = raw_metadata_path(resolved)
    metadata: dict[str, object] = {
        "version": resolved,
        "raw_gdb": str(gdb_path),
        "raw_metadata_xml": str(xml_path) if xml_path.exists() else None,
        "raw_crs": str(gdf.crs),
        "raw_rows": int(len(gdf)),
        "fgdl_metadata": parse_fgdl_metadata(xml_path),
    }
    return gdf, metadata


def _category(type_series: pd.Series) -> pd.Series:
    mapping = {value: "fdot_barrier" for value in FDOT_BARRIER_TYPES}
    mapping.update({value: "other_wall" for value in OTHER_WALL_TYPES})
    return type_series.map(mapping)


def preprocess_barriers(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filter to physically-present walls, tidy the columns, and return a
    GeoDataFrame in EPSG:3087 with the :data:`OUTPUT_COLUMNS` schema."""
    if gdf.crs is not None and gdf.crs.to_epsg() != TARGET_EPSG:
        gdf = gdf.to_crs(TARGET_EPSG)

    keep_types = set(FDOT_BARRIER_TYPES) | set(OTHER_WALL_TYPES)
    walls = gdf[gdf["TYPE"].isin(keep_types)].copy()

    # Drop exact-geometry duplicates (a handful recur among constructed walls).
    walls = walls[~walls.geometry.to_wkb().duplicated()].copy()

    out = gpd.GeoDataFrame(
        {"geometry": walls.geometry.to_numpy()}, geometry="geometry", crs=walls.crs
    )
    for src, dst in COLUMN_RENAMES.items():
        if src in walls.columns:
            out[dst] = walls[src].to_numpy()

    out["category"] = _category(walls["TYPE"]).to_numpy()
    if "FLAG" in walls.columns:
        out["is_programmed"] = walls["FLAG"].eq(PROGRAMMED_FLAG).to_numpy()

    if "FED_YRCON" in walls.columns:
        year = pd.to_numeric(walls["FED_YRCON"], errors="coerce")
        year = year.where(year.between(BUILT_YEAR_MIN, BUILT_YEAR_MAX))
        out["built_year"] = pd.array(year.round().to_numpy(), dtype="Int64")
    if "FED_HEIGHT" in walls.columns:
        out["height_m"] = (pd.to_numeric(walls["FED_HEIGHT"], errors="coerce") * FT_TO_M).round(2).to_numpy()
    if "FED_LENGTH" in walls.columns:
        out["length_m"] = (pd.to_numeric(walls["FED_LENGTH"], errors="coerce") * FT_TO_M).round(1).to_numpy()
    if "SHAPE_Length" in walls.columns:
        out["seg_len_m"] = pd.to_numeric(walls["SHAPE_Length"], errors="coerce").round(1).to_numpy()
    else:
        out["seg_len_m"] = out.geometry.length.round(1)

    ordered = [column for column in OUTPUT_COLUMNS if column in out.columns]
    remaining = [column for column in out.columns if column not in ordered]
    out = out[ordered + remaining]
    if "gcid" in out.columns:
        out = out.sort_values("gcid").reset_index(drop=True)
    else:
        out = out.reset_index(drop=True)
    return out


def save_processed_barriers(
    gdf: gpd.GeoDataFrame, metadata: dict[str, object]
) -> dict[str, str]:
    """Write ``barriers.parquet`` and its ``barriers.json`` provenance sidecar."""
    parquet_path = processed_barriers_path()
    meta_path = processed_metadata_path()
    gdf.to_parquet(parquet_path, index=False)

    provenance = {
        "source": "fdot_noise_barriers_fgdl",
        "version": metadata.get("version"),
        "raw_gdb": metadata.get("raw_gdb"),
        "raw_metadata_xml": metadata.get("raw_metadata_xml"),
        "fgdl_metadata": metadata.get("fgdl_metadata"),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "crs": f"EPSG:{TARGET_EPSG}",
        "built_year_range": [BUILT_YEAR_MIN, BUILT_YEAR_MAX],
        "raw_rows": metadata.get("raw_rows"),
        "rows": int(len(gdf)),
        "rows_by_category": {str(k): int(v) for k, v in gdf["category"].value_counts().items()},
        "exact_geometry_duplicates_dropped": metadata.get("duplicates_dropped"),
        "built_year_known": int(gdf["built_year"].notna().sum()) if "built_year" in gdf.columns else 0,
        "columns": list(gdf.columns),
        "parquet": str(parquet_path),
    }
    meta_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"parquet": str(parquet_path), "metadata": str(meta_path)}


def run_barrier_preprocess(version: str | None = None) -> dict[str, object]:
    """Load one raw release, clean it, and persist the tidy layer + sidecar."""
    raw_gdf, metadata = load_raw_barriers(version)

    keep_types = set(FDOT_BARRIER_TYPES) | set(OTHER_WALL_TYPES)
    kept = int(raw_gdf["TYPE"].isin(keep_types).sum())

    processed = preprocess_barriers(raw_gdf)
    metadata["duplicates_dropped"] = kept - int(len(processed))
    saved = save_processed_barriers(processed, metadata)

    return {
        "version": metadata["version"],
        "raw_gdb": metadata["raw_gdb"],
        "raw_rows": metadata["raw_rows"],
        "rows": int(len(processed)),
        "rows_by_category": {str(k): int(v) for k, v in processed["category"].value_counts().items()},
        "duplicates_dropped": metadata["duplicates_dropped"],
        "built_year_known": int(processed["built_year"].notna().sum()) if "built_year" in processed.columns else 0,
        "crs": f"EPSG:{TARGET_EPSG}",
        "columns": list(processed.columns),
        "fgdl_metadata": metadata["fgdl_metadata"],
        "saved": saved,
    }
