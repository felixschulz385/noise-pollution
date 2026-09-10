from __future__ import annotations

import json
from textwrap import dedent
from pathlib import Path

from src.regions.sweden.sources._trafikverket import read_api_key, trafikverket_api_call_json
from src.regions.sweden.sources.stations.shared import STATION_FIELDS, normalize_station_filters, station_paths


def build_train_station_request(api_key: str, filters: dict | None = None) -> str:
    normalized_filters = normalize_station_filters(filters)
    include_xml = "\n".join(f"      <INCLUDE>{field}</INCLUDE>" for field in STATION_FIELDS)
    filter_clauses = [
        f'<EQ name="CountryCode" value="{normalized_filters["country_code"]}" />',
        '<EQ name="Deleted" value="false" />',
    ]
    if normalized_filters.get("location_signature"):
        filter_clauses.append(
            f'<EQ name="LocationSignature" value="{normalized_filters["location_signature"]}" />'
        )
    if normalized_filters.get("advertised") is not None:
        filter_clauses.append(
            f'<EQ name="Advertised" value="{str(normalized_filters["advertised"]).lower()}" />'
        )
    if normalized_filters.get("prognosticated") is not None:
        filter_clauses.append(
            f'<EQ name="Prognosticated" value="{str(normalized_filters["prognosticated"]).lower()}" />'
        )
    filter_xml = "\n".join(f"        {item}" for item in filter_clauses)
    return dedent(
        f"""
        <REQUEST>
          <LOGIN authenticationkey=\"{api_key}\" />
          <QUERY objecttype=\"TrainStation\" namespace=\"rail.infrastructure\" schemaversion=\"1.5\" orderby=\"LocationSignature\" limit=\"10000\">
            <FILTER>
              <AND>
{filter_xml}
              </AND>
            </FILTER>
{include_xml}
          </QUERY>
        </REQUEST>
        """
    ).strip()


def fetch_stations(filters: dict | None = None) -> dict:
    api_key = read_api_key()
    request_xml = build_train_station_request(api_key, filters=filters)
    return trafikverket_api_call_json(request_xml)


def save_raw_stations(payload: dict, filename: str = "train_stations_sweden.json") -> str:
    paths = station_paths()
    raw_path = paths["raw"] / filename
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(raw_path)


def load_raw_stations(filename: str = "train_stations_sweden.json") -> dict:
    paths = station_paths()
    raw_path = Path(paths["raw"] / filename)
    return json.loads(raw_path.read_text(encoding="utf-8"))
