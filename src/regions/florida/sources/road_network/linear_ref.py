"""Reusable road-network geometry helpers: nearest-segment matching, linear
referencing (milepost + signed side-of-centerline), and a network-distance-
bounded "corridor" test.

These are the building blocks for the ``schools`` source's matching
algorithms 3-5 (``road_gated`` / ``same_segment`` / ``same_side``, see
``docs/data/florida/schools/README.md``'s rigour ladder) — validated against
the real fetched data in ``src/experiments/florida/schools.ipynb`` §7 before
being promoted here. See ``docs/data/florida/road_network/README.md``'s Open
Question 7 for the full design writeup, including two bugs found building
the corridor flood-fill (both about the same failure mode: assuming
``rciroads``' segmentation is regular enough for a count/length proxy to
stand in for true distance, when some segments run 30-57 km unbroken).

Callers pass in ``road_network.parquet`` (already EPSG:3087, already
``MultiLineString``-flattened by ``road_network/preprocess.py``) — this
module does no geometry cleanup of its own.
"""
from __future__ import annotations

from collections import deque

import geopandas as gpd
import numpy as np
from shapely.ops import substring, unary_union

# Candidate network for the matching algorithms: state-highway-class roads
# only. Noise walls are an FDOT facility register (state highways/tollways),
# so the ~19k local/collector segments in the full network only add noise —
# nearest-matching a school against them can "steal" the match away from the
# state highway a wall actually sits on (confirmed in schools.ipynb §7.3).
_ARTERIAL_CONTAINS = "Arterial"
_MINOR_COLLECTOR_FED_AID = "URBAN: Minor Collector (Fed Aid)"

# Defaults validated in schools.ipynb §7.4: 99.1% recovery of the point-only
# algorithm 1/2 baseline (ever_near_wall_500m) at these settings.
DEFAULT_CORRIDOR_BUDGET_M = 800.0
DEFAULT_CORRIDOR_BUFFER_M = 600.0


def arterial_subset(road_network: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The state-highway-class candidate network, reset-indexed — downstream
    code positionally indexes into it via ``sjoin_nearest``'s
    ``index_right``, which only aligns with a fresh 0..n-1 index."""
    mask = (
        road_network["funclass"].str.contains(_ARTERIAL_CONTAINS)
        | road_network["funclass"].eq(_MINOR_COLLECTOR_FED_AID)
    )
    return road_network[mask].reset_index(drop=True)


def nearest_road(points: gpd.GeoDataFrame, roads: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per input point: its nearest ``roads`` segment + distance.
    ``sjoin_nearest`` only returns the LEFT geometry column — the matched
    road's own geometry is pulled back explicitly via ``index_right`` (easy
    to silently get wrong: the point's own geometry, not the road's)."""
    joined = gpd.sjoin_nearest(points[["geometry"]], roads, distance_col="dist_m", how="left")
    joined = joined[~joined.index.duplicated(keep="first")]
    joined = joined.rename(columns={"geometry": "point_geometry"})
    joined["road_geometry"] = roads.geometry.loc[joined["index_right"]].to_numpy()
    return joined


def milepost_and_side(point, line, begin_post: float, end_post: float) -> tuple[float, float, float]:
    """Project ``point`` onto ``line``: ``(milepost, signed_side, offset_m)``.

    ``side`` is the sign of the cross product between the centerline's local
    tangent and the offset vector — it is **not** a compass direction
    (``rciroads``' digitizing direction is arbitrary per ``ROADWAY``,
    confirmed empirically: an 87/13 aggregate split among matched walls, not
    ~50/50). Valid **only pairwise**, comparing two points matched to the
    SAME line.
    """
    frac = line.project(point, normalized=True)
    milepost = begin_post + frac * (end_post - begin_post)
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
    return milepost, side, offset_m


def _endpoint_key(pt, precision: int = 0) -> tuple[float, float]:
    return (round(pt[0], precision), round(pt[1], precision))


def build_adjacency(roads: gpd.GeoDataFrame) -> dict[tuple[float, float], list[int]]:
    """Endpoint-adjacency graph: maps a rounded ``(x, y)`` junction (1 m
    grid, to absorb float noise) to the row-positions of every ``roads``
    segment whose ``LineString`` starts or ends there. ``roads`` must be
    positionally indexed 0..n-1 (see :func:`arterial_subset`)."""
    endpoints: dict[tuple[float, float], list[int]] = {}
    for i, geom in enumerate(roads.geometry):
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
    """Network-distance-bounded flood fill from ``origin_point`` (projected
    onto ``geoms[seg_idx]``), walking the connectivity graph ``endpoints``
    (from :func:`build_adjacency`) outward in both directions and consuming
    *true path distance* — deliberately not a segment-count or
    total-length-per-hop proxy, which silently breaks on ``rciroads``'
    occasional 30-57 km unsegmented stretches (confirmed in
    ``schools.ipynb`` §7.4: a per-hop-layer budget check let one corridor
    reach 10.5 km on a 3.2 km budget).

    The seed segment is trimmed (``shapely.ops.substring``) to the portion
    within ``budget_m`` of ``origin_point`` — skipping this let a wall whose
    nearest segment *was* one of those long unsegmented stretches produce a
    24 km corridor. A neighbor segment is included whole only if it fits
    within the remaining budget from its entry junction (a deliberately
    simple approximation: no partial sub-segments for hop-expanded
    neighbors, only for the seed).

    ``geoms``/``lengths`` are the candidate network's geometry/length arrays
    (e.g. ``roads.geometry.to_numpy()`` / ``roads.geometry.length.to_numpy()``)
    — passed in rather than a GeoDataFrame so repeated calls (one per wall)
    don't pay pandas indexing overhead.

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
            if nb_len <= remaining:
                included.add(nb)
                pieces.append(geoms[nb])
                nb_coords = list(geoms[nb].coords)
                nb_start, nb_end = _endpoint_key(nb_coords[0]), _endpoint_key(nb_coords[-1])
                other_end = nb_end if nb_start == junction else nb_start
                new_remaining = remaining - nb_len
                if new_remaining > 0:
                    q.append((other_end, new_remaining))
    return unary_union(pieces)
