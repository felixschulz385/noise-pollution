"""Barrier references: for each noise barrier, the road/track stretch it covers,
its `same_route` corridor, and which side of that road it stands on -- plus
the method that decided the side. The single implementation behind both
`schools/assemble.py` and `grid/side.py`; see
`docs/data/sweden/barrier_matching.md` for the review that motivated it and
the validation numbers quoted below.

**Which stretch.** A barrier's `element_id` is the NVDB reference link it is
registered on and `start_measure`/`end_measure` its position along it; the
network carries the same keys, so the rows a barrier covers come from an
exact key join, not a nearest-distance guess. The row with the largest
overlap is the barrier's primary row. The rare barrier with no overlapping
row (1 road, 6 rail) falls back to the nearest row.

**Which side.** Trafikverket barrier geometry sits on the centreline for
road AND rail, and its `side` attribute carries no signal, so the side is
taken from the first of these that applies:

0. `both_sides` (road only) -- the barrier overlaps another one on the same
   road link, by at least half its length, with opposite `side` labels:
   a wall on each side of the road, so both sides are protected. All 58
   such road pairs are left + right; where OSM maps walls around them it
   shows both sides for 7 of 12, vs 3 of 33 for single barriers.
1. `osm_offset` -- an OpenStreetMap wall running alongside the barrier, on
   the barrier's own road's side (not the neighbouring road's): its offset
   from the road gives the side directly.
2. `geometric_offset` -- the barrier's own geometry genuinely sits off its
   road (>= 1m): rare, ~0.3% of barriers.
3. `track_offset` (rail only) -- the barrier's recorded
   `distance_from_track_center_m` is >= 1m and another track runs
   alongside: the wall stands on the side away from it (registered on its
   nearest track). Agrees 27/28 with OSM walls found at the recorded
   distance. Where that distance is known, an OSM wall only counts for
   `osm_offset` if it lies at it (+-3m): otherwise it agrees only 50%, so
   it is probably a different wall.
4. `parallel_road` (road only) -- another road runs alongside (a divided
   road's other carriageway, the mainline beside a ramp): the wall stands
   on the side away from it. Agrees with OSM wall positions 93% (tagged,
   n=102) / 100% (untyped, n=37).
5. `unknown` -- none of the above. Never counted as the protected side.

Side is always a sign against ONE reference line per barrier -- its
through-line (`_linear_ref.through_line`), which follows the barrier's own
road across junctions -- so every point is judged against the same line the
barrier's own sign came from. A manual override (`side_method="manual"`,
from the planned audit app) will slot in ahead of `osm_offset`.
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString
from shapely.ops import substring, unary_union

from src.regions.sweden.sources._linear_ref import (
    DEFAULT_CORRIDOR_BUDGET_M,
    DEFAULT_CORRIDOR_BUFFER_M,
    METRIC_CRS,
    _unit,
    build_adjacency,
    corridor_geometry,
    local_tangent,
    nearest_segment,
    parallel_neighbor,
    signed_side,
    through_line,
)

SIDE_METHODS = ("both_sides", "osm_offset", "geometric_offset", "track_offset", "parallel_road", "unknown")
OSM_MATCH_M = 40.0
OSM_MIN_OVERLAP_M = 30.0
OSM_MIN_COS = 0.8
OSM_MIN_OFFSET_M = 2.0
GEOMETRIC_OFFSET_MIN_M = 1.0
OSM_WALL_PRIORITY = {"noise_barrier": 0, "untyped_wall": 1}
BOTH_SIDES_MIN_OVERLAP = 0.5
SIDE_LINE_SIMPLIFY_M = 1.0
TRACK_OFFSET_MIN_M = 1.0
OSM_RECORDED_OFFSET_TOLERANCE_M = 3.0
# Half a grid cell: a 100m cell whose centroid is within 50m of the stretch
# overlaps it. Also absorbs small geometry/measure mismatches.
PROTECTED_SPAN_MARGIN_M = 50.0
# How far from its road a barrier's protected area reaches: the same 600m
# as the `same_route` corridor, so a protected point is always same_route.
PROTECTED_MAX_LATERAL_M = DEFAULT_CORRIDOR_BUFFER_M
# Densification step of the through-line when drawing protection zones.
ZONE_STEP_M = 5.0


@dataclass
class BarrierReferences:
    """`table` is indexed by barrier row position (0..n-1 of the barriers
    passed in): `primary_row`, `side_method`, `barrier_sign` (+1/-1 against
    `lines[row]`, 0 when unknown or both sides), `osm_id`, `span_start_m` /
    `span_end_m` (the barrier's stretch, as distances along `lines[row]`),
    and `route` when requested. `corridors[row]` holds the corridor's
    network lines; a point is `same_route` within `buffer_m` of them. That
    distance test replaces buffering the lines into a polygon, which was
    95% of the build time (~0.4s per barrier) and agrees for 99.97% of grid
    cells (the rest sit on the buffer's polygonal arc)."""

    table: pd.DataFrame
    corridors: dict[int, object]
    lines: dict[int, LineString]
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M


def primary_rows(barriers_m: gpd.GeoDataFrame, network_m: gpd.GeoDataFrame) -> tuple[pd.Series, dict[int, list[int]]]:
    """Per barrier row: its primary network row, and every row it covers,
    from the `element_id` + measure-overlap key join."""
    joined = barriers_m.reset_index(names="barrier_row")[["barrier_row", "element_id", "start_measure", "end_measure"]].merge(
        network_m[["element_id", "start_measure", "end_measure"]]
        .reset_index(names="net_row")
        .rename(columns={"start_measure": "net_start", "end_measure": "net_end"}),
        on="element_id",
    )
    joined["overlap"] = np.minimum(joined["end_measure"], joined["net_end"]) - np.maximum(
        joined["start_measure"], joined["net_start"]
    )
    joined = joined[joined["overlap"] > 0]
    covered = joined.groupby("barrier_row")["net_row"].apply(list).to_dict()
    primary = joined.sort_values("overlap").groupby("barrier_row")["net_row"].last()

    missing = barriers_m.index.difference(primary.index)
    if len(missing):
        midpoints = gpd.GeoDataFrame(
            geometry=barriers_m.geometry.loc[missing].interpolate(0.5, normalized=True), crs=barriers_m.crs
        )
        nearest = nearest_segment(midpoints, network_m)["index_right"]
        primary = pd.concat([primary, nearest.astype(int)])
        covered.update({br: [int(row)] for br, row in nearest.items()})
    return primary.sort_index().astype(int), covered


def both_sides_rows(barriers_m: gpd.GeoDataFrame) -> set[int]:
    """Barrier rows that overlap another barrier on the same link by at
    least `BOTH_SIDES_MIN_OVERLAP` of the shorter one's measure range, with
    opposite `side` labels (left + right)."""
    if "side" not in barriers_m.columns:
        return set()
    keyed = barriers_m.reset_index(names="row")[["row", "element_id", "start_measure", "end_measure", "side"]]
    keyed = keyed[keyed["side"].isin(["left", "right"])]
    pairs = keyed.merge(keyed, on="element_id", suffixes=("_a", "_b"))
    pairs = pairs[(pairs["row_a"] < pairs["row_b"]) & (pairs["side_a"] != pairs["side_b"])]
    overlap = np.minimum(pairs["end_measure_a"], pairs["end_measure_b"]) - np.maximum(
        pairs["start_measure_a"], pairs["start_measure_b"]
    )
    shorter = np.minimum(
        pairs["end_measure_a"] - pairs["start_measure_a"], pairs["end_measure_b"] - pairs["start_measure_b"]
    )
    pairs = pairs[(overlap > 0) & (overlap >= BOTH_SIDES_MIN_OVERLAP * shorter)]
    return set(pairs["row_a"]) | set(pairs["row_b"])


def _longest_part(geom):
    if geom.is_empty:
        return None
    if geom.geom_type == "LineString":
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type == "LineString"]
    return max(parts, key=lambda g: g.length) if parts else None


def _osm_side(
    barrier_geom, anchor, line, neighbour_line, osm_walls, osm_sindex, recorded_offset_m=None
) -> tuple[float, int] | None:
    """Sign and `osm_id` of the best OSM wall alongside this barrier, or None.
    The wall must overlap the barrier for >= `OSM_MIN_OVERLAP_M`, run
    parallel, sit >= `OSM_MIN_OFFSET_M` off the road, -- where another
    road runs alongside -- be nearer this barrier's road than that one (a
    divided road often has walls on both sides), and -- where the barrier's
    distance from its track is recorded -- lie at that distance."""
    zone = barrier_geom.buffer(OSM_MATCH_M)
    tangent = local_tangent(line, anchor)
    best = None
    for i in osm_sindex.query(zone, predicate="intersects"):
        part = _longest_part(osm_walls.geometry.iat[i].intersection(zone))
        if part is None or part.length < OSM_MIN_OVERLAP_M:
            continue
        mid = part.interpolate(0.5, normalized=True)
        if abs(float(local_tangent(part, mid) @ tangent)) < OSM_MIN_COS:
            continue
        sign, offset = signed_side(line, [mid])
        if offset[0] < OSM_MIN_OFFSET_M or sign[0] == 0:
            continue
        if recorded_offset_m is not None and abs(offset[0] - recorded_offset_m) > OSM_RECORDED_OFFSET_TOLERANCE_M:
            continue
        if neighbour_line is not None and mid.distance(neighbour_line) <= mid.distance(line):
            continue
        rank = (OSM_WALL_PRIORITY[osm_walls["wall_type"].iat[i]], -part.length)
        if best is None or rank < best[0]:
            best = (rank, float(sign[0]), int(osm_walls["osm_id"].iat[i]))
    return None if best is None else (best[1], best[2])


def build_barrier_references(
    barriers_gdf: gpd.GeoDataFrame,
    network_gdf: gpd.GeoDataFrame,
    *,
    kind: str,
    osm_walls: gpd.GeoDataFrame | None,
    route_column: str | None = None,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
) -> BarrierReferences:
    """`kind` ("road"/"rail") picks the side methods that apply. `both_sides`
    and `parallel_road` are road only: rail's overlapping barriers are
    neither co-located nor labelled left + right, and a second track only
    says which side a wall is on together with its recorded distance
    (`track_offset`). See `docs/data/sweden/barrier_matching.md` §7."""
    network_m = network_gdf.to_crs(METRIC_CRS).reset_index(drop=True)
    geoms = network_m.geometry.to_numpy()
    lengths = network_m.geometry.length.to_numpy()
    endpoints = build_adjacency(network_m)
    network_sindex = network_m.sindex
    barriers_m = barriers_gdf.to_crs(METRIC_CRS).reset_index(drop=True)
    primary, covered = primary_rows(barriers_m, network_m)
    both_sides = both_sides_rows(barriers_m) if kind == "road" else set()
    recorded = (
        barriers_m["distance_from_track_center_m"].to_numpy(dtype=float)
        if kind == "rail" and "distance_from_track_center_m" in barriers_m.columns
        else np.full(len(barriers_m), np.nan)
    )
    if osm_walls is not None:
        osm_walls = osm_walls.to_crs(METRIC_CRS).reset_index(drop=True)
        osm_sindex = osm_walls.sindex

    records, corridors, lines = [], {}, {}
    for br, barrier_geom in enumerate(barriers_m.geometry):
        row = int(primary.iat[br])
        anchor = barrier_geom.interpolate(0.5, normalized=True)
        # The side reference bridges ramp ends that meet a row mid-way; the
        # parallel-road search keeps the unbridged line it was validated on
        # (a line running on into the mainline would sample its own neighbour).
        own_line, own_rows = through_line(row, anchor, geoms, endpoints, budget_m=budget_m)
        line, _ = through_line(row, anchor, geoms, endpoints, budget_m=budget_m, sindex=network_sindex)
        # Drop sub-metre digitization jogs: a tiny, oddly angled end segment
        # would decide what counts as "beyond the end" of the road.
        line = line.simplify(SIDE_LINE_SIMPLIFY_M)
        lines[br] = line
        corridors[br] = unary_union(
            [corridor_geometry(row, anchor, geoms, lengths, endpoints, budget_m=budget_m), *geoms[covered[br]]]
        )

        # Rail only needs the other track where a recorded distance can use it.
        has_recorded = recorded[br] >= TRACK_OFFSET_MIN_M
        neighbour_sign, neighbour_line = None, None
        if kind == "road" or has_recorded:
            neighbour = parallel_neighbor(anchor, own_line, own_rows, geoms, network_sindex, endpoints)
            if neighbour is not None:
                near = geoms[neighbour].interpolate(geoms[neighbour].project(anchor))
                neighbour_sign = float(signed_side(line, [near])[0][0])
                if kind == "road":
                    neighbour_line, _ = through_line(neighbour, near, geoms, endpoints, budget_m=budget_m)

        osm = None
        if osm_walls is not None:
            osm = _osm_side(
                barrier_geom, anchor, line, neighbour_line, osm_walls, osm_sindex,
                recorded_offset_m=recorded[br] if has_recorded else None,
            )
        anchor_sign, anchor_offset = signed_side(line, [anchor])
        osm_id = pd.NA
        if br in both_sides:
            method, sign = "both_sides", 0.0
        elif osm is not None:
            method, sign, osm_id = "osm_offset", osm[0], osm[1]
        elif anchor_offset[0] >= GEOMETRIC_OFFSET_MIN_M and anchor_sign[0] != 0:
            method, sign = "geometric_offset", float(anchor_sign[0])
        elif neighbour_sign and kind == "rail":
            method, sign = "track_offset", -neighbour_sign
        elif neighbour_sign:
            method, sign = "parallel_road", -neighbour_sign
        else:
            method, sign = "unknown", 0.0
        span = shapely.line_locate_point(line, shapely.points(shapely.get_coordinates(barrier_geom)))
        record = {
            "primary_row": row,
            "side_method": method,
            "barrier_sign": sign,
            "osm_id": osm_id,
            "span_start_m": float(span.min()),
            "span_end_m": float(span.max()),
        }
        if route_column is not None:
            record["route"] = network_m[route_column].iat[row]
        records.append(record)

    table = pd.DataFrame(records)
    table["osm_id"] = table["osm_id"].astype("Int64")
    return BarrierReferences(table=table, corridors=corridors, lines=lines, buffer_m=buffer_m)


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


def classify_points(
    points,
    barrier_rows: np.ndarray,
    refs: BarrierReferences,
    *,
    span_margin_m: float = PROTECTED_SPAN_MARGIN_M,
    max_lateral_m: float = PROTECTED_MAX_LATERAL_M,
) -> pd.DataFrame:
    """One row per point (in `METRIC_CRS`), judged against the barrier at the
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
    area as polygons."""
    pts = np.asarray(points)
    barrier_rows = np.asarray(barrier_rows)
    n = len(pts)
    same_route = np.zeros(n, dtype=bool)
    same_side = np.zeros(n, dtype=bool)
    unknown = np.zeros(n, dtype=bool)
    method = np.full(n, None, dtype=object)
    lateral = np.full(n, np.nan)
    along_offset = np.full(n, np.nan)
    for br in np.unique(barrier_rows):
        idx = np.flatnonzero(barrier_rows == br)
        inside = shapely.dwithin(refs.corridors[int(br)], pts[idx], refs.buffer_m)
        idx = idx[inside]
        if not len(idx):
            continue
        same_route[idx] = True
        row = refs.table.iloc[int(br)]
        method[idx] = row["side_method"]
        line = refs.lines[int(br)]
        along = shapely.line_locate_point(line, pts[idx]) + _past_end_m(line, pts[idx])
        lateral[idx] = shapely.distance(line, pts[idx])
        along_offset[idx] = np.maximum.reduce(
            [np.zeros(len(idx)), row["span_start_m"] - along, along - row["span_end_m"]]
        )
        if row["side_method"] == "unknown":
            unknown[idx] = True
            continue
        # _past_end_m keeps these at/after the ends; a closed line has none.
        beyond_end = ((along <= 0.0) | (along >= line.length)) & (not line.is_closed)
        if row["side_method"] == "both_sides":
            same_side[idx] = ~beyond_end
        else:
            signs, _ = signed_side(line, pts[idx])
            same_side[idx] = (signs == row["barrier_sign"]) & ~beyond_end
        unknown[idx] = beyond_end
    beside = (along_offset <= span_margin_m) & (lateral <= max_lateral_m)  # False where NaN
    return pd.DataFrame(
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


def _half_plane(origin: np.ndarray, outward: np.ndarray, width: float):
    """A square, large enough to cover a zone `width` wide, covering the side
    of the line through `origin` perpendicular to `outward` that `outward`
    points into."""
    u = _unit(outward)
    n = np.array([-u[1], u[0]])
    big = 4 * width
    return shapely.Polygon([origin + n * big, origin + n * big + u * big, origin - n * big + u * big, origin - n * big])


def _zone_polygon(line: LineString, start: float, end: float, sign: float, width: float, step: float):
    """The points whose nearest point on `line` lies in `[start, end]`
    (distances along it), at most `width` from it, and -- unless `sign` is
    0 -- on that side of it. Nearest-point regions come from a Voronoi
    split of `line` densified every `step` m, so zone edges are exact to
    about `step` / 2."""
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
    cells = shapely.get_parts(shapely.voronoi_polygons(shapely.multipoints(points), extend_to=extent, ordered=True))
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
    zone = region.intersection(substring(line, start, end).buffer(width))
    if sign == 0 or zone.is_empty:
        return zone
    # Split along the road and keep the barrier's side.
    cutter = substring(line, max(start - 2 * step, 0.0), min(end + 2 * step, line.length)).buffer(0.01)
    pieces = [p for p in shapely.get_parts(zone.difference(cutter)) if p.area > 0]
    signs, _ = signed_side(line, [p.representative_point() for p in pieces])
    return shapely.union_all([p for p, side in zip(pieces, signs) if side == sign])


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
    the barrier's stretch +-`span_margin_m`; both sides for `both_sides` and
    `unknown`.

    Not a plain buffer of the stretch: a point in front of a wall but
    nearer another, unshielded part of the same road (inside a bend, or
    where the road turns back) gets that part's noise and isn't protected.
    The point test is authoritative; zone edges match it to about
    `step_m` / 2, so consumers that need exact membership should query
    zones with that tolerance and decide with `classify_points`."""
    records = []
    for br, row in refs.table.iterrows():
        line = refs.lines[int(br)]
        start = max(row["span_start_m"] - span_margin_m, 0.0)
        end = min(row["span_end_m"] + span_margin_m, line.length)
        if end - start <= 0:
            continue
        sign = 0.0 if row["side_method"] in ("unknown", "both_sides") else row["barrier_sign"]
        zone = _zone_polygon(line, start, end, sign, max_lateral_m, step_m)
        if zone.is_empty:
            continue
        records.append(
            {
                "barrier_row": int(br),
                "side_method": row["side_method"],
                "zone_status": "side_unknown" if row["side_method"] == "unknown" else "protected",
                "geometry": zone,
            }
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=METRIC_CRS)
