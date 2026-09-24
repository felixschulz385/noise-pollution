"""Tests for `osm_walls/preprocess.py` -- Overpass JSON to one GeoParquet."""
import json

import pytest

from src.regions.sweden.sources.osm_walls import preprocess as op


def _payload(ways):
    return {"elements": [{"type": "way", "id": i, "tags": tags, "geometry": [{"lon": lon, "lat": lat} for lon, lat in pts]} for i, tags, pts in ways]}


def test_parse_overpass_ways_projects_to_metres_and_drops_degenerate_ways():
    payload = _payload(
        [
            (1, {"barrier": "wall", "wall": "noise_barrier", "material": "wood"}, [(18.0, 59.3), (18.001, 59.3)]),
            (2, {"barrier": "wall"}, [(18.0, 59.3)]),  # one node -- dropped
        ]
    )
    walls = op.parse_overpass_ways(payload, "noise_barrier")
    assert walls["osm_id"].tolist() == [1]
    assert walls.loc[0, "material"] == "wood"
    assert walls.crs.to_epsg() == 3006
    assert walls.length.iloc[0] == pytest.approx(57, abs=2)  # 0.001 deg lon at 59.3N


def test_run_osm_walls_preprocess_merges_both_queries(tmp_path, monkeypatch):
    raw = {
        "noise_barrier": _payload([(1, {"wall": "noise_barrier"}, [(18.0, 59.3), (18.001, 59.3)])]),
        "untyped_wall": _payload([(2, {"barrier": "wall"}, [(18.0, 59.31), (18.001, 59.31)])]),
    }
    for wall_type, payload in raw.items():
        (tmp_path / f"{wall_type}.json").write_text(json.dumps(payload))
    monkeypatch.setattr(op, "raw_query_path", lambda wall_type, root=None: tmp_path / f"{wall_type}.json")
    monkeypatch.setattr(op, "processed_osm_walls_path", lambda root=None: tmp_path / "out" / "osm_walls.parquet")

    report = op.run_osm_walls_preprocess()
    assert report["by_type"] == {"noise_barrier": 1, "untyped_wall": 1}
    assert (tmp_path / "out" / "osm_walls.parquet").exists()


def test_run_osm_walls_preprocess_requires_a_fetch_first(tmp_path, monkeypatch):
    monkeypatch.setattr(op, "raw_query_path", lambda wall_type, root=None: tmp_path / f"{wall_type}.json")
    with pytest.raises(FileNotFoundError, match="osm-walls fetch"):
        op.run_osm_walls_preprocess()
