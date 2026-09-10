"""Florida's `florida data <domain> <verb>` subtree resolves every wired
subcommand to a handler, and `noise-barriers fetch` defaults to the release the
notebook is built against."""
import pytest

from src.core.cli.main import build_parser
from src.regions.florida.sources.assessments.shared import (
    RESULTS_PAGES,
    validate_year,
)
from src.regions.florida.sources.master_file.shared import (
    DATASETS,
    DEFAULT_DATASET,
    dataset_filename,
    dataset_url,
)
from src.regions.florida.sources.noise_barriers.fetch import _find_gdb_prefix
from src.regions.florida.sources.noise_barriers.shared import (
    DEFAULT_VERSION,
    parse_index_versions,
    validate_version,
    version_sort_key,
)


@pytest.mark.parametrize(
    "argv",
    [
        ["florida", "data", "noise-barriers", "list-versions"],
        ["florida", "data", "noise-barriers", "fetch"],
        ["florida", "data", "noise-barriers", "fetch", "--version", "apr23", "--keep-zip", "--no-metadata"],
        ["florida", "data", "assessments", "list-years"],
        ["florida", "data", "assessments", "fetch"],
        ["florida", "data", "assessments", "fetch", "--year", "2024", "--from-file", "a.xlsx"],
        ["florida", "data", "master-file", "fetch"],
        ["florida", "data", "master-file", "fetch", "--dataset", "all_schools", "--dataset", "active_schools"],
        ["florida", "data", "master-file", "fetch", "--from-file", "msid.xlsx"],
    ],
)
def test_known_commands_resolve_to_a_handler(argv):
    args = build_parser().parse_args(argv)
    assert callable(args.func)


def test_master_file_dataset_registry():
    assert DEFAULT_DATASET == "all_schools" and DEFAULT_DATASET in DATASETS
    assert dataset_url("all_schools") == (
        "https://eds.fldoe.org/EDS/MasterSchoolID/Downloads/All_schools.cfm"
    )
    assert dataset_filename("all_schools") == "MSID_all_schools.tsv"
    with pytest.raises(ValueError):
        dataset_url("nope")


def test_master_file_dataset_flag_accumulates_and_is_constrained():
    args = build_parser().parse_args(
        ["florida", "data", "master-file", "fetch", "--dataset", "all_schools", "--dataset", "verification"]
    )
    assert args.dataset == ["all_schools", "verification"]
    with pytest.raises(SystemExit):
        build_parser().parse_args(["florida", "data", "master-file", "fetch", "--dataset", "bogus"])


def test_assessments_fetch_flags_accumulate():
    args = build_parser().parse_args(
        ["florida", "data", "assessments", "fetch",
         "--year", "2022", "--year", "2024",
         "--from-file", "a.xlsx", "--from-file", "b.xlsx"]
    )
    assert args.year == [2022, 2024]
    assert args.from_file == ["a.xlsx", "b.xlsx"]


def test_assessments_registry_and_year_validation():
    assert RESULTS_PAGES[2024].endswith("/results/2024.stml")
    assert 2015 in RESULTS_PAGES and 2026 in RESULTS_PAGES
    assert 2020 not in RESULTS_PAGES  # no COVID-year spring administration
    assert validate_year("2024") == 2024
    with pytest.raises(ValueError):
        validate_year("24")


def test_fetch_defaults_to_notebook_release():
    args = build_parser().parse_args(["florida", "data", "noise-barriers", "fetch"])
    assert args.version == DEFAULT_VERSION == "jul26"


def test_validate_version_rejects_garbage():
    assert validate_version("JUL26") == "jul26"
    with pytest.raises(ValueError):
        validate_version("2026-07")


def test_parse_index_versions_sorts_newest_first():
    html = (
        '<a href="noise_barriers_apr10.zip">x</a>'
        '<a href="noise_barriers_jul26.zip">x</a>'
        '<a href="noise_barriers_mar22.zip">x</a>'
        '<a href="other_dataset_jan20.zip">x</a>'
    )
    assert parse_index_versions(html) == ["jul26", "mar22", "apr10"]
    assert version_sort_key("jul26") > version_sort_key("dec13")


@pytest.mark.parametrize(
    "members, expected",
    [
        # apr23 layout: geodatabase at the archive root
        (["noise_barriers_apr23.gdb/a00000001.gdbtable", "noise_barriers_apr23.gdb/gdb"],
         "noise_barriers_apr23.gdb/"),
        # jul26 layout: geodatabase one folder down
        (["noise_barriers_jul26/noise_barriers_jul26.gdb/a1.gdbtable"],
         "noise_barriers_jul26/noise_barriers_jul26.gdb/"),
    ],
)
def test_find_gdb_prefix_handles_both_archive_layouts(members, expected):
    assert _find_gdb_prefix(members) == expected


def test_find_gdb_prefix_errors_without_a_geodatabase():
    with pytest.raises(RuntimeError):
        _find_gdb_prefix(["readme.txt", "data/points.shp"])
