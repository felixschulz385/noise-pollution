# `barrier_protection`

For every road and rail noise barrier in Sweden, this stage records:
- which road or track stretch it covers
- which side of that road it stands on, and how that side was decided
- the area it protects

It is computed once and saved. `schools`, `grid` and any other analysis
load it rather than re-deriving it from the 2M-row road network. The method
and its validation are in [`../barrier_matching.md`](../barrier_matching.md).

**Status (2026-09-24): implemented and run on the real layers.** One build
covers all of Sweden in about 4.5 minutes: road 205s, mostly loading the 2M-row
network and drawing the zones; rail 57s. The whole downstream regeneration
(schools, panel, grid) then takes about 1 minute.

## Command

```
python -m src.cli sweden data barrier-protection build [--kind road|rail] [--budget-m 800] [--buffer-m 600]
```

Requires:
- `noise-barriers preprocess` (road and rail)
- `road-network preprocess`
- `network preprocess-tracks`
- `osm-walls preprocess`

Re-run it whenever any of those inputs change. `schools
assemble-*-network`, `panel recover-vanished-schools` and `grid assemble`
read its output. They refuse a reference file that no longer lines up with
the current barrier layer.

## Outputs (`data/sweden/barrier_protection/processed/`)

### `protection_zones.parquet`: the national protection layer

One polygon per barrier (EPSG:3006), both kinds. The polygon covers every
point within 600m of the barrier's road whose **nearest point on that
road** lies within the barrier's stretch ±50m:
- **on its protected side**, when the side is known
- **on both sides**, for `both_sides` barriers and for barriers whose side
  is unknown

Near a bend, a point in front of a wall can be nearer another, unshielded
part of the same road, which it then hears unshielded. So on curving roads
and at interchanges the areas are wedges or fans, not rectangles. This is
the same definition `classify_points` applies to points (`protected` /
`protected_unknown`).

**Checked against the point test** for every 100m grid cell within 700m of
a barrier:
- **protected pairs:** road 22,384 and rail 9,387 cell–barrier pairs, none
  more than 5m outside their zone
- **the reverse:** 1 in 34k (road) and 1 in 42k (rail) points deep inside a
  zone aren't flagged
- **side-unknown pairs:** 0.6% (road) and 0.2% (rail) lie up to 51m outside.
  These are points just past an end of the road line, where the side is
  undefined; zones leave them out.

| column | meaning |
|---|---|
| `kind` | `road` / `rail` |
| `barrier_row` | row position in `load_noise_barriers(kind)`; the key into the reference file |
| `element_id`, `start_measure`, `end_measure` | the barrier's NVDB link and position along it |
| `side_method` | `both_sides` / `osm_offset` / `geometric_offset` / `track_offset` / `parallel_road` / `unknown` |
| `zone_status` | `protected`; or `side_unknown` (the barrier protects one of the two sides, but which is not known, so it must not count as protected) |
| `built_year` | the barrier's construction year (often missing) |
| `osm_id` | the OpenStreetMap wall that decided the side, for `osm_offset` |

Use it for any unit of analysis:

```python
from src.regions.sweden.sources.barrier_protection.shared import load_protection_zones
zones = load_protection_zones()                  # or kind="road"
hits = units.to_crs(3006).sjoin(zones, predicate="within")
```

A point inside several zones is protected by several barriers. Keep the
`side_unknown` rows apart from the `protected` ones. For per-point
distances (`lateral_m`, `along_offset_m`), use the reference file.

### `barrier_references_{road,rail}.parquet`: the per-barrier reference

One row per barrier, keyed by `barrier_row`:
- the key columns
- `primary_row` (the network row the barrier is registered on)
- `side_method`, `barrier_sign` and `osm_id`
- `span_start_m` / `span_end_m`: the barrier's stretch along its
  through-line
- `route` (rail `bandel`)
- two geometries: the through-line (`geometry`, the side reference) and
  the `same_route` corridor lines (`corridor`)

`load_barrier_references(kind, barriers_gdf=...)` returns the
`BarrierReferences` object that `_barrier_reference.classify_points` takes.
It gives any points `same_route`, `same_side`, `same_side_unknown`,
`lateral_m`, `along_offset_m`, `protected` and `protected_unknown`.

## Real run (2026-09-24)

| | road | rail |
|---|---|---|
| barriers | 2,172 | 1,829 |
| `both_sides` | 112 | — |
| `osm_offset` | 192 | 98 |
| `geometric_offset` | 1 | 6 |
| `track_offset` | — | 630 |
| `parallel_road` | 1,232 | — |
| `unknown` | 635 | 1,095 |
| protected area (dissolved) | 172.1 km² | 59.2 km² |
| side-unknown area (dissolved) | 119.2 km² | 223.1 km² |
| 100m grid cells protected (any barrier) | 17,152 | 5,880 |
| … of which not by their nearest barrier | 2,875 | 1,366 |

## Why a separate stage

Before 2026-09-24, `schools`, `panel recover-vanished-schools` and `grid`
each rebuilt every barrier's reference themselves. Road was rebuilt three
times per full run, and so was rail. Each build buffered every barrier's
800m network corridor by 600m to make its `same_route` polygon, which was
95% of the time (~0.4s per barrier). A full regeneration took about 4
hours.

The corridor is now kept as lines, and `same_route` is a distance test
against them (`shapely.dwithin`). That is about 100× faster and agrees with
the polygon for 99.97% of grid cells (tested on 60 barriers and 34k cells;
the rest lie on the buffer's polygonal arc). A full regeneration now takes
about 7 minutes, notebook included.
