"""Tests for the `barrier_protection` stage: saved barrier references load
back identical, a stale file is refused, and the protection-zone polygons
match `classify_points`. Synthetic geometry in EPSG:3006."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.sweden.sources._barrier_reference import build_barrier_references, classify_points, protection_zones
from src.regions.sweden.sources.barrier_protection import build as bpb
from src.regions.sweden.sources.barrier_protection import shared as bps

CRS = "EPSG:3006"


def _network():
    # Divided road: carriageways A (y=0) and B (y=20); undivided road C (y=-1000).
    return gpd.GeoDataFrame(
        {"element_id": ["A", "B", "C"], "start_measure": 0.0, "end_measure": 1.0},
        geometry=[
            LineString([(0, 0), (2000, 0)]),
            LineString([(0, 20), (2000, 20)]),
            LineString([(0, -1000), (2000, -1000)]),
        ],
        crs=CRS,
    )


def _barriers():
    return gpd.GeoDataFrame(
        {
            "element_id": ["A", "C"],
            "start_measure": [0.20, 0.40],
            "end_measure": [0.25, 0.45],
            "built_year": pd.array([2010, pd.NA], dtype="Int64"),
        },
        geometry=[LineString([(400, 0), (500, 0)]), LineString([(800, -1000), (900, -1000)])],
        crs=CRS,
    )


@pytest.fixture
def built(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    monkeypatch.setattr(bps, "barrier_protection_paths", lambda root=None: paths)
    monkeypatch.setattr(bpb, "load_noise_barriers", lambda kind, root=None: _barriers())
    monkeypatch.setattr(bpb, "NETWORK_LOADERS", {"road": lambda root=None: _network()})
    monkeypatch.setattr(bpb, "load_osm_walls", lambda root=None: None)
    report = bpb.run_barrier_protection_build(kinds=("road",))
    return report


def test_saved_references_load_back_and_classify_identically(built):
    fresh = build_barrier_references(_barriers(), _network(), kind="road", osm_walls=None)
    loaded = bps.load_barrier_references("road", barriers_gdf=_barriers())
    pd.testing.assert_frame_equal(loaded.table, fresh.table[loaded.table.columns])
    points = [Point(450, -40), Point(450, 40), Point(850, -1040), Point(850, -960), Point(1500, -40)]
    rows = np.array([0, 0, 1, 1, 0])
    pd.testing.assert_frame_equal(classify_points(points, rows, loaded), classify_points(points, rows, fresh))
    assert built["kinds"]["road"]["side_method"] == {"parallel_road": 1, "unknown": 1}


def test_stale_references_are_refused(built):
    moved = _barriers().assign(end_measure=[0.26, 0.45])
    with pytest.raises(ValueError, match="barrier-protection build"):
        bps.load_barrier_references("road", barriers_gdf=moved)


def test_zone_layer_carries_kind_status_and_year(built):
    zones = bps.load_protection_zones(kind="road")
    assert zones["zone_status"].tolist() == ["protected", "side_unknown"]
    assert zones["built_year"].iloc[0] == 2010 and pd.isna(zones["built_year"].iloc[1])
    assert zones.crs.to_epsg() == 3006


def test_zones_match_the_point_test_on_a_straight_road():
    refs = build_barrier_references(_barriers(), _network(), kind="road", osm_walls=None)
    zones = protection_zones(refs)
    xs, ys = np.meshgrid(np.arange(250, 700, 25.0), np.arange(-700, 700, 25.0))
    points = [Point(x, y) for x, y in zip(xs.ravel(), ys.ravel())]
    classified = classify_points(points, np.zeros(len(points), dtype=int), refs)
    in_zone = np.array([zones.geometry.iloc[0].covers(p) for p in points])
    # Only points exactly on the zone's edge may disagree.
    disagree = in_zone != classified["protected"].to_numpy()
    on_edge = np.array([zones.geometry.iloc[0].boundary.distance(p) < 1e-6 for p in points])
    assert not (disagree & ~on_edge).any()
    assert classified["protected"].sum() > 0
