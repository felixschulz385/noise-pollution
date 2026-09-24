"""Tests for the assessments `kvalitetssystem` (live PxWeb API)
subsource -- network calls (`_get_json`/`_post_json`) are monkeypatched, no
network. `flatten_jsonstat2`'s expected shape is taken from a real payload
fetched live 2026-09-15 (see docs/data/sweden/assessments/README.md §1), not
invented."""
import io

import pandas as pd
import pytest

from src.regions.sweden.sources.assessments import kvalitetssystem as ks


METADATA = {
    "variables": [
        {
            "code": "variable",
            "values": ["26", "27"],
            "valueTexts": [
                "Delmål 1: Andel (%) elever ... årskurs 6",
                "Delmål 1: Andel (%) elever ... årskurs 9",
            ],
        },
        {"code": "level", "values": []},
        {
            "code": "time",
            "values": ["2022", "2023", "2024"],
            "valueTexts": ["2022/23", "2023/24", "2024/25"],
        },
    ]
}

# A real response, fetched live 2026-09-15 against
# .../Grundskola/Grundskola.px for measures 26/27, level
# 2120001355-53332364, years 2022-2024.
REAL_MEASURE_RESPONSE = {
    "id": ["variable", "level", "time"],
    "size": [2, 1, 3],
    "dimension": {
        "variable": {
            "category": {
                "index": {"26": 0, "27": 1},
                "label": {"26": "Delmål 1: ... årskurs 6", "27": "Delmål 1: ... årskurs 9"},
            }
        },
        "level": {
            "category": {
                "index": {"2120001355-53332364": 0},
                "label": {"2120001355-53332364": "GÖTEBORGS KOMMUN (2120001355): FJÄLLSKOLAN F-6 (53332364)"},
            }
        },
        "time": {
            "category": {
                "index": {"2022": 0, "2023": 1, "2024": 2},
                "label": {"2022": "2022/23", "2023": "2023/24", "2024": "2024/25"},
            }
        },
    },
    "value": [71.6, 75, 76.9, None, None, None],
    "status": {"3": ".", "4": ".", "5": "."},
}

LEVEL_CODELIST = {
    "dimension": {
        "level": {
            "category": {
                "label": {
                    "00": "RIKET: TOTALT",
                    "5568373228": "021 SKOL AB (5568373228): HUVUDMAN",
                    "2120001447-51403955": "LERUMS KOMMUN (2120001447): ALLÉSKOLAN SKOLENHET ASK (51403955)",
                    "2120001355-53332364": "GÖTEBORGS KOMMUN (2120001355): FJÄLLSKOLAN F-6 (53332364)",
                }
            }
        }
    }
}


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ks, "assessments_paths", lambda root=None: paths)
    return paths


def test_extract_measure_codes():
    assert ks.extract_measure_codes(METADATA) == {
        "26": "Delmål 1: Andel (%) elever ... årskurs 6",
        "27": "Delmål 1: Andel (%) elever ... årskurs 9",
    }


def test_extract_year_codes():
    assert ks.extract_year_codes(METADATA) == {"2022": "2022/23", "2023": "2023/24", "2024": "2024/25"}


def test_parse_school_level_codes_keeps_only_skolenhet_rows():
    codes = ks.parse_school_level_codes(LEVEL_CODELIST)
    assert {entry["level_code"] for entry in codes} == {"2120001447-51403955", "2120001355-53332364"}
    fjallskolan = next(entry for entry in codes if entry["skolenhetskod"] == "53332364")
    assert fjallskolan["huvudman_orgnr"] == "2120001355"


def test_flatten_jsonstat2_matches_the_real_response_shape():
    rows = ks.flatten_jsonstat2(REAL_MEASURE_RESPONSE)
    assert len(rows) == 6
    first = rows[0]
    assert first["variable_code"] == "26"
    assert first["level_code"] == "2120001355-53332364"
    assert first["time_code"] == "2022"
    assert first["value"] == 71.6
    assert first["status"] is None

    suppressed = rows[3]
    assert suppressed["variable_code"] == "27"
    assert suppressed["time_code"] == "2022"
    assert suppressed["value"] is None
    assert suppressed["status"] == "."


def test_preprocess_kvalitetssystem_splits_level_code_and_renames_columns():
    df = ks.preprocess_kvalitetssystem([REAL_MEASURE_RESPONSE])
    assert set(df.columns) == {
        "skolenhetskod",
        "huvudman_orgnr",
        "measure_code",
        "measure_label",
        "year_code",
        "year_label",
        "value",
        "status",
    }
    assert (df["skolenhetskod"] == "53332364").all()
    assert (df["huvudman_orgnr"] == "2120001355").all()
    row = df[(df["measure_code"] == "26") & (df["year_code"] == "2024")].iloc[0]
    assert row["value"] == pytest.approx(76.9)


