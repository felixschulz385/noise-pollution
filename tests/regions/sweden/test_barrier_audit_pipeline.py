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


def test_stub_records_are_never_chosen():
    """A record under 1 m (pilot task 9376dc21: 2 cm) is an invisible line:
    neither a target nor a validation task."""
    lines = [LineString([(X0, Y0 + 100 * i), (X0 + 300, Y0 + 100 * i)]) for i in range(2)]
    lines += [LineString([(X0, Y0 + 100 * i), (X0 + 0.02, Y0 + 100 * i)]) for i in range(2, 4)]
    barriers_m = gpd.GeoDataFrame(
        {"element_id": [f"E{i}" for i in range(4)], "start_measure": 0.0, "end_measure": 1.0, "extent_length_m": 300.0},
        geometry=lines, crs=CRS,
    )
    references = pd.DataFrame(
        {"side_method": ["unknown", "track_offset", "unknown", "track_offset"], "osm_id": pd.array([pd.NA] * 4, dtype="Int64")}
    )
    pairs = pd.DataFrame({
        "barrier_row": range(4), "skolenhetskod": "S1", "dist_m": 100.0, "same_route": True,
        "protected_unknown": [True, False, True, False], "same_side_unknown": [True, False, True, False],
    })
    data = {"rail": {"barriers": barriers_m.to_crs(4326), "barriers_m": barriers_m, "references": references, "pairs": pairs}}
    spec = {**ex.BATCHES["protected"], "n_practice": 0}
    no_walls = gpd.GeoDataFrame({"osm_id": [], "wall_type": []}, geometry=[], crs=CRS)
    selection = ex.select_barriers(
        "protected", spec, data=data, previous=pd.DataFrame(columns=["kind", *sh.KEY_COLUMNS, "group"]),
        osm_walls=no_walls, context_m=ex.context_layer(data), rng=np.random.default_rng(0),
    )
    assert selection[["barrier_row", "group"]].values.tolist() == [[0, "target"], [1, "validation"]]


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


def _wall_in_pieces():
    """One wall along y = Y0 in three register pieces (the last digitised
    backwards, the first an earth berm), and a separate record 100 m north."""
    lines = [
        LineString([(X0, Y0), (X0 + 100, Y0)]),
        LineString([(X0 + 101, Y0), (X0 + 200, Y0)]),
        LineString([(X0 + 300, Y0), (X0 + 201, Y0)]),
        LineString([(X0, Y0 + 100), (X0 + 300, Y0 + 100)]),
    ]
    barriers_m = gpd.GeoDataFrame(
        {
            "element_id": ["E0", "E1", "E2", "E3"],
            "start_measure": 0.0,
            "end_measure": 1.0,
            "material_type": ["earth_berm", "wood", "wood", "wood"],
            "height_m": [2.0, 3.0, 3.5, 3.0],
            "extent_length_m": [100.0, 99.0, 99.0, 300.0],
        },
        geometry=lines,
        crs=CRS,
    )
    barriers_m["material_type"] = barriers_m["material_type"].str.replace("earth_berm", "earth berm")
    references = pd.DataFrame(
        {"side_method": ["unknown", "parallel_road", "unknown", "parallel_road"], "barrier_sign": [0.0, -1.0, 0.0, -1.0],
         "osm_id": pd.array([pd.NA] * 4, dtype="Int64")}
    )
    data = {"road": {"barriers": barriers_m.to_crs(4326), "barriers_m": barriers_m, "references": references}}
    walls = gpd.GeoDataFrame({"osm_id": pd.array([], dtype="int64"), "wall_type": []}, geometry=[], crs=CRS)
    schools = gpd.GeoSeries([Point(X0 + 150, Y0 - 50)], index=["S1"], crs=CRS)
    selection = pd.DataFrame({"kind": "road", "barrier_row": [1, 2, 3], "group": ["target", "validation", "validation"],
                              "skolenhetskod": ["S1", None, None]})
    return data, walls, schools, selection


