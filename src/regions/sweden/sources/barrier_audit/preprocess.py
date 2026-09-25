"""`sweden data barrier-audit preprocess`: every imported answer file ->
``processed/manual_sides.parquet`` (one row per audited barrier, read by
`barrier-protection build`), ``audit_answers.parquet`` and
``audit_report.json``.

**One answer per reviewer and task:** the file's last line for the task.
Each answer gets a category: `left` / `right` (aligned, |lateral_m| >=
`MIN_SIDE_OFFSET_M`, signed along the task's left normal), `centre`
(aligned closer than that), `both_sides` (walls on both sides), or its
unsure reason.

**One decision per barrier** (answers from every reviewer and batch;
practice answers excluded). `occluded` and `other` abstain. If the other
answers all share one category it decides:

| category | decision | used by `build_barrier_references` |
|---|---|---|
| `left` / `right` | `side` | yes: `manual`, the aligned point's side |
| `both_sides` | `both_sides` | yes: `manual_both_sides` |
| `centre` | `centre` | no |
| `not_visible` | `not_visible` | no; listed in the report |
| (only abstentions) | `unsure` | no |
| (disagreement) | `conflict` | no; listed in the report |

The aligned point is the view centre moved by the mean `lateral_m` along
the normal: where the reviewer put the line on the wall. The row's geometry
is the barrier offset by that distance (shapely's `offset_curve`, positive =
left, the same convention as the app).

**Report:** answers whose barrier is no longer in the barrier layer
(`stale`), the `not_visible` and `conflict` barriers, validation accuracy
per automatic method (manual vs automatic sign against the saved
through-line, with a Wilson 95% interval), the same for rail's candidate
`outer_track_sign`, double-coding agreement
(Cohen's kappa on the category, median |difference| in `lateral_m`), and
practice results per reviewer.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from src.core.barrier_geometry.linear_ref import signed_side
from src.regions.sweden.sources._layout import METRIC_CRS
from src.regions.sweden.sources.barrier_audit.shared import (
    KEY_COLUMNS,
    MIN_SIDE_OFFSET_M,
    barrier_audit_paths,
    load_key,
    manual_sides_path,
    read_answer_lines,
)
from src.regions.sweden.sources.barrier_protection.shared import references_path
from src.regions.sweden.sources.noise_barriers.shared import load_noise_barriers

ABSTAIN = ("occluded", "other")
# Aids beyond the aerial photo a reviewer used on a barrier (app 0.3.0+).
AID_COLUMNS = ("with_streetview", "with_satellite", "with_infrared")
DECISIONS = {
    "left": "side", "right": "side", "both_sides": "both_sides", "centre": "centre", "not_visible": "not_visible",
    "changes_side": "changes_side",  # the wall switches sides along a chain task: back to one task per record
}
ANSWER_COLUMNS = [
    "batch", "reviewer", "task_id", "status", "reason", "note", "lateral_m", "along_residual_m",
    "zoom", "seconds_on_task", "answered_at", "app_version", "streetview_opens", "satellite_opens", "imagery",
]


def load_answers(root: Path | None = None) -> pd.DataFrame:
    """Latest answer per (batch, reviewer, task) from every
    ``raw/<batch>/answers_*.jsonl``, joined with its batch key."""
    frames = []
    for batch_dir in sorted(p for p in barrier_audit_paths(root)["raw"].iterdir() if p.is_dir()):
        files = sorted(batch_dir.glob("answers_*.jsonl"))
        if not files:
            continue
        key = pd.DataFrame(load_key(batch_dir.name, root).drop(columns="geometry"))
        if "chain_orient" not in key.columns:  # keys exported before chain tasks: one record per task
            key["chain_orient"] = 1
        for file in files:
            records, _ = read_answer_lines(file)
            if not records:
                continue
            answers = pd.DataFrame(records).reindex(columns=ANSWER_COLUMNS)
            # Absent before app 0.3.0 (Street View) / 0.4.0 (satellite, imagery).
            for column in ("streetview_opens", "satellite_opens"):
                answers[column] = answers[column].fillna(0).astype(int)
            answers["imagery"] = answers["imagery"].fillna("colour")
            answers["batch"] = batch_dir.name
            answers = answers.drop_duplicates(["reviewer", "task_id"], keep="last")
            frames.append(answers.merge(key, on=["task_id", "batch"], how="inner"))
    if not frames:
        return pd.DataFrame(columns=ANSWER_COLUMNS)
    answers = pd.concat(frames, ignore_index=True)
    answers["category"] = categorize(answers)
    answers["aligned_x"] = answers["center_x"] + answers["lateral_m"] * answers["n_x"]
    answers["aligned_y"] = answers["center_y"] + answers["lateral_m"] * answers["n_y"]
    return answers


def categorize(answers: pd.DataFrame) -> pd.Series:
    aligned = answers["status"] == "aligned"
    lateral = answers["lateral_m"].astype(float)
    return pd.Series(
        np.select(
            [aligned & (lateral >= MIN_SIDE_OFFSET_M), aligned & (lateral <= -MIN_SIDE_OFFSET_M), aligned, answers["status"] == "both_sides"],
            ["left", "right", "centre", "both_sides"],
            default=answers["reason"].astype(object),
        ),
        index=answers.index,
    )


def decide(categories: list[str]) -> tuple[str, str | None]:
    """(decision, winning category) for one barrier's answer categories."""
    votes = {c for c in categories if c not in ABSTAIN}
    if not votes:
        return "unsure", None
    if len(votes) > 1:
        return "conflict", None
    category = votes.pop()
    return DECISIONS[category], category


