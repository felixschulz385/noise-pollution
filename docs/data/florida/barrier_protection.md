# Florida barrier protection: Sweden's approach, transferred (implemented 2026-09-24)

Sweden now models **the area each noise barrier protects**:
- **the zone:** one polygon per barrier, covering every point on the
  barrier's side of its road, within 600m of the road, whose nearest point
  on the road lies beside the barrier's own stretch (±50m)
- **the build:** computed once by a `barrier-protection build` stage
- **the uses:** schools, the grid, or any other unit via a spatial join

The method and its validation are in
[`../sweden/barrier_matching.md`](../sweden/barrier_matching.md) and
[`../sweden/barrier_protection/README.md`](../sweden/barrier_protection/README.md).
This document explains how the approach was brought to Florida, what
carried over unchanged, and what Florida's data changed. It started as a
plan; the Status section records what was built and the real run. Every
number was measured on 2026-09-24 against the current Florida outputs
(`noise_barriers` `jul26` release, `rciroads`, `schools_treatment.parquet`).

## Status (2026-09-24): implemented and run

**Code:**
- **Shared geometry:** `src/core/barrier_geometry/linear_ref.py` (line
  primitives, formerly Sweden's `_linear_ref.py`) and
  `src/core/barrier_geometry/protection.py` (`BarrierReferences`,
  `classify_points`, `protection_zones`). The CRS travels on the references
  object.
- **Florida:** `src/regions/florida/sources/barrier_protection/`:
  - `reference.py`: reference-road choice, side, trimming
  - `shared.py`: references keyed by `gcid`, the zones layer, the
    stale-file check
  - `build.py`: `florida data barrier-protection build`
- **Consumers:** `schools/assemble.py::match_barriers_road` classifies
  every (school, wall) pair against the saved references. The pair columns
  `school_side`/`wall_side` are gone; `side_method`, `same_side`,
  `same_side_unknown`, `lateral_m`, `along_offset_m`, `protected` and
  `protected_unknown` replace them. The rollup gains
  `{first_treat_year,ever_treated,timing_unknown}_protected`, and the panel
  carries the `_protected` tier plus both unknown flags.
- **CLI:** the corridor options moved from `schools assemble` to
  `barrier-protection build` (`--budget-m`, `--buffer-m`).
- **Loaders:** `load_barriers` and `load_road_network` now live in their
  sources' `shared.py`, replacing three identical copies.

**Decisions:**
- **Margin and reach** stay at Sweden's values: 50m along the stretch,
  600m from the road.
- **Both analysis notebooks** now use the `protected` tier.

**Real run:**

| | result |
|---|---|
| build time (all 1,263 walls) | 39-46s |
| `side_method` | `geometric_offset` 1,262, `bloc_side` 1, `unknown` 0 |
| `side_check` vs `BLOC_SIDE` | agrees 1,190, disagrees 16, undecided (label along the road) 53, no label 4 |
| reference road runs parallel to the wall | 96.4% |
| protected area (dissolved) | 367.9 km² |
| zones vs point test (436k points within 700m of a wall, 50m grid) | 0 protected pairs outside their zone; 0 points deep inside a zone not protected |
| schools `ever_treated` point / same_route / same_side / protected | 578 / 348 / 260 / **128** |
| panel treated schools point / same_route / same_side / protected | 513 / 303 / 228 / **116** (before: 513 / 293 / 221 / —) |
| schools with a `protected_unknown` wall | 0 |

- **`same_route` and `same_side` moved slightly**:
  - `same_route` grew, because the corridor now reaches the budget past
    each end of the wall, not only past its midpoint.
  - `same_side` is now a true side test against one line.
- **`same_side_unknown` (48 schools)** marks schools past the end of a
  wall's reference line, where the side is undefined. No wall has an
  unknown side.

Outputs from before the switch are kept in
`data/florida/_backup_pre_protection_2026-09-24/`.

## Summary

- **Florida's data is better suited than Sweden's.** Trafikverket draws
  barriers on the road centreline, so Sweden had to infer the side from OSM
  walls, parallel roads and track distances. FDOT draws each wall where it
  stands: a median 32m from the arterial centreline, and only 0.3% within
  1m of it. The side can be read directly off the geometry, and it agrees
  with FDOT's own `BLOC_SIDE` label for **98.3%** of walls.
- **Florida's `same_side` before this change had the two flaws Sweden's
  had** (see "Florida before this change"). It compares signs taken against different road
  segments, and it counts "same side" anywhere in an ~800m corridor, not
  beside the wall.
- **The geometry code carries over unchanged**: through-line, point
  classification, protection zones. The Sweden-specific parts don't come
  along: the link-key join, and the OSM, track-distance and
  parallel-road side inference. Florida instead needs a spatial choice of
  each wall's reference road.

## Florida before this change

`schools/assemble.py::match_barriers_road` (algorithms 3-5) works as
follows:
- It grows a corridor from each wall's nearest arterial segment (800m along
  the network, buffered 600m). A pair is `same_route` when the school falls
  inside it.
