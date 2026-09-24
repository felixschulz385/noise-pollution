"""Tests for the assessments `siris` (historical S3 archive) subsource
-- network calls (`_get_bytes`) are monkeypatched, no network. The synthetic
CSV fixtures below mirror the real header shapes confirmed live 2026-09-15
(dataset 139: one header row; dataset 95/SALSA: a category row over
repeated sub-columns) -- see docs/data/sweden/assessments/README.md §2."""
import pandas as pd
import pytest

from src.regions.sweden.sources.assessments import siris


SLUTBETYG_CSV = (
    "Statistik från Skolverket, http://www.skolverket.se\n"
    "\n"
    "Grundskolan - Slutbetyg årskurs 9, samtliga elever\n"
    "Valt läsår: 2018/19\n"
    "\n"
    "Skola;Skol-enhetskod;Skolkommun;Kommun-kod;Typ av huvudman;Huvudman;Huvudman orgnr;Antal elever;"
    "Andel som uppnått kunskapskraven i alla ämnen;Andel (%) behörig yrkesprog.;Genomsnittligt meritvärde (17);\n"
    "Ahlafors Fria skola;71387206;Ale;1440;Enskild;Ahlafors Fria Skola Ekonomisk förening;7696142343;25;96,0;~100;274,2;\n"
    "Some School;99999999;Ale;1440;Kommunal;Ale;2120001439;..;.;.;..;\n"
).encode("utf-8-sig")

SALSA_CSV = (
    "Statistik från Skolverket, http://www.skolverket.se\n"
    "\n"
    "Grundskolan - Salsa, skolenheters resultat av slutbetygen i årskurs 9 med hänsyn till elevsammansättningen\n"
    "Valt läsår: 2018/19\n"
    "\n"
    ";;;;;;;Bakgrundsinformation;Bakgrundsinformation;Bakgrundsinformation;"
    "Andel (%) som uppn. kunskapskraven;Andel (%) som uppn. kunskapskraven;Andel (%) som uppn. kunskapskraven;"
    "Genomsnittligt meritvärde;Genomsnittligt meritvärde;Genomsnittligt meritvärde;\n"
    "Skola;Skol-enhetskod;Skolkommun;Kommun-kod;Typ av huvudman;Huvudman;Huvudman orgnr;"
    "Föräldrarnas genomsnittliga utb.nivå;Andel (%) nyinvandrade;Andel (%) pojkar;"
    "Faktiskt värde (F);Modell- beräknat värde (B);Residual (R=F-B);"
    "Faktiskt värde (F);Modell- beräknat värde (B);Residual (R=F-B);\n"
    "Ahlafors Fria skola;71387206;Ale;1440;Enskild;Ahlafors Fria Skola Ekonomisk förening;7696142343;"
    "2,46;0;32;96;85;11;274;251;23;\n"
).encode("utf-8-sig")

DATASETS_INDEX = [
    {"databas": "siris", "skolnivå": "Grundskolan", "dataset": "139-Slutbetyg årskurs 9, samtliga elever", "år": "2018", "uttag": "1", "format": "CSV", "url": "https://example/139-2018.csv"},
    {"databas": "siris", "skolnivå": "Grundskolan", "dataset": "139-Slutbetyg årskurs 9, samtliga elever", "år": "2019", "uttag": "1", "format": "CSV", "url": "https://example/139-2019.csv"},
    {"databas": "siris", "skolnivå": "Grundskolan", "dataset": "138-Slutbetyg årskurs 9, samtliga elever", "år": "2019", "uttag": "1", "format": "CSV", "url": "https://example/138-2019.csv"},
    {"databas": "siris", "skolnivå": "Grundskolan", "dataset": "95-Salsa, skolenheters resultat av slutbetygen i årskurs 9 med hänsyn till elevsammansättningen", "år": "2019", "uttag": "1", "format": "CSV", "url": "https://example/95-2019.csv"},
]


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    paths = {"raw": tmp_path / "raw", "processed": tmp_path / "processed", "assembled": tmp_path / "assembled"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(siris, "assessments_paths", lambda root=None: paths)
    return paths


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        (".", None),
        ("..", None),
        ("...", None),
        ("-", None),
        ("", None),
        ("~100", 100.0),
        ("15,0", 15.0),
        ("243,1", 243.1),
        ("0", 0.0),
    ],
)
def test_parse_numeric_se(raw_value, expected):
    assert siris._parse_numeric_se(raw_value) == expected