def manual_sides(answers: pd.DataFrame, lines: gpd.GeoSeries) -> gpd.GeoDataFrame:
    """One row per barrier with a non-practice answer. `lines` maps a key
    row's (`task_id`, `kind`, *KEY_COLUMNS) to that record's line (EPSG:3006)
    stored in the batch key. In a task covering several records of one wall,
    the offset is along the task's left normal, so a record digitised against
    the chain (`chain_orient` -1) gets its offset line on its own right."""
    work = answers[answers["group"] != "practice"]
    rows = []
    for (kind, *key), group in work.groupby(["kind", *KEY_COLUMNS], sort=True):
        decision, category = decide(group["category"].tolist())
        record = {
            "kind": kind,
            **dict(zip(KEY_COLUMNS, key)),
            "decision": decision,
            "lateral_m": np.nan,
            "aligned_x": np.nan,
            "aligned_y": np.nan,
            "n_answers": len(group),
            "reviewers": ",".join(sorted(set(group["reviewer"]))),
            "categories": ",".join(group["category"]),
            "groups": ",".join(sorted(set(group["group"]))),
            "batches": ",".join(sorted(set(group["batch"]))),
            "notes": " | ".join(n for n in group["note"].dropna() if n) or None,
            "geometry": None,
        }
        if decision == "side":
            chosen = group[group["category"] == category]
            first = chosen.iloc[0]
            lateral = float(chosen["lateral_m"].mean())
            record.update(
                lateral_m=lateral,
                aligned_x=first["center_x"] + lateral * first["n_x"],
                aligned_y=first["center_y"] + lateral * first["n_y"],
                geometry=lines.loc[(first["task_id"], kind, *key)].offset_curve(lateral * first["chain_orient"]),
            )
        rows.append(record)
    return gpd.GeoDataFrame(rows, columns=list(rows[0]) if rows else ["kind", *KEY_COLUMNS, "decision", "geometry"],
                            geometry="geometry", crs=METRIC_CRS)


def through_line_signs(sides: pd.DataFrame, root: Path | None) -> pd.Series:
    """Manual sign (+1 left / -1 right of the barrier's saved through-line)
    of each `side` row's aligned point; NaN where there is none."""
    signs = pd.Series(np.nan, index=sides.index)
    for kind, group in sides[sides["decision"] == "side"].groupby("kind"):
        path = references_path(kind, root)
        if not path.exists():
            continue
        refs = gpd.read_parquet(path, columns=[*KEY_COLUMNS, "geometry"])
        joined = group[KEY_COLUMNS].reset_index().merge(refs, on=KEY_COLUMNS, how="inner")
        for r in joined.itertuples():
            point = Point(sides.at[r.index, "aligned_x"], sides.at[r.index, "aligned_y"])
            signs[r.index] = float(signed_side(r.geometry, [point])[0][0])
    return signs


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 3), round(centre + half, 3)]


