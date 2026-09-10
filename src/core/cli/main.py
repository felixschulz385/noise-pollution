"""Parser construction and top-level dispatch for `python -m src.cli`.

`build_parser()` creates one subparser per region; each region contributes its
own subtree via a `register(subparsers)` function. See
docs/design/01-multi-region-layout.md.
"""
from __future__ import annotations

import argparse
import logging

from src.core.cli import common

logger = logging.getLogger("src.cli")


def _region_registrars():
    # Imported lazily so a broken region module can't stop the whole CLI from
    # building, and so a region's heavy deps aren't pulled in just to show help.
    from src.regions.florida.cli import register as register_florida
    from src.regions.sweden.cli import register as register_sweden

    return (register_sweden, register_florida)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noise-pollution", description="Noise pollution research project CLI")
    common.add_logging_args(parser)
    regions = parser.add_subparsers(dest="region", required=True)

    for register in _region_registrars():
        register(regions)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Configure logging before parsing so early errors are visible...
    common.setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    # ...then re-apply once the flags are known.
    common.setup_logging(level=getattr(args, "log_level", "INFO"), debug=getattr(args, "debug", False))

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

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
