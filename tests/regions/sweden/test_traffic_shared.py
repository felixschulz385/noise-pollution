"""Tests for `traffic/shared.py` -- no network, tmp_path only."""
import pytest

from src.regions.sweden.sources.traffic.shared import all_traffic_gpkgs


def test_all_traffic_gpkgs_raises_when_none_found(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.regions.sweden.sources.traffic.shared.traffic_paths", lambda root=None: paths)

    with pytest.raises(FileNotFoundError, match="No .gpkg found"):
        all_traffic_gpkgs()


def test_all_traffic_gpkgs_returns_every_match(tmp_path, monkeypatch):
    """Multiple orders under `raw/` are expected and meaningful (each a
    different `Betraktelsedatum` historical vintage) -- `preprocess`
    unions all of them, so this must return every match, not just one."""
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    gpkgs = []
    for name in ["Traffic_220914_Geopackage_653449/Traffic_220914_653449.gpkg",
                 "Traffic_260916_Geopackage_653409/Traffic_260916_653409.gpkg"]:
        p = paths["raw"] / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        gpkgs.append(p)
    monkeypatch.setattr("src.regions.sweden.sources.traffic.shared.traffic_paths", lambda root=None: paths)

    assert all_traffic_gpkgs() == sorted(gpkgs)
