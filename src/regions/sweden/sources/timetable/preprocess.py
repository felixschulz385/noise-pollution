from __future__ import annotations

import json

import pandas as pd

from src.regions.sweden.sources.timetable.shared import normalize_timetable_filters, timetable_paths


def as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def flatten_route(items: object) -> str | None:
    route = []
    for item in sorted(as_list(items), key=lambda row: row.get("Order", 9999)):
        name = item.get("LocationName")
        if name:
            route.append(name)
    return " | ".join(route) if route else None


def flatten_key_value(items: object) -> str | None:
    rows = as_list(items)
    return json.dumps(rows, ensure_ascii=False) if rows else None


def extract_train_announcements(payloads: list[dict]) -> list[dict]:
    records = []
    for payload in payloads:
        for result in payload.get("RESPONSE", {}).get("RESULT", []):
            for item in result.get("TrainAnnouncement", []):
                record = dict(item)
                record["FromLocation"] = flatten_route(item.get("FromLocation"))
                record["ToLocation"] = flatten_route(item.get("ToLocation"))
                record["ViaFromLocation"] = flatten_route(item.get("ViaFromLocation"))
                record["ViaToLocation"] = flatten_route(item.get("ViaToLocation"))
                for field in ["Deviation", "ProductInformation", "TypeOfTraffic"]:
                    record[field] = flatten_key_value(item.get(field))
                records.append(record)
    return records


def filter_train_announcements(df: pd.DataFrame, filters: dict | None = None) -> pd.DataFrame:
    filters = normalize_timetable_filters(filters)
    filtered = df.copy()

    if "location_signature" in filters and "LocationSignature" in filtered.columns:
        filtered = filtered.loc[filtered["LocationSignature"].eq(filters["location_signature"])]
    if "advertised_train_ident" in filters and "AdvertisedTrainIdent" in filtered.columns:
        filtered = filtered.loc[filtered["AdvertisedTrainIdent"].astype(str).eq(str(filters["advertised_train_ident"]))]
    if "activity_type" in filters and "ActivityType" in filtered.columns:
        filtered = filtered.loc[filtered["ActivityType"].eq(filters["activity_type"])]
    if "operator" in filters and "Operator" in filtered.columns:
        filtered = filtered.loc[filtered["Operator"].eq(filters["operator"])]
    if "canceled" in filters and "Canceled" in filtered.columns:
        filtered = filtered.loc[filtered["Canceled"].astype(str).str.lower().eq(str(filters["canceled"]).lower())]

    return filtered.reset_index(drop=True)


def preprocess_train_announcements(raw_df: pd.DataFrame, filters: dict | None = None) -> pd.DataFrame:
    df = filter_train_announcements(raw_df, filters)

    if df.empty:
        raise RuntimeError(
            "The configured historical window returned zero rows. Try another date range, smaller chunk size, or a specific location."
        )

    datetime_columns = [
        "AdvertisedTimeAtLocation",
        "DepartureDateOTN",
        "EstimatedTimeAtLocation",
        "ModifiedTime",
        "PlannedEstimatedTimeAtLocation",
        "ScheduledDepartureDateTime",
        "TimeAtLocation",
    ]
    for column in datetime_columns:
        if column in df.columns:
            # Trafikverket responses can mix offsets (+01:00, +02:00, Z) in one column.
            # Normalize to UTC so pandas does not fail on mixed timezone-aware strings.
            df[column] = pd.to_datetime(df[column], errors="coerce", utc=True)

    boolean_columns = [
        "Advertised",
        "Canceled",
        "Deleted",
        "EstimatedTimeIsPreliminary",
        "PlannedEstimatedTimeAtLocationIsValid",
    ]
    for column in boolean_columns:
        if column in df.columns:
            df[column] = df[column].astype("boolean")

    if "NewEquipment" in df.columns:
        df["NewEquipment"] = pd.to_numeric(df["NewEquipment"], errors="coerce")

    df["is_departure"] = df["ActivityType"].eq("Avgang") if "ActivityType" in df.columns else pd.NA
    df["is_arrival"] = df["ActivityType"].eq("Ankomst") if "ActivityType" in df.columns else pd.NA

    if {"EstimatedTimeAtLocation", "AdvertisedTimeAtLocation"}.issubset(df.columns):
        df["estimated_delay_minutes"] = (
            (df["EstimatedTimeAtLocation"] - df["AdvertisedTimeAtLocation"]).dt.total_seconds().div(60)
        )

    if {"TimeAtLocation", "AdvertisedTimeAtLocation"}.issubset(df.columns):
        df["actual_delay_minutes"] = (
            (df["TimeAtLocation"] - df["AdvertisedTimeAtLocation"]).dt.total_seconds().div(60)
        )

    df["service_date"] = df["AdvertisedTimeAtLocation"].dt.date
    df["service_hour"] = df["AdvertisedTimeAtLocation"].dt.hour

    column_order = [
        "ActivityId",
        "LocationSignature",
        "AdvertisedTrainIdent",
        "OperationalTrainNumber",
        "ActivityType",
        "AdvertisedTimeAtLocation",
        "EstimatedTimeAtLocation",
        "TimeAtLocation",
        "estimated_delay_minutes",
        "actual_delay_minutes",
        "TrackAtLocation",
        "FromLocation",
        "ViaFromLocation",
        "ToLocation",
        "ViaToLocation",
        "Operator",
        "InformationOwner",
        "ProductInformation",
        "TypeOfTraffic",
        "Deviation",
        "Canceled",
        "WebLink",
        "WebLinkName",
    ]
    existing_columns = [column for column in column_order if column in df.columns]
    df = df[existing_columns + [column for column in df.columns if column not in existing_columns]]
    sort_columns = [column for column in ["AdvertisedTimeAtLocation", "LocationSignature", "AdvertisedTrainIdent"] if column in df.columns]
    return df.sort_values(sort_columns).reset_index(drop=True)


def save_processed_train_announcements(
    df: pd.DataFrame,
    *,
    csv_name: str = "train_announcements_sample.csv",
    parquet_name: str = "train_announcements_sample.parquet",
) -> dict[str, str]:
    paths = timetable_paths()
    csv_path = paths["processed"] / csv_name
    parquet_path = paths["processed"] / parquet_name
    df.to_csv(csv_path, index=False)

    status = {"csv": str(csv_path), "parquet": ""}
    try:
        df.to_parquet(parquet_path, index=False)
        status["parquet"] = str(parquet_path)
    except Exception as exc:
        status["parquet"] = f"skipped: {exc}"
    return status
