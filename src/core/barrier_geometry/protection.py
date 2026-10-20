"""The protected-area model, shared by every region: given, per barrier, a
reference line along its road (the through-line), the side it stands on and
the stretch it covers, decide for any point whether the barrier protects it
(:func:`classify_points`) and draw that area as polygons
(:func:`protection_zones`).

A point is **protected** by a barrier when it lies on the barrier's side of
its road, within `PROTECTED_MAX_LATERAL_M` of the road, and its *nearest
point on the road* lies beside the barrier's stretch (±`PROTECTED_SPAN_MARGIN_M`).
A point in front of a wall but nearer another, unshielded part of the same
road (inside a bend) hears that part unshielded, so it isn't protected.

Optionally, the same rule one ring further out gives a **control band**: on
the barrier's side, beside its stretch, but between `PROTECTED_MAX_LATERAL_M`
and `CONTROL_MAX_LATERAL_M` from the road. That is the comparison area of a
within-barrier design (Moretti & Wheeler 2025 compare homes 0-500m behind a
wall with homes 500-1500m behind the same wall).

Which road a barrier belongs to and which side it stands on is region data:
Sweden infers the side (`src/regions/sweden/sources/_barrier_reference.py`),
Florida reads it off the wall's own geometry
(`src/regions/florida/sources/barrier_protection/`). Both hand this module a
:class:`BarrierReferences`. See `docs/data/sweden/barrier_matching.md` and
`docs/data/florida/barrier_protection.md`.
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString
from shapely.ops import substring, unary_union

from src.core.barrier_geometry.linear_ref import (
    DEFAULT_CORRIDOR_BUDGET_M,
    DEFAULT_CORRIDOR_BUFFER_M,
    _unit,
    corridor_geometry,
    signed_side,
    through_line,
)

# Half a 100m grid cell: a cell whose centroid is within 50m of the stretch
# overlaps it. Also absorbs small geometry/measure mismatches.
PROTECTED_SPAN_MARGIN_M = 50.0
# How far from its road a barrier's protected area reaches: the same 600m
# as the `same_route` corridor, so a protected point is always same_route.
PROTECTED_MAX_LATERAL_M = DEFAULT_CORRIDOR_BUFFER_M
# Outer edge of the control band (opt-in, see `classify_points`): as in
# Moretti & Wheeler (2025), whose controls lie 500-1500m from the wall.
# Beyond ~800m along the road the through-line may not reach the next road
# a point is nearer to, so the band's "beside the stretch" is a looser test
# than the protected area's.
CONTROL_MAX_LATERAL_M = 1500.0
# Optional per-barrier column of `BarrierReferences.table`: the barrier's
# engineered noise reduction in dB (Florida: FHWA `FED_ANR`; Sweden's
# registers have none).
NOISE_REDUCTION_COLUMN = "noise_reduction_db"
# Densification step of the through-line when drawing protection zones.
ZONE_STEP_M = 5.0
# Sub-metre digitization jogs dropped from the side reference line.
SIDE_LINE_SIMPLIFY_M = 1.0
# Side methods for a wall on each side of the road (both sides protected),
# and all side methods with no single protected side.
BOTH_SIDES_METHODS = ("both_sides", "osm_both_sides", "manual_both_sides")
TWO_SIDED_METHODS = ("unknown", *BOTH_SIDES_METHODS)


@dataclass
class BarrierReferences:
    """Per barrier, keyed by row position 0..n-1 of the barriers it was built
    from. `table` has at least `side_method` (`"unknown"` = side not known,
    one of `BOTH_SIDES_METHODS` = walls on both sides, anything else = one
    known side),
    `barrier_sign` (+1 left / -1 right of `lines[row]`, 0 when not one
    side) and `span_start_m` / `span_end_m` (the barrier's stretch, as
    distances along `lines[row]`); regions add their own columns, e.g.
    `NOISE_REDUCTION_COLUMN`.
    `corridors[row]` holds the `same_route` corridor's network lines: a
    point is `same_route` within `buffer_m` of them (a distance test, ~100x
    faster than buffering the lines into a polygon, agreeing for 99.97% of
    grid cells). All geometry is in `crs`, a metric CRS."""

    table: pd.DataFrame
    corridors: dict[int, object]
    lines: dict[int, LineString]
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M
    crs: object = None


def side_reference_line(row: int, anchor, geoms: np.ndarray, endpoints, sindex, *, budget_m: float):
    """`(own_line, own_rows, line)` for a barrier registered on network row
    `row`: its through-line without and with ramp-end bridging. `line` (the
    bridged one, simplified to `SIDE_LINE_SIMPLIFY_M` so a tiny, oddly
    angled end segment can't decide what lies "beyond the end") is the side
    reference; a parallel-road search should use `own_line`, since a line
    running on into the mainline would sample its own neighbour."""
    own_line, own_rows = through_line(row, anchor, geoms, endpoints, budget_m=budget_m)
    line, _ = through_line(row, anchor, geoms, endpoints, budget_m=budget_m, sindex=sindex)
    return own_line, own_rows, line.simplify(SIDE_LINE_SIMPLIFY_M)


def corridor_lines(row: int, anchor, geoms: np.ndarray, lengths: np.ndarray, endpoints, covered_rows, *, budget_m: float):
    """The `same_route` corridor's lines: the network grown `budget_m` along
    the road from `row`, plus every row the barrier itself covers."""
    return unary_union([corridor_geometry(row, anchor, geoms, lengths, endpoints, budget_m=budget_m), *geoms[list(covered_rows)]])


def barrier_span(line: LineString, barrier_geom) -> tuple[float, float]:
    """The barrier's stretch along `line`: its own vertices projected on it."""
    along = shapely.line_locate_point(line, shapely.points(shapely.get_coordinates(barrier_geom)[:, :2]))
    return float(along.min()), float(along.max())


def _past_end_m(line: LineString, pts: np.ndarray) -> np.ndarray:
    """Signed along-line distance a point lies past an end of `line`
    (negative past the start, positive past the end, 0 beside it), measured
    along that end's direction. `line_locate_point` clamps such points to
    the end, which would put a cell 500m past a short line "beside" a
    barrier near that end. A closed line (a roundabout) has no ends."""
    if line.is_closed:
        return np.zeros(len(pts))
    coords = shapely.get_coordinates(line)
    xy = shapely.get_coordinates(pts)
    out_start = _unit(coords[0] - coords[1])
    out_end = _unit(coords[-1] - coords[-2])
    past_start = np.maximum((xy - coords[0]) @ out_start, 0.0)
    past_end = np.maximum((xy - coords[-1]) @ out_end, 0.0)
    frac = shapely.line_locate_point(line, pts, normalized=True)
    return np.where(frac <= 0.0, -past_start, np.where(frac >= 1.0, past_end, 0.0))


def _position(line: LineString, row, pts: np.ndarray):
    """`(lateral_m, along_offset_m, same_side, side_unknown)` of `pts`
    against one barrier (`row` of the reference table, `line` its
    through-line). `same_side` is False and `side_unknown` True beyond an
    end of the line, where the side is undefined, and for a barrier whose
    side is unknown."""
    along = shapely.line_locate_point(line, pts) + _past_end_m(line, pts)
    lateral = shapely.distance(line, pts)
    along_offset = np.maximum.reduce([np.zeros(len(pts)), row["span_start_m"] - along, along - row["span_end_m"]])
    if row["side_method"] == "unknown":
        return lateral, along_offset, np.zeros(len(pts), dtype=bool), np.ones(len(pts), dtype=bool)
    # _past_end_m keeps these at/after the ends; a closed line has none.
    beyond_end = ((along <= 0.0) | (along >= line.length)) & (not line.is_closed)
    if row["side_method"] in BOTH_SIDES_METHODS:
        return lateral, along_offset, ~beyond_end, beyond_end
    signs, _ = signed_side(line, pts)
    return lateral, along_offset, (signs == row["barrier_sign"]) & ~beyond_end, beyond_end


def classify_points(
    points,
    barrier_rows: np.ndarray,
    refs: BarrierReferences,
    *,
    span_margin_m: float = PROTECTED_SPAN_MARGIN_M,
    max_lateral_m: float = PROTECTED_MAX_LATERAL_M,
    control_max_lateral_m: float | None = None,
) -> pd.DataFrame:
    """One row per point (in `refs.crs`), judged against the barrier at the
    same position in `barrier_rows`: `same_route` (inside that barrier's
    corridor), and for `same_route` points `side_method`, `same_side` (on
    the barrier's side of its road) and `same_side_unknown` -- `same_side`
    is then False, not a guess. A point is `same_side_unknown` either when
    the barrier has no side method, or when the point lies beyond an end of
    the barrier's through-line: it isn't beside the barrier's road there
    (only reached through the corridor's side streets or buffer), so
    "which side" is undefined for it.

    **The protected area.** `same_side` holds anywhere in the corridor
    (~800m along the road), but a wall only shields what lies beside it.
    So each `same_route` point also gets `lateral_m` (distance from the
    through-line) and `along_offset_m` (how far past the barrier's own
    stretch it lies along the through-line, 0 when beside it); NaN
    elsewhere. `protected` is `same_side` within `span_margin_m` of the
    stretch and `max_lateral_m` of the road; `protected_unknown` is such a
    point whose side is unknown. A point further along is known not to be
    protected, whatever its side. :func:`protection_zones` draws the same
    area as polygons.

    **The control band** (only when `control_max_lateral_m` is given; the
    output is otherwise unchanged): `control_band` is a point on the
    barrier's side, within `span_margin_m` of its stretch, and more than
    `max_lateral_m` but at most `control_max_lateral_m` from its road;
    `control_band_unknown` the same where the side is unknown. These
    points are mostly outside the `same_route` corridor, so they are
    measured against the through-line alone, and `side_method`,
    `lateral_m` and `along_offset_m` are then also filled for every point
    within `control_max_lateral_m` of it. :func:`control_band_zones` draws
    the band."""
    if control_max_lateral_m is not None and control_max_lateral_m <= max_lateral_m:
        raise ValueError(f"control_max_lateral_m ({control_max_lateral_m}) must exceed max_lateral_m ({max_lateral_m})")
    pts = np.asarray(points)
    barrier_rows = np.asarray(barrier_rows)
    n = len(pts)
    same_route = np.zeros(n, dtype=bool)
    same_side = np.zeros(n, dtype=bool)
    unknown = np.zeros(n, dtype=bool)
    method = np.full(n, None, dtype=object)
    lateral = np.full(n, np.nan)
    along_offset = np.full(n, np.nan)
    band = np.zeros(n, dtype=bool)
    band_unknown = np.zeros(n, dtype=bool)
    for br in np.unique(barrier_rows):
        candidates = np.flatnonzero(barrier_rows == br)
        row = refs.table.iloc[int(br)]
        line = refs.lines[int(br)]
        idx = candidates[shapely.dwithin(refs.corridors[int(br)], pts[candidates], refs.buffer_m)]
        if len(idx):
            same_route[idx] = True
            method[idx] = row["side_method"]
            lateral[idx], along_offset[idx], same_side[idx], unknown[idx] = _position(line, row, pts[idx])
        if control_max_lateral_m is None:
            continue
        far = candidates[shapely.dwithin(line, pts[candidates], control_max_lateral_m)]
        if not len(far):
            continue
        lat, off, side, side_unknown = _position(line, row, pts[far])
        ring = (off <= span_margin_m) & (lat > max_lateral_m) & (lat <= control_max_lateral_m)
        band[far] = side & ring
        band_unknown[far] = side_unknown & ring
        method[far] = row["side_method"]
        lateral[far], along_offset[far] = lat, off
    beside = (along_offset <= span_margin_m) & (lateral <= max_lateral_m)  # False where NaN
    out = pd.DataFrame(
        {
            "same_route": same_route,
            "side_method": method,
            "same_side": same_side,
            "same_side_unknown": unknown,
            "lateral_m": lateral,
            "along_offset_m": along_offset,
            "protected": same_side & beside,
            "protected_unknown": unknown & beside,
        }
    )
    if control_max_lateral_m is not None:
        out["control_band"] = band
        out["control_band_unknown"] = band_unknown
    return out


def _half_plane(origin: np.ndarray, outward: np.ndarray, width: float):
    """A square, large enough to cover a zone `width` wide, covering the side
    of the line through `origin` perpendicular to `outward` that `outward`
    points into."""
    u = _unit(outward)
    n = np.array([-u[1], u[0]])
    big = 4 * width
    return shapely.Polygon([origin + n * big, origin + n * big + u * big, origin - n * big + u * big, origin - n * big])


# Sample nudge for the fallback in `_voronoi_cells`.
VORONOI_NUDGE_M = 0.001


def _voronoi_cells(points: np.ndarray, extent) -> np.ndarray:
    """The Voronoi cell of each of `points`, in their order. GEOS returns
    wrong, overlapping cells for long runs of exactly collinear samples (a
    straight segment in synthetic geometry; no real reference line in either
    region, checked 2026-09-30). When any cell misses its own sample, the
    samples are nudged by up to `VORONOI_NUDGE_M` and the cells recomputed."""
    cells = shapely.get_parts(shapely.voronoi_polygons(shapely.multipoints(points), extend_to=extent, ordered=True))
    if len(cells) == len(points) and shapely.covers(cells, points).all():
        return cells
    nudge = np.random.default_rng(0).uniform(-VORONOI_NUDGE_M, VORONOI_NUDGE_M, (len(points), 2))
    nudged = shapely.points(shapely.get_coordinates(points) + nudge)
    cells = shapely.get_parts(shapely.voronoi_polygons(shapely.multipoints(nudged), extend_to=extent, ordered=True))
    if len(cells) != len(points) or not shapely.covers(cells, nudged).all():
        raise RuntimeError("Voronoi cells don't match their samples, even after nudging them")
    return cells


def _zone_polygon(
    line: LineString,
    start: float,
    end: float,
    sign: float,
    width: float,
    step: float,
    *,
    inner: float | None = None,
):
    """The points whose nearest point on `line` lies in `[start, end]`
    (distances along it), at most `width` (and, given `inner`, more than
    `inner`) from it, and -- unless `sign` is 0 -- on that side of it.
    Nearest-point regions come from a Voronoi split of `line` densified
    every `step` m, so zone edges are exact to about `step` / 2."""
    # Samples just outside the stretch's ends pin the region's end edges to
    # the exact normals there (otherwise Voronoi cells fan out on the outside
    # of a bend).
    ends = np.clip([start - 0.05, end + 0.05], 0.0, line.length)
    along = np.unique(np.concatenate([np.arange(0.0, line.length, step), [line.length, start, end], ends]))
    points = shapely.line_interpolate_point(line, along)
    # A line can pass the same spot twice (Voronoi needs distinct points).
    _, first = np.unique(np.round(shapely.get_coordinates(points), 3), axis=0, return_index=True)
    keep = np.sort(first)
    along, points = along[keep], points[keep]
    extent = shapely.box(*line.buffer(width + step).bounds)
    cells = _voronoi_cells(points, extent)
    # Beyond an end of the line the side is undefined (`classify_points`:
    # beyond_end): those points are the end sample's Voronoi cell past the
    # end segment's normal. Only that cell is cut -- a half-plane cut of the
    # whole zone would also remove area beside a stretch that curves round.
    if not line.is_closed:
        coords = shapely.get_coordinates(line)
        if start <= 0.0:
            cells[0] = cells[0].difference(_half_plane(coords[0], coords[0] - coords[1], width))
        if end >= line.length:
            cells[-1] = cells[-1].difference(_half_plane(coords[-1], coords[-1] - coords[-2], width))
    region = shapely.union_all(cells[(along >= start) & (along <= end)])
    stretch = substring(line, start, end)
    zone = region.intersection(stretch.buffer(width))
    if sign != 0 and not zone.is_empty:
        # Split along the road and keep the barrier's side.
        cutter = substring(line, max(start - 2 * step, 0.0), min(end + 2 * step, line.length)).buffer(0.01)
        pieces = [p for p in shapely.get_parts(zone.difference(cutter)) if p.area > 0]
        signs, _ = signed_side(line, [p.representative_point() for p in pieces])
        zone = shapely.union_all([p for p, side in zip(pieces, signs) if side == sign])
    # Only now cut out the inner ring: a ring no longer touches the road, so
    # its two sides can join round a line end and the split above would fail.
    return zone if inner is None else zone.difference(stretch.buffer(inner))


def _zones(refs: BarrierReferences, status: str, *, span_margin_m: float, width: float, step_m: float, **kwargs):
    """One polygon per barrier (see `_zone_polygon`), `zone_status` `status`
    or "side_unknown" (both sides) for a barrier whose side is unknown."""
    records = []
    for br, row in refs.table.iterrows():
        line = refs.lines[int(br)]
        start = max(row["span_start_m"] - span_margin_m, 0.0)
        end = min(row["span_end_m"] + span_margin_m, line.length)
        if end - start <= 0:
            continue
        sign = 0.0 if row["side_method"] in TWO_SIDED_METHODS else row["barrier_sign"]
        zone = _zone_polygon(line, start, end, sign, width, step_m, **kwargs)
        if zone.is_empty:
            continue
        records.append(
            {
                "barrier_row": int(br),
                "side_method": row["side_method"],
                "zone_status": "side_unknown" if row["side_method"] == "unknown" else status,
                "geometry": zone,
            }
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=refs.crs)


def protection_zones(
    refs: BarrierReferences,
    *,
    span_margin_m: float = PROTECTED_SPAN_MARGIN_M,
    max_lateral_m: float = PROTECTED_MAX_LATERAL_M,
    step_m: float = ZONE_STEP_M,
) -> gpd.GeoDataFrame:
    """One polygon per barrier: the area :func:`classify_points` calls
    `protected` (`zone_status="protected"`), or `protected_unknown` for a
    barrier whose side is unknown (`zone_status="side_unknown"`, both
    sides). That is every point on the barrier's side, within
    `max_lateral_m` of its road, whose nearest point on the road lies within
    the barrier's stretch +-`span_margin_m`; both sides for `TWO_SIDED_METHODS`.

    Not a plain buffer of the stretch: a point in front of a wall but
    nearer another, unshielded part of the same road (inside a bend, or
    where the road turns back) gets that part's noise and isn't protected.
    The point test is authoritative; zone edges match it to about
    `step_m` / 2, so consumers that need exact membership should query
    zones with that tolerance and decide with `classify_points`."""
    return _zones(refs, "protected", span_margin_m=span_margin_m, width=max_lateral_m, step_m=step_m)


def control_band_zones(
    refs: BarrierReferences,
    *,
    span_margin_m: float = PROTECTED_SPAN_MARGIN_M,
    max_lateral_m: float = PROTECTED_MAX_LATERAL_M,
    control_max_lateral_m: float = CONTROL_MAX_LATERAL_M,
    step_m: float = ZONE_STEP_M,
) -> gpd.GeoDataFrame:
    """One polygon per barrier: the area :func:`classify_points` calls
    `control_band` (`zone_status="control_band"`) or `control_band_unknown`
    (`zone_status="side_unknown"`, both sides) -- the protected area's
    rule, but between `max_lateral_m` and `control_max_lateral_m` from the
    road. It starts where :func:`protection_zones` ends, so the two never
    overlap for one barrier; another barrier's zones can overlap it."""
    if control_max_lateral_m <= max_lateral_m:
        raise ValueError(f"control_max_lateral_m ({control_max_lateral_m}) must exceed max_lateral_m ({max_lateral_m})")
    return _zones(
        refs,
        "control_band",
        span_margin_m=span_margin_m,
        width=control_max_lateral_m,
        step_m=step_m,
        inner=max_lateral_m,
    )
