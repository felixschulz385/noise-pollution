# `barrier_protection`

For every road and rail noise barrier in Sweden, this stage records:
- which road or track stretch it covers
- which side of that road it stands on, and how that side was decided
- the area it protects

It is computed once and saved. `schools`, `grid` and any other analysis
load it rather than re-deriving it from the 2M-row road network. The method
and its validation are in [`../barrier_matching.md`](../barrier_matching.md).
Sweden's side inference is `src/regions/sweden/sources/_barrier_reference.py`.
The protected-area model (`classify_points`, `protection_zones`) is the
region-agnostic `src/core/barrier_geometry/protection.py`, shared with
Florida.

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

Re-run it whenever any of those inputs change. `schools assemble` and
`grid assemble` read its output (until 2026-10-20 also `panel
recover-vanished-schools`, since removed). They refuse a reference file that no longer lines up with
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
| `side_method` | `manual` / `manual_both_sides` / `both_sides` / `osm_both_sides` / `osm_offset` / `geometric_offset` / `track_offset` / `parallel_road` / `bis_sibling` / `unknown` |
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
- `audit_decision` (2026-10-20): the audit's decision on the barrier, NA
  if it was never audited. `side` and `both_sides` set `side_method` to
  `manual` / `manual_both_sides`. `not_visible` (the reviewer saw no wall),
  `unsure`, `centre` and `conflict` leave the automatic side standing, so
  only this column marks them. Records that share a key with a co-located
  record share its decision. (Rail's `outer_track_sign` and
  `outer_track_spacing_m` were removed the same day, with the rule:
  [`../barrier_matching.md`](../barrier_matching.md) §7.6.)
- `chain_id`, `chain_orient`: pieces of one physical wall that the register
  splits (`_barrier_reference.register_chains`, 2026-09-25; rules revised
  2026-09-29: each end joins its best continuation -- within 2 m, 5 m in
  line or 25 m within one rail BIS object, turning < 30° -- ranked by the
  `side` label, and never two co-located records in one chain; road 1,581 →
  1,438 walls, rail 1,177 → 902). The audit asks one task per chain;
  nothing else uses them yet
- two geometries: the through-line (`geometry`, the side reference) and
  the `same_route` corridor lines (`corridor`)

`load_barrier_references(kind, barriers_gdf=...)` returns the
`BarrierReferences` object that `core/barrier_geometry/protection.classify_points` takes.
It gives any points `same_route`, `same_side`, `same_side_unknown`,
`lateral_m`, `along_offset_m`, `protected` and `protected_unknown`.

## Real run (2026-09-25, rebuilt after §7.6)

With the §7.6 matching fixes and all 35 pilot answers
([`../barrier_matching.md`](../barrier_matching.md) §7.6); the
2026-09-24 run in brackets where it differs.

| | road | rail |
|---|---|---|
| barriers | 2,172 | 1,829 |
| `manual` | 7 (0) | 9 (0) |
| `both_sides` | 112 | — |
| `osm_both_sides` | 2 (0) | 0 |
| `osm_offset` | 172 (194) | 77 (99) |
| `geometric_offset` | 1 | 6 |
| `track_offset` | — | 629 |
| `parallel_road` | 1,240 (1,230) | — |
| `unknown` | 638 (635) | 1,108 (1,095) |
| protected area (dissolved) | 171.8 km² (172.1) | 60.5 km² (59.2) |
| side-unknown area (dissolved) | 119.6 km² (119.2) | 225.1 km² (223.1) |
| 100m grid cells protected (any barrier) | 17,117 (17,152) | 6,015 (5,880) |
| … of which not by their nearest barrier | 2,884 (2,875) | 1,339 (1,366) |

**Rebuild of 2026-09-25, afternoon.** It adds the 24 pilot answers given
that day and the new rail method `bis_sibling`, which lets a record under
1 m take its side from its BIS object's other records
([`../barrier_audit/README.md`](../barrier_audit/README.md), "Stub
records"). Changed rows, previous value in brackets:

| | road | rail |
|---|---|---|
| `manual` | 14 (7) | 20 (9) |
| `osm_offset` | 169 (172) | 76 (77) |
| `track_offset` | — | 624 (629) |
| `parallel_road` | 1,236 (1,240) | — |
| `bis_sibling` | — | 2 (—) |
| `unknown` | 638 | 1,101 (1,108) |
| protected area (dissolved) | 171.9 km² (171.8) | 61.1 km² (60.5) |
| side-unknown area (dissolved) | 119.6 km² | 224.5 km² (225.1) |
| 100m grid cells protected (any barrier) | 17,122 (17,117) | 6,072 (6,015) |

Panel schools: rail `same_side` 67 (64), rail side-unknown 206 (208);
`protected` unchanged (road 37, rail 25).

## Control band (2026-09-30)

The build also saves **`control_band_zones.parquet`** (loader:
`shared.load_control_band_zones(kind=...)`). It holds one polygon per
barrier: the protected area's rule one ring further out. That is on the
barrier's side, with its nearest road point beside the stretch ±50m, and
600-1500m from the road (`CONTROL_MAX_LATERAL_M`, `--control-max-lateral-m`).
- **Purpose:** the comparison area of a within-barrier design, as in
  Moretti & Wheeler (2025), who compare homes 0-500m and 500-1500m behind
  the same wall.
- **Columns:** those of `protection_zones.parquet`, with `zone_status`
  `control_band` / `side_unknown`.
- **Point test:** `classify_points(..., control_max_lateral_m=1500)` adds
  `control_band` / `control_band_unknown`. Without the argument, its
  output is unchanged.
- **Explained with figures:**
  [`shared_methodology.ipynb`](../../../src/experiments/shared_methodology.ipynb) §2.

| | road | rail |
|---|---|---|
| band zones | 2,089 | 1,814 |
| band area (dissolved) | 265.6 km² | 90.5 km² |
| side-unknown band area | 210.6 km² | 341.1 km² |
| band area inside a protected zone of the same kind | 0.4% | 0.0% |
| barriers without a band | 83 | 15 |

- **Barriers without a band** sit where nothing beside their stretch lies
  beyond 600m: inside tight bends, or at a line end.
- **Existing outputs unchanged:** the references and `protection_zones.parquet`
  are identical to the 2026-09-25 build, column by column.
- **Registers:** Sweden's have no noise-reduction field (Florida:
  `noise_reduction_db`), so the references gain no column.
- **Voronoi fallback:** the zone code checks its Voronoi cells and nudges
  the samples by up to 1mm when GEOS returns wrong cells. That happens for
  long runs of exactly collinear samples; no real line triggers it.

## Known gaps in the register (2026-10-20)

**Construction years: being worked on.** Trafikverket records no
`built_year` for 1,114 of 2,172 road records (51%; 813 of 1,438 walls) and
487 of 1,829 rail records (27%; 281 of 902 walls). Everything downstream
treats an undated protecting barrier as unknown timing, never as a year:
- schools: `timing_unknown`; the 2026-10-20 `protected` analysis drops 59
  treated schools for it
- grid: `{kind}_timing_unknown`, 8,228 of 19,196 treated road cells and
  3,670 of 15,338 rail cells
Another source of construction dates is being looked for.

**Barriers outside the register: ignored for now.** Only Trafikverket's
registers are used. OSM maps at least 350 noise barriers (about 50 km) more
than 100 m from any register barrier, e.g. along municipal streets
(measured 2026-09-29). They are not in the protected areas or the audit, so
a unit behind one of them can sit among the controls.

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