def test_a_wall_split_into_pieces_is_one_task_whose_answer_places_every_piece():
    data, walls, schools, selection = _wall_in_pieces()
    document, key = ex.build_tasks(
        "protected", selection, data=data, schools_m=schools, osm_walls_m=walls, context_m=ex.context_layer(data),
        reviewer="tester", double_code_share=0.0, rng=np.random.default_rng(1),
    )
    tasks = {t["task_id"]: t for t in document["tasks"]}
    assert len(tasks) == 2 and len(key) == 4
    wall = key[key["element_id"].isin(["E0", "E1", "E2"])]
    assert wall["task_id"].nunique() == 1
    task = tasks[wall["task_id"].iat[0]]
    # The whole wall is the overlay, centred at the school's nearest point; the other pieces aren't "other barriers".
    assert task["n_records"] == 3 and task["length_m"] == 298
    assert task["line_m"][0] == pytest.approx([-150, 0]) and task["line_m"][-1] == pytest.approx([150, 0])
    assert len(task["others_lonlat"]) == 1  # only E3
    assert (task["type_group"], task["material"]) == ("mixed", "wood, earth berm")
    assert task["height_m"] == [2.0, 3.5]
    # Each record keeps its own group: the unchosen piece joins as `chain`; the task is a target task.
    assert wall.set_index("element_id")["group"].to_dict() == {"E0": "chain", "E1": "target", "E2": "validation"}
    assert set(wall["task_group"]) == {"target"}
    assert wall.set_index("element_id")["chain_orient"].to_dict() == {"E0": 1, "E1": 1, "E2": -1}

    # One answer, 6 m to the task's left (north): every piece's wall lands north of the road.
    answers = pd.DataFrame(key.drop(columns="geometry")).assign(
        status="aligned", reason=None, note=None, lateral_m=6.0, reviewer="r", batch="protected"
    )
    answers["category"] = pp.categorize(answers)
    lines = key.set_index(["task_id", "kind", "element_id", "start_measure", "end_measure"]).geometry
    sides = pp.manual_sides(answers[answers["element_id"] != "E3"], lines).set_index("element_id")
    assert sides["decision"].tolist() == ["side"] * 3
    assert sides["aligned_y"].to_numpy() == pytest.approx([Y0 + 6] * 3)
    for element_id, row in sides.iterrows():
        assert row.geometry.centroid.y == pytest.approx(Y0 + 6), element_id


@pytest.mark.parametrize(
    "material,expected",
    [("earth berm", "berm"), ("earth berm and wood", "berm_screen"), ("glass or plexiglass", "glass"), ("wood", "wall"), (None, None)],
)
def test_type_groups_tell_the_reviewer_what_to_look_for(material, expected):
    assert ex.type_group(material) == expected


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
        for task_id, status, lateral, reason, *aids in rows:
            record = {
                "task_id": task_id, "status": status, "reason": reason, "note": None, "lateral_m": lateral,
                "along_residual_m": 0.0, "zoom": 19.0, "seconds_on_task": 10.0, "answered_at": "2026-09-24T12:00:00Z",
                "batch": batch, "reviewer": reviewer, "app_version": "0.1.0",
            }
            if aids:  # app 0.4.0 records them; older answers have none
                record.update(app_version="0.4.0", **aids[0])
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
        ("t_valid", "aligned", -7.0, None, {"streetview_opens": 1, "satellite_opens": 0, "imagery": "infrared"}),
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
        "n_barriers": 1, "decisions": {"side": 1}, "n_sided": 1, "n_walls_sided": 1, "agree": 1, "share_agree": 1.0,
        "wilson_95": [0.207, 1.0],
        "with_streetview": {"n_sided": 1, "agree": 1},
        "with_satellite": {"n_sided": 0, "agree": 0},
        "with_infrared": {"n_sided": 1, "agree": 1},
    }
    assert result["double_coding"]["n_tasks"] == 2 and result["double_coding"]["share_same_category"] == 0.5
    assert result["double_coding"]["median_abs_lateral_diff_m"] == pytest.approx(1.0)
    assert result["practice"] == {"assistant": {"n": 1, "same_side_as_osm": 1, "median_abs_error_m": 0.5}}
    answers = pd.read_parquet(sh.barrier_audit_paths(root)["processed"] / "audit_answers.parquet").set_index(["reviewer", "task_id"])
    assert answers.loc[("assistant", "t_valid"), "streetview_opens"] == 1
    assert answers.loc[("assistant", "t_side"), "streetview_opens"] == 0  # absent before app 0.3.0
    assert answers.loc[("assistant", "t_side"), "satellite_opens"] == 0 and answers.loc[("assistant", "t_side"), "imagery"] == "colour"
    assert answers.loc[("assistant", "t_valid"), "imagery"] == "infrared"
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


