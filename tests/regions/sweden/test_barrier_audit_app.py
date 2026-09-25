"""Tests for the reviewer-side barrier-audit app and its zips: the app uses
the standard library only, the local API serves the pages, saves self-test
reports and appends answers (latest per task wins, a torn line is
survived, Street View opens are recorded), the unzipped package starts on
its own, and the browser's maths (geometry.js, run in Node) matches
shapely's side convention and the true azimuth for Street View."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pytest

from src.regions.sweden.sources.barrier_audit.package import build_device_check_zip
from src.regions.sweden.sources.barrier_audit.shared import APP_DIR


@pytest.fixture
def server_module(monkeypatch):
    monkeypatch.syspath_prepend(str(APP_DIR))
    from barrier_audit import server

    return server


@pytest.fixture
def running(server_module, tmp_path):
    srv = server_module.make_server(tmp_path, 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    srv.shutdown()
    srv.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_app_imports_only_the_standard_library():
    for file in (APP_DIR / "barrier_audit").rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                assert top in sys.stdlib_module_names or top in ("barrier_audit", "__future__"), f"{file.name}: {name}"


TASKS = {
    "batch": "pilot",
    "reviewer": "tester",
    "tasks": [{"task_id": "aaaa0001", "practice": False}, {"task_id": "aaaa0002", "practice": False}],
}


def _answer(task_id="aaaa0001", **kw):
    base = {"task_id": task_id, "status": "aligned", "reason": None, "note": None, "lateral_m": 6.5,
            "along_residual_m": 1.0, "zoom": 19.2, "seconds_on_task": 12.0, "answered_at": "2026-09-24T12:00:00Z"}
    return {**base, **kw}


@pytest.fixture
def audit(server_module, tmp_path):
    (tmp_path / "tasks.json").write_text(json.dumps(TASKS))
    srv = server_module.make_server(tmp_path, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    srv.shutdown()
    srv.server_close()


def test_info_reports_device_check_mode_without_tasks(running):
    base, root = running
    status, ctype, body = _get(base + "/api/info")
    info = json.loads(body)
    assert status == 200 and ctype.startswith("application/json")
    assert info["mode"] == "device_check" and info["answers_writable"] is True
    assert b"selftest.js" in _get(base + "/")[2]


def test_audit_mode_serves_the_audit_page_and_tasks(audit):
    base, _ = audit
    assert json.loads(_get(base + "/api/info")[2])["mode"] == "audit"
    assert b"audit.js" in _get(base + "/")[2]
    data = json.loads(_get(base + "/api/tasks")[2])
    assert [t["task_id"] for t in data["tasks"]] == ["aaaa0001", "aaaa0002"] and data["answers"] == {}


def test_answers_append_and_the_latest_per_task_wins(audit):
    base, root = audit
    assert _post(base + "/api/answer", _answer(lateral_m=6.5))[0] == 200
    assert _post(base + "/api/answer", _answer(status="unsure", reason="occluded", lateral_m=0.0)) == (200, {"ok": True, "n_answered": 1})
    lines = (root / "answers" / "answers_tester.jsonl").read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["lateral_m"] == 6.5 and first["batch"] == "pilot" and first["reviewer"] == "tester" and first["app_version"]
    answers = json.loads(_get(base + "/api/tasks")[2])["answers"]
    assert answers["aaaa0001"]["status"] == "unsure"


def test_walls_on_both_sides_is_its_own_answer(audit):
    base, _ = audit
    assert _post(base + "/api/answer", _answer(status="both_sides", lateral_m=0.0))[0] == 200
    assert json.loads(_get(base + "/api/tasks")[2])["answers"]["aaaa0001"]["status"] == "both_sides"


@pytest.mark.parametrize(
    "bad",
    [
        {"task_id": "nope"},
        {"status": "maybe"},
        {"status": "unsure", "reason": "tired"},
        {"status": "unsure", "reason": "both_sides"},  # an answer of its own since 0.2.0
        {"status": "both_sides", "reason": "occluded"},
        {"status": "unsure", "reason": "other", "note": "  "},
        {"reason": "occluded"},
        {"lateral_m": float("nan")},
        {"lateral_m": "5"},
        {"seconds_on_task": None},
        {"streetview_opens": -1},
        {"streetview_opens": 1.5},
        {"streetview_opens": "2"},
        {"streetview_opens": True},
    ],
)
def test_invalid_answers_are_rejected_and_not_written(audit, bad):
    base, root = audit
    body = _answer(**bad)
    payload = json.dumps(body, allow_nan=True).encode()
    req = urllib.request.Request(base + "/api/answer", data=payload, headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 400
    assert not (root / "answers" / "answers_tester.jsonl").exists()


def test_streetview_opens_are_recorded_and_default_to_zero(audit):
    base, root = audit
    assert _post(base + "/api/answer", _answer(streetview_opens=2))[0] == 200
    assert _post(base + "/api/answer", _answer("aaaa0002"))[0] == 200  # an app 0.2.0 answer has no count
    lines = [json.loads(line) for line in (root / "answers" / "answers_tester.jsonl").read_text().splitlines()]
    assert [line["streetview_opens"] for line in lines] == [2, 0]


def test_a_torn_last_line_is_skipped_and_not_glued_to_the_next(audit):
    base, root = audit
    path = root / "answers" / "answers_tester.jsonl"
    path.write_text(json.dumps(_answer("aaaa0002")) + "\n" + '{"task_id": "aaaa00')
    assert _post(base + "/api/answer", _answer())[0] == 200
    data = json.loads(_get(base + "/api/tasks")[2])
    assert set(data["answers"]) == {"aaaa0001", "aaaa0002"} and data["skipped_lines"] == 1


def test_page_and_bundled_maplibre_are_served_with_explicit_types(running):
    base, _ = running
    status, ctype, body = _get(base + "/")
    assert status == 200 and ctype.startswith("text/html") and b"selftest.js" in body
    status, ctype, body = _get(base + "/static/vendor/maplibre-gl.js")
    assert ctype.startswith("text/javascript") and b"MapLibre GL JS" in body[:200]


@pytest.mark.parametrize("path", ["/static/../server.py", "/static/%2e%2e/server.py", "/server.py", "/static/nope.js"])
def test_files_outside_static_are_not_served(running, path):
    base, _ = running
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base + path)
    assert exc.value.code == 404


def test_selftest_report_is_saved_to_answers(running):
    base, root = running
    status, body = _post(base + "/api/selftest", {"report_id": "2026-09-24T10-00-00-000", "results": {"webgl": {"status": "ok"}}})
    assert status == 200 and body["saved"] == "answers/device_check_2026-09-24T10-00-00-000.json"
    saved = json.loads((root / body["saved"]).read_text(encoding="utf-8"))
    assert saved["results"]["webgl"]["status"] == "ok" and saved["server"]["mode"] == "device_check"
    # A second save for the same report replaces the file.
    _post(base + "/api/selftest", {"report_id": "2026-09-24T10-00-00-000", "results": {}})
    assert list((root / "answers").iterdir()) == [root / body["saved"]]


@pytest.mark.parametrize("report_id", ["../escape", "", "a" * 65, None])
def test_selftest_rejects_unsafe_report_ids(running, report_id):
    base, root = running
    status, body = _post(base + "/api/selftest", {"report_id": report_id})
    assert status == 400 and "report_id" in body["error"]
    assert list((root / "answers").iterdir()) == []


def test_busy_port_moves_to_the_next_one(server_module, tmp_path):
    first = server_module.make_server(tmp_path, 0)
    try:
        port = first.server_address[1]
        second = server_module.make_server(tmp_path, port)
        assert second.server_address[1] != port
        second.server_close()
    finally:
        first.server_close()


def test_temporary_zip_folders_are_flagged(server_module):
    assert server_module.looks_temporary(Path(r"C:\Users\x\AppData\Local\Temp\Temp1_barrier_audit.zip\barrier_audit"))
    assert not server_module.looks_temporary(Path("/Users/x/Documents/barrier_audit_device_check_20260924"))


def test_device_check_zip_layout(tmp_path):
    import datetime as dt

    result = build_device_check_zip(tmp_path, today=dt.date(2026, 9, 24))
    top = "barrier_audit_device_check_20260924/"
    with zipfile.ZipFile(result["path"]) as zf:
        names = set(zf.namelist())
        assert {top + "README.md", top + "start_audit.bat", top + "start_audit.command",
                top + "barrier_audit/__main__.py", top + "barrier_audit/static/vendor/maplibre-gl.js",
                top + "answers/README.txt"} <= names
        assert all(n.startswith(top) for n in names)
        assert not any("__pycache__" in n or n.endswith("tasks.json") for n in names)
        assert (zf.getinfo(top + "start_audit.command").external_attr >> 16) & 0o111
        bat = zf.read(top + "start_audit.bat")
        assert bat.count(b"\r\n") == bat.count(b"\n")


def test_batch_zip_carries_the_tasks_but_not_the_key(tmp_path, monkeypatch):
    from src.regions.sweden.sources.barrier_audit import package

    monkeypatch.setattr(package, "tasks_path", lambda batch, root=None: tmp_path / f"{batch}_tasks.json")
    monkeypatch.setattr(package, "barrier_audit_paths", lambda root=None: {"packages": tmp_path / "packages"})
    (tmp_path / "pilot_tasks.json").write_text(json.dumps(TASKS))
    (tmp_path / "pilot_key.parquet").write_text("secret")
    result = package.build_batch_zip("pilot")
    with zipfile.ZipFile(result["path"]) as zf:
        names = zf.namelist()
        top = names[0].split("/")[0] + "/"
        assert json.loads(zf.read(top + "tasks.json")) == TASKS
        assert not any("key" in n for n in names)
        assert b"Barrier audit" in zf.read(top + "README.md")


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_browser_offset_maths_matches_shapely_and_signed_side():
    """geometry.js (what the reviewer sees) against the pipeline: the offset
    curve lies |d| from the line, on the side `signed_side` calls left for
    d > 0, and decompose inverts centerAt."""
    from shapely.geometry import LineString, Point

    from src.core.barrier_geometry.linear_ref import signed_side

    theta = np.linspace(0, np.pi / 3, 25)
    arc = np.c_[300 * np.sin(theta), 300 * (1 - np.cos(theta))]  # curving left
    line = LineString(arc)
    task = {
        "center": [18.0, 59.3],
        "jacobian": [[1.7e-5, 1.0e-7], [-2.0e-7, 9.0e-6]],
        "tangent": [0.8, 0.6],
        "normal": [-0.6, 0.8],
        "line_m": arc.tolist(),
        "line_lonlat": arc.tolist(),
    }
    script = """
