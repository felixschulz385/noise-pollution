"""Florida's `florida data <domain> <verb>` subtree resolves every wired
subcommand to a handler, and `noise-barriers fetch` defaults to the release the
notebook is built against."""
import pytest

from src.core.cli.main import build_parser
from src.regions.florida.sources.assessments.shared import (
    RESULTS_PAGES,
    validate_year,
)
from src.regions.florida.sources.schools.shared import (
    DEFAULT_SUBSOURCES,
    MSID_DATASETS,
    MSID_DEFAULT_DATASET,
    SUBSOURCES,
    api_url,
    msid_dataset_filename,
    msid_dataset_url,
    parse_year_range,
    resolve_subsources,
)
from src.regions.florida.sources.noise_barriers.fetch import _find_gdb_prefix
from src.regions.florida.sources.noise_barriers.shared import (
    DEFAULT_VERSION,
    parse_index_versions,
    validate_version,
    version_sort_key,
)
from src.regions.florida.sources.road_network.fetch import _find_shapefile_members
from src.regions.florida.sources.road_network.shared import (
    DEFAULT_VERSION as ROAD_NETWORK_DEFAULT_VERSION,
    dataset_stem as road_network_dataset_stem,
)


@pytest.mark.parametrize(
    "argv",
    [
        ["florida", "data", "noise-barriers", "list-versions"],
        ["florida", "data", "noise-barriers", "fetch"],
        ["florida", "data", "noise-barriers", "fetch", "--version", "apr23", "--keep-zip", "--no-metadata"],
        ["florida", "data", "noise-barriers", "preprocess"],
        ["florida", "data", "noise-barriers", "preprocess", "--version", "apr23"],
        ["florida", "data", "assessments", "list-years"],
        ["florida", "data", "assessments", "fetch"],
        ["florida", "data", "assessments", "fetch", "--year", "2024", "--from-file", "a.xlsx"],
        ["florida", "data", "assessments", "preprocess"],
        ["florida", "data", "assessments", "preprocess", "--year", "2024", "--year", "2025"],
        ["florida", "data", "schools", "fetch"],
        ["florida", "data", "schools", "fetch", "--subsource", "msid", "--subsource", "edge"],
        ["florida", "data", "schools", "fetch", "--subsource", "all", "--years", "2000:2010", "--refresh"],
        ["florida", "data", "schools", "fetch", "--msid-dataset", "all_schools", "--from-file", "msid.tsv"],
        ["florida", "data", "schools", "preprocess"],
        ["florida", "data", "schools", "preprocess", "--panel-years", "1995:2020", "--edge-vintage", "2324"],
        ["florida", "data", "schools", "assemble"],
        ["florida", "data", "schools", "assemble", "--max-dist", "500"],
        ["florida", "data", "schools", "assemble", "--corridor-budget", "500", "--corridor-buffer", "400"],
        ["florida", "data", "road-network", "list-versions"],
        ["florida", "data", "road-network", "fetch"],
        ["florida", "data", "road-network", "fetch", "--version", "apr23", "--keep-zip", "--no-metadata"],
        ["florida", "data", "road-network", "preprocess"],
        ["florida", "data", "road-network", "preprocess", "--version", "apr23"],
        ["florida", "data", "traffic", "list-versions"],
        ["florida", "data", "traffic", "fetch"],
        ["florida", "data", "traffic", "fetch", "--version", "apr23", "--version", "jul26", "--force"],
        ["florida", "data", "traffic", "fetch", "--limit", "5", "--keep-road-network-raw"],
        ["florida", "data", "traffic", "preprocess"],
        ["florida", "data", "traffic", "assemble"],
        ["florida", "data", "traffic", "assemble", "--max-dist", "500"],
        ["florida", "data", "road-projects", "fetch"],
        ["florida", "data", "road-projects", "fetch", "--force"],
        ["florida", "data", "road-projects", "preprocess"],
        ["florida", "data", "road-projects", "assemble"],
        ["florida", "data", "road-projects", "assemble", "--max-dist", "500", "--tolerance-mi", "0.1"],
        ["florida", "data", "shocks", "fetch"],
        ["florida", "data", "shocks", "fetch", "--force"],
        ["florida", "data", "shocks", "preprocess"],
        ["florida", "data", "shocks", "assemble"],
        ["florida", "data", "panel", "assemble"],
    ],
)
def test_known_commands_resolve_to_a_handler(argv):
    args = build_parser().parse_args(argv)
    assert callable(args.func)


