"""Sweden's `sweden data <domain> <verb>` subtree resolves every subcommand to
a handler, and noise-barriers keeps `--source` as an alias for `--dataset-source`."""
import pytest

from src.core.cli.main import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["sweden", "data", "timetable", "fetch", "--start", "2020-01-01", "--end", "2020-01-02"],
        ["sweden", "data", "stations", "preprocess"],
        ["sweden", "data", "network", "assemble"],
        ["sweden", "data", "noise-barriers", "fetch", "--source", "railway", "--dataset-name", "X"],
        ["sweden", "data", "schools", "fetch"],
        ["sweden", "data", "schools", "preprocess"],
        ["sweden", "data", "schools", "assemble"],
        ["sweden", "data", "schools", "assemble-rail-network"],
        ["sweden", "data", "schools", "assemble-road-network"],
        ["sweden", "data", "schools", "build-lineage"],
        ["sweden", "data", "network", "preprocess-tracks"],
        ["sweden", "data", "road-network", "preprocess"],
        ["sweden", "data", "assessments", "fetch-kvalitetssystem"],
        ["sweden", "data", "assessments", "preprocess-kvalitetssystem"],
        ["sweden", "data", "assessments", "fetch-siris", "--dataset-key", "salsa"],
        ["sweden", "data", "assessments", "preprocess-siris", "--dataset-key", "salsa"],
        ["sweden", "data", "panel", "assemble"],
        ["sweden", "data", "traffic", "preprocess"],
        ["sweden", "data", "traffic", "assemble"],
    ],
)
def test_known_commands_resolve_to_a_handler(argv):
    args = build_parser().parse_args(argv)
    assert callable(args.func)


def test_noise_barriers_source_alias_maps_to_dataset_source():
    args = build_parser().parse_args(
        ["sweden", "data", "noise-barriers", "fetch", "--source", "highway", "--dataset-name", "X"]
    )
    assert args.dataset_source == "highway"
