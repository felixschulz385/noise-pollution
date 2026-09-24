"""Tests for `road_network/preprocess.py` -- no network, synthetic data."""
import geopandas as gpd
from shapely.geometry import LineString

from src.regions.sweden.sources.road_network.preprocess import preprocess_road_network


def _raw_road_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "ELEMENT_ID": ["a", "b", "c"],
            "VALID_FROM": [20200101, 20200101, 20200101],
            "VALID_TO": [99991231, 99991231, 20240101],  # c is not "always valid"
            "START_MEASURE": [0.0, 0.0, 0.0],
            "END_MEASURE": [1.0, 1.0, 1.0],
            "EXTENT_LENGTH": [100.0, 250.0, 50.0],
            "Nattyp": ["bilnät", "bilnät", "bilnät"],
        },
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (350, 0)]),
            LineString([(0, 0), (50, 0)]),
        ],
        crs="EPSG:3006",
    )


def test_preprocess_road_network_drops_non_current_rows():
    roads = preprocess_road_network(_raw_road_gdf())
    assert list(roads["element_id"]) == ["a", "b"]


def test_preprocess_road_network_uses_local_extent_as_km_from_to():
    roads = preprocess_road_network(_raw_road_gdf())
    row = roads[roads["element_id"] == "b"].iloc[0]
    assert row["km_from_m"] == 0.0
    assert row["km_to_m"] == 250.0


def test_preprocess_road_network_renames_and_keeps_expected_columns():
    roads = preprocess_road_network(_raw_road_gdf())
    assert set(roads.columns) == {
        "element_id",
        "network_type",
        "km_from_m",
        "km_to_m",
        "start_measure",
        "end_measure",
        "extent_length_m",
        "valid_from",
        "geometry",
    }
