"""Tests for the `panel` domain's `assemble` stage -- joins `assessments`
(SIRIS only; `kvalitetssystem` is deliberately excluded, see
`panel/assemble.py`'s module docstring) with `schools assemble`'s road/rail
treatment timing into one long analysis panel. Plain-pandas synthetic
fixtures, no network, no geopandas (this stage joins already-processed
tables, no geometry)."""
import pandas as pd
import pytest

from src.regions.sweden.sources.panel import assemble as pa


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pa, "assessments_paths", lambda root=None: paths)
    monkeypatch.setattr(pa, "schools_paths", lambda root=None: paths)
    monkeypatch.setattr(pa, "assembled_panel_path", lambda root=None: paths["assembled"] / "event_study_panel.parquet")
    monkeypatch.setattr(pa, "assembled_metadata_path", lambda root=None: paths["assembled"] / "event_study_panel.json")
    monkeypatch.setattr(
        pa, "assembled_school_traffic_path", lambda root=None: paths["assembled"] / "school_traffic.parquet"
    )
    monkeypatch.setattr(
        pa,
        "assembled_school_neighbourhood_path",
        lambda root=None: paths["assembled"] / "school_neighbourhood.parquet",
    )
    return paths


def _kvalitetssystem_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s2"],
            "huvudman_orgnr": ["1", "1", "2"],
            "measure_code": ["27", "27", "27"],
            "measure_label": ["Andel E i alla ämnen åk9", "Andel E i alla ämnen åk9", "Andel E i alla ämnen åk9"],
            "year_code": ["2022", "2023", "2022"],
            "year_label": ["2022/23", "2023/24", "2022/23"],
            "value": [80.0, 85.0, None],  # s2/2022 suppressed -> dropped
            "status": [None, None, "."],
        }
    )


def _siris_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset_key": ["slutbetyg_arskurs9", "slutbetyg_arskurs9"],
            "year": [2010, 2011],
            "skola_namn": ["Skola 1", "Skola 1"],
            "skolenhetskod": ["s1", "s1"],
            "kommun_namn": ["X", "X"],
            "kommunkod": ["01", "01"],
            "huvudman_typ": ["Kommunal", "Kommunal"],
            "huvudman_namn": ["X kommun", "X kommun"],
            "huvudman_orgnr": ["1", "1"],
            "genomsnittligt_meritvärde_16": [200.0, None],  # 2011 not reported -> dropped
        }
    )


def _rollup_df(*, first_treat_year_point, first_treat_year_same_route, first_treat_year_same_side) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s2"],
            "nearest_dist_m": [50.0, 900.0],
            "nearest_barrier_row": [0, 1],
            "nearest_element_id": ["b1", "b2"],
            "n_barriers_1000m": [1, 1],
            "ever_near_1000m": [True, True],
            "first_treat_year": [first_treat_year_point, pd.NA],
            "ever_treated": [True, False],
            "timing_unknown": [False, False],
            "first_treat_year_same_route": [first_treat_year_same_route, pd.NA],
            "ever_treated_same_route": [first_treat_year_same_route is not pd.NA, False],
            "timing_unknown_same_route": [False, False],
            "first_treat_year_same_side": [first_treat_year_same_side, pd.NA],
            "ever_treated_same_side": [first_treat_year_same_side is not pd.NA, False],
            "timing_unknown_same_side": [False, False],
            "first_treat_year_protected": [first_treat_year_same_side, pd.NA],
            "ever_treated_protected": [first_treat_year_same_side is not pd.NA, False],
            "timing_unknown_protected": [False, False],
            "same_side_unknown": [False, True],
            "protected_unknown": [False, False],
        }
    )


