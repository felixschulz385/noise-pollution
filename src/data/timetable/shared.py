from __future__ import annotations

from pathlib import Path
from typing import Any

from src.data.shared.paths import ensure_domain_dirs


TIMETABLE_FIELDS = [
    "ActivityId",
    "ActivityType",
    "Advertised",
    "AdvertisedTimeAtLocation",
    "AdvertisedTrainIdent",
    "Canceled",
    "Deleted",
    "DepartureDateOTN",
    "Deviation",
    "EstimatedTimeAtLocation",
    "EstimatedTimeIsPreliminary",
    "FromLocation",
    "InformationOwner",
    "LocationSignature",
    "ModifiedTime",
    "NewEquipment",
    "Operator",
    "OperationalTrainNumber",
    "PlannedEstimatedTimeAtLocation",
    "PlannedEstimatedTimeAtLocationIsValid",
    "ProductInformation",
    "ScheduledDepartureDateTime",
    "TimeAtLocation",
    "ToLocation",
    "TrackAtLocation",
    "TypeOfTraffic",
    "ViaFromLocation",
    "ViaToLocation",
    "WebLink",
    "WebLinkName",
]


def timetable_paths(root: Path | None = None) -> dict[str, Path]:
    return ensure_domain_dirs("timetable", root)


TIMETABLE_FILTER_FIELDS = [
    "location_signature",
    "advertised_train_ident",
    "activity_type",
    "operator",
    "canceled",
]


def normalize_timetable_filters(filters: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    merged = dict(filters or {})
    merged.update({key: value for key, value in kwargs.items() if value is not None})
    return {key: merged.get(key) for key in TIMETABLE_FILTER_FIELDS if merged.get(key) is not None}
