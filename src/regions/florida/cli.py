"""Florida's CLI subtree.

Placeholder: no sources or analysis wired up yet. The region owner adds a
``data`` subtree here mirroring ``src/regions/sweden/cli.py`` once Florida
sources exist. See docs/design/01-multi-region-layout.md.
"""
from __future__ import annotations

import argparse


def register(regions: argparse._SubParsersAction) -> None:
    florida = regions.add_parser("florida", help="Florida pipeline (no sources wired up yet)")
    florida.add_subparsers(dest="domain", required=True)
