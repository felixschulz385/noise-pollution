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

**One task per wall.** The register splits a wall into pieces wherever an
attribute or the road link / track element changes (a quarter of all
records are under 30 m). A chosen record's task therefore covers every
piece of its wall (`linear_ref.chain_lines`: ends within 2 m, continuing
within 30 degrees, simple paths only), drawn as one line; the pieces that
weren't chosen join the key as group `chain`, and the answer applies to
all of them. The key has one row per record; `task_group` is the task's
highest group (target > validation > chain > practice). Practice tasks stay
single records.

**Type badge.** Each task carries its materials (by length) and a
`type_group` -- `berm`, `berm_screen`, `glass`, `wall` or `mixed` -- that the
app shows as a badge with what to look for: an earth berm is a grassy bank,
not a wall.

**No stubs.** A record whose geometry is under 1 m (`is_stub`; 63 rail
records) is never chosen as a target, validation or practice task: its
line is invisible (pilot task `9376dc21`, 2 cm). Such a record takes its
side from its BIS object's other records instead (`bis_sibling` in
`_barrier_reference.py`), and may still ride along as a `chain` piece.

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

from src.core.barrier_geometry.linear_ref import chain_lines, join_chain
from src.regions.sweden.sources._barrier_reference import is_stub
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


def context_barriers(context_m: gpd.GeoDataFrame, kind: str, rows, center: Point, radius_m: float = CONTEXT_RADIUS_M) -> list:
    """The other barrier records (`context_m`: `kind`, `barrier_row`,
    metric geometry) within `radius_m` of `center` -- all but the task's own
    `rows` (one row or a set) -- clipped to that circle, as lon/lat lines."""
    own = {int(rows)} if np.isscalar(rows) else {int(r) for r in rows}
    circle = center.buffer(radius_m)
    lines = []
    for i in context_m.sindex.query(circle, predicate="intersects"):
        if context_m["kind"].iat[i] == kind and int(context_m["barrier_row"].iat[i]) in own:
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


# The app's type badge: what to look for on the photo.
TYPE_GROUPS = {"earth berm": "berm", "earth berm and wood": "berm_screen", "glass or plexiglass": "glass"}


def type_group(material: str | None) -> str | None:
    """`berm` / `berm_screen` / `glass` / `wall` for a display material, None
    when the register has no type."""
    return None if not material else TYPE_GROUPS.get(material, "wall")


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
    # Stubs are never shown: nothing to see (see the module docstring).
    taken: dict[str, set[int]] = {kind: set() for kind in data}
    stubs = {kind: set(np.flatnonzero(is_stub(d["barriers_m"])).tolist()) for kind, d in data.items()}

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
        rows -= stubs[kind]
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
        for kind in (k for k in kinds if k in data):
            d = data[kind]
            known = set(d["pairs"].loc[d["pairs"]["same_route"] & ~d["pairs"]["same_side_unknown"], "barrier_row"])
            refs = d["references"]
            rows = set(refs.index[refs["side_method"] == method]) & known
            rows -= taken[kind] | excluded(kind, ("validation", "target")) | stubs[kind]
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
        pool = sorted(set(refs.index[ok]) - taken[kind] - set(d["pairs"]["barrier_row"]) - stubs[kind])
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


GROUP_PRIORITY = ("target", "validation", "chain", "practice")


def _chains(d: dict) -> pd.DataFrame:
    """`chain_lines` over one kind's barriers (cached in `d`)."""
    if "chains" not in d:
        d["chains"] = chain_lines([_line_2d(g) for g in d["barriers_m"].geometry])
    return d["chains"]


