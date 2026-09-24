"""Tests for the neighbourhood `assemble` (school <-> containing DeSO
point-in-polygon match, plus the merged income/education/employment
panel) stage -- synthetic geometries in EPSG:3006, no network."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from src.regions.sweden.sources.neighbourhood import assemble as na


def _schools_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"skolenhetskod": ["s1", "s2"]},
        # s1 falls inside deso "A" (the [0,10]x[0,10] square); s2 falls
        # outside every DeSO polygon below (a geocoding-error case).
        geometry=[Point(5, 5), Point(1000, 1000)],
        crs="EPSG:3006",
    )


def _deso_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "desokod": ["0114C1010"],
            "regsokod": ["0114R001"],
            "lanskod": ["01"],
            "kommunkod": ["0114"],
        },
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
        crs="EPSG:3006",
    )


def _income_df() -> pd.DataFrame:
    # Real coverage window is the widest of the three (mirrors the real
    # 2011-2023 vs. education's 2015-2023 vs. employment's 2020-2023).
    return pd.DataFrame(
        {
            "desokod": ["0114C1010"] * 3,
            "year": [2021, 2022, 2023],
            "mean_net_income_tkr": [300.0, 310.0, None],
        }
    )


def _education_df() -> pd.DataFrame:
    # Only 2022 -- narrower than income, to exercise the outer merge.
    return pd.DataFrame(
        {
            "desokod": ["0114C1010"],
            "year": [2022],
            "share_eftergymnasial": [0.45],
        }
    )


def _employment_df() -> pd.DataFrame:
    # Only 2023 -- narrower than income, different year than education.
    return pd.DataFrame(
        {
            "desokod": ["0114C1010"],
            "year": [2023],
            "employment_rate": [0.82],
        }
    )


def test_match_schools_to_deso_finds_containing_polygon():
    matched = na.match_schools_to_deso(_schools_gdf(), _deso_gdf())
    s1 = matched.set_index("skolenhetskod").loc["s1"]
    assert s1["desokod"] == "0114C1010"
    assert s1["kommunkod"] == "0114"


def test_match_schools_to_deso_nulls_out_a_school_outside_every_polygon():
    matched = na.match_schools_to_deso(_schools_gdf(), _deso_gdf())
    s2 = matched.set_index("skolenhetskod").loc["s2"]
    assert pd.isna(s2["desokod"])


def test_merge_deso_panels_outer_joins_on_desokod_and_year():
    """The three subsources have different real coverage windows -- a
    year present in only one of them must survive with real `NA` in the
    others' columns, not be dropped."""
    merged = na.merge_deso_panels(_income_df(), _education_df(), _employment_df())

    assert set(merged["year"]) == {2021, 2022, 2023}
    row_2021 = merged[merged["year"] == 2021].iloc[0]
    assert row_2021["mean_net_income_tkr"] == pytest.approx(300.0)
    assert pd.isna(row_2021["share_eftergymnasial"])
    assert pd.isna(row_2021["employment_rate"])

    row_2022 = merged[merged["year"] == 2022].iloc[0]
    assert row_2022["share_eftergymnasial"] == pytest.approx(0.45)
    assert pd.isna(row_2022["employment_rate"])

    row_2023 = merged[merged["year"] == 2023].iloc[0]
    assert row_2023["employment_rate"] == pytest.approx(0.82)
    assert pd.isna(row_2023["mean_net_income_tkr"])  # real suppressed 2023 income value


def test_build_school_neighbourhood_panel_gives_one_row_per_matched_school_year():
    matched = na.match_schools_to_deso(_schools_gdf(), _deso_gdf())
    deso_panel = na.merge_deso_panels(_income_df(), _education_df(), _employment_df())
    panel = na.build_school_neighbourhood_panel(matched, deso_panel)

    s1_rows = panel[panel["skolenhetskod"] == "s1"].sort_values("year")
    assert list(s1_rows["year"]) == [2021, 2022, 2023]


