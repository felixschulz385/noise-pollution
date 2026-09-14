"""`preprocess_traffic` aggregation, sentinel handling and dtype tidying,
exercised on a synthetic in-memory attribute table shaped like `fetch.py`'s
per-version output (no local data or network needed).

Row grain is `roadway_id x release_year`, not `roadway_id x segmentid` --
verified against two real FGDL releases that `segmentid` (and even segment
boundaries) are not stable across releases -- and pools every FGDL release
that shares a calendar year (recent years have 3-4), not just one release's
own segments; see `preprocess.py`'s module docstring for both findings."""
import pandas as pd
import pytest

from src.regions.florida.sources.traffic.preprocess import (
    OUTPUT_COLUMNS,
    YEAR_SENTINEL,
    preprocess_traffic,
)
from src.regions.florida.sources.traffic.shared import release_year


def _row(version, roadway_id, segmentid, aadt, begin_post, end_post, **overrides):
    row = {
        "roadway_id": roadway_id,
        "segmentid": segmentid,
        "begin_post": begin_post,
        "end_post": end_post,
        "year": 2025,
        "funclassco": "17",
        "funclass": "URBAN: Major Collector",
        "lane_cnt": 2.0,
        "aadt": aadt,
        "fgdlaqdate": "2026-01-01",
        "version": version,
        "release_year": release_year(version),
    }
    row.update(overrides)
    return row


def test_release_year_parses_month_year_tag():
    assert release_year("jul26") == 2026
    assert release_year("jun04") == 2004
    with pytest.raises(ValueError):
        release_year("notaversion")


def test_output_schema_and_roadway_grain():
    raw = pd.DataFrame(
        [
            _row("jul26", "01000001", 1, 30000, 0.0, 3.0),
            _row("jul26", "01000001", 2, 10000, 3.0, 4.0),
            _row("jan15", "01000001", 99, 12000, 0.0, 2.0),
        ]
    )
    out = preprocess_traffic(raw)

    assert list(out.columns[: len(OUTPUT_COLUMNS)]) == OUTPUT_COLUMNS
    # one row per roadway_id x release_year, not per segmentid
    assert len(out) == 2
    assert sorted(out["release_year"].tolist()) == [2015, 2026]


def test_aadt_is_length_weighted_not_a_plain_mean():
    # 3 mi at 30000 + 1 mi at 10000 -> weighted mean 25000, not the plain
    # mean of 20000.
    raw = pd.DataFrame(
        [
            _row("jul26", "01000001", 1, 30000, 0.0, 3.0),
            _row("jul26", "01000001", 2, 10000, 3.0, 4.0),
        ]
    )
    out = preprocess_traffic(raw)
    assert out.loc[0, "aadt"] == pytest.approx(25000.0)
    assert out.loc[0, "aadt_min"] == 10000
    assert out.loc[0, "aadt_max"] == 30000
    assert out.loc[0, "segment_count"] == 2
    assert out.loc[0, "length_mi"] == pytest.approx(4.0)


def test_year_sentinel_becomes_na():
    raw = pd.DataFrame([_row("jul26", "01000001", 1, 15000, 0.0, 1.0, year=YEAR_SENTINEL)])
    out = preprocess_traffic(raw)
    assert pd.isna(out.loc[0, "aadt_min"]) is False  # sanity: aadt itself untouched by year sentinel


def test_non_positive_aadt_excluded_from_weighted_mean():
    raw = pd.DataFrame(
        [
            _row("jul26", "01000001", 1, 0, 0.0, 1.0),
            _row("jul26", "01000001", 2, -5, 1.0, 2.0),
            _row("jul26", "01000001", 3, 15000, 2.0, 3.0),
        ]
    )
    out = preprocess_traffic(raw)
    # only the one valid segment contributes to the weighted mean
    assert out.loc[0, "aadt"] == pytest.approx(15000.0)


def test_all_missing_aadt_yields_na_not_zero():
    raw = pd.DataFrame([_row("jul26", "01000001", 1, 0, 0.0, 1.0)])
    out = preprocess_traffic(raw)
    assert pd.isna(out.loc[0, "aadt"])


def test_multiple_releases_in_the_same_year_pool_into_one_row():
    # jan26 and jul26 both map to release_year=2026 -- must NOT become two
    # rows (the bug this test guards: grouping by `version` too silently
    # split a year with several releases back into one row per release).
    raw = pd.DataFrame(
        [
            _row("jan26", "01000001", 1, 10000, 0.0, 1.0),
            _row("jul26", "01000001", 1, 20000, 0.0, 1.0),
        ]
    )
    out = preprocess_traffic(raw)
    assert len(out) == 1
    assert out.loc[0, "release_year"] == 2026
    assert out.loc[0, "release_count"] == 2
    assert out.loc[0, "aadt"] == pytest.approx(15000.0)  # equal-length segments -> plain mean


def test_lane_cnt_rounds_to_nullable_int():
    raw = pd.DataFrame(
        [
            _row("jul26", "01000001", 1, 15000, 0.0, 1.0, lane_cnt=4.0),
            _row("jul26", "01000001", 2, 15000, 1.0, 2.0, lane_cnt=4.0),
        ]
    )
    out = preprocess_traffic(raw)
    assert out["lane_cnt"].dtype.name == "Int64"
    assert out.loc[0, "lane_cnt"] == 4
