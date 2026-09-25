"""`sweden data barrier-audit import`: check a returned answers file against
its batch key and copy it to ``raw/<batch>/answers_<reviewer>.jsonl``.

The file is append-only on the reviewer's side, so a later copy contains
every earlier line: importing replaces the stored file, and refuses a file
with fewer lines than the one already stored (an older copy) unless forced.
"""
from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

from src.regions.sweden.sources.barrier_audit.shared import answers_dir, load_key, read_answer_lines


def run_barrier_audit_import(path: Path, *, force: bool = False, root: Path | None = None) -> dict:
    path = Path(path)
    records, skipped = read_answer_lines(path)
    if not records:
        raise ValueError(f"{path} holds no answers")
    batches = {r.get("batch") for r in records}
    reviewers = {r.get("reviewer") for r in records}
    if len(batches) != 1 or len(reviewers) != 1:
        raise ValueError(f"expected one batch and one reviewer, got batches {batches} and reviewers {reviewers}")
    batch, reviewer = batches.pop(), reviewers.pop()

    key = load_key(batch, root)
    known = set(key["task_id"])
    latest = {r["task_id"]: r for r in records if "task_id" in r}
    unknown = sorted(set(latest) - known)
    if unknown:
        raise ValueError(f"{len(unknown)} task_id(s) not in batch {batch!r}'s key, e.g. {unknown[:3]}")

    dest = answers_dir(batch, root) / f"answers_{reviewer}.jsonl"
    if dest.exists() and not force:
        stored, _ = read_answer_lines(dest)
        if len(stored) > len(records):
            raise ValueError(
                f"{dest} already has {len(stored)} answers, this file only {len(records)}: an older copy? Use --force to replace."
            )
    if dest.resolve() != path.resolve():
        shutil.copyfile(path, dest)

    # A task's group (a chain task has a key row per record; older keys one).
    groups = key.drop_duplicates("task_id").set_index("task_id")["task_group" if "task_group" in key.columns else "group"]
    answered = {t for t in latest}
    return {
        "batch": batch,
        "reviewer": reviewer,
        "saved": str(dest),
        "lines": len(records),
        "unreadable_lines": skipped,
        "tasks_answered": len(answered),
        "tasks_in_batch": len(known),
        "answered_by_group": dict(Counter(groups[t] for t in answered)),
        "status": dict(Counter(r["status"] if r["status"] == "aligned" else f"unsure:{r.get('reason')}" for r in latest.values())),
    }