- `wall_side` and `school_side` are signed offsets, each taken against the
  point's **own** nearest arterial segment. `same_side` is
  `school_side == wall_side`.

Measured on the 1,282 `same_route` pairs:

| check | result |
|---|---|
| school and wall nearest the **same** arterial segment | 32.5% (same `roadway_id`: 44.6%) |
| `same_side` pairs beside the wall's own stretch | 26% |
| … more than 100m / 300m past the wall's end | 60% / 36% |
| median wall length | 297m |

- **Mismatched segments.** A sign is only meaningful against one line,
  since RCI digitizing direction is arbitrary per roadway. The Florida
  schools README warns about exactly this. For two-thirds of pairs the two
  signs come from different segments, so `same_side` there is not a side
  test.
- **Not beside the wall.** Most "same side" schools are along the road,
  past the wall. Florida walls are longer than Sweden's (297m vs ~70m
  median), so the effect is smaller than Sweden's 8%-beside, but still
  large.

## Data: Sweden vs Florida

| | Sweden | Florida |
|---|---|---|
| barrier geometry | on the road centreline (99.8% road, 99.7% rail) | where the wall stands: median 32m off the arterial centreline, 0.3% within 1m |
| barrier's own side label | `side`: no signal (73.7% vs a 72.3% baseline) | `BLOC_SIDE` (compass E/W/N/S, 1,260 of 1,263 walls): agrees with geometry 98.3% where road orientation and compass axis match (n=1,120); 87.7% overall, the rest on diagonal roads |
| barrier → road key | exact (`element_id` + measures) | none in `jul26` (FGDL dropped `BEGIN_POST`); `fed_route` is a route label RCI doesn't carry, so the match is spatial |
| road network | NVDB, 2M rows, all roads, carriageways as separate lines | RCI `rciroads`, 17,171 arterial rows used for matching |
| divided roads | separate carriageway lines → `parallel_road` rule | 377 of 1,256 walls have another arterial within 120m on the far side of their road (a second carriageway or a frontage road); not needed for the side, since the wall's own offset decides |
| walls on both sides | one registered pair, identical geometry → `both_sides` rule | each wall has its own geometry → no special rule; the two zones cover both sides |
| rail | yes (1,829 barriers) | none (FDOT road walls only) |
| grid output | yes (100m cells) | none yet |

## What carries over unchanged

These parts of `src/regions/sweden/sources/_linear_ref.py` and
`_barrier_reference.py` are pure geometry and need no Florida-specific
logic:

- **`through_line`**: the reference line following the wall's road across
  junctions, including the no-reversal and ramp-end-bridging rules. The
  same endpoint adjacency applies; `road_network/linear_ref.py::build_adjacency`
  already builds it for Florida.
  - **Long rows:** RCI arterial rows are much longer than NVDB's: median
    852m, 99th percentile 13km, longest 57km. `through_line` adds whole
    rows, so a Florida through-line can run for kilometres. That's harmless
    for the side, but trim it to the budget around the wall before drawing
    zones: the Voronoi step densifies the whole line every 5m.
  - **Mid-row junctions:** where RCI doesn't split a row at a junction,
    ramp-end bridging covers the case.
- **`corridor_geometry` plus the distance-tested corridor**, for
  `same_route`. Florida's current corridor also buffers into a polygon;
  switching to the `dwithin` test on lines gives the same answer about 100×
  faster.
- **`classify_points`**: `same_route`, `same_side`, `same_side_unknown`,
  `lateral_m`, `along_offset_m`, `protected`, `protected_unknown`.
- **`protection_zones`**: the polygons exact to the point test, built from
  a Voronoi split of the densified road line, with the end cuts, closed-ring
  handling and 1m line simplification.
- **The stretch**: the wall's own geometry projected onto its through-line
  (`span_start_m`/`span_end_m`). Same code.
- **The `barrier_protection` stage pattern**: build once, save references
  plus zones, and let consumers refuse a stale file.

**One generalization is needed.** `METRIC_CRS = "EPSG:3006"` is hard-coded
in `_linear_ref.py`, while Florida works in EPSG:3087. Move the
region-agnostic parts into a shared module (e.g. `src/core/barrier_geometry.py`)
that takes the CRS as a parameter. Sweden's `_barrier_reference.py` then
keeps only its Sweden-specific side inference, and Florida gets its own
thin equivalent.

