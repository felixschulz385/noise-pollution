from __future__ import annotations

from pathlib import Path
from typing import Any

from src.regions.sweden.sources._layout import domain_dirs


STATION_FIELDS = [
    "Advertised",
    "AdvertisedLocationName",
    "AdvertisedShortLocationName",
    "CountryCode",
    "CountyNo",
    "Geometry",
    "LocationInformationText",
    "LocationSignature",
    "ModifiedTime",
    "OfficialLocationName",
    "PlatformLine",
    "PrimaryLocationCode",
    "Prognosticated",
]


def station_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("stations", root)


STATION_FILTER_FIELDS = [
    "country_code",
    "location_signature",
    "advertised",
    "prognosticated",
]


def normalize_station_filters(filters: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    merged = dict(filters or {})
    merged.update({key: value for key, value in kwargs.items() if value is not None})
    normalized = {key: merged.get(key) for key in STATION_FILTER_FIELDS if merged.get(key) is not None}
    if "country_code" not in normalized:
        normalized["country_code"] = "SE"
    return normalized
