# Barrier ↔ road/track matching: review, consolidation and implementation (2026-09-23)

Covers the code that decides, for each noise barrier, **which road or track
it belongs to, which stretch it covers, and which side of it the barrier
stands on**. At the time of the review that code lived in three places
(`_linear_ref.py`, `schools/assemble.py::match_barriers_network`,
`grid/side.py::match_grid_side`). It now lives in one:
`src/regions/sweden/sources/_barrier_reference.py`, built on the primitives
in `_linear_ref.py`, and used by both schools and grid (see Status).

**Why it matters.** The end goal is to model the *area a barrier protects*:
the land on the far side of the barrier from the traffic, along the stretch
the barrier covers. That area depends on three things:

1. which road or track the barrier belongs to
2. which stretch of it the barrier covers
3. which side of it the barrier stands on

Every number below was measured live on the real layers, not assumed. The
scripts behind each number are reproduced in the notes at the end.

## Summary

| question | status |
|---|---|
| 1. Which road/track | **Solved.** It can be an exact key join instead of a spatial guess. |
| 2. Which stretch | **Partly.** Only one network row per barrier is used; the rest of what it covers is dropped. |
| 3. Which side | **Not recoverable from the barrier data for most barriers, road or rail.** Current `same_side` values are mostly not side tests. |

## Status: implemented (2026-09-23, extended 2026-09-24)

The review below led to a rewrite, now in the pipeline:

- **`_barrier_reference.py`** holds, per barrier: the exact link-key join,
  a corridor that trims long neighbours instead of dropping them, a
  through-line used as the single side reference, and a `side_method`
  (`both_sides` (road) → `osm_offset` → `geometric_offset` →
  `track_offset` (rail) → `parallel_road` (road) → `unknown`; `both_sides`
  and `track_offset` added in §7), plus the protected-area columns (§7.1).
  Its `classify_points` gives every point `same_route` / `same_side` /
  `same_side_unknown` / `lateral_m` / `along_offset_m` / `protected` /
  `protected_unknown`.
- **New `barrier_protection` stage** (`sweden data barrier-protection
  build`, 2026-09-24). It computes every barrier's reference once
  (~4.5 min for all of Sweden, road and rail) and saves it, together with
  a **national protection layer**: one polygon per barrier.
  `schools/assemble.py`, `panel/vanished_recovery.py` and `grid/side.py`
  load the saved references instead of each rebuilding them. See
  [`barrier_protection/README.md`](barrier_protection/README.md).
- **New `osm_walls` source** (`sweden data osm-walls fetch|preprocess`):
  8,169 walls, 561 km.
- **Cleanup items 2-6 (§6) are done.** Wrappers and aliases are deleted, the
  run functions merged, loaders moved to their sources' `shared.py`,
  `METRIC_CRS` defined once, and the 999 sentinel cleaned (the rail
  preprocess re-run changed only that column).
- **Tests.** 255 Sweden tests pass; the new modules have their own.
- **Speed.** A full regeneration (build, schools, panel, grid, grid
  notebook) takes ~7 min, down from ~4 h. Buffering each barrier's corridor
  into a polygon was 95% of the old cost, and road and rail were each
  rebuilt three times per run. `same_route` is now a distance test against
  the corridor lines, which is ~100× faster and agrees for 99.97% of cells.

**Through-line refinements (2026-09-24).** The notebook's case plots showed
three problems with the side reference line, each now fixed and tested:

1. **No reversal.** The line followed a hook, a chain of individually gentle
   turns that ended up heading back the way it came. Every cell projecting
   onto the hook got the opposite sign. It now stops before any segment
   heading against the seed direction.
2. **Beyond the end → unknown.** A cell whose nearest point on the line is
   one of its ends isn't beside the barrier's road. It reaches the corridor
   only through side streets or the buffer, so "which side" has no meaning
   there. Such cells are now `same_side_unknown`, not a sign from the
   end-segment's extrapolation.
3. **Bridging ramp ends.** NVDB often starts a ramp mid-way along the
   mainline row, without a shared node, so the line stopped at the ramp
   end. 356 of 2,172 road barriers (16%) had such an end. The Nacka ramp
   barrier's line was 260m long, and 148 of its 165 corridor cells fell
   under rule 2. The side reference line now continues onto a row passing
   within 2m of such an end, under the same turn and no-reversal rules.
   Barriers with a line under 800m drop from 8.0% to 2.9%, and Nacka's line
   becomes 2,046m. The parallel-road search still uses the unbridged line
   it was validated on: a line that ran on into the mainline would sample
   its own neighbour.

