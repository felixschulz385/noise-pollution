"""Parser construction and top-level dispatch for `python -m src.cli`."""
from __future__ import annotations

import argparse
import logging

from src.cli import common
from src.cli.data import commands as data_commands

logger = logging.getLogger("src.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noise-pollution", description="Noise pollution research project CLI")
    common.add_logging_args(parser)
    subparsers = parser.add_subparsers(dest="domain", required=True)

    # One top-level subparser per domain; each domain registers its own tree.
    data_commands.register(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Configure logging before parsing so early errors are visible...
    common.setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    # ...then re-apply once the flags are known.
    common.setup_logging(level=getattr(args, "log_level", "INFO"), debug=getattr(args, "debug", False))

    try:
        result = args.func(args)
        return int(result) if isinstance(result, int) else 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception:
        logger.exception("command failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
