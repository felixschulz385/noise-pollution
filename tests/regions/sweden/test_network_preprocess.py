"""Tests for the rail network's `preprocess_network_tracks` (the candidate
network for `schools`' algorithms 4/5) -- no network, synthetic data."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from src.regions.sweden.sources.network.preprocess import parse_km, preprocess_network_tracks


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("66+280", 66280.0),
        ("0+0", 0.0),
        ("123+45", 123045.0),
        (None, None),
        ("not a km value", None),
        ("", None),
    ],
)
def test_parse_km(raw_value, expected):
    assert parse_km(raw_value) == expected


def _raw_tracks_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "ELEMENT_ID": ["a", "a", "b", "c", "d"],
            "Bandel": ["100", "100", "200", None, "300"],
            "Bandelnamn": ["Ingår ej i bandelsindelning"] * 2 + [None, "X", "Y"],
            "Status": ["Öppen", "Öppen", "Nedlagd", "Öppen", "Öppen"],
            "KmFr": ["10+0", "10+500", "0+0", "5+0", "1+0"],
            "KmTi": ["10+500", "11+0", "1+0", "6+0", "2+0"],
            "START_MEASURE": [0.0, 0.5, 0.0, 0.0, 0.0],
            "END_MEASURE": [0.5, 1.0, 1.0, 1.0, 1.0],
            "SEGMENT_LENGTH": [500.0, 500.0, 1000.0, 1000.0, 1000.0],
            "VALID_FROM": [20260101] * 5,
        },
        geometry=[
            LineString([(0, 0), (500, 0)]),
            LineString([(500, 0), (1000, 0)]),
            LineString([(0, 0), (0, 1000)]),
            LineString([(0, 0), (1000, 1000)]),
            LineString([(2000, 0), (3000, 0)]),
        ],
        crs="EPSG:3006",
    )


def test_preprocess_network_tracks_drops_closed_and_null_bandel_rows():
    tracks = preprocess_network_tracks(_raw_tracks_gdf())
    # row "b" (Nedlagd/closed) and row "c" (Bandel is None) are both dropped.
    assert list(tracks["bandel"]) == ["100", "100", "300"]


def test_preprocess_network_tracks_parses_km_columns_to_metres():
    tracks = preprocess_network_tracks(_raw_tracks_gdf())
    row = tracks.iloc[0]
    assert row["km_from_m"] == 10000.0
    assert row["km_to_m"] == 10500.0


def test_preprocess_network_tracks_renames_columns():
    tracks = preprocess_network_tracks(_raw_tracks_gdf())
    assert set(tracks.columns) == {
        "element_id",
        "bandel",
        "bandel_namn",
        "km_from_m",
        "km_to_m",
        "start_measure",
        "end_measure",
        "segment_length_m",
        "valid_from",
        "geometry",
    }
