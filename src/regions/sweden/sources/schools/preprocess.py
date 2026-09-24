"""Turn fetched `Skolenhetsregistret` detail records into a tidy, geocoded
school-unit table. EPSG:4326, matching this repo's other Sweden processed
layers (`noise_barriers`, `stations` both reproject/build to WGS84)."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.regions.sweden.sources.schools.fetch import raw_detail_dir
from src.regions.sweden.sources.schools.shared import GRUNDSKOLA_GRADE_FIELDS, schools_paths


def load_all_details(root: Path | None = None) -> list[dict]:
    records = []
    for path in sorted(raw_detail_dir(root).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        info = payload.get("SkolenhetInfo")
        if info:
            records.append(info)
    return records


def extract_grundskola_grades(skolformer: list[dict]) -> dict[str, object]:
    for entry in skolformer or []:
        if entry.get("type") == "Grundskola" or entry.get("SkolformKod") == "11":
            return {field.lower(): entry.get(field) for field in GRUNDSKOLA_GRADE_FIELDS}
    return {field.lower(): None for field in GRUNDSKOLA_GRADE_FIELDS}


def flatten_skolenhet(info: dict) -> dict:
    besoksadress = info.get("Besoksadress") or {}
    geodata = besoksadress.get("GeoData") or {}
    kommun = info.get("Kommun") or {}
    huvudman = info.get("Huvudman") or {}
    skolformer = info.get("Skolformer") or []

    row = {
        "skolenhetskod": info.get("Skolenhetskod"),
        "namn": info.get("Namn"),
        "status": info.get("Status"),
        "startdatum": info.get("Startdatum"),
        "skolenhet_valid_from": info.get("Skolenhet_ValidFrom"),
        "resursskola": info.get("Resursskola"),
        "adress": besoksadress.get("Adress"),
        "postnr": besoksadress.get("Postnr"),
        "ort": besoksadress.get("Ort"),
        "sweref_e": geodata.get("Koordinat_SweRef_E"),
        "sweref_n": geodata.get("Koordinat_SweRef_N"),
        "wgs84_lat": geodata.get("Koordinat_WGS84_Lat"),
        "wgs84_lng": geodata.get("Koordinat_WGS84_Lng"),
        "kommunkod": kommun.get("Kommunkod"),
        "kommun_namn": kommun.get("Namn"),
        "huvudman_orgnr": huvudman.get("PeOrgNr"),
        "huvudman_namn": huvudman.get("Namn"),
        "huvudman_typ": huvudman.get("Typ"),
        "skolformer_typer": ",".join(sorted({entry.get("type") for entry in skolformer if entry.get("type")})),
    }
    row.update(extract_grundskola_grades(skolformer))
    return row


def parse_point(row: pd.Series) -> Point | None:
    lat, lng = row.get("wgs84_lat"), row.get("wgs84_lng")
    if pd.isna(lat) or pd.isna(lng):
        return None
    try:
        return Point(float(lng), float(lat))
    except (TypeError, ValueError):
        return None


def preprocess_schools(details: list[dict]) -> gpd.GeoDataFrame:
    rows = [flatten_skolenhet(info) for info in details]
    schools_df = pd.DataFrame.from_records(rows)

    for numeric_column in ["sweref_e", "sweref_n", "wgs84_lat", "wgs84_lng"]:
        if numeric_column in schools_df.columns:
            schools_df[numeric_column] = pd.to_numeric(schools_df[numeric_column], errors="coerce")
    for grade_field in [field.lower() for field in GRUNDSKOLA_GRADE_FIELDS]:
        if grade_field in schools_df.columns:
            schools_df[grade_field] = schools_df[grade_field].astype("boolean")

    schools_gdf = gpd.GeoDataFrame(
        schools_df,
        geometry=schools_df.apply(parse_point, axis=1) if len(schools_df) else [],
        crs="EPSG:4326",
    )
    return schools_gdf.sort_values("skolenhetskod", na_position="last").reset_index(drop=True)


def save_processed_schools(
    schools_gdf: gpd.GeoDataFrame,
    *,
    geojson_name: str = "schools.geojson",
    csv_name: str = "schools.csv",
    root: Path | None = None,
) -> dict[str, str]:
    paths = schools_paths(root)
    geojson_path = paths["processed"] / geojson_name
    csv_path = paths["processed"] / csv_name
    schools_gdf.to_file(geojson_path, driver="GeoJSON")
    schools_gdf.drop(columns="geometry").to_csv(csv_path, index=False)
    return {"geojson": str(geojson_path), "csv": str(csv_path)}
