"""Pure-function tests for the schools `preprocess` stage -- no network."""
import pytest

from src.regions.sweden.sources.schools.preprocess import (
    extract_grundskola_grades,
    flatten_skolenhet,
    preprocess_schools,
)


GRUNDSKOLA_SKOLFORMER = [
    {
        "type": "Grundskola",
        "SkolformKod": "11",
        "Ak1": False,
        "Ak2": False,
        "Ak3": False,
        "Ak4": True,
        "Ak5": True,
        "Ak6": True,
        "Ak7": True,
        "Ak8": True,
        "Ak9": True,
    },
    {"type": "Fritidshem", "SkolformKod": "15"},
]

GYMNASIUM_SKOLFORMER = [{"type": "Gymnasieskola", "SkolformKod": "21", "NA": True, "SA": True}]


def _detail(**overrides) -> dict:
    base = {
        "Namn": "Fjällskolan",
        "Skolenhetskod": "57004269",
        "Status": "Aktiv",
        "Startdatum": "2026-07-01",
        "Skolenhet_ValidFrom": "2026-07-01T00:00:00",
        "Resursskola": True,
        "Besoksadress": {
            "Adress": "Sångvägen 19",
            "Postnr": "45171",
            "Ort": "Uddevalla",
            "GeoData": {
                "Koordinat_SweRef_E": "320304.352",
                "Koordinat_SweRef_N": "6474401.621",
                "Koordinat_WGS84_Lat": "58.37352579255229",
                "Koordinat_WGS84_Lng": "11.927218742989618",
            },
        },
        "Kommun": {"Kommunkod": "1485", "Namn": "Uddevalla"},
        "Huvudman": {"PeOrgNr": "2120001397", "Namn": "UDDEVALLA KOMMUN", "Typ": "Kommun"},
        "Skolformer": GRUNDSKOLA_SKOLFORMER,
    }
    base.update(overrides)
    return base


def test_extract_grundskola_grades_reads_the_grade_span():
    grades = extract_grundskola_grades(GRUNDSKOLA_SKOLFORMER)
    assert grades == {
        "ak1": False,
        "ak2": False,
        "ak3": False,
        "ak4": True,
        "ak5": True,
        "ak6": True,
        "ak7": True,
        "ak8": True,
        "ak9": True,
    }


def test_extract_grundskola_grades_returns_all_none_for_a_gymnasium():
    grades = extract_grundskola_grades(GYMNASIUM_SKOLFORMER)
    assert set(grades.values()) == {None}
    assert set(grades.keys()) == {f"ak{n}" for n in range(1, 10)}


def test_extract_grundskola_grades_handles_empty_skolformer():
    grades = extract_grundskola_grades([])
    assert set(grades.values()) == {None}


def test_flatten_skolenhet_pulls_geocoding_operator_and_grades():
    row = flatten_skolenhet(_detail())
    assert row["skolenhetskod"] == "57004269"
    assert row["kommunkod"] == "1485"
    assert row["huvudman_orgnr"] == "2120001397"
    assert row["huvudman_typ"] == "Kommun"
    assert row["sweref_e"] == "320304.352"
    assert row["wgs84_lat"] == "58.37352579255229"
    assert row["skolformer_typer"] == "Fritidshem,Grundskola"
    assert row["ak4"] is True
    assert row["ak1"] is False


def test_flatten_skolenhet_tolerates_missing_besoksadress():
    row = flatten_skolenhet({"Skolenhetskod": "1", "Skolformer": []})
    assert row["sweref_e"] is None
    assert row["wgs84_lat"] is None
    assert row["kommunkod"] is None


def test_preprocess_schools_builds_geometry_from_wgs84():
    schools_gdf = preprocess_schools([_detail()])
    assert len(schools_gdf) == 1
    assert schools_gdf.crs.to_epsg() == 4326
    point = schools_gdf.geometry.iloc[0]
    assert point.x == pytest.approx(11.927218742989618)
    assert point.y == pytest.approx(58.37352579255229)


def test_preprocess_schools_keeps_a_row_with_no_coordinates_but_null_geometry():
    schools_gdf = preprocess_schools([{"Skolenhetskod": "1", "Skolformer": []}])
    assert len(schools_gdf) == 1
    assert schools_gdf.geometry.iloc[0] is None


def test_preprocess_schools_sorts_by_skolenhetskod():
    schools_gdf = preprocess_schools([_detail(Skolenhetskod="2"), _detail(Skolenhetskod="1")])
    assert list(schools_gdf["skolenhetskod"]) == ["1", "2"]
