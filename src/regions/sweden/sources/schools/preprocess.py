"""Turn fetched `Skolenhetsregistret` (API v2) detail records into a tidy,
geocoded school-unit table. EPSG:4326, matching this repo's other Sweden
processed layers (`noise_barriers`, `stations` both reproject/build to
WGS84).

One row per school unit, closed (`UPPHORT`) units included, with their
`nedlaggningsdatum`. v2 writes a closed unit's SWEREF 99 coordinates with
a decimal comma (`708435,088`) and an open unit's without decimals; both
parse here. v2 carries no municipality name, only `kommunkod`."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.regions.sweden.sources.schools.fetch import raw_detail_dir
from src.regions.sweden.sources.schools.shared import GRUNDSKOLA_GRADES, schools_paths


GRADE_COLUMNS = [f"ak{grade}" for grade in GRUNDSKOLA_GRADES]
COORD_COLUMNS = ["sweref_e", "sweref_n", "wgs84_lat", "wgs84_lng"]


def load_all_details(root: Path | None = None) -> list[dict]:
    records = []
    for path in sorted(raw_detail_dir(root).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("data"):
            records.append(payload)
    return records


def extract_grundskola_grades(school_type_properties: dict | None) -> dict[str, object]:
    """`ak1`..`ak9` booleans from `schoolTypeProperties.gr.grades`; all
    `None` for a unit without grundskola."""
    grundskola = (school_type_properties or {}).get("gr")
    if grundskola is None:
        return {column: None for column in GRADE_COLUMNS}
    grades = set(grundskola.get("grades") or [])
    return {f"ak{grade}": grade in grades for grade in GRUNDSKOLA_GRADES}


def _visiting_address(addresses: list[dict]) -> dict:
    for address in addresses or []:
        if address.get("type") == "BESOKSADRESS":
            return address
    return {}


def _organizer(payload: dict) -> dict:
    included = payload.get("included")
    if isinstance(included, list):
        included = next((item for item in included if item.get("type") == "organizer"), None)
    return included if isinstance(included, dict) and included.get("type") == "organizer" else {}


def flatten_skolenhet(payload: dict) -> dict:
    data = payload.get("data") or {}
    info = data.get("attributes") or {}
    besoksadress = _visiting_address(info.get("addresses"))
    geodata = besoksadress.get("geoCoordinates") or {}
    organizer = _organizer(payload)
    organizer_info = organizer.get("attributes") or {}
    meta = payload.get("meta") or {}

    row = {
        "skolenhetskod": data.get("schoolUnitCode"),
        "namn": info.get("displayName"),
        "status": info.get("status"),
        "skolenhetstyp": info.get("schoolUnitType"),
        "startdatum": info.get("startdate"),
        "nedlaggningsdatum": info.get("endDate"),
        "senast_andrad": meta.get("modified"),
        "resursskola": info.get("specialSupportSchool"),
        "adress": besoksadress.get("streetAddress"),
        "postnr": besoksadress.get("postalCode"),
        "ort": besoksadress.get("locality"),
        "sweref_e": geodata.get("coordinateSweRefE"),
        "sweref_n": geodata.get("coordinateSweRefN"),
        "wgs84_lat": geodata.get("latitude"),
        "wgs84_lng": geodata.get("longitude"),
        "kommunkod": info.get("municipalityCode"),
        "huvudman_orgnr": organizer.get("organizationNumber"),
        "huvudman_namn": organizer_info.get("displayName"),
        "huvudman_typ": organizer_info.get("organizerType"),
        "skolformer_typer": ",".join(sorted(set(info.get("schoolTypes") or []))),
    }
    row.update(extract_grundskola_grades(info.get("schoolTypeProperties")))
    return row


def _to_number(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.astype("string").str.replace(",", ".", regex=False), errors="coerce")


def parse_point(row: pd.Series) -> Point | None:
    lat, lng = row.get("wgs84_lat"), row.get("wgs84_lng")
    if pd.isna(lat) or pd.isna(lng):
        return None
    return Point(float(lng), float(lat))


def preprocess_schools(details: list[dict]) -> gpd.GeoDataFrame:
    rows = [flatten_skolenhet(payload) for payload in details]
    schools_df = pd.DataFrame.from_records(rows)

    for column in COORD_COLUMNS:
        if column in schools_df.columns:
            schools_df[column] = _to_number(schools_df[column])
    for column in GRADE_COLUMNS:
        if column in schools_df.columns:
            schools_df[column] = schools_df[column].astype("boolean")

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
