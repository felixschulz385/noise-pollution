"""Shared CLI helpers. Define once here; import everywhere else — never
redefine any of these in a domain module."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.data.shared.paths import find_repo_root

try:
    DEFAULT_PIPELINE_CONFIG: Path | None = (
        find_repo_root() / "orchestration" / "configs" / "noise_pollution.yaml"
    )
except FileNotFoundError:  # not run from inside the repo
    DEFAULT_PIPELINE_CONFIG = None


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


def add_config_arg(parser: argparse.ArgumentParser, default: Path | None = DEFAULT_PIPELINE_CONFIG) -> None:
    """Add --config. Defaults to the project's one unified config file; pass
    default=None to make --config required instead."""
    parser.add_argument(
        "--config",
        type=Path,
        default=default,
        required=default is None,
        help="Path to the unified project config file.",
    )


def add_source_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        required=True,
        help="Name of a source defined in the configuration file.",
    )
