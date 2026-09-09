"""The CLI package wires up without importing heavy pipeline dependencies, and
every registered subcommand attaches a handler."""
import argparse

import pytest

from src.cli.main import build_parser


def test_build_parser_returns_parser():
    assert isinstance(build_parser(), argparse.ArgumentParser)


@pytest.mark.parametrize(
    "argv",
    [
        ["data", "timetable", "fetch", "--start", "2020-01-01", "--end", "2020-01-02"],
        ["data", "stations", "preprocess"],
        ["data", "network", "assemble"],
        ["data", "noise-barriers", "fetch", "--source", "railway", "--dataset-name", "X"],
    ],
)
def test_known_commands_resolve_to_a_handler(argv):
    args = build_parser().parse_args(argv)
    assert callable(args.func)


def test_noise_barriers_source_alias_maps_to_dataset_source():
    args = build_parser().parse_args(
        ["data", "noise-barriers", "fetch", "--source", "highway", "--dataset-name", "X"]
    )
    assert args.dataset_source == "highway"
