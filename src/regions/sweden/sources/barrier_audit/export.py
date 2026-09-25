"""`sweden data barrier-audit export`: pick a batch's barriers, and write the
blinded `tasks.json` the app shows plus the key that stays on our side.

**Groups** (see docs/data/sweden/barrier_audit/README.md, "Task set"):

- `target`: barriers paired with panel schools whose side is unknown
  (`protected_unknown` for batch `protected`, `same_side_unknown` for
  `same_side`, a sample of the latter for `pilot`).
- `validation`: a blind sample of auto-sided barriers paired with panel
  schools, `validation_per_method` each of `parallel_road`, `track_offset`
  and `osm_offset`.
- `practice`: `osm_offset` barriers whose OSM wall is a tagged noise
  barrier, with no second barrier record running alongside (a double
  track's twin); the app shows that wall after each one. Excluded from
  results.

**Order.** Practice first, then the rest by area: tasks within
`CLUSTER_LINK_M` of each other (chained) form one area, areas come in random
order, and within an area the tasks follow a nearest-neighbour walk, so the
reviewer solves one place after the other. Each task shows the other barrier
records (both kinds) within `CONTEXT_RADIUS_M` of its view in a second
colour, at their recorded (centreline) positions.

A random `double_code_share` of the non-practice tasks is flagged in the key
for double-coding (`serve --double-coded`). Barriers already in another
batch's key are not drawn again (targets of `protected` excepted).

**Geometry per task.** The browser has no projection library, so each task
carries the barrier line both in lon/lat and in local metres (EPSG:3006,
relative to the view centre), plus the Jacobian of lon/lat with respect to
those metres at the centre. The app converts small displacements with it:
the error over a 50 m offset is millimetres. The view centre is the point
of the barrier nearest the paired school (the barrier's midpoint for
practice tasks); the tangent `t` is the barrier's direction over
`VIEW_M` around it, and the normal `n` its left normal, which the app
puts screen-up. `lateral_m` answers are signed along `n`.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import Transformer
from shapely import force_2d
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point

from src.regions.sweden.sources._layout import METRIC_CRS
from src.regions.sweden.sources.barrier_audit.shared import KEY_COLUMNS, barrier_audit_paths, key_path, tasks_path
from src.regions.sweden.sources.barrier_protection.shared import references_path
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers
from src.regions.sweden.sources.osm_walls.shared import load_osm_walls
from src.regions.sweden.sources.panel.shared import assembled_panel_path
from src.regions.sweden.sources.schools.assemble import load_geocoded_schools
from src.regions.sweden.sources.schools.shared import schools_paths

VIEW_M = 150.0
VALIDATION_METHODS = {"parallel_road": ("road",), "track_offset": ("rail",), "osm_offset": ("road", "rail")}
PRACTICE_MIN_LENGTH_M = 80.0
PRACTICE_WALL_BUFFER_M = 40.0
MAX_PLAUSIBLE_HEIGHT_M = 30.0
CONTEXT_RADIUS_M = 300.0
TWIN_BUFFER_M = 25.0
TWIN_MIN_SHARE = 0.5
CLUSTER_LINK_M = 2000.0
DEFAULT_SEED = 20260924

BATCHES = {
    "pilot": {"target": "pilot", "n_targets": 15, "validation_per_method": 5, "n_practice": 5, "double_code_share": 0.0},
    "protected": {"target": "protected_unknown", "n_targets": None, "validation_per_method": 40, "n_practice": 10, "double_code_share": 0.15},
    "same_side": {"target": "same_side_unknown", "n_targets": None, "validation_per_method": 0, "n_practice": 10, "double_code_share": 0.15},
}
DISPLAY_COLUMNS = {
    "road": {"material": "material_type", "height": "height_m"},
    "rail": {"material": "barrier_type", "height": "height_above_rail_top_m"},
}
_TO_LONLAT = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)


# -- geometry --------------------------------------------------------------

def _line_2d(geom) -> LineString:
    geom = force_2d(geom)
    if geom.geom_type == "LineString":
        return geom
    return max(geom.geoms, key=lambda g: g.length)


def jacobian(x: float, y: float, h: float = 0.5) -> np.ndarray:
    """d(lon, lat)/d(x, y) at an EPSG:3006 point, in degrees per metre:
    rows lon/lat, columns x/y."""
    lon, lat = _TO_LONLAT.transform([x + h, x - h, x, x], [y, y, y + h, y - h])
    return np.array([[lon[0] - lon[1], lon[2] - lon[3]], [lat[0] - lat[1], lat[2] - lat[3]]]) / (2 * h)


def window_frame(line: LineString, center: Point, view_m: float = VIEW_M) -> tuple[np.ndarray, np.ndarray]:
    """Unit tangent (digitised direction) of `line` over `view_m` around
    `center`, and its left normal."""
    s = line.project(center)
    a = line.interpolate(max(s - view_m / 2, 0.0))
    b = line.interpolate(min(s + view_m / 2, line.length))
    t = np.array([b.x - a.x, b.y - a.y])
    if np.hypot(*t) < 1e-6:
        (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
        t = np.array([x1 - x0, y1 - y0])
    t = t / np.hypot(*t)
    return t, np.array([-t[1], t[0]])


def map_bearing(t: np.ndarray, jac: np.ndarray, lat: float) -> float:
    """MapLibre bearing that puts direction `t` (EPSG:3006) pointing right
    on screen. Both projections are conformal, so screen-up is then `n`."""
    dlon, dlat = jac @ t
    azimuth = math.degrees(math.atan2(dlon * math.cos(math.radians(lat)), dlat))
    return (azimuth - 90.0 + 180.0) % 360.0 - 180.0


def task_geometry(line: LineString, center: Point, view_m: float = VIEW_M) -> dict:
    t, n = window_frame(line, center, view_m)
    jac = jacobian(center.x, center.y)
    lon0, lat0 = _TO_LONLAT.transform(center.x, center.y)
    xy = np.asarray(line.coords)
    lon, lat = _TO_LONLAT.transform(xy[:, 0], xy[:, 1])
    return {
        "center": [round(lon0, 8), round(lat0, 8)],
        "jacobian": [[float(v) for v in row] for row in jac],
        "line_lonlat": [[round(a, 8), round(b, 8)] for a, b in zip(lon, lat)],
        "line_m": [[round(float(a - center.x), 3), round(float(b - center.y), 3)] for a, b in xy],
        "tangent": [round(float(v), 6) for v in t],
        "normal": [round(float(v), 6) for v in n],
        "bearing": round(map_bearing(t, jac, lat0), 3),
        "view_m": view_m,
    }


def context_barriers(context_m: gpd.GeoDataFrame, kind: str, row: int, center: Point, radius_m: float = CONTEXT_RADIUS_M) -> list:
    """The other barrier records (`context_m`: `kind`, `barrier_row`,
    metric geometry) within `radius_m` of `center`, clipped to that circle,
    as lon/lat lines."""
    circle = center.buffer(radius_m)
    lines = []
    for i in context_m.sindex.query(circle, predicate="intersects"):
        if context_m["kind"].iat[i] == kind and context_m["barrier_row"].iat[i] == row:
            continue
        part = force_2d(context_m.geometry.iat[i]).intersection(circle).simplify(0.5)
        for g in getattr(part, "geoms", [part]):
            if g.geom_type == "LineString" and not g.is_empty:
                lon, lat = _TO_LONLAT.transform(*np.asarray(g.coords).T)
                lines.append([[round(a, 8), round(b, 8)] for a, b in zip(lon, lat)])
    return lines


def has_twin(line: LineString, kind: str, row: int, context_m: gpd.GeoDataFrame) -> bool:
    """Another barrier record runs alongside `line` (within `TWIN_BUFFER_M`
    for at least `TWIN_MIN_SHARE` of the shorter one): e.g. one record per
    track of a double track, each with its own wall."""
    zone = line.buffer(TWIN_BUFFER_M)
    for i in context_m.sindex.query(zone, predicate="intersects"):
        if context_m["kind"].iat[i] == kind and context_m["barrier_row"].iat[i] == row:
            continue
        other = context_m.geometry.iat[i]
        if other.intersection(zone).length >= TWIN_MIN_SHARE * min(line.length, other.length):
            return True
    return False


def cluster_order(xy: np.ndarray, rng: np.random.Generator, link_m: float = CLUSTER_LINK_M) -> tuple[list[int], list[dict]]:
    """Visiting order of points `xy` (n x 2, metres): areas of points
    chained within `link_m` in random order, each walked nearest-neighbour
    from its point farthest from the area's centre. Returns the order and,
    per ordered point, its `area` label (1-based number, count, size,
    position)."""
    n = len(xy)
    if n == 0:
        return [], []
    pairs = cKDTree(xy).query_pairs(link_m, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    areas = rng.permutation(np.unique(labels))
    order, info = [], []
    for number, label in enumerate(areas, start=1):
        members = list(np.flatnonzero(labels == label))
        pts = xy[members]
        walk = [members[int(np.argmax(np.hypot(*(pts - pts.mean(axis=0)).T)))]]
        left = set(members) - {walk[0]}
        while left:
            last = xy[walk[-1]]
            walk.append(min(left, key=lambda j: (np.hypot(*(xy[j] - last)), j)))
            left.discard(walk[-1])
        order += walk
        info += [{"number": number, "count": len(areas), "size": len(walk), "position": k} for k in range(1, len(walk) + 1)]
    return [int(i) for i in order], info


def practice_answer(line: LineString, center: Point, normal: np.ndarray, wall) -> dict | None:
    """The OSM wall's offset from the barrier at the view centre, along
    `normal`, and the wall (near the barrier) in lon/lat for the feedback."""
    part = _line_2d(wall).intersection(line.buffer(PRACTICE_WALL_BUFFER_M))
    if part.is_empty:
        return None
    if part.geom_type != "LineString":
        part = max((g for g in getattr(part, "geoms", []) if g.geom_type == "LineString"), key=lambda g: g.length, default=None)
        if part is None:
            return None
    nearest = part.interpolate(part.project(center))
    lateral = float(np.dot([nearest.x - center.x, nearest.y - center.y], normal))
    lon, lat = _TO_LONLAT.transform(*np.asarray(part.coords).T)
    return {"lateral_m": round(lateral, 2), "wall_lonlat": [[round(a, 8), round(b, 8)] for a, b in zip(lon, lat)]}


def display_metadata(row: pd.Series, kind: str) -> dict:
    cols = DISPLAY_COLUMNS[kind]
    material = row.get(cols["material"])
    height = row.get(cols["height"])
    length = row.get("extent_length_m")
    return {
        "material": None if pd.isna(material) else str(material).replace("_", " "),
        "height_m": round(float(height), 1) if pd.notna(height) and 0 < height <= MAX_PLAUSIBLE_HEIGHT_M else None,
        "length_m": round(float(length)) if pd.notna(length) and length > 0 else None,
    }


# -- selection -------------------------------------------------------------

def _panel_schools(root: Path | None) -> set[str]:
    codes = pd.read_parquet(assembled_panel_path(root), columns=["skolenhetskod"])["skolenhetskod"]
    return set(codes.astype(str))


def _pairs(kind: str, panel: set[str], root: Path | None) -> pd.DataFrame:
    path = schools_paths(root)["assembled"] / f"schools_{kind}_pairs_network.parquet"
    pairs = pd.read_parquet(path)
    pairs["skolenhetskod"] = pairs["skolenhetskod"].astype(str)
    return pairs[pairs["skolenhetskod"].isin(panel)]


def _references(kind: str, barriers: gpd.GeoDataFrame, root: Path | None) -> pd.DataFrame:
    path = references_path(kind, root)
    columns = ["barrier_row", *KEY_COLUMNS, "side_method", "barrier_sign", "osm_id", "outer_track_sign"]
    refs = pd.read_parquet(path, columns=[c for c in columns if c in pq.read_schema(path).names])
    if "outer_track_sign" not in refs.columns:  # references built before 2026-09-24
        refs["outer_track_sign"] = np.nan
    refs = refs.set_index("barrier_row").sort_index()
    current = barriers[KEY_COLUMNS].reset_index(drop=True)
    if len(refs) != len(current) or not refs[KEY_COLUMNS].reset_index(drop=True).equals(current):
        raise ValueError(f"barrier_references_{kind} is stale against the barrier layer: re-run `barrier-protection build`.")
    return refs


def _previous_keys(batch: str, root: Path | None) -> pd.DataFrame:
    frames = []
    for path in sorted(barrier_audit_paths(root)["packages"].glob("*_key.parquet")):
        if path.name != f"{batch}_key.parquet":
            frames.append(pd.read_parquet(path, columns=["kind", *KEY_COLUMNS, "group"]))
    if not frames:
        return pd.DataFrame(columns=["kind", *KEY_COLUMNS, "group"])
    return pd.concat(frames, ignore_index=True)


def _nearest_school(pairs: pd.DataFrame) -> pd.Series:
    """barrier_row -> skolenhetskod of its nearest paired panel school."""
    return pairs.sort_values("dist_m").drop_duplicates("barrier_row").set_index("barrier_row")["skolenhetskod"]


def select_barriers(
    batch: str,
    spec: dict,
    *,
    data: dict[str, dict],
    previous: pd.DataFrame,
    osm_walls: gpd.GeoDataFrame,
    context_m: gpd.GeoDataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """One row per chosen barrier: `kind`, `barrier_row`, `group`,
    `skolenhetskod` (the view's school; None for practice)."""
    def excluded(kind: str, groups: tuple[str, ...]) -> set[int]:
        prev = previous[(previous["kind"] == kind) & previous["group"].isin(groups)]
        rows = data[kind]["barriers"][KEY_COLUMNS].reset_index(names="barrier_row").merge(prev[KEY_COLUMNS], on=KEY_COLUMNS)
        return set(rows["barrier_row"])

    chosen = []
    taken: dict[str, set[int]] = {kind: set() for kind in data}

    # Targets.
    for kind, d in data.items():
        pairs = d["pairs"]
        if spec["target"] == "protected_unknown":
            rows = set(pairs.loc[pairs["protected_unknown"], "barrier_row"])
        elif spec["target"] == "same_side_unknown":
            rows = set(pairs.loc[pairs["same_side_unknown"], "barrier_row"]) - excluded(kind, ("target",))
        else:  # pilot: side unknown, but not the protected targets
            rows = set(pairs.loc[pairs["same_side_unknown"], "barrier_row"]) - set(pairs.loc[pairs["protected_unknown"], "barrier_row"])
            rows -= excluded(kind, ("target", "validation"))
        taken[kind] |= rows
        chosen += [{"kind": kind, "barrier_row": int(r), "group": "target"} for r in sorted(rows)]
    if spec["n_targets"] is not None:
        targets = pd.DataFrame(chosen)
        keep = targets.sample(n=min(spec["n_targets"], len(targets)), random_state=rng.integers(2**31)) if len(targets) else targets
        dropped = targets.drop(keep.index)
        for r in dropped.itertuples():
            taken[r.kind].discard(r.barrier_row)
        chosen = keep.sort_values(["kind", "barrier_row"]).to_dict("records")

    # Validation: blind sample of auto-sided barriers paired with panel schools.
    for method, kinds in VALIDATION_METHODS.items():
        if not spec["validation_per_method"]:
            break
        pool = []
        for kind in kinds:
            d = data[kind]
            known = set(d["pairs"].loc[d["pairs"]["same_route"] & ~d["pairs"]["same_side_unknown"], "barrier_row"])
            refs = d["references"]
            rows = set(refs.index[refs["side_method"] == method]) & known
            rows -= taken[kind] | excluded(kind, ("validation", "target"))
            pool += [(kind, int(r)) for r in sorted(rows)]
        picks = rng.choice(len(pool), size=min(spec["validation_per_method"], len(pool)), replace=False) if pool else []
        for i in sorted(picks):
            kind, row = pool[i]
            taken[kind].add(row)
            chosen.append({"kind": kind, "barrier_row": row, "group": "validation"})

    # Practice: tagged OSM noise barriers alongside, not in any other group,
    # without a twin record (whose wall could be the one the reviewer picks).
    tagged = set(osm_walls.loc[osm_walls["wall_type"] == "noise_barrier", "osm_id"].astype("int64"))
    per_kind = {"road": spec["n_practice"] - spec["n_practice"] // 2, "rail": spec["n_practice"] // 2}
    for kind, d in data.items():
        refs, barriers = d["references"], d["barriers"]
        ok = (
            (refs["side_method"] == "osm_offset")
            & refs["osm_id"].isin(tagged)
            & (barriers["extent_length_m"].to_numpy() >= PRACTICE_MIN_LENGTH_M)
        )
        pool = sorted(set(refs.index[ok]) - taken[kind] - set(d["pairs"]["barrier_row"]))
        pool = [r for r in pool if not has_twin(_line_2d(d["barriers_m"].geometry.iat[r]), kind, r, context_m)]
        picks = rng.choice(len(pool), size=min(per_kind.get(kind, 0), len(pool)), replace=False) if pool else []
        chosen += [{"kind": kind, "barrier_row": int(pool[i]), "group": "practice"} for i in sorted(picks)]

    frame = pd.DataFrame(chosen, columns=["kind", "barrier_row", "group"])
    schools = {kind: _nearest_school(d["pairs"]) for kind, d in data.items()}
    frame["skolenhetskod"] = [
        None if r.group == "practice" else schools[r.kind].get(r.barrier_row) for r in frame.itertuples()
    ]
    return frame


# -- export ----------------------------------------------------------------

def _load_inputs(kinds: tuple[str, ...], root: Path | None) -> dict[str, dict]:
    panel = _panel_schools(root)
    data = {}
    for kind in kinds:
        barriers = load_noise_barriers(kind, root).reset_index(drop=True)
        data[kind] = {
            "barriers": barriers,
            "barriers_m": barriers.to_crs(METRIC_CRS),
            "pairs": _pairs(kind, panel, root),
            "references": _references(kind, barriers, root),
        }
    return data


def context_layer(data: dict[str, dict]) -> gpd.GeoDataFrame:
    """Every current barrier record of the loaded kinds (`kind`,
    `barrier_row`, metric geometry): what `context_barriers` and `has_twin`
    search."""
    frames = []
    for kind, d in data.items():
        b = d["barriers_m"]
        current = b["is_current"].fillna(False).to_numpy(dtype=bool) if "is_current" in b.columns else np.ones(len(b), dtype=bool)
        frames.append(gpd.GeoDataFrame({"kind": kind, "barrier_row": np.flatnonzero(current)}, geometry=b.geometry.to_numpy()[current], crs=b.crs))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=METRIC_CRS)


def build_tasks(
    batch: str,
    selection: pd.DataFrame,
    *,
    data: dict[str, dict],
    schools_m: gpd.GeoSeries,
    osm_walls_m: gpd.GeoDataFrame,
    context_m: gpd.GeoDataFrame,
    reviewer: str,
    double_code_share: float,
    rng: np.random.Generator,
    view_m: float = VIEW_M,
) -> tuple[dict, gpd.GeoDataFrame]:
    """The blinded tasks document and the key, in task order: practice
    first (shuffled), then everything else area by area (`cluster_order`)."""
    walls_by_id = osm_walls_m.set_index(osm_walls_m["osm_id"].astype("int64")).geometry
    selection = selection.reset_index(drop=True)
    lines, centers = [], []
    for r in selection.itertuples():
        line = _line_2d(data[r.kind]["barriers_m"].geometry.iat[r.barrier_row])
        if isinstance(r.skolenhetskod, str) and r.skolenhetskod in schools_m.index:
            centers.append(line.interpolate(line.project(schools_m.loc[r.skolenhetskod])))
        else:
            centers.append(line.interpolate(0.5, normalized=True))
        lines.append(line)
    practice = list(rng.permutation(np.flatnonzero(selection["group"].to_numpy() == "practice")))
    rest = np.flatnonzero(selection["group"].to_numpy() != "practice")
    walk, areas = cluster_order(np.array([[centers[i].x, centers[i].y] for i in rest]).reshape(-1, 2), rng)
    ordered = [int(i) for i in practice] + [int(rest[j]) for j in walk]
    area_of = dict(zip(ordered[len(practice):], areas))
    n_double = int(round(double_code_share * len(rest)))
    double = set(rng.choice(np.arange(len(practice), len(ordered)), size=n_double, replace=False).tolist()) if n_double else set()

    ids: set[str] = set()
    tasks, keys = [], []
    for order, i in enumerate(ordered):
        r = selection.iloc[i]
        d = data[r.kind]
        barrier = d["barriers"].iloc[r.barrier_row]
        line, center = lines[i], centers[i]
        geometry = task_geometry(line, center, view_m)
        ref = d["references"].loc[r.barrier_row]

        task_id = None
        while task_id is None or task_id in ids:
            task_id = f"{int(rng.integers(16**8)):08x}"
        ids.add(task_id)

        task = {
            "task_id": task_id,
            "kind": r.kind,
            **display_metadata(barrier, r.kind),
            **geometry,
            "others_lonlat": context_barriers(context_m, r.kind, int(r.barrier_row), center),
            "area": area_of.get(i),
            "practice": r.group == "practice",
        }
        answer = None
        if r.group == "practice":
            answer = practice_answer(line, center, np.array(geometry["normal"]), walls_by_id.loc[int(ref["osm_id"])])
            task["practice_answer"] = answer
        tasks.append(task)
        keys.append(
            {
                "task_id": task_id,
                "batch": batch,
                "order": order,
                "group": r.group,
                "double_code": order in double,
                "kind": r.kind,
                "barrier_row": int(r.barrier_row),
                **{c: barrier[c] for c in KEY_COLUMNS},
                "side_method": ref["side_method"],
                "barrier_sign": float(ref["barrier_sign"]),
                "osm_id": ref["osm_id"],
                "outer_track_sign": float(ref.get("outer_track_sign", np.nan)),
                "skolenhetskod": r.skolenhetskod,
                "center_x": center.x,
                "center_y": center.y,
                "n_x": geometry["normal"][0],
                "n_y": geometry["normal"][1],
                "practice_lateral_m": np.nan if answer is None else answer["lateral_m"],
                "geometry": line,
            }
        )
    document = {
        "batch": batch,
        "reviewer": reviewer,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "n_tasks": len(tasks),
        "tasks": tasks,
    }
    key = gpd.GeoDataFrame(keys, geometry="geometry", crs=METRIC_CRS)
    key["osm_id"] = key["osm_id"].astype("Int64")
    return document, key


def run_barrier_audit_export(
    batch: str,
    *,
    reviewer: str = "assistant",
    seed: int = DEFAULT_SEED,
    n_targets: int | None = None,
    validation_per_method: int | None = None,
    n_practice: int | None = None,
    double_code_share: float | None = None,
    kinds: tuple[str, ...] = BARRIER_KINDS,
    root: Path | None = None,
) -> dict:
    if batch not in BATCHES:
        raise ValueError(f"unknown batch {batch!r}; one of {sorted(BATCHES)}")
    spec = dict(BATCHES[batch])
    for name, value in {
        "n_targets": n_targets,
        "validation_per_method": validation_per_method,
        "n_practice": n_practice,
        "double_code_share": double_code_share,
    }.items():
        if value is not None:
            spec[name] = value
    rng = np.random.default_rng(seed)
    data = _load_inputs(kinds, root)
    osm_walls_m = load_osm_walls(root).to_crs(METRIC_CRS)
    context_m = context_layer(data)
    selection = select_barriers(
        batch, spec, data=data, previous=_previous_keys(batch, root), osm_walls=osm_walls_m, context_m=context_m, rng=rng
    )

    schools = load_geocoded_schools(root)
    schools_m = schools.set_index(schools["skolenhetskod"].astype(str)).to_crs(METRIC_CRS).geometry
    schools_m = schools_m[~schools_m.index.duplicated()]
    document, key = build_tasks(
        batch, selection, data=data, schools_m=schools_m, osm_walls_m=osm_walls_m, context_m=context_m,
        reviewer=reviewer, double_code_share=spec["double_code_share"], rng=rng,
    )
    tasks_file, key_file = tasks_path(batch, root), key_path(batch, root)
    tasks_file.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    key.to_parquet(key_file, index=False)
    counts = key.groupby(["group", "kind"]).size()
    return {
        "batch": batch,
        "reviewer": reviewer,
        "n_tasks": len(key),
        "groups": {f"{g}/{k}": int(n) for (g, k), n in counts.items()},
        "validation_methods": {m: int(n) for m, n in key.loc[key["group"] == "validation", "side_method"].value_counts().items()},
        "n_double_coded": int(key["double_code"].sum()),
        "tasks": str(tasks_file),
        "key": str(key_file),
        "spec": spec,
        "seed": seed,
    }
