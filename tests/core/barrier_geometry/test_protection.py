"""Tests for `src/core/barrier_geometry/protection.py`'s control band: the
opt-in ring beyond the protected area (same side, beside the stretch,
600-1500m from the road) and its zones. Synthetic geometry in EPSG:3006; the
protected area itself is tested per region (`tests/regions/*/test_barrier_protection.py`)."""
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from src.core.barrier_geometry.linear_ref import signed_side
from src.core.barrier_geometry.protection import (
    ZONE_STEP_M,
    BarrierReferences,
    classify_points,
    control_band_zones,
    protection_zones,
)


def _refs(line: LineString, span: tuple[float, float], *, method: str = "geometric_offset") -> BarrierReferences:
    """One barrier north of `line`, covering `span` (distances along it)."""
    mid = line.interpolate(np.mean(span))
    sign = 0.0 if method in ("unknown", "both_sides") else float(signed_side(line, [Point(mid.x, mid.y + 100)])[0][0])
    table = pd.DataFrame(
        [{"side_method": method, "barrier_sign": sign, "span_start_m": span[0], "span_end_m": span[1]}]
    )
    return BarrierReferences(table=table, corridors={0: line}, lines={0: line}, buffer_m=600.0, crs="EPSG:3006")


def _straight():
    # East-west road, barrier on the north side from x=2000 to x=2300.
    return _refs(LineString([(0, 0), (4000, 0)]), (2000.0, 2300.0))


def _classify(refs, points, **kwargs):
    return classify_points(points, np.zeros(len(points), dtype=int), refs, **kwargs)


def test_without_a_band_the_output_is_unchanged():
    out = _classify(_straight(), [Point(2150, 300), Point(2150, 1000)])
    assert list(out.columns) == [
        "same_route", "side_method", "same_side", "same_side_unknown",
        "lateral_m", "along_offset_m", "protected", "protected_unknown",
    ]
    # Outside the corridor nothing is measured.
    assert np.isnan(out.loc[1, "lateral_m"])


def test_the_band_leaves_every_existing_column_as_it_was_for_corridor_points():
    refs = _straight()
    points = [Point(x, y) for x in (1500, 2150, 2400) for y in (-500, -100, 100, 500)]
    plain = _classify(refs, points)
    banded = _classify(refs, points, control_max_lateral_m=1500.0)
    pd.testing.assert_frame_equal(banded[plain.columns], plain)


def test_the_band_is_same_side_beside_the_stretch_beyond_the_reach():
    refs = _straight()
    points = {
        "protected": Point(2150, 300),
        "band": Point(2150, 1000),
        "band_edge_of_stretch": Point(2340, 1000),  # 40m past the end, within the 50m margin
        "opposite_side": Point(2150, -1000),
        "past_the_stretch": Point(2500, 1000),
        "beyond_the_band": Point(2150, 1600),
    }
    out = _classify(refs, list(points.values()), control_max_lateral_m=1500.0).set_index(pd.Index(points))
    assert out["control_band"].to_dict() == {
        "protected": False, "band": True, "band_edge_of_stretch": True,
        "opposite_side": False, "past_the_stretch": False, "beyond_the_band": False,
    }
    assert out.loc["protected", "protected"] and not out.loc["band", "protected"]
    assert out.loc["band", "lateral_m"] == pytest.approx(1000.0)
    assert out.loc["band", "side_method"] == "geometric_offset"
    assert not out["control_band_unknown"].any()


def test_an_unknown_side_puts_both_sides_in_the_unknown_band():
    refs = _refs(LineString([(0, 0), (4000, 0)]), (2000.0, 2300.0), method="unknown")
    out = _classify(refs, [Point(2150, 1000), Point(2150, -1000)], control_max_lateral_m=1500.0)
    assert out["control_band"].tolist() == [False, False]
    assert out["control_band_unknown"].tolist() == [True, True]


def test_the_band_must_reach_beyond_the_protected_area():
    with pytest.raises(ValueError, match="must exceed"):
        _classify(_straight(), [Point(2150, 1000)], control_max_lateral_m=500.0)
    with pytest.raises(ValueError, match="must exceed"):
        control_band_zones(_straight(), control_max_lateral_m=600.0)


@pytest.mark.parametrize(
    ("line", "span", "has_band"),
    [
        (LineString([(0, 0), (4000, 0)]), (2000.0, 2300.0), True),
        # A bend just past the barrier: the band fans out on the outside of it.
        (LineString([(0, 0), (2400, 0), (4000, -1200)]), (2000.0, 2300.0), True),
        # The barrier spans a bend, outside it: the zones fan out round the corner.
        (LineString([(0, 0), (2700, 0), (4200, -1500)]), (2500.0, 2900.0), True),
        # The barrier spans a bend, inside it: the area beside it closes to a
        # wedge within ~600m, so the band is at most a sliver at its tip. (The
        # diagonal segment's exactly collinear samples make GEOS return wrong
        # Voronoi cells, which once drew a near-full disc here.)
        (LineString([(0, 0), (2700, 0), (4200, 1500)]), (2500.0, 2900.0), False),
    ],
)
def test_zones_match_the_point_test_and_the_band_never_overlaps_the_protected_area(line, span, has_band):
    refs = _refs(line, span)
    xs, ys = np.meshgrid(np.arange(500, 4501, 50.0), np.arange(-1900, 1901, 50.0))
    points = [Point(x, y) for x, y in zip(xs.ravel(), ys.ravel())]
    out = _classify(refs, points, control_max_lateral_m=1500.0)
    protected = protection_zones(refs).geometry.iloc[0]
    band = control_band_zones(refs)
    assert band["zone_status"].tolist() == ["control_band"]
    band_zone = band.geometry.iloc[0]
    assert band_zone.intersection(protected).area < 1.0
    if has_band:
        assert out["control_band"].sum() > 100
    else:
        assert band_zone.area < 100.0
        assert not out["control_band"].any()
    for zone, flag in ((protected, "protected"), (band_zone, "control_band")):
        in_zone = np.array([zone.covers(p) for p in points])
        near_edge = np.array([zone.boundary.distance(p) <= ZONE_STEP_M for p in points])
        assert not ((in_zone != out[flag].to_numpy()) & ~near_edge).any()
