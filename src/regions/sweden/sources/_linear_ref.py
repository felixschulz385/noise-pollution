"""Shared line-network geometry primitives for road and rail: nearest-segment
matching, linear referencing, signed side-of-line, a network-distance-bounded
corridor, a "through-line" following one road across junctions, and a
parallel-neighbour search. Composed by `_barrier_reference.py`, which is what
the `schools` and `grid` matching code actually call -- see
`docs/data/sweden/barrier_matching.md`.
"""
from __future__ import annotations

from collections import deque

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import LineString
from shapely.ops import substring, unary_union


METRIC_CRS = "EPSG:3006"  # SWEREF99 TM
DEFAULT_CORRIDOR_BUDGET_M = 800.0
DEFAULT_CORRIDOR_BUFFER_M = 600.0


def nearest_segment(points: gpd.GeoDataFrame, network: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per input point: its nearest `network` segment + distance.
    `sjoin_nearest` only returns the LEFT geometry column -- the matched
    segment's own geometry is pulled back explicitly via `index_right`."""
    joined = gpd.sjoin_nearest(points[["geometry"]], network, distance_col="dist_m", how="left")
    joined = joined[~joined.index.duplicated(keep="first")]
    joined = joined.rename(columns={"geometry": "point_geometry"})
    joined["segment_geometry"] = network.geometry.loc[joined["index_right"]].to_numpy()
    return joined


def position_and_side(point, line, begin: float, end: float) -> tuple[float, float, float]:
    """Project `point` onto `line`: `(position, signed_side, offset_m)`,
    rescaling the 0-1 fraction along `line` to `[begin, end]`.

    `side` is the sign of the cross product between the line's local
    tangent and the offset vector -- it is **not** a compass direction
    (the network's own digitizing-direction convention was not verified
    to be consistent -- Florida's own equivalent found `rciroads`'
    direction was empirically inconsistent, not assumed safe). Valid
    **only pairwise**, comparing two points projected onto the SAME line.
    """
    frac = line.project(point, normalized=True)
    position = begin + frac * (end - begin)
    eps = 1e-4
    f0, f1 = max(0.0, frac - eps), min(1.0, frac + eps)
    tangent = np.array(line.interpolate(f1, normalized=True).coords[0]) - np.array(
        line.interpolate(f0, normalized=True).coords[0]
    )
    proj_pt = line.interpolate(frac, normalized=True)
    offset_vec = np.array([point.x - proj_pt.x, point.y - proj_pt.y])
    offset_m = point.distance(proj_pt)
    cross = tangent[0] * offset_vec[1] - tangent[1] * offset_vec[0]
    side = float(np.sign(cross)) if offset_m > 1e-6 else 0.0
    return position, side, offset_m


def signed_side(line, points) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized :func:`position_and_side` for many points against ONE line:
    `(sign, offset_m)` arrays. Sign is +1 left / -1 right of the line's own
    digitizing direction, 0 on it -- meaningful only when comparing points
    against the same `line`. A point projecting past an end is judged by the
    tangent at that end; its along-line component doesn't enter the cross
    product, so the sign still reflects the lateral side."""
    pts = np.asarray(points)
    frac = shapely.line_locate_point(line, pts, normalized=True)
    eps = 1e-4
    p0 = shapely.line_interpolate_point(line, np.clip(frac - eps, 0.0, 1.0), normalized=True)
    p1 = shapely.line_interpolate_point(line, np.clip(frac + eps, 0.0, 1.0), normalized=True)
    proj = shapely.line_interpolate_point(line, frac, normalized=True)
    tx, ty = shapely.get_x(p1) - shapely.get_x(p0), shapely.get_y(p1) - shapely.get_y(p0)
    ox, oy = shapely.get_x(pts) - shapely.get_x(proj), shapely.get_y(pts) - shapely.get_y(proj)
    offset = np.hypot(ox, oy)
    sign = np.where(offset > 1e-6, np.sign(tx * oy - ty * ox), 0.0)
    return sign, offset


def _unit(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def local_tangent(line, point) -> np.ndarray:
    """Unit tangent of `line` (2-D) at the point on it nearest `point`."""
    frac = line.project(point, normalized=True)
    eps = 1e-4
    a = line.interpolate(max(0.0, frac - eps), normalized=True)
    b = line.interpolate(min(1.0, frac + eps), normalized=True)
    return _unit(np.array([b.x - a.x, b.y - a.y]))


def _endpoint_key(pt, precision: int = 0) -> tuple[float, float]:
    return (round(pt[0], precision), round(pt[1], precision))


def build_adjacency(network: gpd.GeoDataFrame) -> dict[tuple[float, float], list[int]]:
    """Endpoint-adjacency graph: maps a rounded `(x, y)` junction (1 m grid,
    to absorb float noise) to the row-positions of every `network` segment
    whose `LineString` starts or ends there. `network` must be positionally
    indexed 0..n-1."""
    endpoints: dict[tuple[float, float], list[int]] = {}
    for i, geom in enumerate(network.geometry):
        coords = list(geom.coords)
        for pt in (coords[0], coords[-1]):
            endpoints.setdefault(_endpoint_key(pt), []).append(i)
    return endpoints


def corridor_geometry(
    seg_idx: int,
    origin_point,
    geoms: np.ndarray,
    lengths: np.ndarray,
    endpoints: dict[tuple[float, float], list[int]],
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
):
    """Network-distance-bounded flood fill from `origin_point` (projected
    onto `geoms[seg_idx]`), walking the connectivity graph `endpoints`
    outward in both directions and consuming *true path distance* -- not a
    segment-count or per-hop-length proxy (Florida's own corridor code
    found that proxy silently breaks on long unsegmented stretches; both
    Sweden networks have the same shape of risk -- segment lengths up to
    13 km on rail, 130 km on the road network).

    The seed segment is trimmed (`shapely.ops.substring`) to the portion
    within `budget_m` of `origin_point`. A neighbor segment longer than the
    remaining budget is trimmed the same way from its entry junction rather
    than dropped -- dropping it cut corridors off at the first junction
    whenever a short seed row met a long neighbour (see
    `docs/data/sweden/barrier_matching.md` §2).

    Returns the corridor's (unbuffered) centerline geometry.
    """
    seg = geoms[seg_idx]
    dist_along = seg.project(origin_point)
    length0 = lengths[seg_idx]
    dist_to_start, dist_to_end = dist_along, length0 - dist_along

    pieces = [substring(seg, max(0.0, dist_along - budget_m), min(length0, dist_along + budget_m))]
    coords0 = list(seg.coords)
    start_key, end_key = _endpoint_key(coords0[0]), _endpoint_key(coords0[-1])
    included = {seg_idx}
    q: deque[tuple[tuple[float, float], float]] = deque()
    if dist_to_start < budget_m:
        q.append((start_key, budget_m - dist_to_start))
    if dist_to_end < budget_m:
        q.append((end_key, budget_m - dist_to_end))

    while q:
        junction, remaining = q.popleft()
        for nb in endpoints.get(junction, []):
            if nb in included:
                continue
            nb_len = lengths[nb]
            included.add(nb)
            nb_coords = list(geoms[nb].coords)
            nb_start, nb_end = _endpoint_key(nb_coords[0]), _endpoint_key(nb_coords[-1])
            enters_at_start = nb_start == junction
            if nb_len <= remaining:
                pieces.append(geoms[nb])
                other_end = nb_end if enters_at_start else nb_start
                if remaining - nb_len > 0:
                    q.append((other_end, remaining - nb_len))
            elif enters_at_start:
                pieces.append(substring(geoms[nb], 0.0, remaining))
            else:
                pieces.append(substring(geoms[nb], nb_len - remaining, nb_len))
    return unary_union(pieces)


def through_line(
    seg_idx: int,
    origin_point,
    geoms: np.ndarray,
    endpoints: dict[tuple[float, float], list[int]],
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    min_cos: float = 0.7,
    sindex=None,
    bridge_m: float = 2.0,
) -> tuple[LineString, set[int]]:
    """One continuous 2-D line following the road `seg_idx` belongs to,
    about `budget_m` either side of `origin_point`: at each junction it
    continues onto the neighbour that turns least (|turn| < ~45°), so side
    streets aren't followed the way :func:`corridor_geometry`'s flood fill
    follows them, and it stops rather than take a segment that heads back
    against the seed's direction (a loop or hook would otherwise flip the
    side for everything projecting onto it). Used as the single reference
    line for side tests, since a sign is only comparable along one line.

    With `sindex`, an end that has no such continuation also *bridges* onto
    a row whose interior passes within `bridge_m` of it, under the same
    turn and no-reversal rules: NVDB often starts a ramp mid-way along the
    mainline row with no shared node (16% of road barriers' lines had such
    an end), which would otherwise cut the line short at the ramp.
    Returns the line and the network rows it uses."""
    coords = [np.array(c[:2], dtype=float) for c in geoms[seg_idx].coords]
    used = {seg_idx}
    along = geoms[seg_idx].project(origin_point)
    length0 = geoms[seg_idx].length

    def bridge(end: np.ndarray, heading: np.ndarray, seed_heading: np.ndarray):
        best, best_cos, best_coords = None, min_cos, None
        end_pt = shapely.Point(end)
        for j in sindex.query(end_pt, predicate="dwithin", distance=bridge_m):
            if j in used:
                continue
            at = geoms[j].project(end_pt)
            tangent = local_tangent(geoms[j], end_pt)
            piece = substring(geoms[j], at, geoms[j].length if tangent @ heading >= 0 else 0.0)
            if piece.is_empty or piece.geom_type != "LineString" or piece.length < bridge_m:
                continue
            piece_coords = [np.array(c[:2], dtype=float) for c in piece.coords]
            cos = abs(float(tangent @ heading))
            if cos > best_cos and float(np.dot(seed_heading, _unit(piece_coords[-1] - piece_coords[0]))) > 0:
                best, best_cos, best_coords = int(j), cos, piece_coords
        return best, best_coords

    def extend(path: list[np.ndarray], remaining: float) -> list[np.ndarray]:
        seed_heading = _unit(path[-1] - path[0])
        while remaining > 0:
            heading = _unit(path[-1] - path[-2])
            best, best_cos, best_coords = None, min_cos, None
            for nb in endpoints.get(_endpoint_key(path[-1]), []):
                if nb in used:
                    continue
                nb_coords = [np.array(c[:2], dtype=float) for c in geoms[nb].coords]
                if _endpoint_key(nb_coords[0]) != _endpoint_key(path[-1]):
                    nb_coords = nb_coords[::-1]
                cos = float(np.dot(heading, _unit(nb_coords[1] - nb_coords[0])))
                if cos > best_cos and float(np.dot(seed_heading, _unit(nb_coords[-1] - nb_coords[0]))) > 0:
                    best, best_cos, best_coords = nb, cos, nb_coords
            if best is None and sindex is not None:
                best, best_coords = bridge(path[-1], heading, seed_heading)
            if best is None:
                break
            used.add(best)
            path.extend(best_coords[1:])
            remaining -= LineString(best_coords).length
        return path

    forward = extend(list(coords), budget_m - (length0 - along))
    backward = extend(list(coords[::-1]), budget_m - along)
    line = LineString(backward[::-1][: len(backward) - len(coords)] + forward)
    return line, used


def parallel_neighbor(
    anchor,
    own_line: LineString,
    exclude: set[int],
    geoms: np.ndarray,
    sindex,
    endpoints: dict[tuple[float, float], list[int]],
    *,
    search_m: float = 100.0,
    min_cos: float = 0.9,
    min_lateral_m: float = 2.0,
    span_m: float = 200.0,
    step_m: float = 50.0,
    max_lateral_m: float = 80.0,
) -> int | None:
    """Nearest network row that runs *alongside* `own_line` at `anchor`: a
    divided road's other carriageway, or the mainline beside a ramp.

    A candidate must be parallel at its own nearest point (local tangent,
    not the row's chord), within `search_m`, and mostly *sideways* from
    `anchor` (at least `min_lateral_m` across and more across than along),
    which rejects the same road's own continuation past a junction. It must
    also stay beside `own_line` on one side, within `max_lateral_m`, for
    `span_m` either way, which rejects a cross street or a frontage road
    that only briefly parallels it. Validated against OSM wall positions
    2026-09-23: the wall stands on the side of `own_line` away from the
    neighbour for 93% of tagged / 100% of untyped OSM walls (n=102 / 37),
    vs. 76% when simply taking the nearest parallel row; see
    `docs/data/sweden/barrier_matching.md`. `exclude` holds `own_line`'s
    own rows."""
    tangent = local_tangent(own_line, anchor)
    normal = np.array([-tangent[1], tangent[0]])
    candidates = []
    for i in sindex.query(anchor.buffer(search_m), predicate="intersects"):
        if i in exclude:
            continue
        nearest = geoms[i].interpolate(geoms[i].project(anchor))
        vec = np.array([nearest.x - anchor.x, nearest.y - anchor.y])
        lateral, longitudinal = abs(float(vec @ normal)), abs(float(vec @ tangent))
        if lateral < min_lateral_m or lateral <= longitudinal or np.hypot(lateral, longitudinal) > search_m:
            continue
        if abs(float(local_tangent(geoms[i], anchor) @ tangent)) < min_cos:
            continue
        candidates.append((lateral, int(i), nearest))
    along = own_line.project(anchor)
    for _, i, nearest in sorted(candidates, key=lambda c: c[0]):
        other, _ = through_line(i, nearest, geoms, endpoints, budget_m=span_m + 2 * step_m)
        samples = [
            own_line.interpolate(min(max(along + d, 0.0), own_line.length))
            for d in np.arange(-span_m, span_m + step_m / 2, step_m)
        ]
        if any(q.distance(other) > max_lateral_m for q in samples):
            continue
        sides, _ = signed_side(own_line, [other.interpolate(other.project(q)) for q in samples])
        if len(set(sides[sides != 0])) == 1:
            return i
    return None