# -- serve -------------------------------------------------------------------------

def test_serve_writes_only_the_chosen_tasks_in_batch_order(tmp_path):
    from src.regions.sweden.sources.barrier_audit import serve

    root = _repo_root(tmp_path)
    tasks = [{"task_id": t} for t in ("a", "b", "c", "d")]
    sh.tasks_path("pilot", root).write_text(json.dumps({"batch": "pilot", "reviewer": "assistant", "n_tasks": 4, "tasks": tasks}))

    folder, n = serve.prepare_serve_root("pilot", "felix", task_ids=["d", "b"], root=root)
    document = json.loads((folder / "tasks.json").read_text())
    assert n == 2 and [t["task_id"] for t in document["tasks"]] == ["b", "d"]
    assert (document["reviewer"], document["n_tasks"]) == ("felix", 2)
    with pytest.raises(ValueError, match="not in batch"):
        serve.prepare_serve_root("pilot", "felix", task_ids=["zzz"], root=root)


# -- one answer per reviewer and barrier, outer-track report -------------------------

def _answers_for(rows):
    """rows: (task_id, reviewer, answered_at, status, lateral_m, reason) for road barrier E0 along y = 0."""
    frame = pd.DataFrame(rows, columns=["task_id", "reviewer", "answered_at", "status", "lateral_m", "reason"]).assign(
        batch="pilot", note=None, group="target", kind="road", element_id="E0", start_measure=0.0, end_measure=1.0,
        center_x=150.0, center_y=0.0, n_x=0.0, n_y=1.0, chain_orient=1,
    )
    frame["category"] = pp.categorize(frame)
    lines = pd.Series(
        [LineString([(0, 0), (300, 0)])] * frame["task_id"].nunique(),
        index=pd.MultiIndex.from_tuples([(t, "road", "E0", 0.0, 1.0) for t in frame["task_id"].unique()]),
    )
    return frame, lines


def test_a_reviewers_later_answer_to_the_same_barrier_replaces_their_earlier_one():
    # The pilot's earth berm: "no wall visible" in one task, aligned in a later one.
    answers, lines = _answers_for([
        ("t_later", "felix", "2026-09-25T13:15:30Z", "aligned", 13.1, None),
        ("t_early", "felix", "2026-09-24T15:18:02Z", "unsure", -13.3, "not_visible"),
    ])
    sides = pp.manual_sides(answers, lines)
    assert sides.loc[0, ["decision", "n_answers", "n_superseded", "categories"]].tolist() == ["side", 1, 1, "left"]
    assert sides.loc[0, "lateral_m"] == pytest.approx(13.1)
    # Different reviewers still disagree.
    answers, lines = _answers_for([
        ("t_later", "felix", "2026-09-25T13:15:30Z", "aligned", 13.1, None),
        ("t_early", "assistant", "2026-09-24T15:18:02Z", "unsure", -13.3, "not_visible"),
    ])
    assert pp.manual_sides(answers, lines).loc[0, "decision"] == "conflict"