def test_parse_numeric_se_tolerates_a_column_pandas_already_coerced_to_float_nan():
    # A column blank on every data row can come back from
    # `pd.DataFrame.from_records` as float NaN, not str -- hit live
    # 2026-09-15 fetching a real SALSA year.
    assert siris._parse_numeric_se(float("nan")) is None


def test_parse_siris_csv_single_header_row():
    df = siris.parse_siris_csv(SLUTBETYG_CSV)
    assert list(df["skolenhetskod"]) == ["71387206", "99999999"]
    assert df.loc[0, "skola_namn"] == "Ahlafors Fria skola"
    assert df.loc[0, "huvudman_orgnr"] == "7696142343"
    assert df.loc[0, "huvudman_typ"] == "Enskild"
    assert df.loc[0, "genomsnittligt_meritvärde_17"] == pytest.approx(274.2)
    assert df.loc[0, "andel_behörig_yrkesprog"] == pytest.approx(100.0)  # "~100"
    assert pd.isna(df.loc[1, "andel_som_uppnått_kunskapskraven_i_alla_ämnen"])


def test_parse_siris_csv_two_row_category_header():
    df = siris.parse_siris_csv(SALSA_CSV)
    assert df.loc[0, "skolenhetskod"] == "71387206"
    assert df.loc[0, "huvudman_typ"] == "Enskild"
    # The category prefix disambiguates the two "Faktiskt värde (F)" columns.
    assert df.loc[0, "andel_som_uppn_kunskapskraven_faktiskt_värde_f"] == pytest.approx(96.0)
    assert df.loc[0, "genomsnittligt_meritvärde_faktiskt_värde_f"] == pytest.approx(274.0)
    assert df.loc[0, "andel_som_uppn_kunskapskraven_residual_r_f_b"] == pytest.approx(11.0)
    assert df.loc[0, "genomsnittligt_meritvärde_residual_r_f_b"] == pytest.approx(23.0)


def test_find_dataset_rows_matches_exact_dataset_id_not_title_alone():
    rows = siris.find_dataset_rows(
        DATASETS_INDEX, "Grundskolan", "139-Slutbetyg årskurs 9, samtliga elever"
    )
    # Must not pick up "138-..." despite the identical title suffix.
    assert rows == {"2018": "https://example/139-2018.csv", "2019": "https://example/139-2019.csv"}


def test_fetch_siris_dataset_skips_years_already_on_disk(monkeypatch):
    monkeypatch.setattr(siris, "fetch_datasets_index", lambda: DATASETS_INDEX)
    calls = []

    def fake_get_bytes(url):
        calls.append(url)
        return b"data"

    monkeypatch.setattr(siris, "_get_bytes", fake_get_bytes)
    siris.raw_siris_path("slutbetyg_arskurs9", "2018").write_bytes(b"already here")

    result = siris.fetch_siris_dataset("slutbetyg_arskurs9")

    assert result["fetched"] == ["2019"]
    assert result["skipped"] == ["2018"]
    assert calls == ["https://example/139-2019.csv"]


def test_fetch_siris_dataset_rejects_unknown_key():
    with pytest.raises(ValueError):
        siris.fetch_siris_dataset("not_a_real_dataset")


def test_preprocess_siris_dataset_stacks_years_with_year_from_filename(monkeypatch):
    siris.raw_siris_path("slutbetyg_arskurs9", "2018").write_bytes(SLUTBETYG_CSV)
    siris.raw_siris_path("slutbetyg_arskurs9", "2019").write_bytes(SLUTBETYG_CSV)

    df = siris.preprocess_siris_dataset("slutbetyg_arskurs9")

    assert sorted(df["year"].unique().tolist()) == [2018, 2019]
    assert (df["dataset_key"] == "slutbetyg_arskurs9").all()
    assert len(df) == 4
