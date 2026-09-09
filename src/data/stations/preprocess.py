from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely import wkt

from src.data.stations.shared import normalize_station_filters, station_paths


def as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_train_stations(payload: dict) -> list[dict]:
    records = []
    for result in payload.get("RESPONSE", {}).get("RESULT", []):
        records.extend(result.get("TrainStation", []))
        if result.get("ERROR"):
            raise RuntimeError(result["ERROR"])
    return records


def parse_station_geometry(record: dict):
    geometry = record.get("Geometry") or {}
    wkt_text = geometry.get("WGS84") or geometry.get("SWEREF99TM")
    if not wkt_text:
        return None
    return wkt.loads(wkt_text)


def filter_train_stations(stations_df: pd.DataFrame, filters: dict | None = None) -> pd.DataFrame:
    normalized_filters = normalize_station_filters(filters)
    filtered = stations_df.copy()

    if "country_code" in normalized_filters and "CountryCode" in filtered.columns:
        filtered = filtered.loc[filtered["CountryCode"].eq(normalized_filters["country_code"])]
    if "location_signature" in normalized_filters and "LocationSignature" in filtered.columns:
        filtered = filtered.loc[filtered["LocationSignature"].eq(normalized_filters["location_signature"])]
    if "advertised" in normalized_filters and "Advertised" in filtered.columns:
        filtered = filtered.loc[filtered["Advertised"].astype(str).str.lower().eq(str(normalized_filters["advertised"]).lower())]
    if "prognosticated" in normalized_filters and "Prognosticated" in filtered.columns:
        filtered = filtered.loc[
            filtered["Prognosticated"].astype(str).str.lower().eq(str(normalized_filters["prognosticated"]).lower())
        ]

    return filtered.reset_index(drop=True)


def preprocess_train_stations(records: list[dict], filters: dict | None = None) -> gpd.GeoDataFrame:
    stations_df = pd.DataFrame.from_records(records)
    stations_df = filter_train_stations(stations_df, filters)
    stations_df["CountyNo"] = stations_df.get("CountyNo", pd.Series(dtype=object)).apply(as_list)
    stations_df["PlatformLine"] = stations_df.get("PlatformLine", pd.Series(dtype=object)).apply(as_list)
    stations_df["county_numbers"] = stations_df["CountyNo"].apply(lambda values: ",".join(map(str, values)) if values else None)
    stations_df["platform_lines"] = stations_df["PlatformLine"].apply(
        lambda values: ",".join(map(str, values)) if values else None
    )
    stations_df["geometry_wkt"] = stations_df["Geometry"].apply(
        lambda item: (item or {}).get("WGS84") or (item or {}).get("SWEREF99TM")
    )
    stations_df["ModifiedTime"] = pd.to_datetime(stations_df.get("ModifiedTime"), errors="coerce")

    stations_gdf = gpd.GeoDataFrame(
        stations_df.drop(columns=[column for column in ["Geometry"] if column in stations_df.columns]).copy(),
        geometry=stations_df.apply(parse_station_geometry, axis=1),
        crs="EPSG:4326",
    )

    column_order = [
        "LocationSignature",
        "AdvertisedLocationName",
        "OfficialLocationName",
        "AdvertisedShortLocationName",
        "CountryCode",
        "PrimaryLocationCode",
        "Advertised",
        "Prognosticated",
        "county_numbers",
        "platform_lines",
        "LocationInformationText",
        "ModifiedTime",
        "geometry_wkt",
        "geometry",
    ]
    existing_columns = [column for column in column_order if column in stations_gdf.columns]
    stations_gdf = stations_gdf[existing_columns + [column for column in stations_gdf.columns if column not in existing_columns]]
    return stations_gdf.sort_values(["LocationSignature", "AdvertisedLocationName"], na_position="last").reset_index(drop=True)


def save_processed_stations(
    stations_gdf: gpd.GeoDataFrame,
    *,
    geojson_name: str = "train_stations_sweden.geojson",
    csv_name: str = "train_stations_sweden.csv",
) -> dict[str, str]:
    paths = station_paths()
    geojson_path = paths["processed"] / geojson_name
    csv_path = paths["processed"] / csv_name
    stations_gdf.to_file(geojson_path, driver="GeoJSON")
    stations_gdf.drop(columns="geometry").to_csv(csv_path, index=False)
    return {"geojson": str(geojson_path), "csv": str(csv_path)}