def test_rail_neighbour_classes(tmp_path, monkeypatch):
    root = _repo_root(tmp_path)
    lines = [
        LineString([(0, 0), (300, 0)]),  # 0: co-located with 1 (similar length) and 4
        LineString([(0, 0.5), (290, 0.5)]),  # 1: same track, similar length
        LineString([(0, 5), (300, 5)]),  # 2: the other track: a twin
        LineString([(0, 1000), (300, 1000)]),  # 3: alone; the stub beside it doesn't count
        LineString([(100, 0), (150, 0)]),  # 4: nested in 0: co-located, not similar
        LineString([(0, 1000.2), (0.02, 1000.2)]),  # 5: a stub
    ]
    barriers = gpd.GeoDataFrame(
        {"element_id": [f"R{i}" for i in range(6)], "start_measure": 0.0, "end_measure": 1.0,
         "distance_from_track_center_m": [4.0, np.nan, np.nan, 0.5, np.nan, np.nan]},
        geometry=lines, crs=CRS,
    )
    monkeypatch.setattr(pp, "load_noise_barriers", lambda kind, root=None: barriers)
    path = references_path("rail", root)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"barrier_row": range(6), "outer_track_spacing_m": [5.0, 4.5, 5.0, np.nan, 5.0, np.nan]}).to_parquet(path)
    classes = pp.rail_neighbour_classes(root).set_index("element_id")
    assert classes["neighbours"].tolist() == ["co_located", "co_located", "twin", "single", "co_located", "single"]
    assert classes["similar_length"].tolist() == [True, True, False, False, False, False]
    assert classes["recorded_distance"].tolist() == [True, False, False, False, False, False]
    assert classes.loc["R1", "outer_track_spacing_m"] == 4.5


def _outer_track_inputs(n_in_band, n_miss=0, both_sides_co_located=False):
    """Rail targets with outer_track_sign +1: `n_in_band` spaced 5 m (the
    first `n_miss` answered on the other side), one spaced 2 m that
    disagrees, and one co-located, answered left or Both sides."""
    rows = []
    for i in range(n_in_band):
        rows.append((f"R{i}", "target", 5.0, "single", "side", -1.0 if i < n_miss else 1.0))
    rows.append(("Rnear", "target", 2.0, "single", "side", -1.0))
    rows.append(("Rco", "target", 5.0, "co_located", "both_sides" if both_sides_co_located else "side",
                 np.nan if both_sides_co_located else 1.0))
    rows.append(("Rval", "validation", 5.0, "twin", "side", 1.0))
    keys = {"start_measure": 0.0, "end_measure": 1.0}
    answers = pd.DataFrame([{"element_id": r[0], "group": r[1], "kind": "rail", "outer_track_sign": 1.0, "task_id": f"t_{r[0]}", **keys}
                            for r in rows])
    sides = pd.DataFrame([{"element_id": r[0], "kind": "rail", "decision": r[4], "manual_sign": r[5], **keys} for r in rows])
    classes = pd.DataFrame([{"element_id": r[0], "neighbours": r[3], "similar_length": False, "recorded_distance": False,
                             "outer_track_spacing_m": r[2], **keys} for r in rows])
    return answers, sides, classes


@pytest.mark.parametrize(
    "n_in_band,n_miss,both,verdict",
    [
        (20, 0, False, "adopt"),  # 21/21 in band (the co-located one is 5 m out too): Wilson lower 0.845
        (59, 5, False, "adopt"),  # 55/60: 0.917, lower 0.819
        (59, 6, False, "too few answers"),  # 54/60: 0.9, lower 0.799
        (59, 7, False, "do not adopt"),  # 53/60: 0.883
        (7, 0, False, "too few answers"),  # 8/8 (the pilot): lower 0.676
        (20, 0, True, "do not adopt"),  # a co-located target has walls on both sides
    ],
)
def test_outer_track_decision_rule(n_in_band, n_miss, both, verdict):
    report = pp.outer_track_report(*_outer_track_inputs(n_in_band, n_miss, both))
    assert report["decision_rule"]["verdict"] == verdict
    assert report["decision_rule"]["co_located_targets_both_sides"] == int(both)
    # The 2 m target disagrees but sits outside the band; the validation one is reported, never scored.
    assert report["target"]["by_spacing"]["<3.8"]["agree"] == 0
    assert set(report["target"]["by_neighbours"]) == {"single", "co_located"}
    assert report["validation"]["by_neighbours"]["twin"]["agree"] == 1


def test_outer_track_rule_without_answers():
    answers, sides, classes = _outer_track_inputs(0)
    answers = answers[answers["group"] == "validation"]
    assert pp.outer_track_report(answers, sides, classes)["decision_rule"]["verdict"] == "no answers yet"


# -- co-located walls and the national batches -------------------------------