**Real run** (2026-09-24, final: through-line refinements, §7.1-7.3 and
the `barrier_protection` stage):

| | before the rewrite | `same_side` now | `protected` now (new tier, §7.1) |
|---|---|---|---|
| road schools | 869 | 548 (572 with an unknown side) | 143 (63 unknown) |
| rail schools | 749 | 214 (945 unknown) | 77 (287 unknown) |
| panel road, treated schools | 188 | 113 (127 unknown) | 38 (17 unknown) |
| panel rail, treated schools | 167 | 62 (207 unknown) | 27 (75 unknown) |
| grid road cells | 97,487* | 61,143 (91,370 unknown) | 17,152 (10,957 unknown) |
| grid rail cells | 40,705 | 11,553 (77,111 unknown) | 5,880 (21,754 unknown) |

\*already after the superseded grid-only fixes.

The "unknown" counts for `protected` are much smaller than for
`same_side`. A point well past a barrier's stretch is known not to be
protected, whatever the side.

Rail `same_side` recovered from 24 to 62 panel schools because of
`track_offset` (§7.3). For grid `protected`, every barrier near a cell is
judged, not only the nearest one. 2,875 road and 1,366 rail protected cells
(17% and 23%) are protected by a barrier that isn't their nearest.

The first rewrite run, before any of this, was dominated by barriers or
cells whose side became honestly unknown, not by flips. Of the schools
that lost `same_side` then, 296/362 (road) and 646/681 (rail) became
`same_side_unknown`. Before the rewrite, road filled unknown sides with a
"same side" default and rail with sub-millimetre noise signs.

For reference, the first run on 2026-09-23 predates the refinements. It gave:
- road schools 568, rail schools 121
- panel road 119, panel rail 30
- grid road 62,946, grid rail 3,011

The refinements moved these numbers in both directions:
- **Hook fix and beyond-end → unknown** removed signs that had been
  extrapolated. On the first pass this took the panel to road 106 / rail 24.
- **Bridging** then restored the sides of cells beside ramps: panel road 110.
- **§7.2-7.3** (`both_sides`, `track_offset`) then gave panel road 113 and
  rail 62.

**Not yet re-run:** `output/notebooks/sweden/analysis.ipynb` (uses
`MATCH_TIER = "same_side"`; its results will change materially). The
manual-audit app (§5) is next in line for the unknowns.

## 1. Which road/track: exact linear-reference join available

A barrier's `element_id` is **not a barrier id**. It is the NVDB
reference-link id of the road or track the barrier is registered on.
`start_measure` and `end_measure` give the barrier's position along that
link, as fractions from 0 to 1. The road network and the track network carry
the same three fields.

- **Coverage.** 100% of road barriers' `element_id`s exist in
  `road_network.parquet`, and 99.7% of rail barriers' exist in
  `network_tracks.parquet`.
- **The network rows cleanly split each link.** For every link that carries
  a barrier, the rows cover disjoint measure ranges; 0 overlaps.
- **Current method.** Both code paths match the barrier's *midpoint* to its
  nearest network row by distance. That agrees with the exact join for 100%
  of road barriers and 99.5% of rail barriers. The 9 rail disagreements are
  0.0m ties between adjacent rows.

This also explains the "`element_id` is not unique" note in
`schools/README.md`: several barriers share one reference link.

**Recommendation.** Replace the distance match with the key join
(`element_id` plus overlapping measure range). It is deterministic, has no
ties, and returns *every* row the barrier covers.

## 2. Which stretch: only one row is kept

The midpoint match keeps one network row per barrier, but many barriers span
more than one:

- **110 road barriers** span more than one row.
- **1,048 of 1,829 rail barriers** span more than one row.

