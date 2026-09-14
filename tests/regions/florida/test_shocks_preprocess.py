"""`preprocess_shocks` (county-name normalization, assessment-year
derivation, hurricane/statewide flagging), exercised on a synthetic raw
table shaped like `fetch.py`'s OpenFEMA output -- no local data or network
needed."""
import pandas as pd
import pytest

from src.regions.florida.sources.shocks.preprocess import OUTPUT_COLUMNS, preprocess_shocks
from src.regions.florida.sources.shocks.shared import normalize_county_name


def _row(designated_area, declaration_date, incident_type="Hurricane", declaration_type="DR", **overrides):
    row = {
        "disasterNumber": 4337,
        "femaDeclarationString": "DR-4337-FL",
        "declarationType": declaration_type,
        "incidentType": incident_type,
        "declarationTitle": "HURRICANE IRMA",
        "declarationDate": declaration_date,
        "fyDeclared": 2017,
        "designatedArea": designated_area,
        "fipsCountyCode": "011",
        "incidentBeginDate": declaration_date,
        "incidentEndDate": declaration_date,
    }
    row.update(overrides)
    return row


def test_output_schema():
    raw = pd.DataFrame([_row("Broward (County)", "2017-09-10")])
    out = preprocess_shocks(raw)
    assert list(out.columns[: len(OUTPUT_COLUMNS)]) == OUTPUT_COLUMNS


def test_county_name_normalized_and_dade_alias():
    raw = pd.DataFrame(
        [
            _row("Broward (County)", "2017-09-10"),
            _row("Dade (County)", "1992-08-24"),
            _row("Miami-Dade (County)", "2017-09-10"),
        ]
    )
    out = preprocess_shocks(raw)
    assert set(out["county_name"]) == {"BROWARD", "MIAMI-DADE"}


def test_statewide_flag():
    raw = pd.DataFrame([_row("Statewide", "2020-03-01", incident_type="Biological")])
    out = preprocess_shocks(raw)
    assert bool(out.loc[0, "is_statewide"]) is True
    assert out.loc[0, "county_name"] == "STATEWIDE"


def test_tribal_area_kept_not_dropped_and_not_flagged_statewide():
    raw = pd.DataFrame([_row("Big Cypress Indian Reservation", "2017-09-10")])
    out = preprocess_shocks(raw)
    assert len(out) == 1
    assert out.loc[0, "county_name"] == "BIG CYPRESS INDIAN RESERVATION"
    assert bool(out.loc[0, "is_statewide"]) is False


def test_hurricane_flag_only_for_hurricane_incident_type():
    raw = pd.DataFrame(
        [
            _row("Broward (County)", "2017-09-10", incident_type="Hurricane"),
            _row("Broward (County)", "2017-09-10", incident_type="Tropical Storm"),
        ]
    )
    out = preprocess_shocks(raw)
    flags = dict(zip(out["incident_type"], out["is_hurricane"]))
    assert bool(flags["Hurricane"]) is True
    assert bool(flags["Tropical Storm"]) is False


@pytest.mark.parametrize(
    "date,expected_year",
    [
        ("2017-09-10", 2018),  # Sep (month>=7) -> next spring
        ("2016-01-15", 2016),  # Jan (month<7) -> same spring
        ("2016-06-30", 2016),  # June -> same spring (boundary)
        ("2016-07-01", 2017),  # July -> next spring (boundary)
    ],
)
def test_assessment_year_month_aware_derivation(date, expected_year):
    raw = pd.DataFrame([_row("Broward (County)", date)])
    out = preprocess_shocks(raw)
    assert out.loc[0, "assessment_year"] == expected_year


def test_normalize_county_name_standalone():
    s = pd.Series(["Broward (County)", "Dade (County)", "Statewide", pd.NA])
    out = normalize_county_name(s)
    assert out.iloc[0] == "BROWARD"
    assert out.iloc[1] == "MIAMI-DADE"
    assert out.iloc[2] == "STATEWIDE"
    assert pd.isna(out.iloc[3])