def test_build_school_neighbourhood_panel_keeps_one_na_row_for_unmatched_school():
    matched = na.match_schools_to_deso(_schools_gdf(), _deso_gdf())
    deso_panel = na.merge_deso_panels(_income_df(), _education_df(), _employment_df())
    panel = na.build_school_neighbourhood_panel(matched, deso_panel)

    s2_rows = panel[panel["skolenhetskod"] == "s2"]
    assert len(s2_rows) == 1
    assert pd.isna(s2_rows.iloc[0]["mean_net_income_tkr"])
    assert pd.isna(s2_rows.iloc[0]["share_eftergymnasial"])
    assert pd.isna(s2_rows.iloc[0]["employment_rate"])


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(na, "load_geocoded_schools", lambda root=None: _schools_gdf())
    monkeypatch.setattr(
        na, "processed_deso_boundaries_path", lambda root=None: paths["processed"] / "deso_2018_boundaries.parquet"
    )
    monkeypatch.setattr(na, "processed_income_path", lambda root=None: paths["processed"] / "income.parquet")
    monkeypatch.setattr(na, "processed_education_path", lambda root=None: paths["processed"] / "education.parquet")
    monkeypatch.setattr(na, "processed_employment_path", lambda root=None: paths["processed"] / "employment.parquet")
    monkeypatch.setattr(
        na, "assembled_school_neighbourhood_path", lambda root=None: paths["assembled"] / "school_neighbourhood.parquet"
    )
    return paths


def _write_all_processed_inputs(paths):
    _deso_gdf().to_parquet(paths["processed"] / "deso_2018_boundaries.parquet", index=False)
    _income_df().to_parquet(paths["processed"] / "income.parquet", index=False)
    _education_df().to_parquet(paths["processed"] / "education.parquet", index=False)
    _employment_df().to_parquet(paths["processed"] / "employment.parquet", index=False)


def test_run_neighbourhood_assemble_end_to_end(isolated_paths):
    _write_all_processed_inputs(isolated_paths)

    report = na.run_neighbourhood_assemble()

    assert report["n_schools"] == 2
    assert report["n_matched"] == 1
    assert report["n_unmatched"] == 1
    assert report["n_panel_rows"] == 4  # s1's 3 years + s2's 1 NA row
    assert (isolated_paths["assembled"] / "school_neighbourhood.parquet").exists()


def test_run_neighbourhood_assemble_requires_boundaries_preprocess_first(isolated_paths):
    with pytest.raises(FileNotFoundError, match="preprocess-boundaries"):
        na.run_neighbourhood_assemble()


def test_run_neighbourhood_assemble_requires_income_preprocess_first(isolated_paths):
    _deso_gdf().to_parquet(isolated_paths["processed"] / "deso_2018_boundaries.parquet", index=False)
    with pytest.raises(FileNotFoundError, match="preprocess-income"):
        na.run_neighbourhood_assemble()


def test_run_neighbourhood_assemble_requires_education_preprocess_first(isolated_paths):
    _deso_gdf().to_parquet(isolated_paths["processed"] / "deso_2018_boundaries.parquet", index=False)
    _income_df().to_parquet(isolated_paths["processed"] / "income.parquet", index=False)
    with pytest.raises(FileNotFoundError, match="preprocess-education"):
        na.run_neighbourhood_assemble()


def test_run_neighbourhood_assemble_requires_employment_preprocess_first(isolated_paths):
    _deso_gdf().to_parquet(isolated_paths["processed"] / "deso_2018_boundaries.parquet", index=False)
    _income_df().to_parquet(isolated_paths["processed"] / "income.parquet", index=False)
    _education_df().to_parquet(isolated_paths["processed"] / "education.parquet", index=False)
    with pytest.raises(FileNotFoundError, match="preprocess-employment"):
        na.run_neighbourhood_assemble()