The `same_route` corridor is grown outward along the network from that one
row, which partly makes up for this. There is a separate gap that has not
been measured: `corridor_geometry` leaves out a neighbouring segment
*entirely* when that segment is longer than the remaining distance budget,
instead of taking the part that fits. With short seed rows (median 232m for
the schools' road pairs) next to long ones, the corridor can stop at the
first junction.

## 3. Which side: mostly not in the data

A barrier's side could come from three sources: its geometry, its `side`
attribute, or rail's `distance_from_track_center_m`.

### 3a. Geometry sits on the centreline for road AND rail

- **Road (already known, 2026-09-18).** Barrier geometry shares vertices
  with its carriageway's reference line. The offset is 0 for 99.8% of pairs.
- **Rail (NEW, corrects `schools/README.md`).** **99.7% of rail barriers sit
  less than 1mm from their matched track.** They are snapped onto the track,
  not drawn offset from it.
  - The README's claim that rail barriers are "independently digitized,
    offset from the track" came from the sign split among rail pairs (`+1`
    2,645 / `-1` 2,331 / `0` 1,225).
  - `position_and_side` returns ±1 for *any* offset above 1e-6m, so those
    signs are the signs of sub-millimetre floating-point differences.
  - **Consequence: 99.4% of the 2,552 rail `same_side` pairs rest on a noise
    sign. Of the 749 rail `same_side` schools, only 8 are backed by a
    barrier with a real offset.**

### 3b. The `side` attribute: still no usable signal

The attribute says left or right of the reference link's direction. It was
refuted on 2026-09-18, and that conclusion still holds, but for a partly
different reason:

- **The original test was invalid.** It compared the attribute with rail's
  geometric sign, which (3a) is noise.
- **A valid test on road shows no signal either.** Ground truth: on a
  verified divided road (a reciprocal carriageway pair), the wall stands on
  the *outer* side of its carriageway, away from the sibling. Checking each
  road row's digitizing direction against measure direction (chaining
  consecutive rows; 74% of rows determinable, 0% reversed):
  - n = 377 barriers
  - the attribute agrees with the outer side **73.7%** of the time
  - always answering "right" already agrees **72.3%**

| `side` attribute | outer side = right | outer side = left |
|---|---|---|
| right | 266 | 70 |
| left | 29 | 12 |

- **Rail cannot be tested at all:** there is no geometric ground truth (3a).
  On the few rail barriers whose own linked track row is ≥5m away (161), the
  attribute agrees 52.8% of the time. That offset only reflects *which* track
  of a multi-track line the geometry was drawn on, so it is not a side
  signal either.

Don't use the attribute as a side source.

### 3c. `distance_from_track_center_m` (rail)

- It is **unsigned**, so it gives a real offset *magnitude* but no side.
- **999** is an "unknown" sentinel for more than 50% of rows.
- `noise_barriers/preprocess.py` does not clean that sentinel, the same kind
  of issue as the `built_year` sentinel fixed on 2026-09-15.

### 3d. Where the side *is* identifiable

| configuration | how | method |
|---|---|---|
| Road, divided carriageway | The wall is on the outer side of the carriageway it is registered on. Found via `reciprocal_carriageway_sibling`, now searching up to 100m. | Tier 1 in `grid/side.py` |
| Road ramp or spur beside a longer mainline | The ramp is truly offset from the mainline, so the mainline gives a real signed offset. Example: 19.7m for the Nacka/Sickla school barrier `12732:220514`. | Tier 2 in `grid/side.py` |
| Everything else (undivided road, all rail) | **Unknown** from this data. | Tier 3 / `same_side_unknown` in `grid/side.py` |

## 4. Current state of the side test in each code path

### `grid/side.py`: fixed 2026-09-23

Three tiers, and `same_side_unknown` is flagged rather than defaulted.

Still open:

- The sibling search starts from the matched row's *midpoint*, not the
  barrier's own position. A row can be kilometres long.
- Tier 2 uses the raw reference row, so the short-segment problem can
  return, more rarely.
- Rail compares school and barrier signs taken from different track rows.
  That is moot anyway: rail's side is unknown under 3a.

### `schools/assemble.py`: NOT fixed; feeds the shipped regression

`output/notebooks/sweden/analysis.ipynb` uses `MATCH_TIER = "same_side"`.

**Road:**

- **No sibling found → "same side" by default.** When no reciprocal sibling
  is found, the side is simply set to "same side".
  - 1,652 of the 3,312 `same_side=True` pairs were never tested.
  - **364 of the 869 `same_side` schools (42%) are treated only through this
    default.**
  - With the grid's three tiers, those 1,652 pairs would split as: 263
    tested against a sibling found at 100m, 1,128 against the nearest
    parallel road, and 261 unknown.
- **Short-segment problem.** The side test measures distance to the raw
  matched segments. In 2,031 of the 2,958 pairs that do get a real test
  (69%), the school lies beyond the ends of its barrier's segment, which is
  the failure mode fixed in the grid.

