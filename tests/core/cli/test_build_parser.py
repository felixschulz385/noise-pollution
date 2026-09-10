"""The region-agnostic CLI framework builds a parser with one subparser per
registered region, without importing heavy pipeline dependencies."""
import argparse

from src.core.cli.main import build_parser


def test_build_parser_returns_parser():
    assert isinstance(build_parser(), argparse.ArgumentParser)


def test_regions_are_registered():
    parser = build_parser()
    region_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    assert {"sweden", "florida"} <= set(region_action.choices)


def test_region_is_required():
    parser = build_parser()
    region_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    assert region_action.required