def _school_traffic_df() -> pd.DataFrame:
    """s1 has TWO recovered historical windows for its matched element
    (2000-2015 at ADT 3000, 2015-onward at ADT 5000) -- the real shape
    `traffic/assemble.py::build_school_traffic_history` produces now that
    `preprocess` keeps full history instead of filtering to current-only
    (a real bug found and fixed 2026-09-16, see `traffic/README.md`'s
    "Correction" section). s2 is unmatched (beyond match distance),
    kept as one NA row."""
    common = {
        "adt_tunga_fordon": [400.0, 300.0, pd.NA],
        "adt_axelpar": [5400.0, 3400.0, pd.NA],
        "adt_latta_fordon_06_18": [3000.0, 1800.0, pd.NA],
        "adt_latta_fordon_18_22": [1000.0, 600.0, pd.NA],
        "adt_latta_fordon_22_06": [600.0, 360.0, pd.NA],
        "adt_medeltunga_fordon_06_18": [200.0, 120.0, pd.NA],
        "adt_medeltunga_fordon_18_22": [100.0, 60.0, pd.NA],
        "adt_medeltunga_fordon_22_06": [50.0, 30.0, pd.NA],
        "adt_tunga_fordon_06_18": [250.0, 150.0, pd.NA],
        "adt_tunga_fordon_18_22": [100.0, 60.0, pd.NA],
        "adt_tunga_fordon_22_06": [50.0, 30.0, pd.NA],
        "matmetod": ["Stickprovsmätning", "Stickprovsmätning", pd.NA],
        "osakerhet_samtliga_fordon": [5.0, 8.0, pd.NA],
        "osakerhet_tunga_fordon": [10.0, 15.0, pd.NA],
        "osakerhet_axelpar": [5.0, 8.0, pd.NA],
    }
    return pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s2"],
            "dist_m": [120.0, 120.0, pd.NA],
            "element_id": ["10015:1", "10015:1", pd.NA],
            "valid_from": [20150101, 20000101, pd.NA],
            "valid_to": [99991231, 20150101, pd.NA],
            "direction": ["Med", "Med", pd.NA],
            "role": ["Normal", "Normal", pd.NA],
            "adt_samtliga_fordon": [5000.0, 3000.0, pd.NA],
            "matarsperiod": [201501, 200001, pd.NA],
            **common,
        }
    )


def _school_neighbourhood_df() -> pd.DataFrame:
    """s1 has real DeSO "d1" coverage for 2020-2021; s2 never matched a
    DeSO at all (kept as one all-NA row, mirroring
    `neighbourhood/assemble.py`'s own real "no match" convention)."""
    return pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s2"],
            "desokod": ["d1", "d1", pd.NA],
            "kommunkod": ["0114", "0114", pd.NA],
            "lanskod": ["01", "01", pd.NA],
            "year": [2020, 2021, pd.NA],
            "mean_net_income_tkr": [300.0, 310.0, pd.NA],
            "pop_forgymnasial": [100.0, 100.0, pd.NA],
            "pop_gymnasial": [300.0, 300.0, pd.NA],
            "pop_eftergymnasial_kort": [80.0, 80.0, pd.NA],
            "pop_eftergymnasial_lang": [90.0, 90.0, pd.NA],
            "pop_uppgift_saknas": [20.0, 20.0, pd.NA],
            "total_pop": [590.0, 590.0, pd.NA],
            "share_eftergymnasial": [0.288, 0.288, pd.NA],
            "antal_sysselsatta": [400.0, 400.0, pd.NA],
            "antal_totalt": [500.0, 500.0, pd.NA],
            "employment_rate": [0.8, 0.8, pd.NA],
        }
    )