def test_preprocess_kvalitetssystem_handles_no_batches():
    df = ks.preprocess_kvalitetssystem([])
    assert list(df.columns) == [
        "skolenhetskod",
        "huvudman_orgnr",
        "measure_code",
        "measure_label",
        "year_code",
        "year_label",
        "value",
        "status",
    ]
    assert len(df) == 0


def test_fetch_kvalitetssystem_orchestrates_metadata_codelist_and_batches(monkeypatch):
    monkeypatch.setattr(ks, "fetch_table_metadata", lambda skolform: METADATA)
    monkeypatch.setattr(ks, "fetch_level_codelist", lambda skolform, probe_measure, probe_year: LEVEL_CODELIST)
    fetch_calls = []

    def fake_fetch_measure_values(measure_codes, level_codes, year_codes, *, skolform, batch_size, root, force):
        fetch_calls.append((tuple(level_codes), batch_size))
        ks.save_measure_batch(0, REAL_MEASURE_RESPONSE, skolform, root)
        return {"n_batches": 1, "saved": [0], "skipped": []}

    monkeypatch.setattr(ks, "fetch_measure_values", fake_fetch_measure_values)

    result = ks.fetch_kvalitetssystem(limit_schools=1)

    assert result["n_schools_in_codelist"] == 2
    assert result["n_schools_queried"] == 1
    assert result["n_batches"] == 1
    assert result["batches_fetched"] == 1
    assert result["batches_skipped"] == 0
    assert len(fetch_calls[0][0]) == 1
    assert ks.load_measure_batches() == [REAL_MEASURE_RESPONSE]


def test_fetch_measure_values_batches_over_level_codes(monkeypatch):
    monkeypatch.setattr(ks.time, "sleep", lambda *_args: None)
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][1]["selection"]["values"]))
        return {"ok": True}

    monkeypatch.setattr(ks, "_post_json", fake_post)

    result = ks.fetch_measure_values(["26"], ["a", "b", "c"], ["2024"], batch_size=2)

    assert seen_batches == [["a", "b"], ["c"]]
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}
    assert len(ks.load_measure_batches()) == 2


def _payload_with_levels(*level_codes: str) -> dict:
    """A minimal json-stat2-shaped payload whose `level` dimension covers
    exactly the given codes -- enough for `fetch_measure_values`'s
    cached-batch coverage check, without a full real response."""
    return {"dimension": {"level": {"category": {"label": {code: code for code in level_codes}}}}}


def test_fetch_measure_values_skips_batches_already_on_disk(monkeypatch):
    monkeypatch.setattr(ks.time, "sleep", lambda *_args: None)
    ks.save_measure_batch(0, _payload_with_levels("a", "b"), ks.DEFAULT_SKOLFORM, None)
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][1]["selection"]["values"]))
        return {"ok": True}

    monkeypatch.setattr(ks, "_post_json", fake_post)

    result = ks.fetch_measure_values(["26"], ["a", "b", "c"], ["2024"], batch_size=2)

    assert seen_batches == [["c"]]  # batch 0 ("a","b") skipped, already on disk
    assert result == {"n_batches": 2, "saved": [1], "skipped": [0]}


def test_fetch_measure_values_refetches_a_cached_batch_missing_codes(monkeypatch):
    """Regression test for a real bug found 2026-09-15: a stale batch file
    left on disk from an earlier, smaller-scoped fetch (e.g. a 5-school
    smoke test) was silently trusted as if it were the real full batch,
    dropping 195 real schools from the output with no error anywhere. A
    cached batch missing even one code this call expects must be treated
    as stale, not skipped."""
    monkeypatch.setattr(ks.time, "sleep", lambda *_args: None)
    ks.save_measure_batch(0, _payload_with_levels("a"), ks.DEFAULT_SKOLFORM, None)  # stale: missing "b"
    seen_batches = []

    def fake_post(url, body):
        seen_batches.append(list(body["query"][1]["selection"]["values"]))
        return _payload_with_levels("a", "b")

    monkeypatch.setattr(ks, "_post_json", fake_post)

    result = ks.fetch_measure_values(["26"], ["a", "b", "c"], ["2024"], batch_size=2)

    assert seen_batches == [["a", "b"], ["c"]]  # batch 0 re-fetched, not skipped
    assert result == {"n_batches": 2, "saved": [0, 1], "skipped": []}
    assert ks.load_measure_batches()[0] == _payload_with_levels("a", "b")


def test_read_json_retries_on_429_then_succeeds(monkeypatch):
    import json as _json
    import urllib.error

    monkeypatch.setattr(ks.time, "sleep", lambda *_args: None)
    attempts = {"n": 0}

    def fake_urlopen(request, timeout):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"rate limited"))
        return io.BytesIO(_json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr(ks, "urlopen", fake_urlopen)

    result = ks._get_json("https://example.invalid/table")

    assert result == {"ok": True}
    assert attempts["n"] == 3
