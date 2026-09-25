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

M. `manual` / `manual_both_sides` -- a reviewer aligned the barrier with the
   wall in Lantmäteriet aerial imagery (the `barrier_audit` source,
   `docs/data/sweden/barrier_audit/README.md`). `manual`: the aligned
   point's side of the through-line, the same test `osm_offset` applies to
   an OSM wall. `manual_both_sides`: the reviewer saw walls on both sides.
0. `both_sides` (road only) -- the barrier overlaps another one on the same
   road link, by at least half its length, with opposite `side` labels:
   a wall on each side of the road, so both sides are protected. All 58
   such road pairs are left + right; where OSM maps walls around them it
   shows both sides for 7 of 12, vs 3 of 33 for single barriers.
1. `osm_offset` -- an OpenStreetMap wall running beside the barrier (not
   past its ends), nearer the barrier's own road or track than any parallel
   one (a double track's walls are registered one per track): its offset
   from the road gives the side directly. `osm_both_sides`: such walls on
   both sides. (2026-09-24: before the "beside, not past its ends" and
   rail "nearer its own track" rules, 73 of 293 matches were a wall off
   the barrier's end and two twin records often claimed the same wall.)
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
5. `bis_sibling` (rail only) -- a stub record, its geometry under 1m
   although its kilometre posts often span hundreds of metres, takes the
   side of the other records of its BIS object (`bis_object_number`) within
   50m, if they all agree. 63 rail records are such stubs (2026-09-25):
   the pilot showed one as an invisible line, and 40 share their object
   with longer records that carry the wall's geometry.
6. `unknown` -- none of the above. Never counted as the protected side.

Rail also records `outer_track_sign`: where parallel tracks run on one side
only, the side away from them (the wall of an outer track stands outside).
Not a side method yet: it agrees 22/26 with OSM walls where no twin record
lies on the other track; the audit validates it (2026-09-24).

Side is always a sign against ONE reference line per barrier -- its
through-line (`src/core/barrier_geometry/linear_ref.through_line`), which follows the barrier's own
road across junctions -- so every point is judged against the same line the
barrier's own sign came from.

The result is a `src/core/barrier_geometry/protection.BarrierReferences`;
that module's `classify_points` / `protection_zones` turn it into the
protected-area model, the same code Florida uses.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from src.core.barrier_geometry.linear_ref import (
    DEFAULT_CORRIDOR_BUDGET_M,
    DEFAULT_CORRIDOR_BUFFER_M,
    build_adjacency,
    local_tangent,
    nearest_segment,
    parallel_neighbor,
    parallel_neighbors_by_side,
    signed_side,
    through_line,
)
from src.core.barrier_geometry.protection import (
    BarrierReferences,
    barrier_span,
    corridor_lines,
    side_reference_line,
)
from src.regions.sweden.sources._layout import METRIC_CRS

SIDE_METHODS = (
    "manual", "manual_both_sides", "both_sides", "osm_both_sides", "osm_offset", "geometric_offset", "track_offset",
    "parallel_road", "bis_sibling", "unknown",
)
OSM_MATCH_M = 40.0
OSM_MIN_OVERLAP_M = 30.0
OSM_MIN_COS = 0.8
OSM_MIN_OFFSET_M = 2.0
GEOMETRIC_OFFSET_MIN_M = 1.0
OSM_WALL_PRIORITY = {"noise_barrier": 0, "untyped_wall": 1}
BOTH_SIDES_MIN_OVERLAP = 0.5
TRACK_OFFSET_MIN_M = 1.0
OSM_RECORDED_OFFSET_TOLERANCE_M = 3.0
STUB_MAX_M = 1.0
BIS_SIBLING_MAX_M = 50.0
BIS_SIBLING_PROBE_M = 5.0
# `manual` input: one row per barrier key, `decision` "side" (with the
# aligned wall point `aligned_x`/`aligned_y` in METRIC_CRS) or "both_sides".
MANUAL_KEY = ["element_id", "start_measure", "end_measure"]
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
    barrier_geom, anchor, line, neighbour_lines, osm_walls, osm_sindex, recorded_offset_m=None
) -> tuple[float, int] | None:
    """Sign and `osm_id` of the best OSM wall alongside this barrier, sign
    0.0 when qualifying walls stand on both sides, or None.
    The wall must run beside the barrier (not past its ends) for >=
    `OSM_MIN_OVERLAP_M` (half the barrier, if that is shorter), run parallel, sit >= `OSM_MIN_OFFSET_M` off the
    road, -- where other roads or tracks run alongside -- be nearer this
    barrier's line than any of them (a divided road or a double track often
    has a wall on each side, each registered on its own line), and -- where
    the barrier's distance from its track is recorded -- lie at that
    distance."""
    zone = barrier_geom.buffer(OSM_MATCH_M, cap_style="flat")
    min_overlap = min(OSM_MIN_OVERLAP_M, 0.5 * barrier_geom.length)
    tangent = local_tangent(line, anchor)
    best: dict[float, tuple] = {}
    for i in osm_sindex.query(zone, predicate="intersects"):
        part = _longest_part(osm_walls.geometry.iat[i].intersection(zone))
        if part is None or part.length < min_overlap:
            continue
        mid = part.interpolate(0.5, normalized=True)
        if abs(float(local_tangent(part, mid) @ tangent)) < OSM_MIN_COS:
            continue
        sign, offset = signed_side(line, [mid])
        if offset[0] < OSM_MIN_OFFSET_M or sign[0] == 0:
            continue
        if recorded_offset_m is not None and abs(offset[0] - recorded_offset_m) > OSM_RECORDED_OFFSET_TOLERANCE_M:
            continue
        if any(mid.distance(other) <= mid.distance(line) for other in neighbour_lines):
            continue
        rank = (OSM_WALL_PRIORITY[osm_walls["wall_type"].iat[i]], -part.length)
        side = float(sign[0])
        if side not in best or rank < best[side][0]:
            best[side] = (rank, int(osm_walls["osm_id"].iat[i]))
    if not best:
        return None
    side, (_, osm_id) = min(best.items(), key=lambda item: item[1][0])
    return (0.0 if len(best) == 2 else side), osm_id


def _manual_by_row(barriers_m: gpd.GeoDataFrame, manual: pd.DataFrame | None) -> dict[int, tuple]:
    """Barrier row -> (decision, aligned point) for the rows `manual` covers."""
    if manual is None or not len(manual):
        return {}
    joined = barriers_m[MANUAL_KEY].reset_index(names="row").merge(manual, on=MANUAL_KEY)
    return {
        int(r.row): (r.decision, Point(r.aligned_x, r.aligned_y) if r.decision == "side" else None)
        for r in joined.itertuples()
    }


def _manual_sign(entry: tuple | None, line) -> float | None:
    """0.0 for walls on both sides, +-1 for the aligned point's side of
    `line`, None when there is no usable answer (or the point lies on the
    line)."""
    if entry is None:
        return None
    decision, point = entry
    if decision == "both_sides":
        return 0.0
    sign = float(signed_side(line, [point])[0][0])
    return sign if sign != 0 else None


def is_stub(barriers_m: gpd.GeoDataFrame) -> np.ndarray:
    """Records whose geometry is under `STUB_MAX_M`: nothing to see or
    match, whatever their kilometre posts say."""
    return barriers_m.geometry.length.to_numpy() < STUB_MAX_M


def bis_sibling_signs(barriers_m: gpd.GeoDataFrame, table: pd.DataFrame, lines: dict) -> dict[int, float]:
    """Stub row -> the side its BIS object's other records agree on. Each
    decided record within `BIS_SIBLING_MAX_M` of the stub puts a probe
    `BIS_SIBLING_PROBE_M` out on its side of its own through-line, beside
    the stub; the probe's side of the stub's through-line is that record's
    vote. A record with walls on both sides votes 0, which blocks the
    inheritance, as does any disagreement."""
    if "bis_object_number" not in barriers_m.columns:
        return {}
    bis = barriers_m["bis_object_number"].to_numpy()
    stub = is_stub(barriers_m)
    decided = (table["side_method"] != "unknown").to_numpy()
    signs = table["barrier_sign"].to_numpy()
    out = {}
    for row in np.flatnonzero(stub & ~decided & pd.notna(bis)):
        anchor = barriers_m.geometry.iat[row].interpolate(0.5, normalized=True)
        votes = set()
        for sib in np.flatnonzero((bis == bis[row]) & ~stub & decided):
            if barriers_m.geometry.iat[sib].distance(anchor) > BIS_SIBLING_MAX_M:
                continue
            if signs[sib] == 0:
                votes.add(0.0)
                continue
            line = lines[sib]
            near = line.interpolate(line.project(anchor))
            t = local_tangent(line, anchor)
            probe = Point(near.x - t[1] * signs[sib] * BIS_SIBLING_PROBE_M, near.y + t[0] * signs[sib] * BIS_SIBLING_PROBE_M)
            votes.add(float(signed_side(lines[row], [probe])[0][0]))
        if len(votes) == 1 and 0.0 not in votes:
            out[int(row)] = votes.pop()
    return out


def build_barrier_references(
    barriers_gdf: gpd.GeoDataFrame,
    network_gdf: gpd.GeoDataFrame,
    *,
    kind: str,
    osm_walls: gpd.GeoDataFrame | None,
    route_column: str | None = None,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
    manual: pd.DataFrame | None = None,
) -> BarrierReferences:
    """`kind` ("road"/"rail") picks the side methods that apply. `both_sides`
    and `parallel_road` are road only: rail's overlapping barriers are
    neither co-located nor labelled left + right, and a second track only
    says which side a wall is on together with its recorded distance
    (`track_offset`). See `docs/data/sweden/barrier_matching.md` §7.
    `manual` holds the audit's usable answers for this kind (see
    `MANUAL_KEY`); they take priority over every automatic method."""
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
    manual_by_row = _manual_by_row(barriers_m, manual)

    records, corridors, lines = [], {}, {}
    for br, barrier_geom in enumerate(barriers_m.geometry):
        row = int(primary.iat[br])
        anchor = barrier_geom.interpolate(0.5, normalized=True)
        own_line, own_rows, line = side_reference_line(row, anchor, geoms, endpoints, network_sindex, budget_m=budget_m)
        lines[br] = line
        corridors[br] = corridor_lines(row, anchor, geoms, lengths, endpoints, covered[br], budget_m=budget_m)

        # Road: the nearest parallel road. Rail: the nearest parallel track on
        # each side -- one side only makes this an outer track.
        has_recorded = recorded[br] >= TRACK_OFFSET_MIN_M
        if kind == "road":
            nearest = parallel_neighbor(anchor, own_line, own_rows, geoms, network_sindex, endpoints)
            neighbours = [] if nearest is None else [nearest]
        else:
            neighbours = list(parallel_neighbors_by_side(anchor, own_line, own_rows, geoms, network_sindex, endpoints).values())
        neighbour_signs, neighbour_lines = [], []
        for neighbour in neighbours:
            near = geoms[neighbour].interpolate(geoms[neighbour].project(anchor))
            neighbour_signs.append(float(signed_side(line, [near])[0][0]))
            neighbour_lines.append(through_line(neighbour, near, geoms, endpoints, budget_m=budget_m)[0])
        neighbour_sign = neighbour_signs[0] if neighbour_signs else None
        outer_track_sign = -neighbour_signs[0] if kind == "rail" and len(neighbour_signs) == 1 else np.nan

        osm = None
        if osm_walls is not None:
            osm = _osm_side(
                barrier_geom, anchor, line, neighbour_lines, osm_walls, osm_sindex,
                recorded_offset_m=recorded[br] if has_recorded else None,
            )
        anchor_sign, anchor_offset = signed_side(line, [anchor])
        osm_id = pd.NA
        manual_sign = _manual_sign(manual_by_row.get(br), line)
        if manual_sign is not None:
            method, sign = ("manual_both_sides", 0.0) if manual_sign == 0 else ("manual", manual_sign)
        elif br in both_sides:
            method, sign = "both_sides", 0.0
        elif osm is not None:
            method, sign, osm_id = ("osm_both_sides" if osm[0] == 0 else "osm_offset"), osm[0], osm[1]
        elif anchor_offset[0] >= GEOMETRIC_OFFSET_MIN_M and anchor_sign[0] != 0:
            method, sign = "geometric_offset", float(anchor_sign[0])
        elif neighbour_sign and kind == "rail" and has_recorded:
            method, sign = "track_offset", -neighbour_sign
        elif neighbour_sign and kind == "road":
            method, sign = "parallel_road", -neighbour_sign
        else:
            method, sign = "unknown", 0.0
        span_start, span_end = barrier_span(line, barrier_geom)
        record = {
            "primary_row": row,
            "side_method": method,
            "barrier_sign": sign,
            "osm_id": osm_id,
            "outer_track_sign": outer_track_sign,
            "span_start_m": span_start,
            "span_end_m": span_end,
        }
        if route_column is not None:
            record["route"] = network_m[route_column].iat[row]
        records.append(record)

    table = pd.DataFrame(records)
    if kind == "rail":
        for row, sign in bis_sibling_signs(barriers_m, table, lines).items():
            table.loc[row, ["side_method", "barrier_sign"]] = ["bis_sibling", sign]
    table["osm_id"] = table["osm_id"].astype("Int64")
    return BarrierReferences(table=table, corridors=corridors, lines=lines, buffer_m=buffer_m, crs=METRIC_CRS)
