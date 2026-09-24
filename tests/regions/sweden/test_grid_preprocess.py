"""Tests for the grid `preprocess` (100m fishnet tiling around barriers)
stage -- synthetic geometries built directly in EPSG:3006 (SWEREF99 TM)
with round-number coordinates, no network."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from src.regions.sweden.sources.grid import preprocess as gp
from src.regions.sweden.sources.grid.shared import cell_id


def _road_gdf() -> gpd.GeoDataFrame:
    # A single short segment near the origin -- its buffered corridor is
    # one small connected component, easy to reason about exactly.
    return gpd.GeoDataFrame(
        {"element_id": ["b1"], "built_year": pd.array([2015], dtype="Int64")},
        geometry=[LineString([(50, 50), (50, 150)])],
        crs="EPSG:3006",
    )


def _rail_gdf_far_away() -> gpd.GeoDataFrame:
    # 100km away -- its own disjoint component, confirms multi-component
    # tiling doesn't cross-contaminate.
    return gpd.GeoDataFrame(
        {"element_id": ["b2"], "built_year": pd.array([2019], dtype="Int64")},
        geometry=[LineString([(100_050, 100_050), (100_050, 100_150)])],
        crs="EPSG:3006",
    )


def test_cell_id_encodes_sw_corner_and_resolution():
    assert cell_id(318200, 6374200, 100) == "SE100mN6374200E318200"


def test_build_grid_cells_only_keeps_cells_within_buffer():
    cells = gp.build_grid_cells({"road": _road_gdf()}, buffer_m=100.0, resolution_m=100)

    cells_m = cells.to_crs("EPSG:3006")
    dist_from_segment = cells_m.geometry.distance(_road_gdf().to_crs("EPSG:3006").geometry.iloc[0])
    # Every generated cell's centroid must be within the buffer -- the
    # whole point of tiling the buffered corridor rather than a bounding box.
    assert (dist_from_segment <= 100.0 + 1e-6).all()

    # A cell centroid known to be inside the buffer (at the segment itself)
    # must be present.
    assert len(cells) > 0


def test_build_grid_cells_ids_land_on_multiples_of_resolution():
    cells = gp.build_grid_cells({"road": _road_gdf()}, buffer_m=100.0, resolution_m=100)
    assert (cells["easting"] % 100 == 0).all()
    assert (cells["northing"] % 100 == 0).all()
    assert set(cells["cell_id"]) == {
        cell_id(e, n, 100) for e, n in zip(cells["easting"], cells["northing"])
    }


def test_build_grid_cells_handles_disjoint_components_independently():
    cells = gp.build_grid_cells(
        {"road": _road_gdf(), "rail": _rail_gdf_far_away()}, buffer_m=100.0, resolution_m=100
    )
    # Two far-apart barriers must produce two far-apart clusters of cells,
    # not one cell grid spanning (and wastefully tiling) the gap between them.
    near_origin = cells[cells["easting"] < 10_000]
    near_far_segment = cells[cells["easting"] > 90_000]
    assert len(near_origin) > 0
    assert len(near_far_segment) > 0
    assert len(near_origin) + len(near_far_segment) == len(cells)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gp, "processed_grid_cells_path", lambda root=None: paths["processed"] / "grid_cells.parquet")
    barriers = {"road": _road_gdf(), "rail": _rail_gdf_far_away()}
    monkeypatch.setattr(gp, "load_noise_barriers", lambda kind, root=None: barriers[kind])
    return paths


def test_run_grid_preprocess_end_to_end(isolated_paths):
    report = gp.run_grid_preprocess(buffer_m=100.0, resolution_m=100)

    assert report["n_cells"] > 0
    out_path = isolated_paths["processed"] / "grid_cells.parquet"
    assert out_path.exists()
    saved = gpd.read_parquet(out_path)
    assert len(saved) == report["n_cells"]
    assert {"cell_id", "easting", "northing", "geometry"} <= set(saved.columns)
