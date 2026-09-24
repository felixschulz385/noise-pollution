"""Tests for `skolkoll/preprocess.py` -- pure CSV parsing, no network. Real
format confirmed live 2026-09-23 (see that module's docstring): UTF-8, a
leading block of `#`-prefixed metadata lines, `;`-delimited, period decimal
points (not comma, unlike SIRIS)."""
import pandas as pd
import pytest

from src.regions.sweden.sources.skolkoll import preprocess as skp

RAW_CSV = """# Dataset: School data — all school units
# Version: 2026-09-21
# Source: Skolverket (via Skolkoll)
# Variable descriptions:
#   schoolCode — Unique identifier (Skolverket)
schoolCode;schoolName;municipalityName;municipalityCode;county;providerName;schoolForms;status;lat;lng;totalPupils;pupilsPerTeacher;qualifiedTeachersPct;meritValueYear9;eligibleUpperSecondaryPct;_source;_period;_qualityClass
77239653;Albäcksskolan 1;Hultsfred;0860;Kalmar län;HULTSFREDS KOMMUN;GR;UPPHORT;;;;;;;;Skolverket;;
55252119;Albäcksskolan 1;Hultsfred;0860;Kalmar län;HULTSFREDS KOMMUN;GR;UPPHORT;57.485318641979184;15.837787538156721;180;11.3;65.9;;;skolverket;2019;B
forsk-868358;5-ÅRSVEKSAMHET FORSEN;Tidaholm;1498;Västra Götalands län;TIDAHOLMS KOMMUN;FORSK;AKTIV;58.17586;13.953135;32;60;5;;;skolverket;2025;B
"""


def test_extract_version():
    assert skp.extract_version(RAW_CSV) == "2026-09-21"


def test_extract_version_missing_returns_none():
    assert skp.extract_version("schoolCode;status\n1;AKTIV\n") is None


def test_strip_leading_comment_block_finds_the_real_header():
    body = skp._strip_leading_comment_block(RAW_CSV)
    assert body.startswith("schoolCode;schoolName")
    assert "#" not in body.splitlines()[0]


def test_strip_leading_comment_block_raises_if_no_real_header():
    with pytest.raises(ValueError):
        skp._strip_leading_comment_block("# only comments\n# more comments\n")


def test_parse_schools_csv_renames_columns_and_keeps_leading_zero_kommunkod():
    df = skp.parse_schools_csv(RAW_CSV)
    assert list(df.columns) == [
        "skolenhetskod", "namn", "kommun_namn", "kommunkod", "lan", "huvudman_namn", "skolformer",
        "status", "wgs84_lat", "wgs84_lng", "total_pupils", "pupils_per_teacher", "qualified_teachers_pct",
        "merit_value_year9", "eligible_upper_secondary_pct", "source", "period", "quality_class",
    ]
    # Sweden's kommunkod is a zero-padded 4-digit string -- reading numeric
    # columns as str first (then coercing only the ones that are real
    # numbers) is what keeps "0860" from silently becoming the int 860.
    assert df.loc[df["skolenhetskod"] == "77239653", "kommunkod"].iloc[0] == "0860"


def test_parse_schools_csv_coerces_numeric_columns_period_decimal():
    df = skp.parse_schools_csv(RAW_CSV)
    row = df[df["skolenhetskod"] == "55252119"].iloc[0]
    assert row["wgs84_lat"] == pytest.approx(57.485318641979184)
    assert row["pupils_per_teacher"] == pytest.approx(11.3)
    assert pd.api.types.is_float_dtype(df["wgs84_lat"])


def test_parse_schools_csv_blank_numeric_fields_become_real_na():
    df = skp.parse_schools_csv(RAW_CSV)
    row = df[df["skolenhetskod"] == "77239653"].iloc[0]
    assert pd.isna(row["wgs84_lat"])
    assert pd.isna(row["total_pupils"])


def test_preprocess_skolkoll_schools_builds_geometry_only_when_coords_present():
    gdf = skp.preprocess_skolkoll_schools(RAW_CSV)
    by_code = gdf.set_index("skolenhetskod")
    assert by_code.loc["77239653", "geometry"] is None
    geom = by_code.loc["55252119", "geometry"]
    assert geom.x == pytest.approx(15.837787538156721)
    assert geom.y == pytest.approx(57.485318641979184)
    assert str(gdf.crs) == "EPSG:4326"


def test_preprocess_skolkoll_schools_keeps_synthetic_forsk_codes_as_is():
    """Preschool rows carry a Skolkoll-synthetic `forsk-######` id, not a
    real Skolverket `skolenhetskod` -- kept as-is (not filtered here), since
    `vanished_recovery.py`'s exact-id join against SIRIS codes naturally
    never matches one."""
    gdf = skp.preprocess_skolkoll_schools(RAW_CSV)
    assert "forsk-868358" in set(gdf["skolenhetskod"])
