"""Local web server for the barrier-audit app, standard library only.

It binds to 127.0.0.1, serves `static/`, and exposes a small JSON API:

- ``GET /api/info``: app and Python versions, whether `answers/` is
  writable, and whether a `tasks.json` is present. No `tasks.json` means
  device-check mode: the page runs the self-test and nothing else.
- ``POST /api/selftest``: saves the page's self-test report as
  ``answers/device_check_<report_id>.json``, which the reviewer sends back.
- ``GET /api/tasks``: the batch, the tasks and the latest answer per task.
- ``POST /api/answer``: validates one answer and appends it as a JSON line
  to ``answers/answers_<reviewer>.jsonl``, flushed to disk before replying.
  Nothing is ever rewritten: the latest line per task wins.

The package root (the unzipped folder) holds `tasks.json` and `answers/`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import math
import os
import platform
import re
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from barrier_audit import APP_VERSION, MAPLIBRE_VERSION

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 1_000_000

# Explicit types: on Windows `mimetypes` reads the registry, which can map
# .js to text/plain and break the page.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}
REPORT_ID = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
REVIEWER = re.compile(r"^[0-9A-Za-z_-]{1,32}$")
STATUSES = ("aligned", "both_sides", "unsure")
UNSURE_REASONS = ("occluded", "not_visible", "other")
NUMBER_FIELDS = ("lateral_m", "along_residual_m", "zoom", "seconds_on_task")
MAX_NOTE_CHARS = 2000
MAX_STREETVIEW_OPENS = 10_000


def check_answers_dir(answers_dir: Path) -> tuple[bool, str | None]:
    """Create `answers_dir` if needed and prove a file can be written there."""
    try:
        answers_dir.mkdir(parents=True, exist_ok=True)
        probe = answers_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, None
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def looks_temporary(root: Path) -> bool:
    """True when the app seems to run from inside a zip that Windows opened
    in a temp folder, where answers would be lost."""
    text = str(root).lower()
    return ".zip" in text or "\\temp\\" in text or "/temp/" in text


def read_answers(path: Path) -> tuple[dict, int]:
    """Latest answer per task_id from an append-only answers file, and the
    number of unreadable lines (a torn last line after a crash)."""
    latest, skipped = {}, 0
    if not path.exists():
        return latest, skipped
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            latest[record["task_id"]] = record
        except (json.JSONDecodeError, KeyError, TypeError):
            skipped += 1
    return latest, skipped


def validate_answer(answer: dict, task_ids: set) -> dict:
    """The answer fields the app records, checked; raises ValueError."""
    if answer.get("task_id") not in task_ids:
        raise ValueError("unknown task_id")
    status = answer.get("status")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    reason = answer.get("reason")
    note = answer.get("note") or ""
    if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
        raise ValueError("note must be text")
    if status == "unsure":
        if reason not in UNSURE_REASONS:
            raise ValueError(f"reason must be one of {UNSURE_REASONS}")
        if reason == "other" and not note.strip():
            raise ValueError("reason 'other' needs a note")
    elif reason is not None:
        raise ValueError("only unsure answers have a reason")
    clean = {"task_id": answer["task_id"], "status": status, "reason": reason, "note": note.strip() or None}
    for field in NUMBER_FIELDS:
        value = answer.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        clean[field] = round(float(value), 3)
    answered_at = answer.get("answered_at")
    if not isinstance(answered_at, str) or len(answered_at) > 40:
        raise ValueError("answered_at must be an ISO timestamp")
    clean["answered_at"] = answered_at
    # Times Street View was opened on this task (app 0.3.0; absent before).
    opens = answer.get("streetview_opens", 0)
    if isinstance(opens, bool) or not isinstance(opens, int) or not 0 <= opens <= MAX_STREETVIEW_OPENS:
        raise ValueError("streetview_opens must be a whole number >= 0")
    clean["streetview_opens"] = opens
    return clean


class AuditState:
    def __init__(self, root: Path, answers_dir: Path | None = None):
        self.root = root
        self.answers_dir = answers_dir or root / "answers"
        self.answers_writable, self.answers_error = check_answers_dir(self.answers_dir)
        self.lock = threading.Lock()
        self.tasks_doc: dict | None = None
        self.tasks_error: str | None = None
        tasks_file = root / "tasks.json"
        if tasks_file.is_file():
            try:
                self.tasks_doc = json.loads(tasks_file.read_text(encoding="utf-8"))
                if not REVIEWER.match(str(self.tasks_doc.get("reviewer", ""))):
                    raise ValueError("tasks.json has no valid reviewer name")
                self.task_ids = {t["task_id"] for t in self.tasks_doc["tasks"]}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.tasks_doc, self.tasks_error = None, f"{type(exc).__name__}: {exc}"

    @property
    def answers_file(self) -> Path:
        return self.answers_dir / f"answers_{self.tasks_doc['reviewer']}.jsonl"

    def tasks(self) -> dict:
        if self.tasks_doc is None:
            raise ValueError(self.tasks_error or "no tasks.json")
        answers, skipped = read_answers(self.answers_file)
        return {
            "batch": self.tasks_doc.get("batch"),
            "reviewer": self.tasks_doc["reviewer"],
            "answers_file": str(self.answers_file),
            "tasks": self.tasks_doc["tasks"],
            "answers": answers,
            "skipped_lines": skipped,
        }

    def append_answer(self, answer: dict) -> int:
        if self.tasks_doc is None:
            raise ValueError(self.tasks_error or "no tasks.json")
        record = {
            **validate_answer(answer, self.task_ids),
            "batch": self.tasks_doc.get("batch"),
            "reviewer": self.tasks_doc["reviewer"],
            "app_version": APP_VERSION,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self.lock:
            path = self.answers_file
            # A torn last line (crash mid-write) must not swallow this one.
            if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
                line = "\n" + line
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            answers, _ = read_answers(self.answers_file)
        return len(answers)

    def info(self) -> dict:
        tasks_present = self.tasks_doc is not None
        return {
            "app_version": APP_VERSION,
            "maplibre_version": MAPLIBRE_VERSION,
            "mode": "audit" if tasks_present else "device_check",
            "tasks_present": tasks_present,
            "tasks_error": self.tasks_error,
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "root": str(self.root),
            "root_looks_temporary": looks_temporary(self.root),
            "answers_dir": str(self.answers_dir),
            "answers_writable": self.answers_writable,
            "answers_error": self.answers_error,
            "server_time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    def save_selftest(self, report: dict) -> str:
        report_id = report.get("report_id")
        if not isinstance(report_id, str) or not REPORT_ID.match(report_id):
            raise ValueError("report_id must be 1-64 letters, digits, '-' or '_'")
        report = {**report, "server": self.info()}
        path = self.answers_dir / f"device_check_{report_id}.json"
        with self.lock:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        return path.name


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "barrier_audit/" + APP_VERSION
    state: AuditState  # set on the subclass made by make_server

    def log_message(self, format: str, *args) -> None:  # noqa: A002 -- stdlib signature
        pass  # keep the reviewer's console readable; errors are reported via send_error

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), CONTENT_TYPES[".json"])

    def do_GET(self) -> None:  # noqa: N802 -- stdlib name
        path = self.path.split("?", 1)[0]
        if path == "/api/info":
            self._send_json(200, self.state.info())
            return
        if path == "/api/tasks":
            try:
                self._send_json(200, self.state.tasks())
            except ValueError as exc:
                self._send_json(409, {"error": str(exc)})
            return
        if path in ("/", "/index.html"):
            page = "audit.html" if self.state.tasks_doc is not None or self.state.tasks_error else "device_check.html"
            path = "/static/" + page
        if not path.startswith("/static/"):
            self._send_json(404, {"error": "not found"})
            return
        target = (STATIC_DIR / path[len("/static/"):]).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, target.read_bytes(), content_type)

    def do_POST(self) -> None:  # noqa: N802 -- stdlib name
        path = self.path.split("?", 1)[0]
        if path not in ("/api/selftest", "/api/answer"):
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("bad Content-Length")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
            if path == "/api/selftest":
                reply = {"saved": f"answers/{self.state.save_selftest(body)}"}
            else:
                reply = {"ok": True, "n_answered": self.state.append_answer(body)}
        except ValueError as exc:  # includes json.JSONDecodeError
            self._send_json(400, {"error": str(exc)})
            return
        except OSError as exc:
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._send_json(200, reply)


class LocalServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second server bind a port already in
    # use, so a busy port would not be detected.
    allow_reuse_address = sys.platform != "win32"


def make_server(root: Path, port: int, answers_dir: Path | None = None) -> LocalServer:
    """Bind 127.0.0.1 on `port`, the next ten ports, or any free port."""
    handler = type("BoundHandler", (Handler,), {"state": AuditState(root, answers_dir)})
    candidates = [port + i for i in range(11)] + [0] if port else [0]
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            return LocalServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            last_error = exc
    raise OSError(f"could not bind a local port: {last_error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m barrier_audit", description="Barrier audit app")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="folder holding tasks.json and answers/")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--answers-dir", type=Path, help="default: <root>/answers")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args(argv)

    server = make_server(args.root.resolve(), args.port, args.answers_dir.resolve() if args.answers_dir else None)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Barrier audit {APP_VERSION} (Python {platform.python_version()})")
    print(f"Open this address in your browser if it does not open by itself:\n\n    {url}\n")
    print("Keep this window open while you work. Close it (or press Ctrl+C) to stop.")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Stopped.")
    return 0