const G = require(process.argv[1]);
const task = JSON.parse(process.argv[2]);
const out = {};
for (const d of [6, -9]) out[d] = G.offsetDisplacements(task.line_m, d).map((v, i) => [task.line_m[i][0] + v[0], task.line_m[i][1] + v[1]]);
const c = G.centerAt(task, 4.25, -30);
out.decomposed = G.decompose(task, c[0], c[1]);
console.log(JSON.stringify(out));
"""
    geometry_js = str(APP_DIR / "barrier_audit" / "static" / "geometry.js")
    result = subprocess.run([NODE, "-e", script, geometry_js, json.dumps(task)], capture_output=True, text=True, check=True)
    out = json.loads(result.stdout)
    for d in (6, -9):
        pts = np.asarray(out[str(d)])
        distances = [line.distance(Point(p)) for p in pts]
        assert np.allclose(distances, abs(d), atol=0.02)
        signs, _ = signed_side(line, [Point(p) for p in pts[1:-1]])
        assert set(signs) == {np.sign(d)}
        assert LineString(pts).hausdorff_distance(line.offset_curve(d)) < 0.05
    assert out["decomposed"]["d"] == pytest.approx(4.25) and out["decomposed"]["along"] == pytest.approx(-30)


@pytest.mark.skipif(NODE is None, reason="needs node")
@pytest.mark.parametrize(
    "coords",
    [
        [(0, 0), (200, 0)],  # east
        [(200, 0), (0, 0)],  # west: digitised the other way
        [(0, 0), (-3, 200)],  # just west of grid north: the heading wraps to ~359
        [(0, 0), (100, 10), (180, 60), (220, 140)],  # curving left
    ],
)
def test_streetview_looks_along_the_barrier_from_its_nearest_point(coords):
    """The Street View camera (geometry.js) sits on the recorded line nearest
    the view centre moved `along`, and faces the line's digitised direction
    there as a true azimuth (EPSG:3006 grid north is not true north)."""
    from pyproj import Geod, Transformer
    from shapely.geometry import LineString, Point

    from src.regions.sweden.sources.barrier_audit.export import task_geometry

    x0, y0 = 674_000.0, 6_580_000.0  # Stockholm
    line = LineString([(x0 + x, y0 + y) for x, y in coords])
    center = line.interpolate(0.5, normalized=True)
    task = {**task_geometry(line, center), "kind": "road"}
    script = """
