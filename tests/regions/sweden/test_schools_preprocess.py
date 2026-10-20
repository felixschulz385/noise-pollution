"""Pure-function tests for the schools `preprocess` stage (API v2 records) --
no network."""
import pytest

from src.regions.sweden.sources.schools.preprocess import (
    extract_grundskola_grades,
    flatten_skolenhet,
    preprocess_schools,
)


def _detail(code: str = "57004269", **overrides) -> dict:
    attributes = {
        "displayName": "Fjällskolan",
        "status": "AKTIV",
        "schoolUnitType": "SKOLENHET",
        "startdate": "2013-10-01",
        "specialSupportSchool": True,
        "addresses": [
            {
                "type": "BESOKSADRESS",
                "streetAddress": "Sångvägen 19",
                "postalCode": "45171",
                "locality": "Uddevalla",
                "geoCoordinates": {
                    "coordinateSweRefE": "320304",
                    "coordinateSweRefN": "6474401",
                    "latitude": "58.37352579255229",
                    "longitude": "11.927218742989618",
                },
            },
            {"type": "POSTADRESS", "streetAddress": "Box 1", "postalCode": "45180", "locality": "Uddevalla"},
        ],
        "municipalityCode": "1485",
        "schoolTypes": ["GR", "FTH"],
        "schoolTypeProperties": {"gr": {"grades": ["4", "5", "6", "7", "8", "9"]}},
    }
    attributes.update(overrides)
    return {
        "data": {"attributes": attributes, "schoolUnitCode": code, "type": "schoolunit"},
        "included": {
            "attributes": {"displayName": "UDDEVALLA KOMMUN", "organizerType": "KOMMUN"},
            "organizationNumber": "2120001397",
            "type": "organizer",
        },
        "meta": {"created": "2013-10-01", "modified": "2026-07-01"},
    }


def test_extract_grundskola_grades_reads_the_grade_span():
    grades = extract_grundskola_grades({"gr": {"grades": ["4", "5", "6", "7", "8", "9"]}})
    assert grades["ak1"] is False
    assert grades["ak3"] is False
    assert grades["ak4"] is True
    assert grades["ak9"] is True


def test_extract_grundskola_grades_returns_all_none_without_grundskola():
    grades = extract_grundskola_grades({"gy": {"programs": ["NA"]}})
    assert set(grades.values()) == {None}
    assert extract_grundskola_grades(None) == grades


def test_flatten_skolenhet_pulls_geocoding_operator_and_grades():
    row = flatten_skolenhet(_detail())
    assert row["skolenhetskod"] == "57004269"
    assert row["status"] == "AKTIV"
    assert row["kommunkod"] == "1485"
    assert row["adress"] == "Sångvägen 19"
    assert row["huvudman_orgnr"] == "2120001397"
    assert row["huvudman_typ"] == "KOMMUN"
    assert row["sweref_e"] == "320304"
    assert row["wgs84_lat"] == "58.37352579255229"
    assert row["skolformer_typer"] == "FTH,GR"
    assert row["senast_andrad"] == "2026-07-01"
    assert row["nedlaggningsdatum"] is None
    assert row["ak4"] is True
    assert row["ak1"] is False


def test_flatten_skolenhet_tolerates_missing_addresses_and_organizer():
    row = flatten_skolenhet({"data": {"schoolUnitCode": "1", "attributes": {}}})
    assert row["sweref_e"] is None
    assert row["wgs84_lat"] is None
    assert row["kommunkod"] is None
    assert row["huvudman_orgnr"] is None


def test_preprocess_schools_builds_geometry_from_wgs84():
    schools_gdf = preprocess_schools([_detail()])
    assert len(schools_gdf) == 1
    assert schools_gdf.crs.to_epsg() == 4326
    point = schools_gdf.geometry.iloc[0]
    assert point.x == pytest.approx(11.927218742989618)
    assert point.y == pytest.approx(58.37352579255229)


def test_preprocess_schools_parses_a_closed_units_decimal_comma_coordinates():
    closed = _detail(status="UPPHORT", endDate="2017-02-07")
    closed["data"]["attributes"]["addresses"][0]["geoCoordinates"].update(
        coordinateSweRefE="708435,088", coordinateSweRefN="7029297,022"
    )
    row = preprocess_schools([closed]).iloc[0]
    assert row["sweref_e"] == pytest.approx(708435.088)
    assert row["sweref_n"] == pytest.approx(7029297.022)
    assert row["nedlaggningsdatum"] == "2017-02-07"


def test_preprocess_schools_keeps_a_row_with_no_coordinates_but_null_geometry():
    schools_gdf = preprocess_schools([{"data": {"schoolUnitCode": "1", "attributes": {"addresses": []}}}])
    assert len(schools_gdf) == 1
    assert schools_gdf.geometry.iloc[0] is None


def test_preprocess_schools_sorts_by_skolenhetskod():
    schools_gdf = preprocess_schools([_detail("2"), _detail("1")])
    assert list(schools_gdf["skolenhetskod"]) == ["1", "2"]
