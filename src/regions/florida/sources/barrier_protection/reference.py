"""Barrier references for Florida: which arterial road each FDOT noise wall
belongs to, which side of it the wall stands on, and the stretch it covers
-- the region-specific half of the protected-area model; the other half
(`classify_points`, `protection_zones`) is
`src/core/barrier_geometry/protection.py`, shared with Sweden. Plan and
measurements: `docs/data/florida/barrier_protection.md`.

**Which road.** `jul26` walls carry no roadway key, so each wall's
reference road is the nearest arterial row (`road_network/linear_ref.py::
arterial_subset`) within `REFERENCE_SEARCH_M` that runs **parallel** to the
wall (local tangents |cos| >= `REFERENCE_MIN_COS`): simply taking the
nearest row could pick a cross street at a junction. A wall with no
parallel row falls back to the nearest one (`reference_parallel=False`).

**Which side.** Unlike Trafikverket, FDOT draws each wall where it stands
(median 32m off the arterial centreline, 0.3% within 1m), so the side is
read off the geometry:

1. `geometric_offset` -- the wall's midpoint sits >= `GEOMETRIC_OFFSET_MIN_M`
   off its reference line: its sign is the side.
2. `bloc_side` -- otherwise, FDOT's compass `BLOC_SIDE` label, turned into
   a sign against the reference line's local direction -- unless the label
   points along the road (NORTH on a north-south road), which says nothing
   about the side.
3. `unknown` -- neither.

`side_check` compares the two wherever both exist: `agrees`, `disagrees`,
or `undecided` when the label points along the road. 98.3% agree where road
orientation and compass axis match (measured 2026-09-24).

**Line length.** RCI rows are long (median 852m, up to 57km) and a
through-line adds whole rows, so each reference line is trimmed to
`LINE_TRIM_M` beyond the wall's ends -- far beyond anything the protected
area (600m reach, 50m margin) depends on, and it keeps the zone drawing's
5m densification small.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.ops import substring

from src.core.barrier_geometry.linear_ref import (
    DEFAULT_CORRIDOR_BUDGET_M,
    DEFAULT_CORRIDOR_BUFFER_M,
    build_adjacency,
    local_tangent,
    signed_side,
)
from src.core.barrier_geometry.protection import (
    BarrierReferences,
    barrier_span,
    corridor_lines,
    side_reference_line,
)
from src.regions.florida.sources._layout import METRIC_CRS
from src.regions.florida.sources.road_network.linear_ref import arterial_subset

SIDE_METHODS = ("geometric_offset", "bloc_side", "unknown")
REFERENCE_SEARCH_M = 100.0
REFERENCE_MIN_COS = 0.8
GEOMETRIC_OFFSET_MIN_M = 2.0
LINE_TRIM_M = 1500.0
# A compass label only decides the side when it points across the road
# (|cos| between the label direction and the road's normal).
COMPASS_MIN_COS = 0.5
COMPASS = {"EAST": (1.0, 0.0), "WEST": (-1.0, 0.0), "NORTH": (0.0, 1.0), "SOUTH": (0.0, -1.0)}


def reference_row(wall, anchor, roads_m: gpd.GeoDataFrame) -> tuple[int, bool]:
    """`(row, parallel)`: the nearest arterial row that runs parallel to
    `wall` within `REFERENCE_SEARCH_M`, or, failing that, the nearest row at
    all (`parallel=False`)."""
    geoms = roads_m.geometry.values
    wall_tangent = local_tangent(wall, anchor)
    candidates = roads_m.sindex.query(wall, predicate="dwithin", distance=REFERENCE_SEARCH_M)
    parallel = []
    for i in candidates:
        near = geoms[i].interpolate(geoms[i].project(anchor))
        if abs(float(local_tangent(geoms[i], near) @ wall_tangent)) >= REFERENCE_MIN_COS:
            parallel.append((geoms[i].distance(anchor), int(i)))
    if parallel:
        return min(parallel)[1], True
    return int(roads_m.sindex.nearest(anchor, return_all=False)[1][0]), False


def compass_sign(label, line, anchor) -> float:
    """`BLOC_SIDE` as +1 (left) / -1 (right) of `line`, or 0 when the label
    is missing or points along the road."""
    direction = COMPASS.get(str(label).strip().upper()) if label is not None else None
    if direction is None:
        return 0.0
    tangent = local_tangent(line, anchor)
    normal = np.array([-tangent[1], tangent[0]])  # left of the line
    cos = float(np.dot(normal, direction))
    return float(np.sign(cos)) if abs(cos) >= COMPASS_MIN_COS else 0.0


def _trim(line, start: float, end: float):
    """`line` cut to `LINE_TRIM_M` beyond `[start, end]`, and the stretch's
    position on the cut line."""
    lo, hi = max(start - LINE_TRIM_M, 0.0), min(end + LINE_TRIM_M, line.length)
    if lo <= 0.0 and hi >= line.length:
        return line, start, end
    return substring(line, lo, hi), start - lo, end - lo


def build_barrier_references(
    barriers_gdf: gpd.GeoDataFrame,
    road_network_gdf: gpd.GeoDataFrame,
    *,
    budget_m: float = DEFAULT_CORRIDOR_BUDGET_M,
    buffer_m: float = DEFAULT_CORRIDOR_BUFFER_M,
) -> BarrierReferences:
    """References for every wall in `barriers_gdf` (row position = key),
    against the arterial subset of `road_network_gdf`. The table adds
    `gcid`, `roadway_id`, `reference_parallel`, `side_check` and
    `offset_m` (the wall midpoint's distance from its reference line) to
    the shared columns."""
    roads_m = arterial_subset(road_network_gdf).to_crs(METRIC_CRS).reset_index(drop=True)
    roads_m["geometry"] = shapely.force_2d(roads_m.geometry.values)
    geoms = roads_m.geometry.to_numpy()
    lengths = roads_m.geometry.length.to_numpy()
    endpoints = build_adjacency(roads_m)
    sindex = roads_m.sindex
    walls_m = barriers_gdf.to_crs(METRIC_CRS).reset_index(drop=True)
    walls = shapely.force_2d(walls_m.geometry.values)
    labels = walls_m["bloc_side"].to_numpy() if "bloc_side" in walls_m.columns else np.full(len(walls_m), None)

    records, corridors, lines = [], {}, {}
    for br, wall in enumerate(walls):
        anchor = wall.interpolate(0.5, normalized=True)
        row, parallel = reference_row(wall, anchor, roads_m)
        _, _, line = side_reference_line(row, anchor, geoms, endpoints, sindex, budget_m=budget_m)
        start, end = barrier_span(line, wall)
        line, start, end = _trim(line, start, end)
        lines[br] = line
        # Grown from the wall's midpoint, `budget_m` past each of its ends.
        # Unlike Sweden, whole covered rows aren't added: RCI rows run up
        # to 57km and would swamp the budget.
        corridors[br] = corridor_lines(row, anchor, geoms, lengths, endpoints, [], budget_m=budget_m + wall.length / 2)

        sign, offset = signed_side(line, [anchor])
        geometric = float(sign[0]) if offset[0] >= GEOMETRIC_OFFSET_MIN_M else 0.0
        compass = compass_sign(labels[br], line, anchor)
        if geometric:
            method, barrier_sign = "geometric_offset", geometric
        elif compass:
            method, barrier_sign = "bloc_side", compass
        else:
            method, barrier_sign = "unknown", 0.0
        if geometric and compass:
            check = "agrees" if geometric == compass else "disagrees"
        elif geometric and labels[br] is not None and str(labels[br]).strip():
            check = "undecided"
        else:
            check = pd.NA
        records.append(
            {
                "gcid": walls_m["gcid"].iat[br],
                "primary_row": row,
                "roadway_id": roads_m["roadway_id"].iat[row],
                "reference_parallel": parallel,
                "side_method": method,
                "barrier_sign": barrier_sign,
                "side_check": check,
                "offset_m": float(offset[0]),
                "span_start_m": start,
                "span_end_m": end,
            }
        )
    return BarrierReferences(
        table=pd.DataFrame(records), corridors=corridors, lines=lines, buffer_m=buffer_m, crs=METRIC_CRS
    )