const G = require(process.argv[1]);
const task = JSON.parse(process.argv[2]);
const out = [-60, 0, 45].map(a => ({ along: a, sv: G.streetView(task, a), url: G.streetViewUrl(G.streetView(task, a)) }));
console.log(JSON.stringify(out));
"""
    geometry_js = str(APP_DIR / "barrier_audit" / "static" / "geometry.js")
    result = subprocess.run([NODE, "-e", script, geometry_js, json.dumps(task)], capture_output=True, text=True, check=True)
    to_ll = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True)
    geod = Geod(ellps="GRS80")
    t = np.asarray(task["tangent"])
    for case in json.loads(result.stdout):
        target = Point(center.x + case["along"] * t[0], center.y + case["along"] * t[1])
        s = line.project(target)
        lon, lat = to_ll.transform(*line.interpolate(s).coords[0])
        assert geod.inv(lon, lat, case["sv"]["lon"], case["sv"]["lat"])[2] < 0.05  # metres
        a, b = line.interpolate(max(s - 0.5, 0)), line.interpolate(min(s + 0.5, line.length))
        azimuth = geod.inv(*to_ll.transform(a.x, a.y), *to_ll.transform(b.x, b.y))[0] % 360
        diff = (case["sv"]["heading"] - azimuth + 180) % 360 - 180
        assert abs(diff) < 0.5, (case, azimuth)
        assert 0 <= case["sv"]["heading"] < 360
        assert case["url"] == (
            f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={case['sv']['lat']:.6f},{case['sv']['lon']:.6f}"
            f"&heading={round(case['sv']['heading']) % 360}"
        )


def test_unzipped_package_starts_without_the_repo(tmp_path):
    result = build_device_check_zip(tmp_path / "out")
    with zipfile.ZipFile(result["path"]) as zf:
        zf.extractall(tmp_path / "unzipped")
    folder = next((tmp_path / "unzipped").iterdir())
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "barrier_audit", "--no-browser", "--port", "0"],
        cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        url = None
        for _ in range(10):
            line = proc.stdout.readline()
            match = re.search(r"http://127\.0\.0\.1:\d+/", line)
            if match:
                url = match.group(0)
                break
        assert url, "server did not print its address"
        info = json.loads(_get(url + "api/info")[2])
        assert info["mode"] == "device_check" and Path(info["root"]) == folder.resolve()
    finally:
        proc.terminate()
        proc.wait(timeout=5)