def test_melt_siris_to_long_drops_na_and_tags_era_and_dataset():
    long = pa.melt_siris_to_long(_siris_df(), "slutbetyg_arskurs9")

    assert list(long.columns) == ["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]
    assert len(long) == 1  # the 2011 NaN row is dropped
    row = long.iloc[0]
    assert row["skolenhetskod"] == "s1"
    assert row["year"] == 2010
    assert row["era"] == "siris"
    assert row["source_dataset"] == "slutbetyg_arskurs9"
    assert row["outcome_name"] == "genomsnittligt_meritvärde_16"
    assert row["value"] == 200.0


def test_kvalitetssystem_to_long_drops_suppressed_and_casts_year():
    long = pa.kvalitetssystem_to_long(_kvalitetssystem_df())

    assert len(long) == 2  # s2/2022's suppressed (status=".") row is dropped
    assert set(long["era"]) == {"kvalitetssystem"}
    assert set(long["source_dataset"]) == {"kvalitetssystem"}
    assert long["year"].dtype.kind in "iu"
    assert sorted(long["year"]) == [2022, 2023]


def test_build_outcomes_long_excludes_kvalitetssystem():
    """`kvalitetssystem` is deliberately dropped from panel assembly
    (2026-09-17 decision, see module docstring) -- `build_outcomes_long`
    no longer even takes it as an argument."""
    long = pa.build_outcomes_long({"slutbetyg_arskurs9": _siris_df()})

    assert set(long["era"]) == {"siris"}
    # 1 real raw melted row (2011's NaN dropped) -- the single 2010 value is
    # the only observation in its `old_scale` sub-era, so `stitch_meritvarde`
    # produces an undefined (NaN) sample std and contributes 0 rows here.
    assert len(long) == 1


def test_stitch_meritvarde_zscores_each_side_of_the_reform_separately():
    slutbetyg = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s2", "s1", "s2"],
            "year": [2010, 2011, 2016, 2017],
            "genomsnittligt_meritvärde_16": [200.0, 220.0, None, None],
            "inklusive_okänd_bakgrund_genomsnittligt_meritvärde_17": [None, None, 260.0, None],
            "genomsnittligt_meritvärde_17": [None, None, None, 280.0],
        }
    )

    long = pa.stitch_meritvarde(slutbetyg)

    assert list(long.columns) == ["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]
    assert len(long) == 4
    assert set(long["outcome_name"]) == {"meritvärde_z"}
    assert set(long["source_dataset"]) == {"slutbetyg_arskurs9_stitched"}
    # old_scale side (2010/2011, values 200/220): mean 210, std ~14.14
    old_side = long[long["year"].isin([2010, 2011])].set_index("year")["value"]
    assert old_side[2010] < 0 < old_side[2011]
    # new_scale side (2016/2017, picked from the år-2016 `inklusive_okänd_bakgrund`
    # column and the normal `_17` column respectively): mean 270, std ~14.14
    new_side = long[long["year"].isin([2016, 2017])].set_index("year")["value"]
    assert new_side[2016] < 0 < new_side[2017]


def test_build_treatment_rollup_prefixes_by_kind_and_renames_point_tier():
    road = _rollup_df(first_treat_year_point=2015, first_treat_year_same_route=2015, first_treat_year_same_side=2015)
    rail = _rollup_df(first_treat_year_point=2018, first_treat_year_same_route=pd.NA, first_treat_year_same_side=pd.NA)

    combined = pa.build_treatment_rollup({"road": road, "rail": rail})

    assert "road_first_treat_year_point" in combined.columns
    assert "rail_ever_treated_same_route" in combined.columns
    s1 = combined.set_index("skolenhetskod").loc["s1"]
    assert s1["road_first_treat_year_point"] == 2015
    assert s1["rail_first_treat_year_point"] == 2018
    assert bool(s1["rail_ever_treated_same_route"]) is False


def test_remap_treatment_rollup_to_lineage_combines_colocated_rows():
    """A lineage pair's two rows describe the same physical point -- OR the
    `ever_treated_*`/`ever_near_1000m` booleans, take the earliest known
    `first_treat_year_*`, min `nearest_dist_m`, max `n_barriers_1000m`.
    `old` only knows about a rail barrier, `new` only about a road one
    (as if the successor unit's own geocoding barely shifted match
    candidates) -- the combined row must carry both, not just one side's."""
    road = _rollup_df(first_treat_year_point=2015, first_treat_year_same_route=2015, first_treat_year_same_side=2015)
    rail = _rollup_df(first_treat_year_point=2010, first_treat_year_same_route=2010, first_treat_year_same_side=2010)
    rollup = pa.build_treatment_rollup({"road": road, "rail": rail})
    rollup.loc[rollup["skolenhetskod"] == "s1", "road_ever_treated_point"] = False
    rollup.loc[rollup["skolenhetskod"] == "s1", "rail_ever_treated_point"] = True
    rollup.loc[rollup["skolenhetskod"] == "s2", "road_ever_treated_point"] = True
    rollup.loc[rollup["skolenhetskod"] == "s2", "rail_ever_treated_point"] = False
    crosswalk = pd.DataFrame({"old_code": ["s1"], "new_code": ["s2"]})

    combined = pa.remap_treatment_rollup_to_lineage(rollup, crosswalk)

    assert list(combined["skolenhetskod"]) == ["s2"]
    row = combined.iloc[0]
    assert bool(row["road_ever_treated_point"]) is True  # from the row that started as s2
    assert bool(row["rail_ever_treated_point"]) is True  # from the row that started as s1, not lost


def test_remap_outcomes_to_lineage_fills_gaps_but_blocks_real_collisions():
    """`old` reports 2010 (a real pre-reorg year `new` has no data for --
    should get remapped, filling `new`'s history gap) and 2012 (a year
    `new` ALSO independently reports -- two co-located units that
    genuinely coexisted that year, per the module docstring; must be left
    under `old`'s own code, not silently overwritten or duplicated)."""
    outcomes = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s2"],
            "year": [2010, 2012, 2012],
            "era": ["siris", "siris", "siris"],
            "source_dataset": ["slutbetyg_arskurs9"] * 3,
            "outcome_name": ["meritvärde_z"] * 3,
            "value": [1.0, 2.0, 9.0],
        }
    )
    crosswalk = pd.DataFrame({"old_code": ["s1"], "new_code": ["s2"]})

    remapped, stats = pa.remap_outcomes_to_lineage(outcomes, crosswalk)

    assert stats == {"n_links": 1, "n_rows_remapped": 1, "n_rows_blocked_by_collision": 1}
    codes_by_year = remapped.set_index("year")["skolenhetskod"]
    assert codes_by_year[2010] == "s2"  # gap filled: moved to the successor
    assert (remapped.loc[remapped["year"] == 2012, "skolenhetskod"] == ["s1", "s2"]).all()  # both kept, unmerged
    assert len(remapped) == len(outcomes)  # remap never drops or duplicates rows