**Rail:** see 3a. `same_side` is effectively a coin flip.

## 5. Options for modelling the protected area

1. **Side-agnostic model with provenance.** Treat the protected area as both
   sides of the covered stretch. Keep a `side_method` column
   (`carriageway_pair` / `parallel_road` / `unknown`) so `same_side` is only
   used where it was really tested.
   - Honest, and doable with data already on disk.
   - Loses the "wrong side" placebo for most barriers.
2. **External data on true barrier positions.**
   - OpenStreetMap: checked 2026-09-23, see "OSM check" below. **Good
     geometry, low coverage**, so it can supplement the data but cannot
     replace it.
   - Alternatively, a manual audit restricted to the barriers that matter for
     the analysis sample (a few hundred treated schools, not 4,000 barriers).
3. **Both.** Use the geometric tiers where they apply, fill the rest from
   external data, and flag whatever remains.

Decide on this **before** consolidating: the answer determines what the
shared module has to return.

### OSM check (2026-09-23)

Source: Overpass API, OSM data as of 2026-09-22, not saved into `data/`.
Two groups of ways were compared against the Trafikverket layers:

- **Tagged walls:** 510 ways tagged as noise barriers (505 are
  `barrier=wall` + `wall=noise_barrier`), 94 km in total.
- **Untyped walls:** 7,659 plain `barrier=wall` ways with no `wall=`
  subtype, 467 km in total. A match counts only when the OSM wall runs
  parallel to the barrier (|cos| > 0.8), is at least 30m long within 40m of
  it, and is offset at least 2m from it.

Findings:

- **The geometry is real.** Matched OSM walls sit a median 16m from the
  road/track centreline, and 100% are at least 2m off it. They are drawn
  beside the road, which is exactly what the Trafikverket layer lacks.
- **The side is trustworthy.** On verified divided roads, 90% of matched OSM
  walls (n=130, each matched to the carriageway it is actually nearest) sit
  on the carriageway's outer side. That independently confirms the
  outer-side rule used by tier 1.
  - A looser 40m match gives only 77%. The difference is divided highways
    with walls on both sides, where the loose match picks the other
    carriageway's wall.
- **The coverage is low.**

| | Trafikverket barriers matched (tagged only) | + untyped walls | school-relevant barriers matched (`same_route` pairs) |
|---|---|---|---|
| road | 8.4% | 11.2% (13.9% by length) | 169 / 917 (18.4%) |
| rail | 4.8% | 6.8% (8.4% by length) | 91 / 1,147 (7.9%) |

The untyped-wall matches are unvalidated; some may be retaining walls. OSM
can therefore serve as one more `side_method` (`osm_offset`) where it
exists, but more than 80% of school-relevant barriers still need either the
geometric tiers or "unknown".

### Decision (2026-09-23) and planned manual audit

**Chosen approach:** option 3, geometry plus external data. Every barrier
gets a `side_method`, tried in this priority order:

1. `manual` (future, see below)
2. `osm_offset`
3. `geometric_offset`
4. `parallel_road`
5. `unknown`

`parallel_road` covers what was planned as two methods: divided-road
carriageway pairs and ramps beside a mainline. Validated against OSM walls
during implementation, the rule is the same for both: the wall stands on the
side of its road away from a road that runs alongside. What mattered was
*how the other road is identified*. Requiring it to stay alongside for
±200m, on one side and within 80m, gave 93% agreement with tagged OSM walls
(n=102) and 100% with untyped ones (n=37). Taking the nearest parallel row
gave 76%; the old length-ratio heuristic gave 92%.

`unknown` never counts as treated. Rows with an unknown side stay visible
through the `same_side_unknown` flag, rather than being folded into either
group.

**A manual audit will be needed later.** Most school-relevant barriers
remain `unknown` after the geometric and OSM methods: all of rail except
OSM hits, and undivided roads. They can only be resolved by a person looking
at imagery. **We'll build a small app for this:**

- **Scope.** The barriers linked to the analysis sample's treated schools,
  not all 4,000.
- **Display.** One barrier at a time, over aerial imagery, with its road
  centreline and the candidate protected side highlighted.
