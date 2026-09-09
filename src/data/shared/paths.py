from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "src").exists() and (candidate / "data").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root from the current working directory.")


def ensure_domain_dirs(domain: str, root: Path | None = None) -> dict[str, Path]:
    repo_root = find_repo_root(root)
    base_dir = repo_root / "data" / domain
    paths = {
        "base": base_dir,
        "raw": base_dir / "raw",
        "processed": base_dir / "processed",
        "assembled": base_dir / "assembled",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
