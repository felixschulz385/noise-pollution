"""Tests for the traffic `assemble` (school <-> nearest ÅDT segment match,
plus that segment's full historical window history) stage -- synthetic
geometries in EPSG:3006 (SWEREF99 TM) with round-number coordinates so the
expected distances are exact, no network."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.regions.sweden.sources.traffic import assemble as ta


def _schools_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"skolenhetskod": ["s1", "s2"]},
        geometry=[Point(0, 0), Point(0, 2000)],
        crs="EPSG:3006",
    )


def _traffic_row(*, element_id, valid_from, valid_to, adt, geometry) -> dict:
    return {
        "element_id": element_id,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "direction": "Med",
        "role": "Normal",
        "adt_samtliga_fordon": adt,
        "adt_tunga_fordon": adt // 10,
        "adt_axelpar": adt + 100,
        "adt_latta_fordon_06_18": float(adt) * 0.6,
        "adt_latta_fordon_18_22": float(adt) * 0.2,
        "adt_latta_fordon_22_06": float(adt) * 0.1,
        "adt_medeltunga_fordon_06_18": float(adt) * 0.05,
        "adt_medeltunga_fordon_18_22": float(adt) * 0.02,
        "adt_medeltunga_fordon_22_06": float(adt) * 0.01,
        "adt_tunga_fordon_06_18": float(adt) * 0.05,
        "adt_tunga_fordon_18_22": float(adt) * 0.02,
        "adt_tunga_fordon_22_06": float(adt) * 0.01,
        "matarsperiod": valid_from // 100,
        "matmetod": "Stickprovsmätning",
        "osakerhet_samtliga_fordon": 5.0,
        "osakerhet_tunga_fordon": 10.0,
        "osakerhet_axelpar": 5.0,
        "geometry": geometry,
    }


def _traffic_gdf() -> gpd.GeoDataFrame:
    # t1 (element "t1"): a vertical segment at x=50 -> distance from (0,0)
    # is exactly 50. Two historical windows for the SAME element: a closed
    # one (2012-2024, ADT 147) and the currently-open one (2024-, ADT 174).
    # t2 (element "t2"): far away (distance 1000 from (0,0), 3000 from
    # (0,2000)) -- beyond MAX_MATCH_DIST_M for both schools.
    rows = [
        _traffic_row(element_id="t1", valid_from=20120101, valid_to=20240101, adt=147,
                     geometry=LineString([(50, -10), (50, 10)])),
        _traffic_row(element_id="t1", valid_from=20240101, valid_to=99991231, adt=174,
                     geometry=LineString([(50, -10), (50, 10)])),
        _traffic_row(element_id="t2", valid_from=20200101, valid_to=99991231, adt=500,
                     geometry=LineString([(0, -1200), (0, -1000)])),
    ]
    return gpd.GeoDataFrame(rows, crs="EPSG:3006")


def test_most_current_rows_prefers_open_window_per_element():
    current = ta.most_current_rows(_traffic_gdf())
    assert len(current) == 2  # one row per element (t1, t2)
    t1 = current[current["element_id"] == "t1"].iloc[0]
    assert t1["valid_to"] == 99991231
    assert t1["adt_samtliga_fordon"] == 174  # the OPEN window, not the closed 2012-2024 one


def test_match_schools_to_element_picks_nearest_and_reports_dist():
    matched = ta.match_schools_to_element(_schools_gdf(), _traffic_gdf(), max_dist=1000.0)
    s1 = matched.set_index("skolenhetskod").loc["s1"]
    assert s1["dist_m"] == pytest.approx(50.0)
    assert s1["element_id"] == "t1"


def test_match_schools_to_element_nulls_out_beyond_max_dist():
    matched = ta.match_schools_to_element(_schools_gdf(), _traffic_gdf(), max_dist=1000.0)
    s2 = matched.set_index("skolenhetskod").loc["s2"]
    assert pd.isna(s2["dist_m"])
    assert pd.isna(s2["element_id"])


def test_build_school_traffic_history_gives_one_row_per_recovered_window():
    matched = ta.match_schools_to_element(_schools_gdf(), _traffic_gdf(), max_dist=1000.0)
    history = ta.build_school_traffic_history(matched, _traffic_gdf())

    s1_rows = history[history["skolenhetskod"] == "s1"].sort_values("valid_from")
    assert len(s1_rows) == 2  # both of t1's historical windows
    assert list(s1_rows["adt_samtliga_fordon"]) == [147, 174]

    s2_rows = history[history["skolenhetskod"] == "s2"]
    assert len(s2_rows) == 1  # unmatched school keeps exactly one NA row
    assert pd.isna(s2_rows.iloc[0]["adt_samtliga_fordon"])


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ta, "load_geocoded_schools", lambda root=None: _schools_gdf())
    monkeypatch.setattr(ta, "processed_traffic_path", lambda root=None: paths["processed"] / "traffic.parquet")
    monkeypatch.setattr(
        ta, "assembled_school_traffic_path", lambda root=None: paths["assembled"] / "school_traffic.parquet"
    )
    return paths


def test_run_traffic_assemble_end_to_end(isolated_paths):
    _traffic_gdf().to_parquet(isolated_paths["processed"] / "traffic.parquet", index=False)

    report = ta.run_traffic_assemble(max_dist=1000.0)

    assert report["n_schools"] == 2
    assert report["n_matched"] == 1
    assert report["n_unmatched_beyond_max_dist"] == 1
    assert report["median_dist_m"] == pytest.approx(50.0)
    assert report["n_history_rows"] == 3  # s1's 2 windows + s2's 1 NA row
    assert report["median_windows_per_matched_school"] == pytest.approx(2.0)
    assert (isolated_paths["assembled"] / "school_traffic.parquet").exists()


def test_run_traffic_assemble_requires_preprocess_to_have_run_first(isolated_paths):
    with pytest.raises(FileNotFoundError, match="traffic preprocess"):
        ta.run_traffic_assemble()