def test_schools_msid_dataset_registry():
    assert MSID_DEFAULT_DATASET == "all_schools" and MSID_DEFAULT_DATASET in MSID_DATASETS
    assert msid_dataset_url("all_schools") == (
        "https://eds.fldoe.org/EDS/MasterSchoolID/Downloads/All_schools.cfm"
    )
    assert msid_dataset_filename("all_schools") == "MSID_all_schools.tsv"
    with pytest.raises(ValueError):
        msid_dataset_url("nope")


def test_schools_subsource_resolution():
    assert resolve_subsources(None) == list(DEFAULT_SUBSOURCES)
    assert resolve_subsources([]) == []
    assert resolve_subsources(["all"]) == list(SUBSOURCES)
    # order always follows SUBSOURCES, not the argument order
    assert resolve_subsources(["ccd_directory", "msid"]) == ["msid", "ccd_directory"]
    with pytest.raises(ValueError):
        resolve_subsources(["bogus"])


def test_schools_year_range_parsing():
    assert parse_year_range("1990:2026") == (1990, 2026)
    assert parse_year_range("2000-2010") == (2000, 2010)
    assert parse_year_range((1995, 1995)) == (1995, 1995)
    with pytest.raises(ValueError):
        parse_year_range("2026:1990")
    with pytest.raises(ValueError):
        parse_year_range("not-a-range")


def test_schools_api_url_shape():
    url = api_url("ccd_directory", 2015)
    assert url.startswith("https://educationdata.urban.org/api/v1/schools/ccd/directory/2015/?")
    assert "fips=12" in url


def test_schools_fetch_flags_accumulate_and_are_constrained():
    args = build_parser().parse_args(
        ["florida", "data", "schools", "fetch",
         "--subsource", "msid", "--subsource", "ccd_enrollment", "--years", "1995:2005"]
    )
    assert args.subsource == ["msid", "ccd_enrollment"]
    assert args.years == "1995:2005"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["florida", "data", "schools", "fetch", "--subsource", "bogus"])


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


def test_preprocess_defaults_to_notebook_release():
    args = build_parser().parse_args(["florida", "data", "noise-barriers", "preprocess"])
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


def test_road_network_fetch_defaults_to_the_noise_barriers_vintage():
    args = build_parser().parse_args(["florida", "data", "road-network", "fetch"])
    assert args.version == ROAD_NETWORK_DEFAULT_VERSION == "jul26"


@pytest.mark.parametrize(
    "members, stem, expected",
    [
        # flat archive root, confirmed layout for jul26 and jun04
        (
            ["rciroads_jul26.shp", "rciroads_jul26.dbf", "rciroads_jul26.shx", "rciroads_jul26.prj",
             "rciroads_jul26.sbn", "rciroads_jul26.sbx", "rciroads_jul26.cpg", "rciroads_jul26.shp.xml"],
            "rciroads_jul26",
            ["rciroads_jul26.shp", "rciroads_jul26.dbf", "rciroads_jul26.shx", "rciroads_jul26.prj",
             "rciroads_jul26.sbn", "rciroads_jul26.sbx", "rciroads_jul26.cpg", "rciroads_jul26.shp.xml"],
        ),
        # hypothetical one-folder-down nesting, ignored via basename matching
        (
            ["rciroads_apr23/rciroads_apr23.shp", "rciroads_apr23/rciroads_apr23.dbf"],
            "rciroads_apr23",
            ["rciroads_apr23/rciroads_apr23.shp", "rciroads_apr23/rciroads_apr23.dbf"],
        ),
    ],
)
def test_find_shapefile_members_matches_by_stem(members, stem, expected):
    assert _find_shapefile_members(members, stem) == expected


def test_find_shapefile_members_errors_without_a_match():
    with pytest.raises(RuntimeError):
        _find_shapefile_members(["readme.txt", "other_dataset_jul26.shp"], "rciroads_jul26")


def test_road_network_dataset_stem():
    assert road_network_dataset_stem("jul26") == "rciroads_jul26"
