"""Tests for `neighbourhood/fetch.py` -- network calls (`fetch_deso_boundary_page`,
`_post_json`, `urlopen`) are monkeypatched, no real network. Pagination/
resumability logic mirrors `assessments/kvalitetssystem.py`'s own tested
batch-save/skip contract -- see that module's tests for the pattern this
one follows."""
import io

import pytest

from src.regions.sweden.sources.neighbourhood import fetch as nf


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    boundaries_dir = tmp_path / "raw" / "deso_2018_boundaries"
    income_dir = tmp_path / "raw" / "income"
    education_dir = tmp_path / "raw" / "education"
    employment_dir = tmp_path / "raw" / "employment"
    for d in (boundaries_dir, income_dir, education_dir, employment_dir):
        d.mkdir(parents=True)
    monkeypatch.setattr(nf, "deso_boundaries_raw_dir", lambda root=None: boundaries_dir)
    monkeypatch.setattr(nf, "income_raw_dir", lambda root=None: income_dir)
    monkeypatch.setattr(nf, "education_raw_dir", lambda root=None: education_dir)
    monkeypatch.setattr(nf, "employment_raw_dir", lambda root=None: employment_dir)
    monkeypatch.setattr(nf.time, "sleep", lambda *_args: None)
    return {"boundaries": boundaries_dir, "income": income_dir, "education": education_dir, "employment": employment_dir}


def test_deso_boundary_page_url_has_expected_wfs_params():
    url = nf.deso_boundary_page_url(500, 1000)
    assert "typeNames=stat%3ADeSO_2018" in url
    assert "startIndex=500" in url
    assert "count=1000" in url
    assert "outputFormat=application%2Fjson" in url


def _page(n_returned: int, number_matched: int) -> dict:
    return {
        "numberMatched": number_matched,
        "numberReturned": n_returned,
        "features": [{"type": "Feature", "properties": {}, "geometry": None}] * n_returned,
    }


def test_fetch_all_deso_boundaries_pages_until_short_page(monkeypatch):
    """3 areas total, page_size=2 -- expects pages of 2, 1 (a short final
    page signals the end, same convention `numberReturned < page_size`
    other fetchers in this repo don't yet use but PxWeb-style APIs do)."""
    calls = []

    def fake_fetch(start_index, count):
        calls.append((start_index, count))
        if start_index == 0:
            return _page(2, 3)
        return _page(1, 3)

    monkeypatch.setattr(nf, "fetch_deso_boundary_page", fake_fetch)

    result = nf.fetch_all_deso_boundaries(page_size=2)

    assert calls == [(0, 2), (2, 2)]
    assert result == {"number_matched": 3, "n_pages": 2, "pages_fetched": 2, "pages_skipped": 0}
    assert len(nf.load_boundary_pages()) == 2


def test_fetch_all_deso_boundaries_skips_a_full_page_already_on_disk(monkeypatch, isolated_dirs):
    nf.save_boundary_page(0, _page(2, 3), None)
    calls = []

    def fake_fetch(start_index, count):
        calls.append((start_index, count))
        return _page(1, 3)

    monkeypatch.setattr(nf, "fetch_deso_boundary_page", fake_fetch)

    result = nf.fetch_all_deso_boundaries(page_size=2)

    assert calls == [(2, 2)]  # page 0 skipped, only page 1 fetched
    assert result == {"number_matched": 3, "n_pages": 2, "pages_fetched": 1, "pages_skipped": 1}


def test_fetch_income_values_batches_over_region_codes(monkeypatch):
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][0]["selection"]["values"]))
        return {"ok": True}

    monkeypatch.setattr(nf, "_post_json", fake_post)

    result = nf.fetch_income_values(["a", "b", "c"], batch_size=2)

    assert seen_batches == [["a", "b"], ["c"]]
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}
    assert len(nf.load_income_batches()) == 2


def _income_payload_with_regions(*region_codes: str) -> dict:
    return {"dimension": {"Region": {"category": {"label": {code: code for code in region_codes}}}}}


def test_fetch_income_values_refetches_a_stale_batch_missing_codes(monkeypatch):
    """Same trap `kvalitetssystem.py`'s `fetch_measure_values` was found to
    have (2026-09-15): a cached batch missing even one code this call
    expects must be treated as stale and re-fetched, not silently
    skipped."""
    nf.save_income_batch(0, _income_payload_with_regions("a"), None)  # stale: missing "b"
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][0]["selection"]["values"]))
        return _income_payload_with_regions("a", "b")

    monkeypatch.setattr(nf, "_post_json", fake_post)

    result = nf.fetch_income_values(["a", "b", "c"], batch_size=2)

    assert seen_batches == [["a", "b"], ["c"]]
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}


def test_fetch_education_values_batches_over_region_codes_and_wildcards_level_and_year(monkeypatch):
    seen_queries = []

    def fake_post(url, body):
        seen_queries.append(body["query"])
        return {"ok": True}

    monkeypatch.setattr(nf, "_post_json", fake_post)

    result = nf.fetch_education_values(["a", "b", "c"], batch_size=2)

    assert [q[0]["selection"]["values"] for q in seen_queries] == [["a", "b"], ["c"]]
    level_dim = next(d for d in seen_queries[0] if d["code"] == "UtbildningsNiva")
    assert level_dim["selection"] == {"filter": "all", "values": ["*"]}
    year_dim = next(d for d in seen_queries[0] if d["code"] == "Tid")
    assert year_dim["selection"] == {"filter": "all", "values": ["*"]}
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}
    assert len(nf.load_education_batches()) == 2


def test_fetch_education_values_refetches_a_stale_batch_missing_codes(monkeypatch):
    nf.save_education_batch(0, _income_payload_with_regions("a"), None)  # stale: missing "b"
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][0]["selection"]["values"]))
        return _income_payload_with_regions("a", "b")

    monkeypatch.setattr(nf, "_post_json", fake_post)

    result = nf.fetch_education_values(["a", "b", "c"], batch_size=2)

    assert seen_batches == [["a", "b"], ["c"]]
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}


def test_fetch_employment_values_batches_over_region_codes(monkeypatch):
    seen_queries = []

    def fake_post(url, body):
        seen_queries.append(body["query"])
        return {"ok": True}

    monkeypatch.setattr(nf, "_post_json", fake_post)

    result = nf.fetch_employment_values(["a", "b", "c"], batch_size=2)

    assert [q[0]["selection"]["values"] for q in seen_queries] == [["a", "b"], ["c"]]
    content_dim = next(d for d in seen_queries[0] if d["code"] == "ContentsCode")
    assert set(content_dim["selection"]["values"]) == set(nf.EMPLOYMENT_CONTENT_CODES)
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}
    assert len(nf.load_employment_batches()) == 2


def test_fetch_employment_values_refetches_a_stale_batch_missing_codes(monkeypatch):
    nf.save_employment_batch(0, _income_payload_with_regions("a"), None)  # stale: missing "b"
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][0]["selection"]["values"]))
        return _income_payload_with_regions("a", "b")

    monkeypatch.setattr(nf, "_post_json", fake_post)

    result = nf.fetch_employment_values(["a", "b", "c"], batch_size=2)

    assert seen_batches == [["a", "b"], ["c"]]
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}


def test_read_json_retries_on_429_then_succeeds(monkeypatch):
    import json as _json
    import urllib.error

    attempts = {"n": 0}

    def fake_urlopen(request, timeout):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"rate limited"))
        return io.BytesIO(_json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr(nf, "urlopen", fake_urlopen)

    result = nf._get_json("https://example.invalid/table")

    assert result == {"ok": True}
    assert attempts["n"] == 3
