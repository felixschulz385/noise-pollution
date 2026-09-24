"""Tests for `panel/vanished_recovery.py` -- recovering coordinates (via
Skolkoll) for SIRIS-assessed schools absent from the current registry
entirely. Pure-function tests for the join/filter logic; the orchestrator
(`run_recover_vanished_schools`) is tested with monkeypatched loaders and
matchers, since the underlying barrier-matching algorithms themselves
already have their own dedicated tests in `test_schools_assemble.py` --
this file only checks the new wiring, not re-derives correctness of
already-tested geometry code."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from src.regions.sweden.sources.panel import assemble as pa
from src.regions.sweden.sources.panel import vanished_recovery as vr


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    # `vanished_recovery.py` and `panel.assemble` each hold their own bound
    # reference to `schools_paths`/`assessments_paths` -- both need
    # patching for a fully isolated test (see this module's own docstring
    # on why a shared `isolated_paths` fixture can't just patch one).
    monkeypatch.setattr(vr, "schools_paths", lambda root=None: paths)
    monkeypatch.setattr(pa, "schools_paths", lambda root=None: paths)
    monkeypatch.setattr(pa, "assessments_paths", lambda root=None: paths)
    return paths


def _registry_gdf(codes: list[str]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"skolenhetskod": codes, "namn": [f"Skola {c}" for c in codes], "status": ["Aktiv"] * len(codes)},
        geometry=[Point(10 + i, 55 + i) for i in range(len(codes))],
        crs="EPSG:4326",
    )


def _siris_df(codes: list[str], *, dataset_key: str = "slutbetyg_arskurs9") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset_key": [dataset_key] * len(codes),
            "year": [2010] * len(codes),
            "skola_namn": [f"Skola {c}" for c in codes],
            "skolenhetskod": codes,
            "kommun_namn": ["X"] * len(codes),
            "kommunkod": ["01"] * len(codes),
            "huvudman_typ": ["Kommunal"] * len(codes),
            "huvudman_namn": ["X kommun"] * len(codes),
            "huvudman_orgnr": ["1"] * len(codes),
            "genomsnittligt_meritvärde_16": [200.0] * len(codes),
        }
    )


def test_load_registry_codes_reads_every_status_not_just_geocoded(isolated_paths):
    paths = isolated_paths
    _registry_gdf(["r1", "r2"]).to_file(paths["processed"] / "schools.geojson", driver="GeoJSON")
    assert vr.load_registry_codes() == {"r1", "r2"}


def test_load_registry_codes_requires_schools_preprocess_to_have_run(isolated_paths):
    with pytest.raises(FileNotFoundError, match="schools preprocess"):
        vr.load_registry_codes()


def test_find_vanished_codes_is_assessed_minus_registry(isolated_paths):
    paths = isolated_paths
    _registry_gdf(["r1"]).to_file(paths["processed"] / "schools.geojson", driver="GeoJSON")
    _siris_df(["r1", "v1"]).to_parquet(paths["processed"] / "siris_slutbetyg_arskurs9.parquet", index=False)
    # salsa is also in SIRIS_DATASET_KEYS -- an empty-but-real frame, same
    # pattern `test_panel_assemble.py`'s own end-to-end test uses.
    _siris_df([]).to_parquet(paths["processed"] / "siris_salsa.parquet", index=False)

    assert vr.find_vanished_codes() == {"v1"}


def _skolkoll_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "skolenhetskod": ["v1", "v2", "r1"],
            "namn": ["Vanished One", "Vanished Two (no coords)", "Registry One"],
            "kommun_namn": ["X", "Y", "X"],
            "status": ["UPPHORT", "UPPHORT", "AKTIV"],
        },
        geometry=[Point(15.0, 57.0), None, Point(16.0, 58.0)],
        crs="EPSG:4326",
    )


def test_recover_vanished_coordinates_keeps_only_vanished_codes_with_real_coords():
    recovered = vr.recover_vanished_coordinates({"v1", "v2"}, _skolkoll_gdf())

    assert list(recovered["skolenhetskod"]) == ["v1"]  # v2 has no coordinate, r1 isn't vanished
    assert recovered.iloc[0].geometry.x == pytest.approx(15.0)
    assert str(recovered.crs) == "EPSG:4326"


def test_recover_vanished_coordinates_prefixes_provenance_columns():
    recovered = vr.recover_vanished_coordinates({"v1"}, _skolkoll_gdf())

    assert recovered.iloc[0]["skolkoll_namn"] == "Vanished One"
    assert recovered.iloc[0]["skolkoll_status"] == "UPPHORT"
    assert "namn" not in recovered.columns  # renamed, not left ambiguous with the registry's own `namn`


def test_recover_vanished_coordinates_empty_when_nothing_matches():
    recovered = vr.recover_vanished_coordinates({"nope"}, _skolkoll_gdf())
    assert recovered.empty


def test_load_vanished_recovery_rollup_returns_none_when_not_yet_built(isolated_paths):
    assert vr.load_vanished_recovery_rollup("road") is None


def test_load_vanished_recovery_rollup_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown barrier kind"):
        vr.load_vanished_recovery_rollup("water")


def test_load_vanished_recovery_rollup_reads_saved_file(isolated_paths):
    paths = isolated_paths
    saved = pd.DataFrame({"skolenhetskod": ["v1"], "ever_treated": [True]})
    saved.to_parquet(paths["assembled"] / "schools_vanished_road_rollup_network.parquet", index=False)

    loaded = vr.load_vanished_recovery_rollup("road")
    assert list(loaded["skolenhetskod"]) == ["v1"]


def test_run_recover_vanished_schools_wires_point_and_network_matching_per_kind(isolated_paths, monkeypatch):
    """Orchestration only -- the barrier-matching algorithms themselves
    (`match_barriers_point`/`match_barriers_network`) are already covered by
    `test_schools_assemble.py`; this just checks
    `run_recover_vanished_schools` finds the right vanished population,
    calls the right function for each kind, and saves the result."""
    paths = isolated_paths
    _registry_gdf(["r1"]).to_file(paths["processed"] / "schools.geojson", driver="GeoJSON")
    _siris_df(["r1", "v1"]).to_parquet(paths["processed"] / "siris_slutbetyg_arskurs9.parquet", index=False)
    _siris_df([]).to_parquet(paths["processed"] / "siris_salsa.parquet", index=False)

    def fake_load_processed_skolkoll(root=None):
        return _skolkoll_gdf()

    calls = []

    def fake_match_barriers_point(schools_gdf, barriers_gdf, *, max_dist):
        calls.append(("point", list(schools_gdf["skolenhetskod"]), barriers_gdf))
        pair = pd.DataFrame({"skolenhetskod": list(schools_gdf["skolenhetskod"]), "barrier_row": [0] * len(schools_gdf)})
        rollup = pd.DataFrame({"skolenhetskod": list(schools_gdf["skolenhetskod"]), "ever_treated": [True] * len(schools_gdf)})
        return pair, rollup

    def fake_match_barriers_network(pair, schools_gdf, refs, *, kind):
        calls.append((f"{kind}_network", refs))
        return pair.assign(same_route=kind == "rail", same_side=kind == "rail", same_side_unknown=False)

    def fake_add_network_treatment_definitions(pair, rollup):
        out = rollup.copy()
        out["ever_treated_same_route"] = pair["same_route"].fillna(False)
        out["ever_treated_same_side"] = False
        out["ever_treated_protected"] = False
        return out

    monkeypatch.setattr(vr, "load_processed_skolkoll", fake_load_processed_skolkoll)
    monkeypatch.setattr(vr, "load_noise_barriers", lambda kind, root=None: pd.DataFrame({"element_id": []}))
    monkeypatch.setattr(vr, "load_barrier_references", lambda kind, root=None, barriers_gdf=None: f"{kind}_refs")
    monkeypatch.setattr(vr, "match_barriers_point", fake_match_barriers_point)
    monkeypatch.setattr(vr, "match_barriers_network", fake_match_barriers_network)
    monkeypatch.setattr(vr, "add_network_treatment_definitions", fake_add_network_treatment_definitions)

    report = vr.run_recover_vanished_schools()

    assert report["n_vanished_codes"] == 1
    assert report["n_recovered_with_coordinates"] == 1
    kinds_called = {c[0] for c in calls}
    assert kinds_called == {"point", "rail_network", "road_network"}
    assert ("rail_network", "rail_refs") in calls  # each kind gets its own saved references
    assert (paths["assembled"] / "schools_vanished_road_rollup_network.parquet").exists()
    assert (paths["assembled"] / "schools_vanished_rail_rollup_network.parquet").exists()

    rail_rollup = pd.read_parquet(paths["assembled"] / "schools_vanished_rail_rollup_network.parquet")
    assert list(rail_rollup["skolenhetskod"]) == ["v1"]
    assert bool(rail_rollup.iloc[0]["ever_treated_same_route"]) is True
