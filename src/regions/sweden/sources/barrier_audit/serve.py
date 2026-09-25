"""`sweden data barrier-audit serve`: run the reviewer app from the repo, for
the pilot and for double-coding. Answers go straight to
``raw/<batch>/answers_<reviewer>.jsonl``, so they need no `import`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from src.regions.sweden.sources.barrier_audit.shared import (
    APP_DIR,
    answers_dir,
    barrier_audit_paths,
    load_key,
    load_tasks,
)


def prepare_serve_root(batch: str, reviewer: str, *, double_coded: bool = False, root: Path | None = None) -> tuple[Path, int]:
    """Write the working folder's `tasks.json`: the batch's tasks under
    `reviewer`'s name, or only its double-coding tasks."""
    document = load_tasks(batch, root)
    if double_coded:
        key = load_key(batch, root)
        wanted = set(key.loc[key["double_code"], "task_id"])
        document["tasks"] = [t for t in document["tasks"] if t["task_id"] in wanted]
    document["reviewer"] = reviewer
    document["n_tasks"] = len(document["tasks"])
    folder = barrier_audit_paths(root)["serve"] / f"{batch}_{reviewer}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tasks.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return folder, len(document["tasks"])


def run_barrier_audit_serve(
    batch: str,
    *,
    reviewer: str = "felix",
    double_coded: bool = False,
    port: int = 8765,
    open_browser: bool = True,
    root: Path | None = None,
) -> int:
    folder, n_tasks = prepare_serve_root(batch, reviewer, double_coded=double_coded, root=root)
    print(f"Serving batch {batch!r} as {reviewer!r}: {n_tasks} tasks{' (double-coding)' if double_coded else ''}.")
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from barrier_audit.server import main

    argv = ["--root", str(folder), "--answers-dir", str(answers_dir(batch, root)), "--port", str(port)]
    if not open_browser:
        argv.append("--no-browser")
    return main(argv)
