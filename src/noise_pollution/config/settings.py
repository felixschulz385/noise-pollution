"""Read the unified config and its local overrides once (template rule: docs/pipeline/configuration.md).

``orchestration/configs/noise_pollution.yaml`` is the unified config; per-machine values (the data
root) go in ``noise_pollution.local.yaml`` next to it, git-ignored, read on top. A relative
``data_root`` is taken relative to the repository root. Without either file the data root is
``data/`` in the repository, the layout this project has always used.

The region pipelines still take their settings from argparse defaults; moving them into the
``regions`` blocks of the unified config is an open step (docs/design/2026-11-template-port.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

CONFIG = Path("orchestration") / "configs" / "noise_pollution.yaml"
DEFAULT_DATA_ROOT = "data"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@dataclass
class RunContext:
    data_root: Path
    regions: dict = field(default_factory=dict)
    override: bool = False


def read(path: str | Path) -> dict:
    """The config at *path* (``{}`` if absent), with ``<stem>.local.yaml`` next to it on top."""
    path = Path(path)
    cfg: dict = {}
    local = path.with_name(f"{path.stem}.local.yaml")
    if path.exists() or local.exists():
        import yaml  # only when a config exists, so a bare checkout needs no PyYAML

        if path.exists():
            cfg = yaml.safe_load(path.read_text()) or {}
        if local.exists():
            cfg = _merge(cfg, yaml.safe_load(local.read_text()) or {})
    return cfg


def load(path: str | Path, repo_root: Path | None = None) -> RunContext:
    """The run context from the config at *path*; a relative data root is resolved against
    *repo_root* (default: the folder three levels above ``orchestration/configs/<file>``)."""
    path = Path(path)
    cfg = read(path)
    root = repo_root if repo_root is not None else path.resolve().parent.parent.parent
    data_root = Path(cfg.get("data_root") or DEFAULT_DATA_ROOT)
    if not data_root.is_absolute():
        data_root = root / data_root
    return RunContext(data_root=data_root, regions=cfg.get("regions") or {})


@lru_cache(maxsize=None)
def data_root(repo_root: Path) -> Path:
    """The data root for the repository at *repo_root* (cached per process)."""
    return load(repo_root / CONFIG, repo_root=repo_root).data_root