- **Input.** The reviewer marks the side (left of road / right of road /
  both / can't tell) plus an optional note.
- **Output.** A small versioned table keyed by barrier (`element_id` +
  `start_measure` + `end_measure`, since `element_id` alone is the road
  link, not the barrier). The pipeline reads it as the top-priority
  `side_method = "manual"`, overriding every automatic method.
- **Order.** Build the app after the consolidation below. The shared module
  then has one obvious place to read overrides from.

## 6. Consolidation / cleanup plan (done 2026-09-23, see Status above)

**1. One shared barrier-reference module.** Proposed name
`_barrier_reference.py`. It builds, once per barrier:

- the rows it covers, from the linear-reference join (section 1)
- its `same_route` corridor, with neighbouring segments cut to fit the
  budget instead of dropped
- its side method and reference line, found at the barrier's own position
  rather than a row midpoint

It also provides one classifier that assigns points to same side / wrong
side / unknown. `schools/assemble.py` and `grid/side.py` both consume it.
Today `match_barriers_network` (lines 200-252) and `match_grid_side` repeat
the same setup: the barrier-to-network match, position and side, corridor
building, and sibling lookup. That duplication is why the 2026-09-23 fixes
reached the grid but not schools. Sharing the module fixes schools by
construction.

**2. Delete `network/linear_ref.py` and `road_network/linear_ref.py`.** They
are one-line renames (`nearest_track`, `nearest_road`, `milepost_and_side`)
that no production code imports. Point
`tests/regions/sweden/test_network_linear_ref.py` and
`test_road_network_linear_ref.py` at `_linear_ref` instead.

**3. Remove the aliases** `add_rail_network_treatment_definitions` and
`add_road_network_treatment_definitions` (`schools/assemble.py:382-383`),
and update the one test that uses them.

**4. Merge `run_schools_assemble_rail_network` and
`run_schools_assemble_road_network`** (lines 386-469). They are about 40
lines each and nearly identical, so one function taking `kind` would do.

**5. Fix the layering.**

- `grid` imports `BARRIER_KINDS`, `load_noise_barriers`, `load_road_network`
  and `load_network_tracks` from `schools.assemble`. Move each loader to its
  own data source's `shared.py`.
- `METRIC_CRS` is defined twice (`schools/assemble.py`, `grid/shared.py`).
  Define it once.

**6. Small items.**

- Clean the `distance_from_track_center_m` 999 sentinel in
  `noise_barriers/preprocess.py`.
- `grid/side.py`: remove the unreachable "shouldn't happen" fallback in the
  first sibling-search step.
- `carriageway_sibling` recomputes `geoms[i].length` although `lengths` is
  passed in.
- Road barriers get a side computed that is never used.
- `match_barriers_point` computes `argmin` twice.

**Order of work:**

1. Decide the side strategy (section 5).
2. Build the shared module and move both call sites onto it.
3. Re-run `schools assemble-*-network`, `grid assemble`, `panel`, and
   `analysis.ipynb`.

Step 3 changes the headline `same_side` results, so it needs an explicit
go-ahead.

## 7. Next steps (plan and implementation, 2026-09-24)

Measured on the 2026-09-24 outputs (school pairs within 1km, panel =
schools in `event_study_panel.parquet`). Order agreed with the user: 7.2,
then 7.3, then 7.1, then 7.4. **7.1-7.3 are implemented**; the status
under each gives the validation.

### 7.1 The protected area should follow the barrier's own stretch

`same_side` is currently "same side of the barrier's road, anywhere in its
`same_route` corridor". That corridor reaches 800m along the network plus a
600m buffer, while the median barrier is only 72m (road) / 79m (rail) long.
So the flag mostly means "same side of the road near a barrier", not
"behind the wall":

| | road | rail |
|---|---|---|
| `same_side` school pairs | 1,907 | 184 |
| … beside the barrier's own stretch | 8% | 10% |
| … more than 100m / 300m past its end | 79% / 54% | 79% / 52% |
| median distance past the end (pairs beyond it) | 369m | 359m |
| `same_side` schools that count only because of pairs >300m past the end | 174 of 533 (29 in the panel) | 38 of 89 (7 in the panel) |

**Plan:**
- `classify_points` also returns, per point, `lateral_m` (distance from the
  through-line) and `along_offset_m` (distance past the barrier's stretch
  along the through-line, 0 when beside it).
- A new `protected` tier: same side and within a margin of the stretch.
- The existing tiers are kept for comparison, and the continuous distances
  are carried through so the analysis can vary the cutoff.
- Side unknown only matters for `protected` when the point is beside the
  stretch. A point past the stretch is known not to be protected whatever
  its side, so this tier has far fewer unknowns than `same_side`.

**Open choice (user):** the margin. For reference, the FHWA "four-to-one"
design rule of thumb says a barrier should extend about four times the
receiver-to-barrier distance beyond the receiver on each side. A receiver
past a barrier's end therefore gets much less than full shielding.

**Status: implemented.**
- `classify_points` returns `lateral_m`, `along_offset_m`, `protected` and
  `protected_unknown`. The barrier's stretch is its own geometry projected
  onto its through-line (`span_start_m` / `span_end_m` in the reference
  table).
- For a point past an end of the through-line, the along-road distance is
  extended along that end's direction rather than pinned to the end.
  Otherwise a cell 500m past a short line would count as beside a barrier
  near that end.
- **Default margin 50m** (`PROTECTED_SPAN_MARGIN_M`, the `span_margin_m`
  argument): half a grid cell, so a 100m cell whose centroid is within 50m
  of the stretch counts. It also absorbs small geometry/measure mismatches.
  The same margin applies to schools and grid.
- New tier `protected` alongside `point` / `same_route` / `same_side`:
  - schools rollup: `{first_treat_year,ever_treated,timing_unknown}_protected`
    and `protected_unknown`
  - panel: `{kind}_*_protected`, `event_time_{kind}_protected` and
    `{kind}_protected_unknown`
  - grid: `ever_treated_protected`, `timing_unknown_protected` and
    `protected_unknown`
- The pair and cell tables keep `lateral_m` / `along_offset_m`, so the
  margin (or a lateral cutoff) can be varied in the analysis without
  re-running the matching.
- **Reach 600m** (`PROTECTED_MAX_LATERAL_M`, the same distance as the
  `same_route` corridor): a protected point is at most 600m from the road.
- **What "beside the stretch" means.** A point is beside the stretch when
  its *nearest point on the road* lies within the stretch ±50m. Near a bend,
  a point in front of a wall can be nearer another, unshielded part of the
  same road. It then gets that part's noise and is not protected. That is
  why protection areas on curving roads and at interchanges are wedges or
  fans rather than rectangles.
- **Closed through-lines** (a roundabout's ring) have no ends, so nothing on
  them is "beyond the end".
- **Side reference line simplified to 1m.** NVDB lines sometimes end in a
  sub-metre, oddly angled jog. That jog, not the road's real direction,
  would otherwise decide what lies beyond the road's end.
- **Grid: every barrier counts.** `grid/side.py::match_grid_protection`
  judges each cell against every barrier within 700m. A cell is protected
  if any barrier protects it, which differs from the nearest barrier for
  17% (road) / 23% (rail) of protected cells. The count matches an
  exhaustive check of all cell–barrier pairs exactly (17,152 road / 5,880
  rail cells). Schools already judged every barrier within 1km.
- **Polygons.** `_barrier_reference.protection_zones` draws the same area
  per barrier for the national layer (`barrier_protection`). It is built
  from a Voronoi split of the road line densified every 5m, with sample
  points 5cm past the stretch's ends pinning the end edges. Checked against
  the point test for every grid cell within 700m of a barrier:
  - **protected:** road 0 of 22,384 cell–barrier pairs and rail 0 of 9,387
    lie more than 5m outside their zone
  - **the reverse:** 1 of 34k (road) and 1 of 42k (rail) points deep inside
    a zone aren't flagged
  - **side unknown:** 0.6% / 0.2% of pairs lie up to 51m outside. These
    are points just past an end of the road line, within the 50m margin,
    where the side is undefined and the zones leave them out.

### 7.2 Barriers on both sides of the same road

112 road barriers (5%) overlap another barrier on the same road link by at
least half their length, and in **every** such pair the two `side`
attributes differ. So these are left + right walls, even though `side` has
no signal in general (§3b). Today each wall in a pair gets the same
inferred side, so one of them is always wrong. Their geometry is identical
(both on the centreline), so the grid's nearest-barrier assignment picks
one arbitrarily.

**Plan:** a `both_sides` side method, ahead of all others: every point
beside the road is on a protected side. It resolves 26 of the 150
unknown-side road barriers near panel schools. Rail has 331 overlapping
barriers, but `side` differs in only 32% of those pairs, so rail needs a
separate look before any rule.

**Status: implemented, road only.**

OSM check. The 58 road pairs overlapping ≥50% on the same link are all
left + right. Where OSM maps walls within 40m of them, it shows walls on
**both** sides for 7 of 12 pairs, against 3 of 33 for a random sample of
300 single barriers. So these really are two-sided.

Rail doesn't qualify:
- its 208 overlapping pairs mostly have the *same* label (141 same, 66
  opposite)
- they are not co-located (median Hausdorff distance 60m)
- OSM covers them too sparsely to check (0 of 66 opposite-label pairs have
  walls on both sides)

`both_sides_rows` finds 112 road barriers. Their `side_method` is
`both_sides` and every point beside the road counts as same side. The
literal `side == "both_sides"` label (4 road, 10 rail) is **not** used: it
is unvalidated and `side` has no signal in general (§3b).

### 7.3 Rail: the barrier's distance from its track, plus the other track

Rail barriers sit exactly on the track, so rail has a known side only where
OSM maps the wall (24 treated panel schools). About 800 rail barriers carry
a real `distance_from_track_center_m` (unsigned). On a double track it can
still decide the side. A wall on the other track's side, at distance d from
its own track, would stand between the tracks (d < track spacing s) or
right on the other track (d ≈ s). Neither is plausible, so d ≲ s + clearance
puts the wall on the side away from the other track. If Trafikverket
registers each wall on its nearest track, the rule holds whatever d is.

**Plan:** validate both variants against the rail barriers whose side comes
from an OSM wall before using either.

**Validation.** 1,520 of 1,829 rail barriers have a parallel track
(`parallel_neighbor` on the track network; spacing median 4.5m). Against
the side from the best OSM wall:

| subset | n | agrees with "away from the other track" |
|---|---|---|
| all with an OSM side | 116 | 70% (majority-side baseline 60-67%) |
| tagged `noise_barrier` OSM walls | 87 | 68% |
| tagged walls whose offset matches the recorded distance (±3m) | 20 | **100%** |
| tagged walls whose offset does not match it | 26 | 50% |
| any OSM wall at the recorded distance (±3m) | 28 | **96%** (27/28; d ≤ s+2: 22/23, d > s+2: 5/5) |

- **The rule is right.** Where the OSM wall is certainly the same wall
  (it lies at the recorded distance), the barrier stands away from the
  other track 96-100% of the time. That includes walls further out than
  the other track (d > s+2), which points to Trafikverket registering each
  wall on its nearest track.
- **The OSM matching was noisy for rail.** An OSM wall at a different
  offset from the recorded one agrees only at chance level, so it is
  probably another wall (e.g. one for a parallel line).

**Status: implemented.**
- **`track_offset` method** (rail): a recorded distance ≥1m and a parallel
  track → the side away from it. It ranks after `osm_offset` and
  `geometric_offset`.
- **Rail `osm_offset`** now requires the wall to lie at the recorded
  distance (±3m) wherever one is recorded. Without a recorded distance it
  is unchanged.
- **Barriers without a recorded distance** stay unknown beside a second
  track. The no-distance subset agrees only 66% with OSM, and those OSM
  matches can't be verified.

Per-barrier count, full rail network: `track_offset` 630, `osm_offset` 98,
`geometric_offset` 6, `unknown` 1,095 (known: 734, before: ~124).

`build_barrier_references` now takes `kind="road"|"rail"` in place of the
`detect_*` flags, since every rule choice follows from it.

### 7.4 Manual-audit app, scoped to the panel

After 7.2/7.3, audit only the barriers that decide a panel school's
treatment. As of 2026-09-24 that is:
- **road:** 150 unknown-side barriers behind 114 panel schools
- **rail:** 689 barriers behind 196 panel schools; fewer if only each
  school's nearest barrier is audited, and after 7.3

Include a stratified sample of `parallel_road` barriers, since its 93%
agreement was measured only where OSM maps a wall.

**Outside the matching:** most barriers have no construction year (162,328 of
271,116 treated road grid cells have `timing_unknown`), which may matter as
much for the event study as the side question.

## Notes on reproduction

- Every number above was computed with ad-hoc scripts on 2026-09-23 against
  `data/sweden/{noise_barriers,road_network,network,schools,grid}/`.
- Road digitizing direction was checked by chaining consecutive rows of the
  same link (end of one row = start of the next, within 1m). Rows on
  single-row links are undeterminable and were excluded.
- Rail snapping was measured with the same nearest-row join
  `schools/assemble.py` uses (`nearest_segment` on the barrier midpoint), so
  it describes exactly what that code sees.
