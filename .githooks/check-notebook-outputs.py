#!/usr/bin/env python3
"""Fail the commit if a staged notebook under src/experiments/ carries cell
outputs or execution counts, unless it is listed in
.githooks/notebook-output-whitelist.txt (one repo-relative path per line).

Bypass deliberately with `git commit --no-verify` when a stripped notebook is
genuinely not what you want to commit.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
WHITELIST = REPO / ".githooks" / "notebook-output-whitelist.txt"


def whitelisted() -> set[str]:
    if not WHITELIST.exists():
        return set()
    return {
        line.strip()
        for line in WHITELIST.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def staged_notebooks() -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], text=True
    )
    return [p for p in out.splitlines() if p.startswith("src/experiments/") and p.endswith(".ipynb")]


def has_outputs(path: Path) -> bool:
    try:
        nb = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    for cell in nb.get("cells", []):
        if cell.get("outputs"):
            return True
        if cell.get("execution_count") is not None:
            return True
    return False


def main() -> int:
    allowed = whitelisted()
    offenders = [
        p for p in staged_notebooks()
        if p not in allowed and has_outputs(REPO / p)
    ]
    if not offenders:
        return 0
    print("Committed notebook outputs detected:", file=sys.stderr)
    for p in offenders:
        print(f"  {p}", file=sys.stderr)
    print(
        "\nStrip them (e.g. `jupyter nbconvert --clear-output --inplace <nb>`),"
        "\nor add the path to .githooks/notebook-output-whitelist.txt if the"
        "\nrendered output is the deliverable, or commit with --no-verify.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
