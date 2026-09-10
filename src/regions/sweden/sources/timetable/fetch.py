from __future__ import annotations

import json
from textwrap import dedent
from pathlib import Path

import pandas as pd

from src.regions.sweden.sources._trafikverket import read_api_key, trafikverket_api_call_json
from src.regions.sweden.sources.timetable.shared import TIMETABLE_FIELDS, normalize_timetable_filters, timetable_paths


def build_train_announcement_request(
    api_key: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    limit: int,
    filters: dict | None = None,
) -> str:
    start_ts = pd.Timestamp(start).isoformat()
    end_ts = pd.Timestamp(end).isoformat()
    normalized_filters = normalize_timetable_filters(filters)

    filter_clauses = [
        f'<GTE name="AdvertisedTimeAtLocation" value="{start_ts}" />',
        f'<LT name="AdvertisedTimeAtLocation" value="{end_ts}" />',
        '<EQ name="Deleted" value="false" />',
    ]
    if normalized_filters.get("location_signature"):
        filter_clauses.append(
            f'<EQ name="LocationSignature" value="{normalized_filters["location_signature"]}" />'
        )
    if normalized_filters.get("advertised_train_ident"):
        filter_clauses.append(
            f'<EQ name="AdvertisedTrainIdent" value="{normalized_filters["advertised_train_ident"]}" />'
        )
    if normalized_filters.get("activity_type"):
        filter_clauses.append(f'<EQ name="ActivityType" value="{normalized_filters["activity_type"]}" />')
    if normalized_filters.get("operator"):
        filter_clauses.append(f'<EQ name="Operator" value="{normalized_filters["operator"]}" />')
    if normalized_filters.get("canceled") is not None:
        canceled = str(normalized_filters["canceled"]).lower()
        filter_clauses.append(f'<EQ name="Canceled" value="{canceled}" />')

    include_xml = "\n".join(f"      <INCLUDE>{field}</INCLUDE>" for field in TIMETABLE_FIELDS)
    filter_xml = "\n".join(f"        {item}" for item in filter_clauses)

    return dedent(
        f"""
        <REQUEST>
          <LOGIN authenticationkey=\"{api_key}\" />
          <QUERY objecttype=\"TrainAnnouncement\" schemaversion=\"1.9\" orderby=\"AdvertisedTimeAtLocation\" limit=\"{limit}\">
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


def split_time_range(start: pd.Timestamp, end: pd.Timestamp, chunk_size: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    boundaries = list(pd.date_range(start=start, end=end, freq=chunk_size))
    if not boundaries or boundaries[0] != start:
        boundaries = [start] + boundaries
    if boundaries[-1] != end:
        boundaries.append(end)
    return list(zip(boundaries[:-1], boundaries[1:]))


def fetch_train_announcements(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    chunk_size: str,
    limit: int,
    filters: dict | None = None,
) -> tuple[list[dict], pd.DataFrame]:
    api_key = read_api_key()
    payloads = []
    chunk_log = []
    filters = normalize_timetable_filters(filters)

    for chunk_start, chunk_end in split_time_range(start, end, chunk_size):
        request_xml = build_train_announcement_request(
            api_key,
            chunk_start,
            chunk_end,
            limit=limit,
            filters=filters,
        )
        payload = trafikverket_api_call_json(request_xml)
        payloads.append(payload)

        result_items = payload.get("RESPONSE", {}).get("RESULT", [])
        records = result_items[0].get("TrainAnnouncement", []) if result_items else []
        chunk_log.append(
            {
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
                "records": len(records),
                "truncated": len(records) >= limit,
            }
        )

    return payloads, pd.DataFrame(chunk_log)


def save_raw_payloads(payloads: list[dict], filename: str = "train_announcements_sample.json") -> str:
    paths = timetable_paths()
    raw_path = paths["raw"] / filename
    raw_path.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(raw_path)


def load_raw_payloads(filename: str = "train_announcements_sample.json") -> list[dict]:
    paths = timetable_paths()
    raw_path = Path(paths["raw"] / filename)
    return json.loads(raw_path.read_text(encoding="utf-8"))
