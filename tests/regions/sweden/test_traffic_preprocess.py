"""Tests for `traffic/preprocess.py` -- no network, synthetic data.

Regression coverage for a real bug found 2026-09-16: an earlier version of
this module filtered to `VALID_TO == 99991231` ("current only"), which
silently discarded genuine historical `[valid_from, valid_to)` windows
that Trafikverket's own web viewer confirms are real, distinct historical
ÅDT measurements -- not noise. `preprocess_traffic` must keep every row."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.regions.sweden.sources.traffic.preprocess import preprocess_traffic


def _raw_traffic_gdf(*, valid_from, valid_to, adt) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "ELEMENT_ID": ["10015:1"],
            "VALID_FROM": [valid_from],
            "VALID_TO": [valid_to],
            "START_MEASURE": [0.0],
            "END_MEASURE": [1.0],
            "EXTENT_LENGTH": [100.0],
            "DIRECTION": ["Med"],
            "ROLE": ["Normal"],
            "Adt_samtliga_fordon": [adt],
            "Adt_tunga_fordon": [adt // 10],
            "Adt_axelpar": [adt + 100],
            "Adt_latta_fordon_06_18": [float(adt) * 0.6],
            "Adt_latta_fordon_18_22": [float(adt) * 0.2],
            "Adt_latta_fordon_22_06": [float(adt) * 0.1],
            "Adt_medeltunga_fordon_06_18": [float(adt) * 0.05],
            "Adt_medeltunga_fordon_18_22": [float(adt) * 0.02],
            "Adt_medeltunga_fordon_22_06": [float(adt) * 0.01],
            "Adt_tunga_fordon_06_18": [float(adt) * 0.05],
            "Adt_tunga_fordon_18_22": [float(adt) * 0.02],
            "Adt_tunga_fordon_22_06": [float(adt) * 0.01],
            "Avsnittsidentitet": [10630008],
            "Matarsperiod": [valid_from // 100],
            "Matmetod": ["Stickprovsmätning"],
            "Mc_floden": [None],
            "Osakerhet_axelpar": [5.0],
            "Osakerhet_samtliga_fordon": [5.0],
            "Osakerhet_tunga_fordon": [10.0],
        },
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:3006",
    )


def test_preprocess_traffic_keeps_historical_windows_not_just_current():
    """Regression test for the real 2026-09-16 bug: two orders for the
    SAME element/section, one an already-closed historical window
    (valid_to != 99991231) and one the currently-open window -- both must
    survive `preprocess`, not just the current one."""
    old_window = _raw_traffic_gdf(valid_from=20120101, valid_to=20240101, adt=147)  # closed historical window
    current_window = _raw_traffic_gdf(valid_from=20240101, valid_to=99991231, adt=174)  # still open

    traffic = preprocess_traffic([old_window, current_window])

    assert len(traffic) == 2
    assert set(traffic["valid_to"]) == {20240101, 99991231}
    assert set(traffic["adt_samtliga_fordon"]) == {147, 174}


def test_preprocess_traffic_deduplicates_identical_rows_across_orders():
    """The SAME historical window (e.g. one that was already closed by
    the time of BOTH orders) appears verbatim in both raw frames -- must
    collapse to one row, not double-count it."""
    window = _raw_traffic_gdf(valid_from=20120101, valid_to=20240101, adt=147)

    traffic = preprocess_traffic([window, window.copy()])

    assert len(traffic) == 1


def test_preprocess_traffic_renames_expected_columns():
    traffic = preprocess_traffic([_raw_traffic_gdf(valid_from=20240101, valid_to=99991231, adt=174)])
    assert "adt_samtliga_fordon" in traffic.columns
    assert "matarsperiod" in traffic.columns
    assert "valid_from" in traffic.columns
    assert "ELEMENT_ID" not in traffic.columns


def test_preprocess_traffic_nulls_the_999998_adt_placeholder():
    frame = _raw_traffic_gdf(valid_from=20200101, valid_to=99991231, adt=999998)
    out = preprocess_traffic([frame]).iloc[0]
    assert pd.isna(out["adt_samtliga_fordon"])
    # the fixture derives the other columns from `adt`, so they aren't the placeholder
    assert out["adt_tunga_fordon"] == 99999