def _road(lines, methods, **columns):
    n = len(lines)
    barriers_m = gpd.GeoDataFrame(
        {"element_id": [f"E{i}" for i in range(n)], "start_measure": 0.0, "end_measure": 1.0, "material_type": "wood",
         "height_m": 3.0, "extent_length_m": [line.length for line in lines], **columns},
        geometry=lines, crs=CRS,
    )
    references = pd.DataFrame({"side_method": methods, "barrier_sign": 0.0, "osm_id": pd.array([pd.NA] * n, dtype="Int64")})
    return {"barriers": barriers_m.to_crs(4326), "barriers_m": barriers_m, "references": references}


NO_WALLS = gpd.GeoDataFrame({"osm_id": pd.array([], dtype="int64"), "wall_type": []}, geometry=[], crs=CRS)
NO_SCHOOLS = gpd.GeoSeries([], crs=CRS)


def test_co_located_walls_are_one_task_and_both_sides_places_every_record():
    """A wall on each side of one road: two records on its centreline (the
    second digitised the other way) are one task; a Both sides answer puts a
    wall on each side for both records."""
    data = {"road": _road(
        [LineString([(X0, Y0), (X0 + 300, Y0)]), LineString([(X0 + 300, Y0), (X0, Y0)]), LineString([(X0, Y0 + 2000), (X0 + 300, Y0 + 2000)])],
        ["both_sides", "both_sides", "unknown"], side=["left", "left", "right"],
    )}
    selection = pd.DataFrame({"kind": "road", "barrier_row": [0, 1, 2], "group": ["validation", "validation", "target"], "skolenhetskod": None})
    document, key = ex.build_tasks(
        "national_1", selection, data=data, schools_m=NO_SCHOOLS, osm_walls_m=NO_WALLS, context_m=ex.context_layer(data),
        reviewer="tester", double_code_share=0.0, rng=np.random.default_rng(0),
    )
    assert len(document["tasks"]) == 2
    pair = key[key["element_id"].isin(["E0", "E1"])]
    assert pair["task_id"].nunique() == 1 and set(pair["strand"]) == {0, 1} and set(pair["n_strands"]) == {2}
    assert pair.set_index("element_id")["chain_orient"].to_dict() == {"E0": 1, "E1": -1}
    task = next(t for t in document["tasks"] if t["task_id"] == pair["task_id"].iat[0])
    assert task["n_strands"] == 2 and task["length_m"] == 300
    assert len(task["others_lonlat"]) == 1  # the second record, shown on the line

    answers = pd.DataFrame(pair.drop(columns="geometry")).assign(
        status="both_sides", reason=None, note=None, lateral_m=6.0, lateral_other_m=-8.0, reviewer="r"
    )
    answers["category"] = pp.categorize(answers)
    lines = key.set_index(["task_id", "kind", "element_id", "start_measure", "end_measure"]).geometry
    sides = pp.manual_sides(answers, lines).set_index("element_id")
    assert sides["decision"].tolist() == ["both_sides", "both_sides"]
    for element_id, row in sides.iterrows():
        ys = sorted(part.centroid.y for part in row.geometry.geoms)
        assert ys == pytest.approx([Y0 - 8, Y0 + 6]), element_id


def test_national_selection_skips_stubs_manual_sides_and_earlier_batches():
    lines = [LineString([(X0, Y0 + 100 * i), (X0 + 300, Y0 + 100 * i)]) for i in range(4)]
    lines.append(LineString([(X0, Y0 + 500), (X0 + 0.02, Y0 + 500)]))  # a stub
    data = {"road": _road(lines, ["unknown", "parallel_road", "manual", "unknown", "unknown"])}
    data["road"]["pairs"] = pd.DataFrame({"barrier_row": [0], "skolenhetskod": ["S1"], "dist_m": [50.0], "same_route": [True]})
    previous = pd.DataFrame({"kind": ["road"], "element_id": ["E3"], "start_measure": [0.0], "end_measure": [1.0], "group": ["target"]})
    selection = ex.select_national(
        {"n_practice": 0}, data=data, previous=previous, osm_walls=NO_WALLS, context_m=ex.context_layer(data), rng=np.random.default_rng(0)
    )
    assert selection[["barrier_row", "group"]].values.tolist() == [[0, "target"], [1, "validation"]]
    assert selection["skolenhetskod"].tolist()[0] == "S1" and selection["skolenhetskod"].isna().tolist()[1]


