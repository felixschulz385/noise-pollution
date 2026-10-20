"""Tests for the schools `fetch` stage's pure logic and idempotent detail
fetching -- `fetch_skolenhet_detail` itself is monkeypatched, no network.

`schools_paths` normally resolves through `find_repo_root`, which walks up
from `root` looking for `pyproject.toml`/`src` -- a plain `tmp_path` doesn't
have those, so the `isolated_paths` fixture monkeypatches `schools_paths`
directly to point at `tmp_path`, sidestepping repo-root discovery entirely
rather than faking a whole repo skeleton under `tmp_path`.
"""
import pytest

from src.regions.sweden.sources.schools import fetch as schools_fetch


LIST_PAYLOAD = {
    "data": {
        "attributes": [
            {"schoolUnitCode": "1", "name": "A", "status": "AKTIV"},
            {"schoolUnitCode": "2", "name": "B", "status": "UPPHORT"},
            {"schoolUnitCode": "3", "name": "C", "status": "AKTIV"},
            {"schoolUnitCode": None, "name": "D", "status": "AKTIV"},
        ]
    },
    "meta": {"extractDate": "2026-10-20T00:02:06+02:00"},
}


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(schools_fetch, "schools_paths", lambda root=None: paths)
    return paths


def test_extract_skolenhet_codes_drops_missing_codes():
    codes = schools_fetch.extract_skolenhet_codes(LIST_PAYLOAD)
    assert codes == ["1", "2", "3"]


def test_extract_skolenhet_codes_filters_by_status():
    codes = schools_fetch.extract_skolenhet_codes(LIST_PAYLOAD, status="AKTIV")
    assert codes == ["1", "3"]


def test_fetch_details_skips_codes_already_on_disk(monkeypatch):
    calls = []

    def fake_detail(code):
        calls.append(code)
        return {"data": {"schoolUnitCode": code}}

    monkeypatch.setattr(schools_fetch, "fetch_skolenhet_detail", fake_detail)
    schools_fetch.save_raw_detail("1", {"data": {"schoolUnitCode": "1"}})

    result = schools_fetch.fetch_details(["1", "2"])

    assert calls == ["2"]
    assert result == {"fetched": ["2"], "skipped": ["1"], "failed": []}


def test_fetch_details_force_refetches_everything(monkeypatch):
    calls = []
    monkeypatch.setattr(
        schools_fetch,
        "fetch_skolenhet_detail",
        lambda code: calls.append(code) or {"data": {"schoolUnitCode": code}},
    )
    schools_fetch.save_raw_detail("1", {"data": {"schoolUnitCode": "1"}})

    result = schools_fetch.fetch_details(["1", "2"], force=True)

    assert sorted(calls) == ["1", "2"]
    assert result["fetched"] == ["1", "2"]
    assert result["skipped"] == []


def test_fetch_details_records_failures_without_raising(monkeypatch):
    def flaky_detail(code):
        if code == "2":
            raise RuntimeError("HTTP 404: not found")
        return {"data": {"schoolUnitCode": code}}

    monkeypatch.setattr(schools_fetch, "fetch_skolenhet_detail", flaky_detail)

    result = schools_fetch.fetch_details(["1", "2"])

    assert result["fetched"] == ["1"]
    assert result["failed"] == ["2"]
    assert schools_fetch.load_raw_detail("1") == {"data": {"schoolUnitCode": "1"}}


def test_fetch_skolenhetsregistret_orchestrates_list_then_details(monkeypatch):
    monkeypatch.setattr(schools_fetch, "fetch_skolenhet_list", lambda: LIST_PAYLOAD)
    monkeypatch.setattr(
        schools_fetch,
        "fetch_skolenhet_detail",
        lambda code: {"data": {"schoolUnitCode": code}},
    )

    result = schools_fetch.fetch_skolenhetsregistret(status="AKTIV")

    assert result["total_in_register"] == 4
    assert result["requested_details"] == 2
    assert sorted(result["fetched"]) == ["1", "3"]
    assert schools_fetch.load_raw_list() == LIST_PAYLOAD


def test_fetch_skolenhetsregistret_respects_limit(monkeypatch):
    monkeypatch.setattr(schools_fetch, "fetch_skolenhet_list", lambda: LIST_PAYLOAD)
    fetched_codes = []
    monkeypatch.setattr(
        schools_fetch,
        "fetch_skolenhet_detail",
        lambda code: fetched_codes.append(code) or {"data": {"schoolUnitCode": code}},
    )

    result = schools_fetch.fetch_skolenhetsregistret(limit=2)

    assert result["requested_details"] == 2
    assert sorted(fetched_codes) == ["1", "2"]