def test_attach_treatment_computes_event_time_and_fills_missing_school_as_untreated():
    outcomes = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s3"],  # s3 has no rollup row at all
            "year": [2016, 2020, 2022],
            "era": ["siris", "siris", "kvalitetssystem"],
            "source_dataset": ["slutbetyg_arskurs9", "slutbetyg_arskurs9", "kvalitetssystem"],
            "outcome_name": ["x", "x", "x"],
            "value": [1.0, 2.0, 3.0],
        }
    )
    road = _rollup_df(first_treat_year_point=2018, first_treat_year_same_route=2018, first_treat_year_same_side=2018)
    rail = _rollup_df(first_treat_year_point=pd.NA, first_treat_year_same_route=pd.NA, first_treat_year_same_side=pd.NA)
    rollup = pa.build_treatment_rollup({"road": road, "rail": rail})

    out = pa.attach_treatment(outcomes, rollup)

    s1_2016 = out[(out["skolenhetskod"] == "s1") & (out["year"] == 2016)].iloc[0]
    assert s1_2016["event_time_road_point"] == 2016 - 2018  # pre-treatment, negative
    s1_2020 = out[(out["skolenhetskod"] == "s1") & (out["year"] == 2020)].iloc[0]
    assert s1_2020["event_time_road_point"] == 2020 - 2018  # post-treatment, positive

    s3 = out[out["skolenhetskod"] == "s3"].iloc[0]
    assert bool(s3["road_ever_treated_point"]) is False  # real "no match" default, not NA
    assert bool(s3["road_timing_unknown_point"]) is False
    assert pd.isna(s3["event_time_road_point"])  # no first_treat_year to compute against


def test_attach_traffic_picks_the_window_that_actually_covers_each_year():
    """Regression test for a real 2026-09-16 fix: traffic is a genuine
    interval-overlap join now, not a flat broadcast of one snapshot -- a
    user-provided real example proved Betraktelsedatum DOES return real
    historical windows, an earlier same-session test had wrongly concluded
    otherwise. s1 has two windows (2000-2015 @ ADT 3000, 2015-open @ ADT
    5000); a year in each window must get THAT window's own value."""
    panel = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s1", "s2"],
            "year": [2005, 2020, 1995, 2022],  # 1995 predates every recovered window -> real NA
        }
    )
    out = pa.attach_traffic(panel, _school_traffic_df())

    assert "traffic_adt_samtliga_fordon" in out.columns
    assert "adt_samtliga_fordon" not in out.columns  # not left unprefixed
    by_year = out[out["skolenhetskod"] == "s1"].set_index("year")["traffic_adt_samtliga_fordon"]
    assert by_year[2005] == 3000.0  # falls in the 2000-2015 window
    assert by_year[2020] == 5000.0  # falls in the 2015-open window
    assert pd.isna(by_year[1995])  # before any recovered window -> real NA, not a wrong stale value
    s2 = out[out["skolenhetskod"] == "s2"].iloc[0]
    assert pd.isna(s2["traffic_adt_samtliga_fordon"])  # s2 beyond match distance -> real NA, not dropped


