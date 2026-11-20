#!/usr/bin/env python3
"""Pre-commit check: block cell outputs in notebooks that must stay stripped.

A notebook "carries output" if a code cell has a non-empty ``outputs`` list or a
non-null ``execution_count``. Outputs are allowed in notebooks matched by
``notebook-output-whitelist.txt`` (``!`` re-blocks; the last match wins), and
are always blocked in a notebook whose code matches ``restricted-patterns.txt``.
Only staged content is inspected (``git show :<path>``). Stdlib only.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
WHITELIST = HOOK_DIR / "notebook-output-whitelist.txt"
PATTERNS = HOOK_DIR / "restricted-patterns.txt"


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def restricted_re() -> re.Pattern | None:
    pats = _lines(PATTERNS)
    return re.compile("|".join(f"(?:{p})" for p in pats), re.IGNORECASE) if pats else None


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def staged_notebooks() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z").decode()
    return [p for p in out.split("\0") if p.endswith(".ipynb")]


def whitelisted(path: str, patterns: list[str]) -> bool:
    allowed = False
    for pat in patterns:
        neg = pat.startswith("!")
        if fnmatch.fnmatch(path, pat[1:] if neg else pat):
            allowed = not neg
    return allowed


def main() -> int:
    patterns, rx = _lines(WHITELIST), restricted_re()
    bad: dict[str, set[str]] = {}
    for path in staged_notebooks():
        try:
            nb = json.loads(_git("show", f":{path}"))
        except json.JSONDecodeError:
            continue
        code = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
        kinds = {k for c in code for k, v in (("outputs", c.get("outputs")),
                                               ("execution_count", c.get("execution_count") is not None)) if v}
        if not kinds:
            continue
        if rx and any(rx.search("".join(c.get("source", []))) for c in code):
            bad[path] = kinds | {"reads restricted data"}
        elif not whitelisted(path, patterns):
            bad[path] = kinds
    if not bad:
        return 0
    print("\nCommit blocked: staged notebook(s) carry outputs that must be stripped.\n", file=sys.stderr)
    for path, kinds in sorted(bad.items()):
        print(f"  {path}  ({', '.join(sorted(kinds))})", file=sys.stderr)
    print("\nStrip them (jupyter nbconvert --clear-output --inplace <nb>), then git add again.\n"
          "Whitelist: .githooks/notebook-output-whitelist.txt. Bypass once: git commit --no-verify\n",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