def task_units(selection: pd.DataFrame, data: dict[str, dict]) -> list[pd.DataFrame]:
    """The records each task covers, in chain order: a practice record on its
    own, any other chosen record together with every piece of its wall's
    chain (`chain_lines`). Records of the chain that weren't chosen join as
    group `chain`: the reviewer sees them in the overlay, so the answer
    applies to them too. Columns: `kind`, `barrier_row`, `group`,
    `skolenhetskod`, `chain_orient`."""
    units = []
    practice = selection[selection["group"] == "practice"]
    for r in practice.itertuples():
        units.append(pd.DataFrame([{"kind": r.kind, "barrier_row": int(r.barrier_row), "group": "practice",
                                    "skolenhetskod": None, "chain_orient": 1}]))
    rest = selection[selection["group"] != "practice"].copy()
    rest["chain_id"] = [int(_chains(data[r.kind])["chain_id"].iat[r.barrier_row]) for r in rest.itertuples()]
    for (kind, chain_id), chosen in rest.groupby(["kind", "chain_id"], sort=False):
        chains = _chains(data[kind])
        members = chains.index[chains["chain_id"] == chain_id]
        unit = chains.loc[members].sort_values("chain_pos")
        unit = pd.DataFrame({"kind": kind, "barrier_row": unit.index.astype(int), "chain_orient": unit["chain_orient"].to_numpy()})
        unit = unit.merge(chosen[["barrier_row", "group", "skolenhetskod"]], on="barrier_row", how="left")
        unit["group"] = unit["group"].fillna("chain")
        units.append(unit)
    return units