def test_national_priority_tiers_and_timing():
    lines = [LineString([(X0, Y0 + 100 * i), (X0 + 300, Y0 + 100 * i)]) for i in range(5)]
    data = {"road": _road(lines, ["unknown", "unknown", "unknown", "parallel_road", "osm_offset"],
                          built_year=[1995.0, np.nan, 2001.0, np.nan, 2010.0])}
    data["road"]["pairs"] = pd.DataFrame({"barrier_row": [0, 1], "same_route": [True, False]})
    units = [pd.DataFrame({"kind": "road", "barrier_row": [r], "group": ["target"], "strand": 0, "chain_orient": 1}) for r in range(5)]
    info = ex.national_priority(units, data, {"road": pd.DataFrame({"barrier_row": [0, 1]})})
    assert [(i["priority_tier"], i["timed"]) for i in info] == [(1, True), (2, False), (3, True), (4, False), (5, True)]


def test_national_order_puts_dated_first_keeps_sites_together_and_never_splits_them():
    far = lambda k: LineString([(X0 + 5000 * k, Y0), (X0 + 5000 * k + 300, Y0)])  # noqa: E731
    lines = [
        far(0), LineString([(X0, Y0 + 20), (X0 + 300, Y0 + 20)]),  # one site: a wall on each carriageway
        far(1), far(2), far(3),
    ]
    info = [
        {"priority_tier": 4, "timed": True}, {"priority_tier": 1, "timed": False},  # site class: dated, tier 4
        {"priority_tier": 1, "timed": True}, {"priority_tier": 2, "timed": False}, {"priority_tier": 3, "timed": True},
    ]
    units = [pd.DataFrame({"kind": "road", "barrier_row": [i], "group": ["target"]}) for i in range(5)]
    centers = [line.interpolate(0.5, normalized=True) for line in lines]
    batches, area_of = ex.order_national(units, centers, lines, info, {}, np.random.default_rng(0), parts=2)
    assert batches == [[2, 4], [0, 1, 3]]
    assert info[0]["site"] == info[1]["site"] and {i["part"] for i in info[:2]} == {2}
    assert set(area_of) == set(range(5)) and area_of[2]["count"] == 2


def test_both_walls_of_a_folded_line_stay_one_geometry():
    # The offset of a spiked wall comes back in two parts on one side.
    line = LineString([(0, 0), (50, 0), (52, 10), (54, 0), (100, 0)])
    lines = pp.offset_lines(line, [6.0, -8.0])
    assert lines.geom_type == "MultiLineString" and len(lines.geoms) >= 3
    left = [p for p in lines.geoms if p.centroid.y > 0]
    assert left and all(p.distance(Point(25, 6)) < 30 for p in left[:1])


@pytest.mark.parametrize("status,other", [("aligned", None), ("both_sides", -8.0)])
def test_co_located_records_sharing_their_key_get_one_row_with_a_line(status, other):
    """Two records of one task with the same element_id and measures (a wall
    each side, identical extents): one manual row, its geometry a line."""
    frame = pd.DataFrame({
        "task_id": "t1", "reviewer": "r", "answered_at": "2026-09-29T10:00:00Z", "status": status, "lateral_m": 6.0,
        "lateral_other_m": other, "reason": None, "note": None, "batch": "national_1", "group": "target", "kind": "road",
        "element_id": "E0", "start_measure": 0.0, "end_measure": 1.0, "center_x": 150.0, "center_y": 0.0, "n_x": 0.0,
        "n_y": 1.0, "chain_orient": [1, -1],
    })
    frame["category"] = pp.categorize(frame)
    lines = gpd.GeoSeries(
        [LineString([(0, 0), (300, 0)]), LineString([(300, 0), (0, 0)])],
        index=pd.MultiIndex.from_tuples([("t1", "road", "E0", 0.0, 1.0)] * 2),
    )
    for rows in (frame, frame.iloc[::-1]):  # whichever record's answer is taken
        sides = pp.manual_sides(rows, lines)
        assert len(sides) == 1
        ys = sorted(part.centroid.y for part in getattr(sides.geometry.iat[0], "geoms", [sides.geometry.iat[0]]))
        assert ys == pytest.approx([6.0] if other is None else [-8.0, 6.0])
