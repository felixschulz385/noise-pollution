"""`preprocess_road_projects` tidying/stacking of the two raw ArcGIS extracts,
exercised on synthetic in-memory tables shaped like `fetch.py`'s raw ArcGIS
attribute dicts (no local data or network needed).

Grain is one row per raw project-item record, kept as two sources
(`work_program_*` / `active_construction`) tagged by a `source` column rather
than unioned into a single date/status scheme -- see `preprocess.py`'s module
docstring for why."""
import pandas as pd
import pytest

from src.regions.florida.sources.road_projects.preprocess import (
    OUTPUT_COLUMNS,
    preprocess_road_projects,
)


def _wp_row(rdwyid, fiscalyr, work_mix, status, description, **overrides):
    row = {
        "RDWYID": rdwyid,
        "BEGSECPT": 0.0,
        "ENDSECPT": 1.0,
        "FISCALYR": fiscalyr,
        "WPWKMIXN": work_mix,
        "WPITSTNM": status,
        "LOCALFULL": description,
        "FINPROJ": "12345678901",
        "MANDISDV": "2",
        "CONTYNAM": "ALACHUA",
    }
    row.update(overrides)
    return row


def _ac_row(roadwayid, start_ms, end_ms, description, cost, **overrides):
    row = {
        "RoadwayId": roadwayid,
        "BeginMP": 0.0,
        "EndMP": 1.0,
        "StartDate": start_ms,
        "EstEndDate": end_ms,
        "Description": description,
        "Cost": cost,
        "FinProjNum": "12345678901",
        "District": "2",
        "County": "ALACHUA",
    }
    row.update(overrides)
    return row


EMPTY_WP = pd.DataFrame(columns=list(_wp_row("x", 2024, "y", "z", "d").keys()))
EMPTY_AC = pd.DataFrame(columns=list(_ac_row("x", 0, 0, "d", 0.0).keys()))


def test_output_schema_and_source_tag():
    wp = pd.DataFrame([_wp_row("13075000", 2024, "RESURFACING", "CONST.COMPLETE", "SR 26 resurfacing")])
    ac = pd.DataFrame([_ac_row("13121000", 1691730000000, 1815022800000, "SR 683 resurfacing", 15150106.33)])

    out = preprocess_road_projects(wp, EMPTY_WP, ac)

    assert list(out.columns[: len(OUTPUT_COLUMNS)]) == OUTPUT_COLUMNS
    assert set(out["source"]) == {"work_program_construction", "active_construction"}


def test_fiscal_year_only_populated_for_work_program_rows():
    wp = pd.DataFrame([_wp_row("13075000", 2024, "RESURFACING", "CONST.COMPLETE", "resurfacing job")])
    ac = pd.DataFrame([_ac_row("13121000", 1691730000000, 1815022800000, "another job", 100.0)])

    out = preprocess_road_projects(wp, EMPTY_WP, ac)

    wp_row = out[out["source"] == "work_program_construction"].iloc[0]
    ac_row = out[out["source"] == "active_construction"].iloc[0]
    assert wp_row["fiscal_year"] == 2024
    assert pd.isna(ac_row["fiscal_year"])


def test_start_end_date_only_populated_for_active_construction_rows():
    wp = pd.DataFrame([_wp_row("13075000", 2024, "RESURFACING", "CONST.COMPLETE", "resurfacing job")])
    ac = pd.DataFrame([_ac_row("13121000", 1691730000000, 1815022800000, "another job", 100.0)])

    out = preprocess_road_projects(wp, EMPTY_WP, ac)

    wp_row = out[out["source"] == "work_program_construction"].iloc[0]
    ac_row = out[out["source"] == "active_construction"].iloc[0]
    assert pd.isna(wp_row["start_date"])
    assert ac_row["start_date"] == pd.Timestamp("2023-08-11 05:00:00")


def test_active_construction_epoch_ms_converted_to_timestamp():
    # 1236038400000 ms -> the real min StartDate found live on 2026-09-14
    # (2009-03-03), confirming the unit=ms conversion is correct.
    ac = pd.DataFrame([_ac_row("86095000", 1236038400000, 1613538000000, "I-595 ITS System", 0.0)])

    out = preprocess_road_projects(EMPTY_WP, EMPTY_WP, ac)

    assert out.loc[0, "start_date"] == pd.Timestamp("2009-03-03")


def test_wall_keyword_flag_case_insensitive():
    ac = pd.DataFrame(
        [
            _ac_row("13160000", 1691730000000, 1815022800000, "Design Build SR 70 - Perimeter Wall", 100.0),
            _ac_row("13075000", 1691730000000, 1815022800000, "SR 683 (US 301) resurfacing", 100.0),
            _ac_row("86110000", 1691730000000, 1815022800000, "noise BARRIER retrofit", 100.0),
        ]
    )

    out = preprocess_road_projects(EMPTY_WP, EMPTY_WP, ac)

    flags = dict(zip(out["description"], out["is_wall_project"]))
    assert bool(flags["Design Build SR 70 - Perimeter Wall"]) is True
    assert bool(flags["SR 683 (US 301) resurfacing"]) is False
    assert bool(flags["noise BARRIER retrofit"]) is True


def test_description_whitespace_normalized():
    ac = pd.DataFrame([_ac_row("13121000", 1691730000000, 1815022800000, "SR 683  from  S of 25TH CT", 100.0)])
    out = preprocess_road_projects(EMPTY_WP, EMPTY_WP, ac)
    assert out.loc[0, "description"] == "SR 683 from S of 25TH CT"


def test_non_positive_cost_becomes_na():
    ac = pd.DataFrame(
        [
            _ac_row("13121000", 1691730000000, 1815022800000, "job a", 0.0),
            _ac_row("13121000", 1691730000000, 1815022800000, "job b", -5.0),
            _ac_row("13121000", 1691730000000, 1815022800000, "job c", 250.0),
        ]
    )
    out = preprocess_road_projects(EMPTY_WP, EMPTY_WP, ac)
    assert pd.isna(out.loc[out["description"] == "job a", "cost"].iloc[0])
    assert pd.isna(out.loc[out["description"] == "job b", "cost"].iloc[0])
    assert out.loc[out["description"] == "job c", "cost"].iloc[0] == pytest.approx(250.0)


def test_roadway_id_kept_as_string_and_stripped():
    wp = pd.DataFrame([_wp_row(" 13075000 ", 2024, "RESURFACING", "CONST.COMPLETE", "job")])
    out = preprocess_road_projects(wp, EMPTY_WP, EMPTY_AC)
    assert out.loc[0, "roadway_id"] == "13075000"


def test_both_work_program_phases_stacked():
    construction = pd.DataFrame([_wp_row("13075000", 2024, "RESURFACING", "CONST.COMPLETE", "construction job")])
    pde = pd.DataFrame([_wp_row("13075000", 2025, "PD&E STUDY", "UNDERWAY", "pde job")])

    out = preprocess_road_projects(construction, pde, EMPTY_AC)

    assert set(out["source"]) == {"work_program_construction", "work_program_pde"}
    assert len(out) == 2