def unit_metadata(unit: pd.DataFrame, d: dict, kind: str) -> dict:
    """The top-bar metadata of a task covering `unit`'s records: the barrier
    type (materials ordered by length; `type_group` for the app's badge), the
    height (or its range) and the total length."""
    rows = [d["barriers"].iloc[r] for r in unit["barrier_row"]]
    meta = [display_metadata(row, kind) for row in rows]
    lengths = [_line_2d(d["barriers_m"].geometry.iat[r]).length for r in unit["barrier_row"]]
    by_material: dict[str, float] = {}
    for m, length in zip(meta, lengths):
        if m["material"]:
            by_material[m["material"]] = by_material.get(m["material"], 0.0) + length
    materials = sorted(by_material, key=lambda k: -by_material[k])
    groups = {type_group(m) for m in materials}
    heights = [m["height_m"] for m in meta if m["height_m"] is not None]
    return {
        "material": ", ".join(materials) or None,
        "type_group": None if not groups else groups.pop() if len(groups) == 1 else "mixed",
        "height_m": None if not heights else [min(heights), max(heights)],
        "length_m": round(sum(lengths)),
        "n_records": len(unit),
    }


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
    first (shuffled), then everything else area by area (`cluster_order`).
    One task per wall (`task_units`); the key has one row per record, each
    with the point of its own piece nearest the view (`center_x/y`) and the
    task's left normal there (`n_x/y`), so an answer's offset places every
    piece's wall."""
    walls_by_id = osm_walls_m.set_index(osm_walls_m["osm_id"].astype("int64")).geometry
    units = task_units(selection.reset_index(drop=True), data)
    lines, centers = [], []
    for unit in units:
        d = data[unit["kind"].iat[0]]
        pieces = [_line_2d(d["barriers_m"].geometry.iat[r]) for r in unit["barrier_row"]]
        line = pieces[0] if len(pieces) == 1 else join_chain(pieces, unit["chain_orient"].tolist())
        chosen = unit[unit["group"] != "chain"].copy()
        chosen["_rank"] = chosen["group"].map(GROUP_PRIORITY.index)
        center = None
        for r in chosen.sort_values(["_rank", "barrier_row"]).itertuples():
            if isinstance(r.skolenhetskod, str) and r.skolenhetskod in schools_m.index:
                center = line.interpolate(line.project(schools_m.loc[r.skolenhetskod]))
                break
        if center is None:
            first = _line_2d(d["barriers_m"].geometry.iat[int(chosen.sort_values("_rank")["barrier_row"].iat[0])])
            center = line.interpolate(line.project(first.interpolate(0.5, normalized=True)))
        lines.append(line)
        centers.append(center)
    is_practice = np.array([u["group"].iat[0] == "practice" for u in units])
    practice = list(rng.permutation(np.flatnonzero(is_practice)))
    rest = np.flatnonzero(~is_practice)
    walk, areas = cluster_order(np.array([[centers[i].x, centers[i].y] for i in rest]).reshape(-1, 2), rng)
    ordered = [int(i) for i in practice] + [int(rest[j]) for j in walk]
    area_of = dict(zip(ordered[len(practice):], areas))
    n_double = int(round(double_code_share * len(rest)))
    double = set(rng.choice(np.arange(len(practice), len(ordered)), size=n_double, replace=False).tolist()) if n_double else set()

    ids: set[str] = set()
    tasks, keys = [], []
    for order, i in enumerate(ordered):
        unit, line, center = units[i], lines[i], centers[i]
        kind = unit["kind"].iat[0]
        d = data[kind]
        geometry = task_geometry(line, center, view_m)
        task_group = min(unit["group"], key=GROUP_PRIORITY.index)

        task_id = None
        while task_id is None or task_id in ids:
            task_id = f"{int(rng.integers(16**8)):08x}"
        ids.add(task_id)

        task = {
            "task_id": task_id,
            "kind": kind,
            **unit_metadata(unit, d, kind),
            **geometry,
            "others_lonlat": context_barriers(context_m, kind, set(unit["barrier_row"]), center),
            "area": area_of.get(i),
            "practice": task_group == "practice",
        }
        answer = None
        if task_group == "practice":
            ref = d["references"].loc[int(unit["barrier_row"].iat[0])]
            answer = practice_answer(line, center, np.array(geometry["normal"]), walls_by_id.loc[int(ref["osm_id"])])
            task["practice_answer"] = answer
        tasks.append(task)
        for r in unit.itertuples():
            barrier = d["barriers"].iloc[r.barrier_row]
            ref = d["references"].loc[r.barrier_row]
            piece = _line_2d(d["barriers_m"].geometry.iat[r.barrier_row])
            point = piece.interpolate(piece.project(center))
            _, normal = window_frame(line, line.interpolate(line.project(point)), view_m)
            if len(unit) == 1:
                normal = np.array(geometry["normal"])
            keys.append(
                {
                    "task_id": task_id,
                    "batch": batch,
                    "order": order,
                    "group": r.group,
                    "task_group": task_group,
                    "double_code": order in double,
                    "kind": kind,
                    "barrier_row": int(r.barrier_row),
                    **{c: barrier[c] for c in KEY_COLUMNS},
                    "side_method": ref["side_method"],
                    "barrier_sign": float(ref["barrier_sign"]),
                    "osm_id": ref["osm_id"],
                    "outer_track_sign": float(ref.get("outer_track_sign", np.nan)),
                    "skolenhetskod": r.skolenhetskod if isinstance(r.skolenhetskod, str) else None,
                    "n_records": len(unit),
                    "chain_orient": int(r.chain_orient),
                    "center_x": point.x,
                    "center_y": point.y,
                    "n_x": float(normal[0]),
                    "n_y": float(normal[1]),
                    "practice_lateral_m": np.nan if answer is None else answer["lateral_m"],
                    "geometry": piece,
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
    tasks_by_group = key.drop_duplicates("task_id").groupby(["task_group", "kind"]).size()
    return {
        "batch": batch,
        "reviewer": reviewer,
        "n_tasks": int(key["task_id"].nunique()),
        "n_records": len(key),
        "tasks": {f"{g}/{k}": int(n) for (g, k), n in tasks_by_group.items()},
        "groups": {f"{g}/{k}": int(n) for (g, k), n in counts.items()},
        "validation_methods": {m: int(n) for m, n in key.loc[key["group"] == "validation", "side_method"].value_counts().items()},
        "n_double_coded": int(key.drop_duplicates("task_id")["double_code"].sum()),
        "tasks_file": str(tasks_file),
        "key": str(key_file),
        "spec": spec,
        "seed": seed,
    }