def cohens_kappa(a: list[str], b: list[str]) -> float | None:
    if not a:
        return None
    cats = sorted(set(a) | set(b))
    a, b = np.asarray(a), np.asarray(b)
    observed = float(np.mean(a == b))
    expected = float(sum(np.mean(a == c) * np.mean(b == c) for c in cats))
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def validation_report(answers: pd.DataFrame, sides: pd.DataFrame) -> dict:
    """Per automatic method: how the validation barriers were decided, and
    how often a manual side agrees with the automatic one -- overall and for
    the barriers where a reviewer opened Street View, opened Google
    satellite, or answered on the infrared photo."""
    validated = answers.loc[answers["group"] == "validation", ["kind", *KEY_COLUMNS, "side_method", "barrier_sign", "task_id"]]
    used = answers.assign(
        with_streetview=answers["streetview_opens"] > 0,
        with_satellite=answers["satellite_opens"] > 0,
        with_infrared=answers["imagery"] == "infrared",
    ).groupby(["kind", *KEY_COLUMNS])[list(AID_COLUMNS)].any().reset_index()
    validated = validated.drop_duplicates(["kind", *KEY_COLUMNS]).merge(sides, on=["kind", *KEY_COLUMNS])
    validated = validated.merge(used, on=["kind", *KEY_COLUMNS], how="left")
    report = {}
    for method, group in validated.groupby("side_method"):
        sided = group[(group["decision"] == "side") & group["manual_sign"].notna()]
        agree = int((sided["manual_sign"] == sided["barrier_sign"]).sum())
        report[method] = {
            "n_barriers": len(group),
            "decisions": {k: int(v) for k, v in group["decision"].value_counts().items()},
            "n_sided": len(sided),
            # Records of one wall answered in one task aren't independent.
            "n_walls_sided": int(sided["task_id"].nunique()),
            "agree": agree,
            "share_agree": round(agree / len(sided), 3) if len(sided) else None,
            "wilson_95": wilson(agree, len(sided)),
            **{
                aid: {
                    "n_sided": int(flag.sum()),
                    "agree": int((sided.loc[flag, "manual_sign"] == sided.loc[flag, "barrier_sign"]).sum()),
                }
                for aid in AID_COLUMNS
                for flag in [sided[aid].fillna(False).astype(bool)]
            },
        }
    return report


def outer_track_report(answers: pd.DataFrame, sides: pd.DataFrame) -> dict:
    """Rail barriers on an outer track (`outer_track_sign` +-1 in the key):
    how they were decided, and how often a manual side is the one away from
    the other tracks. Decides whether `outer_track` becomes a side method."""
    if "outer_track_sign" not in answers.columns:
        return {"n_barriers": 0}
    work = answers[(answers["group"] != "practice") & (answers["kind"] == "rail") & answers["outer_track_sign"].isin([1.0, -1.0])]
    work = work[["kind", *KEY_COLUMNS, "group", "outer_track_sign"]].drop_duplicates(["kind", *KEY_COLUMNS])
    work = work.merge(sides, on=["kind", *KEY_COLUMNS])
    report = {}
    for label, group in (("all", work), *work.groupby("group")):
        sided = group[(group["decision"] == "side") & group["manual_sign"].notna()]
        agree = int((sided["manual_sign"] == sided["outer_track_sign"]).sum())
        report[label] = {
            "n_barriers": len(group),
            "decisions": {k: int(v) for k, v in group["decision"].value_counts().items()},
            "n_sided": len(sided),
            "agree": agree,
            "share_agree": round(agree / len(sided), 3) if len(sided) else None,
            "wilson_95": wilson(agree, len(sided)),
        }
    return report