def test_attach_neighbourhood_merges_on_school_and_year():
    panel = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s2"],
            "year": [2020, 2021, 2020],
        }
    )
    out = pa.attach_neighbourhood(panel, _school_neighbourhood_df())

    assert "neighbourhood_mean_net_income_tkr" in out.columns
    assert "mean_net_income_tkr" not in out.columns  # renamed, not left unprefixed
    s1_2020 = out[(out["skolenhetskod"] == "s1") & (out["year"] == 2020)].iloc[0]
    assert s1_2020["neighbourhood_mean_net_income_tkr"] == 300.0
    assert s1_2020["neighbourhood_desokod"] == "d1"
    assert s1_2020["neighbourhood_share_eftergymnasial"] == pytest.approx(0.288)
    s2 = out[out["skolenhetskod"] == "s2"].iloc[0]
    assert pd.isna(s2["neighbourhood_mean_net_income_tkr"])  # s2 never matched a DeSO -> real NA, not dropped


def test_attach_neighbourhood_year_outside_coverage_is_na():
    """A school-year the DeSO tables never covered (e.g. before the
    real 2011/2015/2020 coverage floors, or 2024+) gets real `NA`, not a
    dropped row or a stale value from a different year."""
    panel = pd.DataFrame({"skolenhetskod": ["s1"], "year": [1999]})
    out = pa.attach_neighbourhood(panel, _school_neighbourhood_df())

    assert len(out) == 1
    assert pd.isna(out.iloc[0]["neighbourhood_mean_net_income_tkr"])


def test_run_panel_assemble_end_to_end(isolated_paths):
    paths = isolated_paths
    _siris_df().to_parquet(paths["processed"] / "siris_slutbetyg_arskurs9.parquet", index=False)
    # `salsa` also required by SIRIS_DATASET_KEYS -- an empty-but-real frame with the right shape
    empty_salsa = _siris_df().iloc[0:0]
    empty_salsa.to_parquet(paths["processed"] / "siris_salsa.parquet", index=False)
    road = _rollup_df(first_treat_year_point=2015, first_treat_year_same_route=2015, first_treat_year_same_side=2015)
    rail = _rollup_df(first_treat_year_point=pd.NA, first_treat_year_same_route=pd.NA, first_treat_year_same_side=pd.NA)
    road.to_parquet(paths["assembled"] / "schools_road_rollup_network.parquet", index=False)
    rail.to_parquet(paths["assembled"] / "schools_rail_rollup_network.parquet", index=False)
    _school_traffic_df().to_parquet(paths["assembled"] / "school_traffic.parquet", index=False)
    _school_neighbourhood_df().to_parquet(paths["assembled"] / "school_neighbourhood.parquet", index=False)

    report = pa.run_panel_assemble()

    # 1 real raw-melted siris row (2011's NaN dropped); `stitch_meritvarde`
    # contributes 0 rows here -- 2010 is the only observation in its
    # `old_scale` sub-era, so its sample std (and thus z-score) is undefined.
    assert report["rows"] == 1
    assert report["distinct_schools"] == 1
    assert set(report["rows_by_era"]) == {"siris"}
    assert report["treatment_definitions"]["road_point"]["ever_treated_schools"] == 1
    assert report["rows_with_traffic_match"] == 1  # the one remaining row is s1, which has a real traffic match
    assert report["schools_with_traffic_match"] == 1
    # the one remaining row is s1's year 2010 -- outside `_school_neighbourhood_df`'s
    # 2020-2021 coverage window, so this is a real "no match for this year" NA, not a bug
    assert report["rows_with_neighbourhood_match"] == 0
    assert report["schools_with_neighbourhood_match"] == 0
    assert (paths["assembled"] / "event_study_panel.parquet").exists()
    assert (paths["assembled"] / "event_study_panel.json").exists()
    # `run_panel_assemble` no longer loads kvalitetssystem at all -- confirm
    # the file wasn't even looked for (no need to have written it above).
    assert not (paths["processed"] / "kvalitetssystem_grundskola.parquet").exists()


def test_load_treatment_rollup_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown barrier kind"):
        pa.load_treatment_rollup("water")


