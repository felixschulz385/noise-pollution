"""Tests for the pipeline side of `barrier_audit`: the task geometry and
blinding of `export`, the sign convention from a reviewer's offset to
`side_method="manual"` in `build_barrier_references`, the per-barrier
decision rules and report of `preprocess`, and `import`'s checks.
Synthetic geometry in EPSG:3006 (around Stockholm where the projection
matters)."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point

from src.core.barrier_geometry import protection as pr
from src.regions.sweden.sources import _barrier_reference as br
from src.regions.sweden.sources.barrier_audit import export as ex
from src.regions.sweden.sources.barrier_audit import import_answers as imp
from src.regions.sweden.sources.barrier_audit import preprocess as pp
from src.regions.sweden.sources.barrier_audit import shared as sh
from src.regions.sweden.sources.barrier_protection.shared import references_path

CRS = "EPSG:3006"
X0, Y0 = 674_000.0, 6_580_000.0  # Stockholm


# -- export geometry ---------------------------------------------------------

def test_jacobian_matches_the_projection_and_the_bearing_puts_the_barrier_left_to_right():
    to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    jac = ex.jacobian(X0, Y0)
    lon0, lat0 = to_ll.transform(X0, Y0)
    for dx, dy in [(30.0, 0.0), (0.0, -30.0), (21.0, 21.0)]:
        lon, lat = to_ll.transform(X0 + dx, Y0 + dy)
        assert np.allclose(jac @ [dx, dy], [lon - lon0, lat - lat0], atol=1e-9)

    # A line heading north-east: screen-right must be its true azimuth.
    line = LineString([(X0, Y0), (X0 + 100, Y0 + 100)])
    geometry = ex.task_geometry(line, Point(X0 + 50, Y0 + 50))
    (lon_a, lat_a), (lon_b, lat_b) = [to_ll.transform(*c) for c in line.coords]
    azimuth = Geod(ellps="GRS80").inv(lon_a, lat_a, lon_b, lat_b)[0]
    assert geometry["bearing"] + 90 == pytest.approx(azimuth, abs=0.05)
    assert geometry["normal"] == pytest.approx([-np.sqrt(0.5), np.sqrt(0.5)], abs=1e-6)  # left of the direction
    assert geometry["line_m"][0] == pytest.approx([-50, -50])


def test_practice_answer_is_the_osm_walls_offset_along_the_left_normal():
    line = LineString([(X0, Y0), (X0 + 200, Y0)])
    center = Point(X0 + 100, Y0)
    _, n = ex.window_frame(line, center)
    left = ex.practice_answer(line, center, n, LineString([(X0 - 50, Y0 + 8), (X0 + 250, Y0 + 8)]))
    right = ex.practice_answer(line, center, n, LineString([(X0, Y0 - 6), (X0 + 200, Y0 - 6)]))
    assert left["lateral_m"] == pytest.approx(8) and right["lateral_m"] == pytest.approx(-6)
    assert ex.practice_answer(line, center, n, LineString([(X0, Y0 + 500), (X0 + 200, Y0 + 500)])) is None


@pytest.mark.parametrize(
    "kind,row,expected",
    [
        ("road", {"material_type": "glass_or_plexiglass", "height_m": 3.04, "extent_length_m": 212.4}, ("glass or plexiglass", 3.0, 212)),
        ("road", {"material_type": None, "height_m": 0.0, "extent_length_m": 0.0}, (None, None, None)),
        ("rail", {"barrier_type": "wood", "height_above_rail_top_m": 999.0, "extent_length_m": 80}, ("wood", None, 80)),
    ],
)
def test_display_metadata_hides_sentinel_heights(kind, row, expected):
    meta = ex.display_metadata(pd.Series(row), kind)
    assert (meta["material"], meta["height_m"], meta["length_m"]) == expected


def _export_inputs():
    lines = [LineString([(X0, Y0 + 100 * i), (X0 + 300, Y0 + 100 * i)]) for i in range(8)]
    barriers_m = gpd.GeoDataFrame(
        {
            "element_id": [f"E{i}" for i in range(8)],
            "start_measure": 0.0,
            "end_measure": 1.0,
            "material_type": "wood",
            "height_m": 3.0,
            "extent_length_m": 300.0,
        },
        geometry=lines,
        crs=CRS,
    )
    references = pd.DataFrame(
        {"side_method": ["osm_offset"] + ["parallel_road"] * 7, "barrier_sign": [1.0] + [-1.0] * 7, "osm_id": pd.array([7] + [pd.NA] * 7, dtype="Int64")}
    )
    data = {"road": {"barriers": barriers_m.to_crs(4326), "barriers_m": barriers_m, "references": references}}
    walls = gpd.GeoDataFrame({"osm_id": [7], "wall_type": ["noise_barrier"]}, geometry=[LineString([(X0, Y0 + 9), (X0 + 300, Y0 + 9)])], crs=CRS)
    schools = gpd.GeoSeries([Point(X0 + 250, Y0 + 100 - 80)], index=["S1"], crs=CRS)
    selection = pd.DataFrame(
        {"kind": "road", "barrier_row": range(8), "group": ["practice"] + ["target"] * 4 + ["validation"] * 3, "skolenhetskod": [None, "S1"] + [None] * 6}
    )
    return data, walls, schools, selection


def test_build_tasks_blinds_the_tasks_and_keeps_the_answers_in_the_key():
    data, walls, schools, selection = _export_inputs()
    document, key = ex.build_tasks(
        "pilot", selection, data=data, schools_m=schools, osm_walls_m=walls, context_m=ex.context_layer(data),
        reviewer="tester", double_code_share=0.3, rng=np.random.default_rng(1),
    )
    tasks = document["tasks"]
    assert document["reviewer"] == "tester" and len(tasks) == 8
    assert tasks[0]["practice"] and not any(t["practice"] for t in tasks[1:])
    assert tasks[0]["practice_answer"]["lateral_m"] == pytest.approx(9)
    forbidden = {"side", "side_method", "barrier_sign", "osm_id", "group", "skolenhetskod", "double_code", "element_id"}
    for task in tasks:
        assert not forbidden & set(task)
        assert ("practice_answer" in task) == task["practice"]
    assert len({t["task_id"] for t in tasks}) == 8 and key["task_id"].tolist() == [t["task_id"] for t in tasks]
    assert key["double_code"].sum() == 2 and not key.loc[key["group"] == "practice", "double_code"].any()
    # The school's task is centred on the barrier point nearest the school.
    school_row = key[key["skolenhetskod"] == "S1"].iloc[0]
    assert (school_row["center_x"], school_row["center_y"]) == pytest.approx((X0 + 250, Y0 + 100))
    # Other records within 300 m are drawn for context, never the task's own.
    first = tasks[key.index[key["barrier_row"] == 0][0]]
    assert len(first["others_lonlat"]) == 2  # rows 1-2, 100 and 200 m away; row 3 only touches the circle
    # One area (all within 2 km), walked in order; practice has no area.
    assert first["area"] is None
    assert [t["area"]["position"] for t in tasks[1:]] == list(range(1, 8))
    rows = key["barrier_row"].tolist()[1:]
    assert sum(abs(a - b) for a, b in zip(rows, rows[1:])) == 6  # a nearest-neighbour walk up or down the rows


def test_cluster_order_keeps_each_area_together():
    xy = np.array([[0, 0], [50_000, 0], [500, 0], [50_900, 0], [1_000, 0], [51_500, 0]], dtype=float)
    order, areas = ex.cluster_order(xy, np.random.default_rng(3))
    assert sorted(order) == list(range(6))
    walks = [order[:3], order[3:]]
    assert sorted(sorted(w) for w in walks) == [[0, 2, 4], [1, 3, 5]]
    # Each area is walked end to end, from its point farthest from the centre.
    assert all(w in ([0, 2, 4], [4, 2, 0], [1, 3, 5], [5, 3, 1]) for w in walks)
    assert [a["number"] for a in areas] == [1, 1, 1, 2, 2, 2] and all(a["count"] == 2 and a["size"] == 3 for a in areas)


def test_a_record_beside_another_has_a_twin_and_one_further_away_does_not():
    lines = [LineString([(0, 0), (300, 0)]), LineString([(0, 5), (300, 5)]), LineString([(0, 60), (300, 60)])]
    context = gpd.GeoDataFrame({"kind": "rail", "barrier_row": [0, 1, 2]}, geometry=lines, crs=CRS)
    assert ex.has_twin(lines[0], "rail", 0, context)
    assert not ex.has_twin(lines[2], "rail", 2, context)


# -- sign convention: reviewer offset -> manual side -------------------------

def _divided_road():
    return gpd.GeoDataFrame(
        {"element_id": ["A", "B"], "start_measure": 0.0, "end_measure": 1.0},
        geometry=[LineString([(0, 0), (2000, 0)]), LineString([(0, 20), (2000, 20)])],
        crs=CRS,
    )


def _manual(point=None, decision="side"):
    x, y = (point.x, point.y) if point is not None else (np.nan, np.nan)
    return pd.DataFrame({"element_id": ["A"], "start_measure": [0.2], "end_measure": [0.25], "decision": [decision], "aligned_x": [x], "aligned_y": [y]})


@pytest.mark.parametrize("digitised", [[(400, 0), (500, 0)], [(500, 0), (400, 0)]])
@pytest.mark.parametrize("lateral_m", [6.0, -6.0])
def test_a_reviewers_offset_becomes_the_manual_side_whichever_way_the_barrier_is_digitised(digitised, lateral_m):
    """The app offsets along the barrier's own left normal; the pipeline
    judges the aligned point against the road's through-line. The side of
    the road must come out the same either way."""
    line = LineString(digitised)
    center = Point(450, 0)
    _, n = ex.window_frame(line, center)
    aligned = Point(center.x + lateral_m * n[0], center.y + lateral_m * n[1])
    barriers = gpd.GeoDataFrame({"element_id": ["A"], "start_measure": [0.2], "end_measure": [0.25]}, geometry=[line], crs=CRS)

    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=None, kind="road", manual=_manual(aligned))
    assert refs.table.loc[0, "side_method"] == "manual"  # ahead of parallel_road

    wall_side_y = np.sign(aligned.y) * 40
    out = pr.classify_points([Point(450, wall_side_y), Point(450, -wall_side_y)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].tolist() == [True, False]


def test_manual_both_sides_protects_both_sides_and_an_on_line_point_is_ignored():
    barriers = gpd.GeoDataFrame({"element_id": ["A"], "start_measure": [0.2], "end_measure": [0.25]}, geometry=[LineString([(400, 0), (500, 0)])], crs=CRS)
    refs = br.build_barrier_references(barriers, _divided_road(), osm_walls=None, kind="road", manual=_manual(decision="both_sides"))
    assert (refs.table.loc[0, "side_method"], refs.table.loc[0, "barrier_sign"]) == ("manual_both_sides", 0.0)
    out = pr.classify_points([Point(450, -40), Point(450, 10)], np.zeros(2, dtype=int), refs)
    assert out["same_side"].all()
    assert pr.protection_zones(refs).geometry.iloc[0].contains(Point(450, 10))

    on_line = br.build_barrier_references(barriers, _divided_road(), osm_walls=None, kind="road", manual=_manual(Point(450, 0)))
    assert on_line.table.loc[0, "side_method"] == "parallel_road"


# -- preprocess ----------------------------------------------------------------

@pytest.mark.parametrize(
    "categories,expected",
    [
        (["left"], ("side", "left")),
        (["left", "left"], ("side", "left")),
        (["left", "occluded"], ("side", "left")),
        (["left", "right"], ("conflict", None)),
        (["left", "not_visible"], ("conflict", None)),
        (["both_sides"], ("both_sides", "both_sides")),
        (["centre"], ("centre", "centre")),
        (["not_visible", "other"], ("not_visible", "not_visible")),
        (["occluded", "other"], ("unsure", None)),
    ],
)
def test_decision_rules(categories, expected):
    assert pp.decide(categories) == expected


def test_categories_use_the_two_metre_threshold():
    answers = pd.DataFrame({
        "status": ["aligned", "aligned", "aligned", "unsure", "both_sides"],
        "lateral_m": [2.0, -2.5, 1.9, 0.0, 4.0],
        "reason": [None, None, None, "occluded", None],
    })
    assert pp.categorize(answers).tolist() == ["left", "right", "centre", "occluded", "both_sides"]


def _repo_root(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


def _write_answers(root, batch, reviewer, rows):
    path = sh.answers_dir(batch, root) / f"answers_{reviewer}.jsonl"
    with open(path, "w") as f:
        for task_id, status, lateral, reason, *streetview in rows:
            record = {
                "task_id": task_id, "status": status, "reason": reason, "note": None, "lateral_m": lateral,
                "along_residual_m": 0.0, "zoom": 19.0, "seconds_on_task": 10.0, "answered_at": "2026-09-24T12:00:00Z",
                "batch": batch, "reviewer": reviewer, "app_version": "0.1.0",
            }
            if streetview:  # app 0.3.0 records it; older answers have no count
                record.update(app_version="0.3.0", streetview_opens=streetview[0])
            f.write(json.dumps(record) + "\n")
    return path


def _key(root):
    """Six road barriers along y = 100*i, digitised eastward (left = north)."""
    ids = ["t_side", "t_novis", "t_valid", "t_conf", "t_prac", "t_occl", "t_stale"]
    groups = ["target", "target", "validation", "target", "practice", "target", "target"]
    rows = []
    for i, (task_id, group) in enumerate(zip(ids, groups)):
        rows.append({
            "task_id": task_id, "batch": "pilot", "order": i, "group": group, "double_code": task_id in ("t_side", "t_conf"),
            "kind": "road", "barrier_row": i, "element_id": f"E{i}", "start_measure": 0.0, "end_measure": 1.0,
            "side_method": "parallel_road" if group == "validation" else "unknown",
            "barrier_sign": -1.0 if group == "validation" else 0.0, "osm_id": pd.NA, "skolenhetskod": None,
            "center_x": 150.0, "center_y": 100.0 * i, "n_x": 0.0, "n_y": 1.0,
            "practice_lateral_m": -5.5 if group == "practice" else np.nan,
            "geometry": LineString([(0, 100 * i), (300, 100 * i)]),
        })
    key = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)
    key["osm_id"] = key["osm_id"].astype("Int64")
    key.to_parquet(sh.key_path("pilot", root), index=False)
    return key


def test_preprocess_decides_each_barrier_and_reports(tmp_path, monkeypatch):
    root = _repo_root(tmp_path)
    key = _key(root)
    current = key.loc[key["task_id"] != "t_stale", ["element_id", "start_measure", "end_measure"]]
    monkeypatch.setattr(pp, "load_noise_barriers", lambda kind, root=None: current)
    through = gpd.GeoDataFrame(key[["element_id", "start_measure", "end_measure"]], geometry=key.geometry, crs=CRS)
    through.to_parquet(references_path("road", root), index=False)

    _write_answers(root, "pilot", "assistant", [
        ("t_side", "aligned", 3.0, None),
        ("t_side", "aligned", 6.0, None),  # re-answered: the last line wins
        ("t_novis", "unsure", 0.0, "not_visible"),
        ("t_valid", "aligned", -7.0, None, 1),
        ("t_conf", "aligned", 6.0, None),
        ("t_prac", "aligned", -5.0, None),
        ("t_occl", "unsure", 0.0, "occluded"),
        ("t_stale", "both_sides", 0.0, None),
    ])
    _write_answers(root, "pilot", "felix", [("t_side", "aligned", 5.0, None), ("t_conf", "aligned", -6.0, None)])

    result = pp.run_barrier_audit_preprocess(root)
    sides = gpd.read_parquet(sh.manual_sides_path(root)).set_index("element_id")
    assert sides["decision"].to_dict() == {
        "E0": "side", "E1": "not_visible", "E2": "side", "E3": "conflict", "E5": "unsure", "E6": "both_sides",
    }  # practice (E4) is not a barrier decision
    assert sides.loc["E0", "lateral_m"] == pytest.approx(5.5)  # mean of 6 and 5
    assert (sides.loc["E0", "aligned_x"], sides.loc["E0", "aligned_y"]) == pytest.approx((150, 5.5))
    assert sides.loc["E0", "geometry"].distance(Point(150, 0)) == pytest.approx(5.5)
    assert sides.loc["E0", "manual_sign"] == 1.0 and sides.loc["E2", "manual_sign"] == -1.0
    assert sides["stale"].to_dict() == {"E0": False, "E1": False, "E2": False, "E3": False, "E5": False, "E6": True}

    assert result["used_by_build"] == 2  # E0 and E2; E6 is stale
    assert result["validation"]["parallel_road"] == {
        "n_barriers": 1, "decisions": {"side": 1}, "n_sided": 1, "agree": 1, "share_agree": 1.0, "wilson_95": [0.207, 1.0],
        "with_streetview": {"n_sided": 1, "agree": 1},
    }
    assert result["double_coding"]["n_tasks"] == 2 and result["double_coding"]["share_same_category"] == 0.5
    assert result["double_coding"]["median_abs_lateral_diff_m"] == pytest.approx(1.0)
    assert result["practice"] == {"assistant": {"n": 1, "same_side_as_osm": 1, "median_abs_error_m": 0.5}}
    answers = pd.read_parquet(sh.barrier_audit_paths(root)["processed"] / "audit_answers.parquet").set_index(["reviewer", "task_id"])
    assert answers.loc[("assistant", "t_valid"), "streetview_opens"] == 1
    assert answers.loc[("assistant", "t_side"), "streetview_opens"] == 0  # absent before app 0.3.0
    report = json.loads((sh.barrier_audit_paths(root)["processed"] / "audit_report.json").read_text())
    assert [r["element_id"] for r in report["not_visible"]] == ["E1"]
    assert [r["element_id"] for r in report["conflict"]] == ["E3"]

    manual = sh.load_manual_sides("road", root)
    assert sorted(manual["element_id"]) == ["E0", "E2", "E6"]  # build matches keys, so the stale E6 never applies


def test_cohens_kappa():
    assert pp.cohens_kappa(["left", "right"], ["left", "right"]) == 1.0
    assert pp.cohens_kappa(["left", "left", "right", "right"], ["left", "right", "left", "right"]) == 0.0


# -- import ----------------------------------------------------------------------

def test_import_checks_ids_and_refuses_an_older_copy(tmp_path):
    root = _repo_root(tmp_path)
    _key(root)
    outside = tmp_path / "returned"
    outside.mkdir()
    newer = _write_answers(root, "pilot", "assistant", [("t_side", "aligned", 6.0, None), ("t_valid", "aligned", -7.0, None)])
    returned = outside / newer.name
    returned.write_bytes(newer.read_bytes())

    result = imp.run_barrier_audit_import(returned, root=root)
    assert (result["batch"], result["reviewer"], result["tasks_answered"], result["tasks_in_batch"]) == ("pilot", "assistant", 2, 7)

    older = outside / "older.jsonl"
    older.write_text(returned.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="older copy"):
        imp.run_barrier_audit_import(older, root=root)
    assert imp.run_barrier_audit_import(older, root=root, force=True)["lines"] == 1

    bad = outside / "bad.jsonl"
    bad.write_text(json.dumps({"task_id": "zzz", "batch": "pilot", "reviewer": "assistant", "status": "aligned"}) + "\n")
    with pytest.raises(ValueError, match="not in batch"):
        imp.run_barrier_audit_import(bad, root=root)