## What Florida needs instead

### 1. Choosing each wall's reference road (replaces the key join)

Take the nearest arterial row to the wall that runs **parallel** to it:
- within 100m
- local tangents |cos| ≥ 0.8 at the nearest point, as for OSM walls in
  Sweden

Then build its through-line from there. Taking simply the nearest row
risks picking a cross street at a junction, or a frontage road. Walls whose
nearest row isn't parallel are the ones to inspect.

Cross-checks:
- The **road's orientation should match `BLOC_SIDE`'s compass axis**
  (E/W label ⇒ north-south road). Flag walls where it doesn't.
- **`fed_route`** names the route the wall belongs to. RCI has no route
  field, but a crosswalk from `roadway_id` to route (FDOT's roadway
  inventory) could turn this into a key join later. Not needed for a first
  version.

### 2. The side: `geometric_offset` first, `BLOC_SIDE` as check and fallback

| `side_method` | rule | expected coverage |
|---|---|---|
| `geometric_offset` | the wall's own offset from its reference through-line, ≥2m | ~99.7% of walls |
| `bloc_side` | the wall's compass label converted to a sign against the through-line's local direction, where the geometric offset is <2m or ambiguous | the few walls drawn on the road |
| `unknown` | neither | expected near 0 |

- **Keep a `side_check` column**: `agrees` / `disagrees` / `diagonal`, from
  comparing the two. The 136 disagreements measured are almost all diagonal
  roads, where a compass label is ambiguous. A `disagrees` on a clearly
  north-south or east-west road is worth a look.
- **Median walls:** `BLOC_ONRTE` has no median-mounted value in `jul26`, so
  no rule is needed yet. If one appears, treat it like Sweden's
  `both_sides`.
- **`other_wall`** (private and perimeter walls, 18 rows) gets zones too,
  flagged by `category`. They stay a shielding covariate and never become
  treatment, as today.

### 3. A Florida `barrier-protection build` stage

`florida data barrier-protection build` writes
`data/florida/barrier_protection/processed/`:
- `barrier_references.parquet`: keyed by `gcid`, not row position, since
  Florida has a stable wall id
- `protection_zones.parquet`: EPSG:3087, one polygon per wall, with `gcid`,
  `category`, `side_method`, `zone_status`, `built_year`, `is_programmed`

It depends on `noise-barriers preprocess` and `road-network preprocess`.
There's no OSM step.

### 4. Consumers

- **`schools assemble`:** replace `match_barriers_road`'s side logic with
  `classify_points` on the saved references.
  - Every wall within 1km of a school is already paired, so "protected by
    any wall" follows directly.
  - Add the pair columns `lateral_m`, `along_offset_m`, `protected` and
    `protected_unknown`.
  - Add the rollup tier `{first_treat_year,ever_treated,timing_unknown}_protected`.
  - Drop `school_side` / `wall_side`, which only make sense against one
    shared line.
- **`panel assemble`:** carry `_protected` alongside
  `_point`/`_same_route`/`_same_side`, as in Sweden's panel.
- **Any other unit** (census blocks, property sales, a future grid):
  spatially join `protection_zones.parquet`.

## Validation plan

1. **Side:** the `geometric_offset` sign against `BLOC_SIDE`, per wall,
   reported as agreement on clearly north-south / east-west roads (target:
   the measured 98.3%) plus a list of disagreements.
2. **Reference road:** the share of walls whose nearest arterial runs
   parallel to them, and the walls where it doesn't.
3. **Zones vs point test:** the same national check as Sweden. Every
   `protected` point must lie inside its zone (Sweden: 0 misses).
4. **Before/after:** schools' `same_side` under the old and new side test,
   split into flips vs newly unknown, as Sweden's review did. Also, how many
   schools stay under `protected`.
5. **Case plots:** a notebook section like Sweden's `grid.ipynb` §6.
   Include a divided highway, a wall next to a frontage road, and a wall
   beside a curving interchange ramp.

## Choices (decided 2026-09-24)

- **Margin and reach:** Sweden's values kept (50m along the stretch, 600m
  from the road), so results are comparable across regions.
- **Analysis tier:** `protected`, in both regions' analysis notebooks.

## Effort

1. Generalize the geometry module (CRS parameter), with Sweden's tests
   still passing: small.
2. Florida reference-road choice, side methods and build stage, with
   synthetic tests like `test_barrier_reference.py`: moderate.
3. Wire into `schools assemble` and `panel assemble`, then re-run: small.
   Florida's arterial network is ~17k rows against Sweden's 2M, so the
   build should take well under a minute.
4. Validation notebook and doc update: moderate.