def test_load_treatment_rollup_with_recovery_falls_back_when_recovery_not_built(isolated_paths, monkeypatch):
    """`vanished_recovery.py` is additive/optional (see `panel/assemble.py`'s
    module docstring) -- `load_treatment_rollup_with_recovery` must return
    the base rollup unchanged, not raise, when `panel
    recover-vanished-schools` hasn't been run yet."""
    from src.regions.sweden.sources.panel import vanished_recovery as vr

    monkeypatch.setattr(vr, "load_vanished_recovery_rollup", lambda kind, root=None: None)
    base = _rollup_df(first_treat_year_point=2015, first_treat_year_same_route=2015, first_treat_year_same_side=2015)
    base_path = isolated_paths["assembled"] / "schools_road_rollup_network.parquet"
    base.to_parquet(base_path, index=False)

    out = pa.load_treatment_rollup_with_recovery("road")
    pd.testing.assert_frame_equal(out.reset_index(drop=True), pd.read_parquet(base_path).reset_index(drop=True))


def test_load_treatment_rollup_with_recovery_concatenates_recovered_rows(isolated_paths, monkeypatch):
    from src.regions.sweden.sources.panel import vanished_recovery as vr

    base = _rollup_df(first_treat_year_point=2015, first_treat_year_same_route=2015, first_treat_year_same_side=2015)
    base.to_parquet(isolated_paths["assembled"] / "schools_road_rollup_network.parquet", index=False)
    recovered = pd.DataFrame({"skolenhetskod": ["v1"], "ever_treated": [True], "first_treat_year": [2018]})
    monkeypatch.setattr(vr, "load_vanished_recovery_rollup", lambda kind, root=None: recovered)

    out = pa.load_treatment_rollup_with_recovery("road")
    assert set(out["skolenhetskod"]) == {"s1", "s2", "v1"}


def test_load_kvalitetssystem_missing_file_raises_with_guidance():
    with pytest.raises(FileNotFoundError, match="preprocess-kvalitetssystem"):
        pa.load_kvalitetssystem()


def test_load_school_traffic_missing_file_raises_with_guidance():
    with pytest.raises(FileNotFoundError, match="traffic"):
        pa.load_school_traffic()


def test_load_school_neighbourhood_missing_file_raises_with_guidance():
    with pytest.raises(FileNotFoundError, match="neighbourhood assemble"):
        pa.load_school_neighbourhood()


def _segment_history():
    # Segment "hw" (a highway): 20,000 until 2010, then 30,000. Segment "st"
    # (a street): 2,000 throughout.
    return pd.DataFrame(
        {
            "element_id": ["hw", "hw", "st"],
            "start_measure": [0.0, 0.0, 0.0],
            "end_measure": [1.0, 1.0, 1.0],
            "valid_from": [19900101, 20100101, 19900101],
            "valid_to": [20100101, 99991231, 99991231],
            "adt": [20000.0, 30000.0, 2000.0],
        }
    )


def test_attach_nearby_traffic_takes_the_busiest_road_within_each_radius_per_year():
    panel = pd.DataFrame({"skolenhetskod": ["s1", "s1", "s2"], "year": [2005, 2015, 2015]})
    nearby = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s1", "s2"],
            "element_id": ["st", "hw", "st"],
            "start_measure": [0.0, 0.0, 0.0],
            "end_measure": [1.0, 1.0, 1.0],
            "dist_m": [100.0, 400.0, 50.0],
        }
    )
    out = pa.attach_nearby_traffic(panel, nearby, _segment_history()).set_index(["skolenhetskod", "year"])
    assert out.loc[("s1", 2005), "traffic_max_adt_250m"] == 2000.0  # the highway is beyond 250m
    assert out.loc[("s1", 2005), "traffic_max_adt_500m"] == 20000.0
    assert out.loc[("s1", 2015), "traffic_max_adt_500m"] == 30000.0  # the window covering 2015
    assert out.loc[("s2", 2015), "traffic_max_adt_500m"] == 2000.0


def test_attach_protected_road_traffic_is_the_protecting_barriers_road_and_na_otherwise():
    panel = pd.DataFrame(
        {
            "skolenhetskod": ["s1", "s2"],
            "year": [2015, 2015],
            "road_protected_barrier_row": pd.array([7, pd.NA], dtype="Int64"),
        }
    )
    barrier_segments = pd.DataFrame({"barrier_row": [7], "element_id": ["hw"], "start_measure": [0.0], "end_measure": [1.0]})
    out = pa.attach_protected_road_traffic(panel, barrier_segments, _segment_history()).set_index("skolenhetskod")
    assert out.loc["s1", "traffic_protected_road_adt"] == 30000.0
    assert pd.isna(out.loc["s2", "traffic_protected_road_adt"])
