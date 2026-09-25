"""Paths, constants and loaders for the Sweden `barrier_audit` source.

On disk, under ``data/sweden/barrier_audit/``:

- ``packages/<batch>_tasks.json``, ``<batch>_key.parquet`` and the zips.
  The key maps each blinded `task_id` to its barrier, group and automatic
  answer, and never leaves our side.
- ``raw/<batch>/answers_<reviewer>.jsonl``: answers, as returned (append-only,
  latest line per task wins).
- ``serve/<batch>_<reviewer>/``: the working folder of `serve` (its answers
  go straight to ``raw/``).
- ``processed/manual_sides.parquet``: one row per audited barrier, read by
  `barrier-protection build`; ``processed/audit_answers.parquet`` and
  ``processed/audit_report.json`` for checking.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources._layout import domain_dirs

APP_DIR = Path(__file__).resolve().parent / "app"
KEY_COLUMNS = ["element_id", "start_measure", "end_measure"]
STATUSES = ("aligned", "both_sides", "unsure")
UNSURE_REASONS = ("occluded", "not_visible", "other")
# |lateral_m| below this is a wall on the centreline (median, between tracks):
# no side. Same threshold as an OSM wall's offset (`OSM_MIN_OFFSET_M`).
MIN_SIDE_OFFSET_M = 2.0
# `manual_sides.decision` values that `build_barrier_references` uses.
USABLE_DECISIONS = ("side", "both_sides")


def barrier_audit_paths(root: Path | None = None) -> dict[str, Path]:
    paths = domain_dirs("barrier_audit", root)
    for name in ("packages", "serve"):
        paths[name] = paths["base"] / name
        paths[name].mkdir(parents=True, exist_ok=True)
    return paths


def tasks_path(batch: str, root: Path | None = None) -> Path:
    return barrier_audit_paths(root)["packages"] / f"{batch}_tasks.json"


def key_path(batch: str, root: Path | None = None) -> Path:
    return barrier_audit_paths(root)["packages"] / f"{batch}_key.parquet"


def answers_dir(batch: str, root: Path | None = None) -> Path:
    path = barrier_audit_paths(root)["raw"] / batch
    path.mkdir(parents=True, exist_ok=True)
    return path


def manual_sides_path(root: Path | None = None) -> Path:
    return barrier_audit_paths(root)["processed"] / "manual_sides.parquet"


def load_key(batch: str, root: Path | None = None) -> gpd.GeoDataFrame:
    path = key_path(batch, root)
    if not path.exists():
        raise FileNotFoundError(f"No key for batch {batch!r} at {path}. Run `barrier-audit export --batch {batch}` first.")
    return gpd.read_parquet(path)


def load_tasks(batch: str, root: Path | None = None) -> dict:
    return json.loads(tasks_path(batch, root).read_text(encoding="utf-8"))


def read_answer_lines(path: Path) -> tuple[list[dict], int]:
    """Every parseable JSON object in an answers file, in order, and the
    number of lines skipped (a torn last line after a crash)."""
    records, skipped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            skipped += 1
    return records, skipped


def load_manual_sides(kind: str, root: Path | None = None) -> pd.DataFrame | None:
    """The usable manual answers for one barrier kind, in the form
    `build_barrier_references(manual=...)` takes; None when the audit has
    not been preprocessed."""
    path = manual_sides_path(root)
    if not path.exists():
        return None
    sides = pd.read_parquet(path, columns=["kind", *KEY_COLUMNS, "decision", "aligned_x", "aligned_y"])
    sides = sides[(sides["kind"] == kind) & sides["decision"].isin(USABLE_DECISIONS)]
    return sides.drop(columns="kind").reset_index(drop=True)
