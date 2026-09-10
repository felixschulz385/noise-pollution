"""Shared CLI helpers. Define once here; import everywhere else — never
redefine any of these in a region or domain module."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.core.pipeline.layout import find_repo_root


def default_config_for_region(region: str) -> Path | None:
    """``orchestration/configs/<region>.yaml``, or ``None`` when not run from
    inside the repo."""
    try:
        return find_repo_root() / "orchestration" / "configs" / f"{region}.yaml"
    except FileNotFoundError:
        return None


def setup_logging(level: str = "INFO", debug: bool = False) -> None:
    """Configure the root logger once. Called at the very start of main() so
    early errors are visible, then re-called once --log-level/--debug are known."""
    effective = logging.DEBUG if debug else getattr(logging, str(level).upper(), logging.INFO)
    logging.basicConfig(
        level=effective,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def add_logging_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--log-level", default="INFO", help="Root log level (default: INFO)")
    parser.add_argument("--debug", action="store_true", help="Shorthand for --log-level DEBUG")


def add_config_arg(parser: argparse.ArgumentParser, default: Path | None = None) -> None:
    """Add --config. Pass the region's default (see ``default_config_for_region``)
    or leave it ``None`` to make --config required."""
    parser.add_argument(
        "--config",
        type=Path,
        default=default,
        required=default is None,
        help="Path to the region's config file.",
    )


def add_source_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        required=True,
        help="Name of a source defined in the region's configuration file.",
    )
