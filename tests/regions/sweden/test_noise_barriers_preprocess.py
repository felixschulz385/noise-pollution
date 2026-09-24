"""`built_year` sentinel handling -- found live 2026-09-15 while building
`schools/assemble.py`: Trafikverket's "year not recorded" placeholder is
`1900` for road barriers (51% of the real 2172-row dataset!) and `0` for
rail barriers (real non-sentinel ranges: road 1950-2025, rail 1989-2025).
Left uncleaned, `built_year` would silently read as a real construction
year for roughly half of all road barriers."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.regions.sweden.sources.noise_barriers.preprocess import preprocess_noise_barriers


def _raw_gdf(built_years: list[int]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "ELEMENT_ID": [f"e{i}" for i in range(len(built_years))],
            "VALID_FROM": ["20200101"] * len(built_years),
            "VALID_TO": ["99991231"] * len(built_years),
            "Byggar": built_years,
        },
        geometry=[LineString([(i, 0), (i, 1)]) for i in range(len(built_years))],
        crs="EPSG:4326",
    )


def test_road_built_year_1900_sentinel_becomes_na():
    gdf = preprocess_noise_barriers(_raw_gdf([1900, 2019, 1950]), "road")
    assert pd.isna(gdf["built_year"].iloc[0])
    assert gdf["built_year"].iloc[1:].tolist() == [2019, 1950]


def test_rail_built_year_0_sentinel_becomes_na():
    gdf = preprocess_noise_barriers(_raw_gdf([0, 2005, 1989]), "rail")
    assert pd.isna(gdf["built_year"].iloc[0])
    assert gdf["built_year"].iloc[1:].tolist() == [2005, 1989]


def test_road_built_year_0_is_not_treated_as_the_road_sentinel():
    # 0 is rail's sentinel, not road's -- road's own sentinel is 1900.
    gdf = preprocess_noise_barriers(_raw_gdf([0]), "road")
    assert gdf["built_year"].tolist() == [0]


def test_rail_distance_from_track_center_999_sentinel_becomes_na():
    raw = _raw_gdf([2005, 2005])
    raw["Avstand_fr_sparmitt_m"] = [999, 4.8]
    gdf = preprocess_noise_barriers(raw, "rail")
    assert pd.isna(gdf["distance_from_track_center_m"].iloc[0])
    assert gdf["distance_from_track_center_m"].iloc[1] == 4.8