def double_coding_report(answers: pd.DataFrame) -> dict:
    """Agreement between reviewers on the tasks both answered."""
    # One row per reviewer and task: a chain task has a key row per record.
    work = answers[answers["group"] != "practice"].drop_duplicates(["batch", "reviewer", "task_id"])
    pairs = work.merge(work, on=["batch", "task_id"], suffixes=("_a", "_b"))
    pairs = pairs[pairs["reviewer_a"] < pairs["reviewer_b"]]
    if pairs.empty:
        return {"n_tasks": 0}
    both_sided = pairs[pairs["category_a"].isin(["left", "right"]) & (pairs["category_a"] == pairs["category_b"])]
    return {
        "n_tasks": len(pairs),
        "reviewers": sorted(set(pairs["reviewer_a"]) | set(pairs["reviewer_b"])),
        "share_same_category": round(float((pairs["category_a"] == pairs["category_b"]).mean()), 3),
        "kappa_category": cohens_kappa(pairs["category_a"].tolist(), pairs["category_b"].tolist()),
        "median_abs_lateral_diff_m": (
            round(float((both_sided["lateral_m_a"] - both_sided["lateral_m_b"]).abs().median()), 2) if len(both_sided) else None
        ),
    }


def practice_report(answers: pd.DataFrame) -> dict:
    practice = answers[answers["group"] == "practice"]
    report = {}
    for reviewer, group in practice.groupby("reviewer"):
        truth = np.where(group["practice_lateral_m"] > 0, "left", "right")
        report[reviewer] = {
            "n": len(group),
            "same_side_as_osm": int((group["category"].to_numpy() == truth).sum()),
            "median_abs_error_m": round(float((group["lateral_m"] - group["practice_lateral_m"]).abs()[group["status"] == "aligned"].median()), 2)
            if (group["status"] == "aligned").any() else None,
        }
    return report


def stale_rows(sides: pd.DataFrame, root: Path | None) -> pd.Series:
    """True for rows whose barrier key is no longer in the barrier layer."""
    stale = pd.Series(False, index=sides.index)
    for kind, group in sides.groupby("kind"):
        current = load_noise_barriers(kind, root)[KEY_COLUMNS]
        present = group[KEY_COLUMNS].reset_index().merge(current, on=KEY_COLUMNS, how="left", indicator=True)
        stale[present.loc[present["_merge"] == "left_only", "index"]] = True
    return stale


def run_barrier_audit_preprocess(root: Path | None = None) -> dict:
    answers = load_answers(root)
    if answers.empty:
        raise ValueError("No answers imported yet: run `barrier-audit import` (or `serve`) first.")
    lines = pd.concat(
        [load_key(b, root).set_index(["task_id", "kind", *KEY_COLUMNS]).geometry for b in sorted(answers["batch"].unique())]
    )
    sides = manual_sides(answers, lines)
    sides["stale"] = stale_rows(sides, root)
    sides["manual_sign"] = through_line_signs(sides, root)

    processed = barrier_audit_paths(root)["processed"]
    sides.to_parquet(manual_sides_path(root), index=False)
    answers.drop(columns=[c for c in ("geometry",) if c in answers]).to_parquet(processed / "audit_answers.parquet", index=False)

    listing = ["kind", *KEY_COLUMNS, "reviewers", "categories", "notes"]
    report = {
        "n_answers": len(answers),
        "reviewers": {r: int(n) for r, n in answers["reviewer"].value_counts().items()},
        "n_barriers": len(sides),
        "decisions": {k: int(v) for k, v in sides["decision"].value_counts().items()},
        "used_by_build": int((sides["decision"].isin(["side", "both_sides"]) & ~sides["stale"]).sum()),
        "stale": sides.loc[sides["stale"], listing].to_dict("records"),
        "not_visible": sides.loc[sides["decision"] == "not_visible", listing].to_dict("records"),
        "conflict": sides.loc[sides["decision"] == "conflict", listing].to_dict("records"),
        "changes_side": sides.loc[sides["decision"] == "changes_side", listing].to_dict("records"),
        "validation": validation_report(answers, sides),
        "outer_track": outer_track_report(answers, sides),
        "double_coding": double_coding_report(answers),
        "practice": practice_report(answers),
    }
    (processed / "audit_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return {
        "saved": str(manual_sides_path(root)),
        **{k: report[k] for k in ("n_answers", "reviewers", "n_barriers", "decisions", "used_by_build", "validation", "outer_track", "double_coding", "practice")},
        "n_stale": len(report["stale"]),
        "n_not_visible": len(report["not_visible"]),
        "n_conflict": len(report["conflict"]),
        "n_changes_side": len(report["changes_side"]),
        "next": "re-run `sweden data barrier-protection build`, then schools/grid/panel assemble",
    }
