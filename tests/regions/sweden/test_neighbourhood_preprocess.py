"""Tests for `neighbourhood/preprocess.py` -- no network, synthetic
data shaped like the real WFS/PxWeb responses confirmed live 2026-09-17."""
import pandas as pd
import pytest

from src.regions.sweden.sources.neighbourhood import preprocess as np_


def _boundary_page(*features) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def _deso_feature(desokod: str, x: float) -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]]],
        },
        "properties": {
            "objectid": 1,
            "objektidentitet": "abc",
            "objekttyp": "deso",
            "desokod": desokod,
            "regsokod": desokod[:5] + "R001",
            "lanskod": desokod[:2],
            "kommunkod": desokod[:4],
            "version": "2018_v3",
            "referensdatum": "20180101",
        },
    }


def test_preprocess_deso_boundaries_unions_pages_and_keeps_expected_columns():
    page0 = _boundary_page(_deso_feature("0114C1010", 0.0))
    page1 = _boundary_page(_deso_feature("0114C1020", 10.0))

    boundaries = np_.preprocess_deso_boundaries([page0, page1])

    assert len(boundaries) == 2
    assert set(boundaries["desokod"]) == {"0114C1010", "0114C1020"}
    assert list(boundaries.columns) == ["desokod", "regsokod", "lanskod", "kommunkod", "geometry"]
    assert boundaries.crs.to_epsg() == 3006


def test_preprocess_deso_boundaries_deduplicates_on_desokod():
    page = _boundary_page(_deso_feature("0114C1010", 0.0))

    boundaries = np_.preprocess_deso_boundaries([page, page])

    assert len(boundaries) == 1


# A real json-stat2 shape confirmed live 2026-09-17 against
# Tab2InkDesoRegso for one real DeSO2018 code -- includes the genuine
# `None`/".." suppressed 2024 value (2024 income is only published under
# the new DeSO2025 codes, not this DeSO2018 one).
REAL_INCOME_RESPONSE = {
    "id": ["Region", "Inkomstkomponenter", "Kon", "ContentsCode", "Tid"],
    "size": [1, 1, 1, 1, 3],
    "dimension": {
        "Region": {"category": {"index": {"1273C1050": 0}, "label": {"1273C1050": "1273C1050"}}},
        "Inkomstkomponenter": {"category": {"index": {"240": 0}, "label": {"240": "nettoinkomst"}}},
        "Kon": {"category": {"index": {"1+2": 0}, "label": {"1+2": "totalt"}}},
        "ContentsCode": {"category": {"index": {"000008A4": 0}, "label": {"000008A4": "Medelvärde tkr"}}},
        "Tid": {"category": {"index": {"2022": 0, "2023": 1, "2024": 2}, "label": {}}},
    },
    "value": [318.5, 293.6, None],
    "status": {"2": ".."},
}


def test_preprocess_income_gives_one_row_per_deso_and_year():
    df = np_.preprocess_income([REAL_INCOME_RESPONSE])

    assert list(df.columns) == ["desokod", "year", "mean_net_income_tkr"]
    assert len(df) == 3
    assert set(df["desokod"]) == {"1273C1050"}
    assert list(df["year"]) == [2022, 2023, 2024]


def test_preprocess_income_keeps_a_real_suppressed_value_as_nan_not_zero():
    df = np_.preprocess_income([REAL_INCOME_RESPONSE])

    row_2024 = df[df["year"] == 2024].iloc[0]
    assert pd.isna(row_2024["mean_net_income_tkr"])
    row_2023 = df[df["year"] == 2023].iloc[0]
    assert row_2023["mean_net_income_tkr"] == pytest.approx(293.6)


def test_preprocess_income_drops_non_deso2018_region_codes():
    """A real PxWeb `Region` dimension for this table also carries
    RegSO/kommun/national/DeSO2025 codes -- `fetch.py` never requests
    them, but the filter must hold defensively even if one leaked
    through. Also a regression test for a real bug caught 2026-09-17: an
    earlier version of the pattern hardcoded the area-density letter to
    "C", silently dropping real DeSO codes using "A" or "B" (confirmed
    live -- most of a real 30-area WFS sample used A/B, not C)."""
    payload = {
        "id": ["Region", "Inkomstkomponenter", "Kon", "ContentsCode", "Tid"],
        "size": [6, 1, 1, 1, 1],
        "dimension": {
            "Region": {
                "category": {
                    "index": {
                        "0114C1010": 0,
                        "0840A0010": 1,
                        "1273B2010": 2,
                        "0114C1010_DeSO2025": 3,
                        "0114R001": 4,
                        "0114": 5,
                    },
                    "label": {},
                }
            },
            "Inkomstkomponenter": {"category": {"index": {"240": 0}, "label": {}}},
            "Kon": {"category": {"index": {"1+2": 0}, "label": {}}},
            "ContentsCode": {"category": {"index": {"000008A4": 0}, "label": {}}},
            "Tid": {"category": {"index": {"2020": 0}, "label": {}}},
        },
        "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "status": {},
    }

    df = np_.preprocess_income([payload])

    assert set(df["desokod"]) == {"0114C1010", "0840A0010", "1273B2010"}


def test_preprocess_income_handles_no_batches():
    df = np_.preprocess_income([])
    assert list(df.columns) == ["desokod", "year", "mean_net_income_tkr"]
    assert len(df) == 0


