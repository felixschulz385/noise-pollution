# `grid`

A second output spec for the barrier-construction event study: instead of
matching noise barriers to *schools* (`schools/assemble.py`), match them to
a **100m x 100m grid cell**, assigning treated/untreated binary flags in
distance bands (default 100/200/300/400/500/1000m), a continuous
distance-decay exposure index, barrier physical covariates, and a
"relevant side" vs. "wrong side" placebo distinction. Same barrier layers
(`noise_barriers`), same nearest-distance logic, different unit of
analysis.

**Status (2026-09-23): researched, `preprocess` + `assemble` implemented
and run against real data; exposure modeling elaborated (see "Elaborated
exposure modeling" below) to more closely mirror Moretti & Wheeler (2025),
"The Traffic Noise Externality" -- geometry-only, no new data source (see
that section for what couldn't be ported and why).**

## The 100m grid is not SCB's real grid -- researched first, before building

SCB's only genuinely *open* grid geodata product is
["Statistik på rutor"](https://www.scb.se/en/services/open-data-api/open-geodata/grid-statistics/)
-- **1km resolution only** (total population, age, sex; geopackage/WFS/WMS,
SWEREF99TM or INSPIRE/ETRS89-harmonised, annual 2015-2025). Confirmed live
2026-09-22 by reading that page directly, not assumed.

A genuine **100m x 100m** statistical grid does exist at SCB -- each
individual in the population register geocoded to their residence
building's centroid, aggregated to 100m cells -- but it is **restricted
microdata**, distributed only through SCB's **MONA** platform after a
formal researcher data-access application (SNDs's own MONA overview, and
SCB's microdata ordering pages, both confirmed live 2026-09-22). It is not
fetchable the way every other source in this pipeline is.

**This changes what "the grid" means for this output spec.** The
treated/untreated band flags below don't need SCB's real population
counts -- only cell *geometry*, to place distance bands around barriers.
So `preprocess.py` **builds the 100m tiling itself**, deterministically
aligned the same way SCB's/INSPIRE's real grids are keyed (cell id from
the SWEREF99TM coordinates of the cell's lower-left corner, snapped to
multiples of the resolution -- see `grid/shared.py::cell_id`) -- if MONA
access is ever obtained later, these cells line up with the real grid by
construction, they just don't carry any of SCB's real attributes today.

## `preprocess` -- real run 2026-09-22

```bash
python -m src.cli sweden data grid preprocess   # --buffer-m 1000 --resolution-m 100
```

REQUIRES `noise_barriers preprocess`. A nationwide 100m tiling of Sweden
would be ~45M cells -- pointless, since a cell further than the widest
configured band from every barrier is guaranteed `ever_near_*m = False`
regardless. Instead: buffer every barrier geometry (road + rail together)
by `buffer_m` (1000m, the widest default band), take the union, and tile
only that corridor, **per connected component** of the union (each within
its own small bounding box) rather than one pass over the corridor's
overall bounding box (~623km x 1392km for road alone -- tiling that
directly at 100m before filtering would mean materializing tens of
millions of candidate cells).

**Real run**: the buffered union has **694 disjoint components** (barriers
cluster near settlements, not one country-spanning blob), total corridor
area ~4,000 km^2, largest single component ~185 km^2 -- confirmed cheap
(summed per-component bbox tiling is ~1.6x the true corridor cell count).
**400,369 cells**, `data/sweden/grid/processed/grid_cells.parquet`.

## `assemble` -- real run 2026-09-23

```bash
python -m src.cli sweden data grid assemble
# default band radii: 100/200/300/400/500/1000m
```

REQUIRES `grid preprocess`. Run separately for road and rail, same
reasoning `schools/assemble.py` already documents: different noise
sources/exposure types, kept as two parallel tiers rather than merged into
one "nearest barrier of either kind" -- that design decision is inherited
verbatim, not re-litigated here.

Grid cell counts (hundreds of thousands) are too large for
`schools/assemble.py::match_barriers_point`'s dense distance-matrix
approach (cheap only at a few thousand schools) -- this uses the same
spatial-index nearest-neighbour join (`_linear_ref.nearest_segment`,
`gpd.sjoin_nearest` under the hood) the road/rail network-matching
algorithms already use. One nearest-distance value per cell per kind;
`ever_near_{radius}m` is just a threshold on it, one per configured band.

**Real run** (400,369 cells x 2 kinds; `ever_near_*m` unchanged from the
2026-09-22 run -- the finer bins/decay-index/side-matching additions below
are additive, not a change to the existing point-distance logic):

| kind | n_barriers | ever_near_100m | ever_near_200m | ever_near_300m | ever_near_400m | ever_near_500m | ever_near_1000m (= ever_treated) | timing_unknown | ever_treated_same_route | ever_treated_same_side | ever_treated, side unknown | ever_treated_protected | protected_unknown |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| road | 2,172 | 7,685 | 20,717 | 38,561 | 60,865 | 87,118 | 271,116 | 162,328 | 204,012 | 61,143 | 91,370 | 17,152 | 10,957 |
| rail | 1,829 | 5,692 | 13,819 | 24,138 | 36,433 | 50,574 | 145,286 | 52,455 | 97,515 | 11,553 | 77,111 | 5,880 | 21,754 |

The side columns are from the shared `_barrier_reference.py` rewrite
(2026-09-23), re-run 2026-09-24 with its refinements: through-line fixes,
`both_sides` (road), `track_offset` (rail) and the `protected` tier. See
[`../barrier_matching.md`](../barrier_matching.md). `grid assemble` loads
the barrier references saved by `barrier-protection build` and runs in
under a minute.
- **`same_route` / `same_side`** are judged against the cell's nearest
  barrier, like the point-distance tier.
- **`protected`** is judged against **every** barrier within 700m: same
  side and beside that barrier's own stretch (±50m), within 600m of its
  road. 2,875 road and 1,366 rail protected cells are protected by a
  barrier that isn't their nearest. `first_treat_year_protected` is the
  earliest `built_year` among the protecting barriers, and
  `timing_unknown_protected` means one of them is undated. The columns
  `n_protecting_barriers`, `protected_barrier_row`, `protected_side_method`
  and `protected_lateral_m` describe the protection.
- **`same_route`** rose slightly, because corridors no longer stop at the
  first junction.
- **`same_side`** now counts only cells whose side was actually decided.
  Among `ever_treated_same_route` cells, by the side method of the cell's
  nearest barrier:

| kind | `both_sides` | `osm_offset` | `geometric_offset` | `track_offset` | `parallel_road` | `unknown` |
|---|---|---|---|---|---|---|
| road | 1,490 | 13,644 | 303 | — | 103,245 | 85,330 |
| rail | — | 5,150 | 240 | 17,359 | — | 74,766 |

The "side unknown" column above is larger than this `unknown` column.
It also counts cells beyond the end of a known-side barrier's
through-line.

Rail barrier geometry is snapped onto the track, so rail has a known side
only where OSM has the wall, or from its recorded distance to the track
next to a second track (`track_offset`). Earlier numbers (149,286 → 154,894 → 97,487 for
road `same_side`) came from the superseded grid-only fixes below. The
first rewrite run (2026-09-23), before the refinements, gave 62,946 road
and 3,011 rail.

`timing_unknown` (among `ever_treated` cells only -- see `assemble.py`'s
`match_grid_point` docstring for why it's gated on `ever_treated`, unlike
a naive "nearest barrier's year is missing" check) mirrors the same real
gap `schools/assemble.py` inherits from `noise_barriers`' own `built_year`
coverage (most road/rail barrier rows have no recorded construction year)
-- not a bug introduced here, a pre-existing upstream data-quality limit.
Only the *single nearest* barrier's year is looked up per cell (not "any
barrier within the band", unlike schools' pair-table version) -- a
performance tradeoff at grid-cell scale, see the same docstring.

Outputs, mirroring `schools`' per-kind + combined structure:
`data/sweden/grid/assembled/grid_{road,rail}_rollup.parquet` (one row per
cell: `nearest_dist_m`, `nearest_element_id`, `built_year`/`treat_year`,
`timing_unknown`, `ever_near_{100,200,300,400,500,1000}m`, `ever_treated`,
`dist_bin`, `relative_loudness_reduction_pct`, whichever barrier covariates
that `kind`'s layer has (`height_m`/`height_above_rail_top_m`, `absorbent`,
`material_type`, `on_bridge`, `extent_length_m`), `same_route`,
`side_method`, `same_side`, `same_side_unknown`, `ever_treated_same_route`,
`ever_treated_same_side`, `timing_unknown_same_route`,
`timing_unknown_same_side`) and `grid_barrier_rollup.parquet`
(`{kind}_`-prefixed columns side by side, one row per cell).

## Elaborated exposure modeling (2026-09-23)

Ported ingredients from Moretti & Wheeler (2025) -- geometry only, no new
data source (see "What couldn't be ported" below for why):

- **Finer, mutually-exclusive distance bins.** `dist_bin` (`0-100m`,
  `100-200m`, ..., `500-1000m`, `beyond_{max}m`) alongside the existing
  cumulative `ever_near_*m` threshold flags (kept, not replaced) -- the
  paper's Table 2/Figure 4 dose-response bins. `beyond_{max}m` exists
  because a per-*kind* `nearest_dist_m` can exceed `max(band_radii)` even
  though the grid's own tiling buffer doesn't: the buffer is unioned across
  BOTH kinds, so a cell can be well inside the buffer via its nearest RAIL
  barrier while its nearest ROAD barrier is tens of km away (confirmed
  live: road's `beyond_1000m` bucket alone is 129,253 cells, 32% of the
  grid -- purely rail-corridor territory).
- **A continuous distance-decay exposure index**,
  `relative_loudness_reduction_pct` (`assemble.py::compute_relative_loudness_reduction_pct`)
  -- reproduces the paper's Appendix Table A3 physics: inverse-square-law
  decibel decay (-6 dB per doubling of distance) from a 76 dB/25m reference,
  a barrier's assumed 7 dB attenuation subtracted (see "What couldn't be
  ported"), converted to a 0-100 perceived-loudness scale (every 10 dB drop
  halves perceived loudness). Closely matches (within the paper's own
  table's rounding) its worked values: 25m -> 38.4 (paper: 38.5), 100m ->
  16.7 (paper: 17.0), 800m -> 4.8 (paper: 4.9). Clamped at 25m (not
  extrapolated closer) -- an unclamped version blew up past 250 for cells a
  few metres from their nearest barrier, confirmed live while building it.
- **Barrier physical covariates** carried through from the nearest barrier
  (`height_m`/`height_above_rail_top_m`, `absorbent`, `material_type`,
  `on_bridge`, `extent_length_m`) -- heterogeneity controls, the closest
  available analogue to the paper's Table 6 (tree canopy/building density).
- **`same_route`/`same_side`** (the paper's Section 3 "relevant side" vs.
  "wrong side" placebo distinction) -- ported from
  `schools/assemble.py`'s algorithms 4/5 to grid-cell scale in
  `grid/side.py::match_grid_side`, **not** modifying `schools/assemble.py`
  itself (its road/carriageway matching was fixed 2026-09-23 and isn't
  re-litigated here) -- only its already-exported, unmodified
  `load_network_tracks`/`load_road_network` plus the shared low-level
  primitives in `_linear_ref.py` are reused. Schools' version loops per
  school x barrier pair (cheap at a few thousand rows); grid's version
  vectorizes the same algorithm by grouping cells by their matched barrier
  row instead (corridor containment and the carriageway-sibling distance
  test both become one vectorized `GeoSeries` call per barrier group; only
  rail's per-cell signed-offset projection is a genuine per-row cost, and
  it's bounded to the `same_route`-qualifying subset). Full run (400k
  cells) completes in under 8 minutes. `ever_treated_same_route`/
  `ever_treated_same_side` are gated on the existing point-distance
  `ever_treated` tier, same tiering spirit as
  `schools/assemble.py::add_network_treatment_definitions` but simpler --
  grid cells only ever have one candidate (nearest) barrier, so no
  groupby-min-treat-year step is needed.

### `same_side` short-segment fix (2026-09-23)

> **Superseded later on 2026-09-23** by the shared `_barrier_reference.py`
> (see [`../barrier_matching.md`](../barrier_matching.md) and the status
> section above). Kept as history; the numbers here are from the
> pre-rewrite code.

Found while building `src/experiments/sweden/grid.ipynb`'s road case
study: a real barrier's `same_side` split showed some cells on the visibly
wrong side of the road, not just noise. Root cause, checked live: the
original `same_side` (road) compared each cell's distance to the wall's
and sibling's raw matched network ROWS -- single `LineString`s, which
Sweden's road network digitizes as many short edges per physical road
(this barrier's own wall row was ~260m against a ~2,200m sibling). Past a
short row's own extent, `GeoSeries.distance()` to it degenerates into
distance to its nearest endpoint, which stops tracking which side of the
road a cell is actually on.

Scoped against the full 400k-cell road grid before fixing: **31.1% of
`same_side=True` cells (46,689 of 150,151) sat on the minority side**
among cells sharing the same matched row -- pervasive (886 of 1,154
matched rows affected), concentrated where predicted (cells projecting off
the matched row's own extent flipped at 40.1% vs. 26.1% for interior
cells).

**Fix** (`grid/side.py::match_grid_side`): grow both the wall's and
sibling's centerlines to the same network-distance `budget_m` corridor
`same_route` already uses (`_linear_ref.corridor_geometry`, the sibling's
grown from its own "mirror point" -- the point on it nearest the barrier),
and compare distance to those instead of the two raw rows. Re-validated
post-fix with a check independent of the algorithm's own reference line:
each barrier's own digitized geometry (long enough for a stable PCA
direction) as an external yardstick for whether `same_side` and
`(same_route & ~same_side)` cells land on opposite sides of it -- **89.8%
of barriers have the two groups properly separated**, mean `same_side`
internal purity 73.2%, mean wrong-side contamination 15.6% (real road
curvature and digitizing noise, not the fixed degeneracy, account for the
remainder). Road's `ever_treated_same_side` moved 149,286 -> 154,894; rail
is untouched (its `same_side` method is the signed-offset one, which never
had this failure mode -- see `side.py`'s own docstring).

`schools/assemble.py::match_barriers_network`'s road path has the
identical `d_wall <= d_sibling` structure against raw matched rows and is
very likely affected the same way, but is **intentionally left
unmodified** here -- fixing it is a separate decision, not bundled into
this grid-only fix (also: schools' own shipped Callaway-Sant'Anna
regression already uses `same_route`, not `same_side`, as its treatment
tier, so this doesn't retroactively change any run analysis).

### `same_side` tiered sibling search fix (2026-09-23, same day)

> **Superseded later on 2026-09-23** by the shared `_barrier_reference.py`
> (see [`../barrier_matching.md`](../barrier_matching.md) and the status
> section above). Kept as history; the numbers here are from the
> pre-rewrite code.

A second, bigger issue found immediately after the fix above, while
walking through the case-study barrier in `grid.ipynb`: that barrier
(`12732:220514`, real location -- confirmed live -- 59.3117°N 18.1513°E,
Värmdöleden/route 222 at the Sickla/Järla interchange in Nacka; confirmed
independently to sit on the outside of a motorway off-ramp, next to a
school) had NO verified reciprocal sibling for its own matched road row.
Per `side.py`'s then-current fallback ("no sibling -> nothing to be on the
wrong side of"), this silently forced ALL 156 of that barrier's
`same_route` cells to `same_side=True` -- not a real test.

Scoped: **53.4% of `same_route` road cells (102,466 of 192,039) belonged
to a matched row with no verified sibling** -- the majority of the tier
was never actually tested. Two distinct causes, checked separately:

1. Real carriageway pairs the old 30m search radius (`carriageway_sibling`'s
   own default) was too tight for -- some medians/separations are wider
   than that. Widening to `SIBLING_SEARCH_DIST_M = 100.0` (radius alone,
   length ratio unchanged) recovers about half: 49.7% one-directional hit
   rate at 100m vs. 27.3% at 30m, among the 684 affected matched rows
   (`n>=5`).
2. Asymmetric cases like the ramp above -- a short spur beside a much
   longer mainline is not a carriageway PAIR, so the existing reciprocal
   check structurally can't verify it (the mainline's own "nearest
   similar-scale road" search won't point back to a short ramp). The
   ramp's own offset from ITS matched row is 0.0m (degenerate, same reason
   road uses carriageway comparison at all) -- but its offset from the
   *mainline* 17m away is a clean, non-degenerate 19.7m, clearly
   distinguishable from its sibling's 36.6m opposite-signed offset.

**Fix**, three tiers (`side.py::match_grid_side`):

1. Reciprocal sibling, unchanged method, radius widened only.
2. No verified sibling -> search again with no length-ratio cap
   (`NEARBY_PARALLEL_LENGTH_RATIO_RANGE`), no reciprocity required; if
   found, side is decided by signed offset from that one road
   (`_linear_ref.position_and_side`, the same method rail's own
   `use_carriageway_side=False` path already uses -- barrier and every
   cell in the group compared against the SAME single line, never each
   cell's own separate nearest match, since a sign is only meaningful
   pairwise on one line).
3. Neither found -> genuinely unknown. `same_side` is `False` (never
   defaults `True`), and a new `same_side_unknown` column flags it, kept
   through `add_side_treatment_definitions`/`build_combined_rollup` and
   summarized in `run_grid_assemble`'s own report
   (`n_same_side_unknown`).

**Real effect**: the "100% `same_side=True`, no real test" signature among
matched rows drops from 684 to a small remainder (mostly genuine tier-3
unknowns plus rows where every cell really does land on the treated side).
Road's `ever_treated_same_side` moves from 154,894 (after the first fix
only) to 97,487 -- of the 192,039 `same_route` cells, 98,108 resolve
`True`, 54,702 resolve `False` (a real, tested wrong side), and 39,229 are
`same_side_unknown`. A large drop, but an honest one: most of the
difference is cells that were never really tested moving to a real `False`
or an honestly-flagged unknown, not new errors. `grid.ipynb` runs all
three tiers live against real examples (§6 continued) rather than only
describing them.

### Open: barrier side is mostly unidentifiable; consolidation with `schools` pending

See [`../barrier_matching.md`](../barrier_matching.md), a full review of
barrier ↔ road/track matching. Two findings affect this output:

- **Rail.** Rail barrier geometry is snapped onto the track (99.7% within
  1mm). Rail's `same_side` here is therefore effectively a coin flip, the
  same as in `schools`.
- **Road.** Only divided carriageways (tier 1) and ramps beside a mainline
  (tier 2) carry real side information.

The document also holds the planned consolidation of `grid/side.py` and
`schools/assemble.py` into one shared barrier-reference module. The two
fixes above exist only in `grid`; `schools` does not have them yet.

### What couldn't be ported

- **No per-barrier engineering dB noise reduction.** Neither Sweden's
  Trafikverket barrier layer nor Florida's public FGDL layer carries the
  paper's FDOT-internal field (an engineering estimate of each specific
  barrier's noise reduction). `ASSUMED_BARRIER_REDUCTION_DB = 7.0`
  (`grid/shared.py`) is therefore a documented, uniformly-applied
  ASSUMPTION -- close to both the paper's own Florida sample average (7.15
  dB) and the national average it cites (7.0 dB, Rochat 2016) -- not a
  measured per-barrier value. `relative_loudness_reduction_pct` is a
  distance-only exposure proxy, not a claim about any specific barrier's
  real acoustic performance.
- **No "proposed but not built" barriers.** Trafikverket's layer is a
  built-asset inventory only (confirmed while scoping this work), unlike
  Florida's FDOT data (which records recommended-but-unbuilt barriers too).
  The paper's triple-difference design, which depends on matching built to
  proposed-but-unbuilt barriers, has no data to run on here.

## Open questions (not blocking)

1. No panel/timing join yet (Florida/Sweden's `panel/assemble.py`
   equivalent) -- this output spec currently stops at the static
   treated/untreated rollup, same phase `schools assemble` (algorithms 1-2)
   was at before `schools`' network-matching algorithms 4/5 and the panel
   join were added. Whether the grid spec needs its own outcome data to
   join against (and what that outcome even is at 100m grain, since
   `assessments` is school-grain) has not been decided.
