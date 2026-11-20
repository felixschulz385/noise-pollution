#!/usr/bin/env python3
"""Pre-commit check: keep restricted (licensed or confidential) data out of git.

Rejects staged files that are likely to carry it:

1. anything under a ``restricted/`` directory (also git-ignored);
2. data files (.csv .parquet .duckdb .db .xls .xlsx .gpkg .geojson .feather
   .pkl .zarr), unless allow-listed in ``restricted-allowlist.txt``;
3. figures and documents (.png .jpg .jpeg .gif .svg .pdf .html) whose path
   matches ``restricted-patterns.txt``, unless allow-listed.

It cannot read content, so it is a backstop: notebooks are covered by
check-notebook-outputs.py, and docs and commit messages by the rule in the
agent instructions (AGENTS.md). Stdlib only.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
DATA_EXT = (".csv", ".parquet", ".duckdb", ".db", ".xls", ".xlsx", ".gpkg", ".geojson", ".feather", ".pkl", ".zarr")
FIGURE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".html")


def _lines(name: str) -> list[str]:
    p = HOOK_DIR / name
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def staged_paths() -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                         capture_output=True, check=True).stdout.decode()
    return [p for p in out.split("\0") if p]


def reason(path: str, allowed: list[str], rx: re.Pattern | None) -> str | None:
    if "/restricted/" in f"/{path}":
        return "under a restricted/ directory"
    if any(fnmatch.fnmatch(path, pat) for pat in allowed):
        return None
    low = path.lower()
    if low.endswith(DATA_EXT):
        return "data file"
    if rx and low.endswith(FIGURE_EXT) and rx.search(path):
        return "figure or document named after restricted data"
    return None


def main() -> int:
    pats = _lines("restricted-patterns.txt")
    rx = re.compile("|".join(f"(?:{p})" for p in pats), re.IGNORECASE) if pats else None
    allowed = _lines("restricted-allowlist.txt")
    bad = [(p, r) for p in staged_paths() if (r := reason(p, allowed, rx))]
    if not bad:
        return 0
    print("\nCommit blocked: staged file(s) may carry restricted data.\n", file=sys.stderr)
    for p, r in bad:
        print(f"  {p}  ({r})", file=sys.stderr)
    print("\nUnstage them (git restore --staged <path>). If a file holds only aggregate results,\n"
          "add it to .githooks/restricted-allowlist.txt. Bypass once: git commit --no-verify\n",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