# A real json-stat2 shape confirmed live 2026-09-17 against
# UtbSUNBefDesoRegso for one real DeSO2018 code, 2 years (trimmed from the
# real 9-year response for test size) -- dimension order and value
# ordering (Region x UtbildningsNiva x ContentsCode x Tid, last dim
# fastest) match the module docstring's `flatten_jsonstat2` contract.
REAL_EDUCATION_RESPONSE = {
    "id": ["Region", "UtbildningsNiva", "ContentsCode", "Tid"],
    "size": [1, 5, 1, 2],
    "dimension": {
        "Region": {"category": {"index": {"1273C1050": 0}, "label": {}}},
        "UtbildningsNiva": {
            "category": {"index": {"21": 0, "3+4": 1, "5": 2, "6": 3, "US": 4}, "label": {}}
        },
        "ContentsCode": {"category": {"index": {"000005MO": 0}, "label": {}}},
        "Tid": {"category": {"index": {"2022": 0, "2023": 1}, "label": {}}},
    },
    # order: level 21 (2022,2023), level 3+4 (2022,2023), level 5, level 6, level US
    "value": [121, 115, 375, 381, 84, 79, 102, 97, 28, 30],
    "status": {},
}


def test_preprocess_education_pivots_levels_and_computes_total_and_share():
    df = np_.preprocess_education([REAL_EDUCATION_RESPONSE])

    assert set(df.columns) == {
        "desokod",
        "year",
        "pop_forgymnasial",
        "pop_gymnasial",
        "pop_eftergymnasial_kort",
        "pop_eftergymnasial_lang",
        "pop_uppgift_saknas",
        "total_pop",
        "share_eftergymnasial",
    }
    row_2022 = df[df["year"] == 2022].iloc[0]
    assert row_2022["pop_forgymnasial"] == 121
    assert row_2022["pop_gymnasial"] == 375
    assert row_2022["pop_eftergymnasial_kort"] == 84
    assert row_2022["pop_eftergymnasial_lang"] == 102
    assert row_2022["pop_uppgift_saknas"] == 28
    assert row_2022["total_pop"] == 121 + 375 + 84 + 102 + 28
    assert row_2022["share_eftergymnasial"] == pytest.approx((84 + 102) / row_2022["total_pop"])


def test_preprocess_education_drops_non_deso2018_region_codes():
    payload = {
        "id": ["Region", "UtbildningsNiva", "ContentsCode", "Tid"],
        "size": [2, 1, 1, 1],
        "dimension": {
            "Region": {"category": {"index": {"0114C1010": 0, "0114C1010_DeSO2025": 1}, "label": {}}},
            "UtbildningsNiva": {"category": {"index": {"21": 0}, "label": {}}},
            "ContentsCode": {"category": {"index": {"000005MO": 0}, "label": {}}},
            "Tid": {"category": {"index": {"2020": 0}, "label": {}}},
        },
        "value": [10.0, 20.0],
        "status": {},
    }

    df = np_.preprocess_education([payload])

    assert set(df["desokod"]) == {"0114C1010"}


def test_preprocess_education_handles_no_batches():
    df = np_.preprocess_education([])
    assert len(df) == 0
    assert "share_eftergymnasial" in df.columns


# A real json-stat2 shape confirmed live 2026-09-17 against
# ArRegDesoStatusN for one real DeSO2018 code -- includes the genuine
# suppressed 2024 value (2024 employment is only published under the new
# DeSO2025 codes for this DeSO2018 one, same shape as income).
REAL_EMPLOYMENT_RESPONSE = {
    "id": ["Region", "Kon", "Alder", "ContentsCode", "Tid"],
    "size": [1, 1, 1, 2, 3],
    "dimension": {
        "Region": {"category": {"index": {"1273C1050": 0}, "label": {}}},
        "Kon": {"category": {"index": {"1+2": 0}, "label": {}}},
        "Alder": {"category": {"index": {"16-64": 0}, "label": {}}},
        "ContentsCode": {"category": {"index": {"0000089X": 0, "0000089Y": 1}, "label": {}}},
        "Tid": {"category": {"index": {"2022": 0, "2023": 1, "2024": 2}, "label": {}}},
    },
    # order: sysselsatta (2022,2023,2024), totalt (2022,2023,2024)
    "value": [676, 683, None, 932, 944, None],
    "status": {"2": "..", "5": ".."},
}


def test_preprocess_employment_pivots_content_codes_and_computes_rate():
    df = np_.preprocess_employment([REAL_EMPLOYMENT_RESPONSE])

    assert list(df.columns) == ["desokod", "year", "antal_sysselsatta", "antal_totalt", "employment_rate"]
    row_2022 = df[df["year"] == 2022].iloc[0]
    assert row_2022["antal_sysselsatta"] == 676
    assert row_2022["antal_totalt"] == 932
    assert row_2022["employment_rate"] == pytest.approx(676 / 932)


def test_preprocess_employment_keeps_a_real_suppressed_2024_value_as_nan():
    df = np_.preprocess_employment([REAL_EMPLOYMENT_RESPONSE])

    row_2024 = df[df["year"] == 2024].iloc[0]
    assert pd.isna(row_2024["antal_sysselsatta"])
    assert pd.isna(row_2024["antal_totalt"])
    assert pd.isna(row_2024["employment_rate"])


def test_preprocess_employment_handles_no_batches():
    df = np_.preprocess_employment([])
    assert list(df.columns) == ["desokod", "year", "antal_sysselsatta", "antal_totalt", "employment_rate"]
    assert len(df) == 0
