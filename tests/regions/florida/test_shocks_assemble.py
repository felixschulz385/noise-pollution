"""`real_county_names` (the 67-district roster filter) and
`build_county_year_panel` (statewide expansion + county-year rollup),
exercised on synthetic tables -- no local data needed."""
import pandas as pd
import pytest

from src.regions.florida.sources.shocks.assemble import build_county_year_panel, real_county_names


def _cross_section(rows):
    # rows: (msid, district, district_name)
    return pd.DataFrame([{"msid": m, "district": d, "district_name": n} for m, d, n in rows])


def _declaration(county_name, assessment_year, is_statewide=False, is_hurricane=True, declaration_type="DR"):
    return {
        "county_name": county_name,
        "assessment_year": assessment_year,
        "is_statewide": is_statewide,
        "is_hurricane": is_hurricane,
        "declaration_type": declaration_type,
    }


def test_real_county_names_excludes_special_districts():
    xs = _cross_section(
        [
            ("s1", "01", "ALACHUA"),
            ("s2", "67", "LAST COUNTY"),
            ("s3", "68", "FSU LAB SCHOOL"),
            ("s4", "89", None),
        ]
    )
    out = real_county_names(xs)
    assert set(out) == {"ALACHUA", "LAST COUNTY"}


def test_build_county_year_panel_basic_rollup():
    shocks = pd.DataFrame(
        [
            _declaration("BROWARD", 2018, is_hurricane=True),
            _declaration("BROWARD", 2018, is_hurricane=False, declaration_type="EM"),
            _declaration("ALACHUA", 2018, is_hurricane=True),
        ]
    )
    district_names = pd.Series(["BROWARD", "ALACHUA"])

    out = build_county_year_panel(shocks, district_names)

    broward = out[(out["county_name"] == "BROWARD") & (out["assessment_year"] == 2018)].iloc[0]
    assert broward["n_declarations"] == 2
    assert broward["n_hurricane_declarations"] == 1
    assert bool(broward["any_major_disaster"]) is True


def test_build_county_year_panel_statewide_expands_to_every_county():
    shocks = pd.DataFrame([_declaration("STATEWIDE", 2020, is_statewide=True, is_hurricane=False, declaration_type="EM")])
    district_names = pd.Series(["BROWARD", "ALACHUA", "DUVAL"])

    out = build_county_year_panel(shocks, district_names)

    assert len(out) == 3
    assert set(out["county_name"]) == {"BROWARD", "ALACHUA", "DUVAL"}
    assert (out["n_declarations"] == 1).all()


def test_build_county_year_panel_unions_statewide_and_county_specific():
    shocks = pd.DataFrame(
        [
            _declaration("STATEWIDE", 2020, is_statewide=True, is_hurricane=False, declaration_type="EM"),
            _declaration("BROWARD", 2020, is_hurricane=True),
        ]
    )
    district_names = pd.Series(["BROWARD", "ALACHUA"])

    out = build_county_year_panel(shocks, district_names)

    broward = out[out["county_name"] == "BROWARD"].iloc[0]
    alachua = out[out["county_name"] == "ALACHUA"].iloc[0]
    assert broward["n_declarations"] == 2  # statewide + its own
    assert alachua["n_declarations"] == 1  # statewide only


def test_build_county_year_panel_unmapped_county_excluded_from_rollup():
    shocks = pd.DataFrame([_declaration("BIG CYPRESS INDIAN RESERVATION", 2018)])
    district_names = pd.Series(["BROWARD", "ALACHUA"])

    out = build_county_year_panel(shocks, district_names)
    assert out.empty


def test_build_county_year_panel_empty_shocks_returns_empty_frame():
    shocks = pd.DataFrame(columns=["county_name", "assessment_year", "is_statewide", "is_hurricane", "declaration_type"])
    district_names = pd.Series(["BROWARD"])
    out = build_county_year_panel(shocks, district_names)
    assert out.empty
