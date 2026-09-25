"""Build the zips sent to the reviewer.

- Device check (phase 0): the app without a `tasks.json`, which makes it
  run the self-test only.
- Batch: the app plus an exported batch's blinded `tasks.json` (never the
  key).
"""
from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

from src.regions.sweden.sources.barrier_audit.shared import APP_DIR, barrier_audit_paths, tasks_path

EXECUTABLE = 0o100755
REGULAR = 0o100644


def _app_files() -> list[Path]:
    package = APP_DIR / "barrier_audit"
    return sorted(
        p for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store"
    )


def _write(zf: zipfile.ZipFile, arcname: str, data: bytes, mode: int = REGULAR) -> None:
    info = zipfile.ZipInfo(arcname, date_time=dt.datetime.now().timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = mode << 16
    zf.writestr(info, data)


def _build_zip(path: Path, readme: str, extra: dict[str, bytes]) -> dict:
    """The app, launchers, `readme` (a file in APP_DIR) and `extra` files,
    all under one top folder named after the zip, so Extract All gives the
    reviewer a single folder."""
    name = path.stem
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = 0
    with zipfile.ZipFile(path, "w") as zf:
        _write(zf, f"{name}/README.md", (APP_DIR / readme).read_bytes())
        # Windows cmd needs CRLF line endings in a .bat.
        bat = (APP_DIR / "start_audit.bat").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        _write(zf, f"{name}/start_audit.bat", bat)
        _write(zf, f"{name}/start_audit.command", (APP_DIR / "start_audit.command").read_bytes(), EXECUTABLE)
        entries += 3
        for file in _app_files():
            _write(zf, f"{name}/{file.relative_to(APP_DIR).as_posix()}", file.read_bytes())
            entries += 1
        for arcname, data in extra.items():
            _write(zf, f"{name}/{arcname}", data)
            entries += 1
        _write(zf, f"{name}/answers/README.txt", b"The app saves its reports and answers here.\n")
        entries += 1
    return {"path": str(path), "entries": entries, "bytes": path.stat().st_size}


def build_device_check_zip(out_dir: Path | None = None, *, today: dt.date | None = None) -> dict:
    """Write `barrier_audit_device_check_<date>.zip`."""
    today = today or dt.date.today()
    out_dir = out_dir or barrier_audit_paths()["packages"]
    return _build_zip(out_dir / f"barrier_audit_device_check_{today:%Y%m%d}.zip", "README_device_check.md", {})


def build_batch_zip(batch: str, *, root: Path | None = None, today: dt.date | None = None) -> dict:
    """Write `barrier_audit_<batch>_<date>.zip` from an exported batch."""
    source = tasks_path(batch, root)
    if not source.exists():
        raise FileNotFoundError(f"No tasks for batch {batch!r} at {source}. Run `barrier-audit export --batch {batch}` first.")
    today = today or dt.date.today()
    path = barrier_audit_paths(root)["packages"] / f"barrier_audit_{batch}_{today:%Y%m%d}.zip"
    return _build_zip(path, "README_audit.md", {"tasks.json": source.read_bytes()})
