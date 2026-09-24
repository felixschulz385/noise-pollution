"""Tests for the grid `assemble` (grid cell <-> barrier match, distance-band
treated/untreated flags) stage -- synthetic geometries built directly in
EPSG:3006 (SWEREF99 TM) with round-number coordinates so expected
distances/flags are exact, no network."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.sweden.sources.grid import assemble as ga
from src.regions.sweden.sources.barrier_protection import build as bpb
from src.regions.sweden.sources.barrier_protection import shared as bps


def _cells_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"cell_id": ["c1", "c2", "c3"]},
        # c1: 50m from the barrier; c2: 300m; c3: 2000m (beyond every band).
        geometry=[Point(50, 0), Point(300, 0), Point(2000, 0)],
        crs="EPSG:3006",
    )


def _road_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"element_id": ["b1"], "start_measure": [0.0], "end_measure": [1.0], "built_year": pd.array([2015], dtype="Int64")},
        geometry=[LineString([(0, -100), (0, 100)])],
        crs="EPSG:3006",
    )


def _rail_gdf() -> gpd.GeoDataFrame:
    # No barrier close to any cell -- exercises the "real value, not just a
    # dropped row" convention (every cell still gets a real, if large,
    # nearest_dist_m and False band flags).
    return gpd.GeoDataFrame(
        {"element_id": ["b2"], "start_measure": [0.0], "end_measure": [1.0], "built_year": pd.array([pd.NA], dtype="Int64")},
        geometry=[LineString([(0, 50_000), (0, 50_100)])],
        crs="EPSG:3006",
    )


def test_match_grid_point_bands_reflect_nearest_distance():
    rollup = ga.match_grid_point(_cells_gdf(), _road_gdf(), band_radii=(100, 200, 500, 1000))
    by_id = rollup.set_index("cell_id")

    assert by_id.loc["c1", "nearest_dist_m"] == pytest.approx(50.0)
    assert bool(by_id.loc["c1", "ever_near_100m"]) is True
    assert bool(by_id.loc["c1", "ever_treated"]) is True

    assert by_id.loc["c2", "nearest_dist_m"] == pytest.approx(300.0)
    assert bool(by_id.loc["c2", "ever_near_200m"]) is False
    assert bool(by_id.loc["c2", "ever_near_500m"]) is True

    assert by_id.loc["c3", "nearest_dist_m"] == pytest.approx(2000.0)
    assert bool(by_id.loc["c3", "ever_near_1000m"]) is False
    assert bool(by_id.loc["c3", "ever_treated"]) is False


def test_match_grid_point_carries_timing_and_unknown_flag():
    rollup = ga.match_grid_point(_cells_gdf(), _road_gdf(), band_radii=(1000,))
    c1 = rollup.set_index("cell_id").loc["c1"]
    assert c1["treat_year"] == 2015
    assert bool(c1["timing_unknown"]) is False

    # A barrier close enough to treat c1 (50m, well within the 1000m band)
    # but with no recorded built_year -- this is the real "timing_unknown"
    # case: a treated cell whose treatment date isn't known.
    undated_nearby = gpd.GeoDataFrame(
        {"element_id": ["b3"], "built_year": pd.array([pd.NA], dtype="Int64")},
        geometry=[LineString([(0, -100), (0, 100)])],
        crs="EPSG:3006",
    )
    rollup_undated = ga.match_grid_point(_cells_gdf(), undated_nearby, band_radii=(1000,))
    c1_undated = rollup_undated.set_index("cell_id").loc["c1"]
    assert pd.isna(c1_undated["treat_year"])
    assert bool(c1_undated["ever_treated"]) is True
    assert bool(c1_undated["timing_unknown"]) is True

    # The far-away rail barrier never treats c1 at all -- its missing year
    # is irrelevant and must NOT mark c1 "timing unknown".
    rollup_rail = ga.match_grid_point(_cells_gdf(), _rail_gdf(), band_radii=(1000,))
    c1_rail = rollup_rail.set_index("cell_id").loc["c1"]
    assert bool(c1_rail["ever_treated"]) is False
    assert bool(c1_rail["timing_unknown"]) is False


def test_compute_relative_loudness_reduction_pct_is_bounded_and_monotonic():
    dist = pd.Series([1.0, 25.0, 50.0, 100.0, 800.0, 50_000.0])
    index = ga.compute_relative_loudness_reduction_pct(dist.to_numpy())

    # Clamped at `reference_dist_m` (25m) -- 1m and 25m give the identical,
    # maximal value, not an unbounded blow-up as distance -> 0.
    assert index[0] == pytest.approx(index[1])
    assert 0.0 <= index.max() <= 40.0
    # Strictly decreasing from 25m outward.
    assert list(index[1:]) == sorted(index[1:], reverse=True)
    assert index[1:].min() > 0.0


def test_build_dist_bin_mutually_exclusive_with_overflow_bucket():
    dist = pd.Series([50.0, 150.0, 450.0, 750.0, 5000.0])
    bins = ga.build_dist_bin(dist, (100, 200, 500, 1000))
    assert list(bins) == ["0-100m", "100-200m", "200-500m", "500-1000m", "beyond_1000m"]
    assert not bins.isna().any()


def test_add_side_treatment_definitions_gates_on_ever_treated_and_same_route():
    rollup = pd.DataFrame(
        {
            "cell_id": ["treated_same_side", "treated_wrong_side", "untreated_but_in_corridor"],
            "ever_treated": [True, True, False],
            "treat_year": pd.array([2010, 2010, pd.NA], dtype="Int64"),
        }
    )
    side = pd.DataFrame(
        {
            "cell_id": ["treated_same_side", "treated_wrong_side", "untreated_but_in_corridor"],
            "same_route": pd.array([True, True, True], dtype="boolean"),
            "side_method": ["parallel_road", "parallel_road", "parallel_road"],
            "same_side": pd.array([True, False, True], dtype="boolean"),
            "same_side_unknown": pd.array([False, False, False], dtype="boolean"),
            # Protection is judged against every barrier: the wrong-side
            # cell is protected by a different one, built 2012.
            "protected": [False, True, True],
            "protected_unknown": [False, False, False],
            "treat_year_protected": pd.array([pd.NA, 2012, 2015], dtype="Int64"),
            "protected_undated": [False, False, False],
        }
    )

    out = ga.add_side_treatment_definitions(rollup, side).set_index("cell_id")

    assert bool(out.loc["treated_same_side", "ever_treated_same_route"]) is True
    assert bool(out.loc["treated_same_side", "ever_treated_same_side"]) is True
    assert bool(out.loc["treated_wrong_side", "ever_treated_same_route"]) is True
    assert bool(out.loc["treated_wrong_side", "ever_treated_same_side"]) is False
    # Same_route (in-corridor) but never point-treated -- must not count,
    # `ever_treated_same_route` is gated on the point-distance tier too.
    assert bool(out.loc["untreated_but_in_corridor", "ever_treated_same_route"]) is False
    assert bool(out.loc["untreated_but_in_corridor", "ever_treated_same_side"]) is False
    # Same side of the nearest barrier but not beside any barrier's stretch
    # -> not protected; wrong side of the nearest but beside another -> protected.
    assert bool(out.loc["treated_same_side", "ever_treated_protected"]) is False
    assert bool(out.loc["treated_wrong_side", "ever_treated_protected"]) is True
    assert out.loc["treated_wrong_side", "first_treat_year_protected"] == 2012
    assert bool(out.loc["untreated_but_in_corridor", "ever_treated_protected"]) is False
    assert pd.isna(out.loc["untreated_but_in_corridor", "first_treat_year_protected"])


def test_match_grid_point_carries_present_barrier_covariates_only():
    cells_gdf = _cells_gdf()
    road_with_covariates = _road_gdf()
    road_with_covariates["height_m"] = [3.5]
    road_with_covariates["material_type"] = ["concrete"]

    rollup = ga.match_grid_point(cells_gdf, road_with_covariates, band_radii=(100,))
    assert rollup.loc[rollup["cell_id"] == "c1", "height_m"].item() == pytest.approx(3.5)
    assert rollup.loc[rollup["cell_id"] == "c1", "material_type"].item() == "concrete"
    # Rail's own layer (no `height_m` in this test's fixture) must not
    # crash `match_grid_point` -- absent covariate columns are just skipped.
    rail_rollup = ga.match_grid_point(cells_gdf, _rail_gdf(), band_radii=(100,))
    assert "height_m" not in rail_rollup.columns


def test_build_combined_rollup_prefixes_and_fills_false_for_unmatched_kind():
    road_rollup = ga.match_grid_point(_cells_gdf(), _road_gdf(), band_radii=(100,))
    rail_rollup = ga.match_grid_point(_cells_gdf(), _rail_gdf(), band_radii=(100,))
    combined = ga.build_combined_rollup(_cells_gdf(), {"road": road_rollup, "rail": rail_rollup})

    c1 = combined.set_index("cell_id").loc["c1"]
    assert bool(c1["road_ever_treated"]) is True
    assert bool(c1["rail_ever_treated"]) is False  # real False, not NA
    assert bool(c1["rail_timing_unknown"]) is False  # never treated by rail -> not "unknown timing", just untreated


def _road_network_gdf() -> gpd.GeoDataFrame:
    """Coincides with `_road_gdf()`'s own barrier line -- a real network row
    for `barrier-protection build` to attach the barrier to, without pulling
    in the real (2M-row) national road network."""
    return gpd.GeoDataFrame(
        {"element_id": ["b1"], "start_measure": [0.0], "end_measure": [1.0]},
        geometry=[LineString([(0, -100), (0, 100)])],
        crs="EPSG:3006",
    )


def _rail_network_gdf() -> gpd.GeoDataFrame:
    """Coincides with `_rail_gdf()`'s own (far-away) barrier line, same
    reasoning as `_road_network_gdf()`."""
    return gpd.GeoDataFrame(
        {"element_id": ["b2"], "start_measure": [0.0], "end_measure": [1.0], "bandel": ["100"]},
        geometry=[LineString([(0, 50_000), (0, 50_100)])],
        crs="EPSG:3006",
    )


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ga, "processed_grid_cells_path", lambda root=None: paths["processed"] / "grid_cells.parquet")
    monkeypatch.setattr(ga, "assembled_dir", lambda root=None: paths["assembled"])
    barriers = {"road": _road_gdf(), "rail": _rail_gdf()}
    monkeypatch.setattr(ga, "load_noise_barriers", lambda kind, root=None: barriers[kind])
    # `run_grid_assemble`'s side-matching (`grid/side.py`) loads the saved
    # barrier references and protection zones -- built here from tiny
    # synthetic networks by the real `barrier-protection build`, into
    # tmp_path, so this stays hermetic and fast.
    monkeypatch.setattr(bps, "barrier_protection_paths", lambda root=None: paths)
    monkeypatch.setattr(bpb, "load_noise_barriers", lambda kind, root=None: barriers[kind])
    monkeypatch.setattr(
        bpb, "NETWORK_LOADERS", {"road": lambda root=None: _road_network_gdf(), "rail": lambda root=None: _rail_network_gdf()}
    )
    monkeypatch.setattr(bpb, "load_osm_walls", lambda root=None: None)
    bpb.run_barrier_protection_build()
    return paths


def test_run_grid_assemble_requires_preprocess_first(isolated_paths):
    with pytest.raises(FileNotFoundError, match="grid preprocess"):
        ga.run_grid_assemble()


def test_run_grid_assemble_end_to_end(isolated_paths):
    _cells_gdf().to_parquet(isolated_paths["processed"] / "grid_cells.parquet", index=False)

    report = ga.run_grid_assemble(band_radii=(100, 200, 500, 1000))

    assert report["n_cells"] == 3
    assert report["kinds"]["road"]["n_ever_near_100m"] == 1
    assert (isolated_paths["assembled"] / "grid_road_rollup.parquet").exists()
    assert (isolated_paths["assembled"] / "grid_rail_rollup.parquet").exists()
    combined = pd.read_parquet(isolated_paths["assembled"] / "grid_barrier_rollup.parquet")
    assert len(combined) == 3
    assert "road_ever_near_100m" in combined.columns
    assert "rail_ever_near_100m" in combined.columns
