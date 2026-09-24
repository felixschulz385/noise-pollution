# `schools`

Self-contained implementation brief for a fresh agent, mirroring the
`road_network`/`road_projects`/`shocks` README-first pattern used in the
Florida pipeline (`docs/data/florida/*/README.md`). Everything below was
checked live against the real Skolverket API/database on 2026-09-15, not
guessed — see the curl/fetch calls inline.

**Scope**: school-unit *identity* — geocoding, grade span, operator, and
(via `assemble`) barrier-treatment timing. This is the Sweden analogue of
Florida's `schools` source. School-level *achievement* data (the outcome
variable) is a separate domain, [`assessments`](../assessments/README.md)
— split out 2026-09-15 to mirror Florida's `schools` vs. `assessments`
separation (identity/treatment vs. outcome are independently-changing
concerns, eventually joined by a `panel`-equivalent step, not built yet).

**Status (2026-09-15): Phase 1 (`Skolenhetsregistret` directory) and
`assemble` (barrier matching) are both implemented and run against real
data.**

## Phase 1 — `Skolenhetsregistret` directory: implemented

`src/regions/sweden/sources/schools/` — `shared.py` (paths, API URLs,
`GRUNDSKOLA_GRADE_FIELDS`), `fetch.py` (`fetch_skolenhetsregistret`: always
pulls the full lightweight list in one call, then one detail record per
`Skolenhetskod`, idempotent — skips a code already on disk unless
`force=True`, accepts `limit`/`status`/`codes` so a smoke test doesn't have
to pull the whole country), `preprocess.py` (`preprocess_schools`: flattens
each detail record — geocoding, grade span, operator, municipality — into a
GeoDataFrame, EPSG:4326 to match `noise_barriers`/`stations`). CLI:
`sweden data schools {fetch,preprocess}` wired in `cli.py`/`handlers.py`.
Tests: `tests/regions/sweden/test_schools_fetch.py` (9),
`test_schools_preprocess.py` (9) — synthetic-data, no network.

**Real run, full national fetch** (2026-09-15, live API; an initial
`--limit 5` smoke test ran first this session, then the full country):
`total_in_register: 10648` (every school form combined — Grundskola,
Gymnasieskola, Fritidshem, plus non-teaching administrative units, see
below). Full detail fetch: **10,643 fetched + 5 already on disk from the
smoke test = 10,648/10,648, 0 failed** (backgrounded, ran clean end to
end). `preprocess`: **10,648 rows, 9,520 geocoded** (1,128 schools with no
usable coordinates — administrative pooling units, dormant/planned units
with no address yet, etc.). Output:
`data/sweden/schools/processed/schools.{csv,geojson}`.

**One real thing found while running it, not a bug**: the register mixes
genuine teaching units with **administrative pooling entities** —
`skolformer_typer` came back as literally `"Central"` for some records
(e.g. "Central insamlingsenhet", "Elevvårdsenheten"), which are
huvudman-level collection/support units, not schools a student attends.
These also have inconsistent geocoding. Not filtered out yet — worth
deciding whether to exclude non-`Skolenhetstyp=="Skolenhet"` or
`skolformer_typer in {"Central", ...}` records before matching to barriers,
rather than silently carrying administrative units into a per-school panel
(they're a small share of the 9,520 geocoded rows, so unlikely to
materially bias the match counts below, but not yet quantified precisely).

## 1. School-unit directory + geocoding — `Skolenhetsregistret` (open API, no auth)

Two live endpoints, REST, JSON or XML by `Accept` header, updated daily:

- **List**: `GET https://api.skolverket.se/skolenhetsregistret/v1/skolenhet`
  → every school unit nationwide (active + `Vilande`/dormant + `Planerad`),
  lightweight fields only: `Skolenhetskod`, `Kommunkod`, `PeOrgNr`,
  `Skolenhetsnamn`, `Status`.
- **Detail**: `GET https://api.skolverket.se/skolenhetsregistret/v1/skolenhet/{Skolenhetskod}`
  → full record, confirmed live for one gymnasium and one grundskola:
  - **Geocoded address**: `Besoksadress.GeoData` carries both
    `Koordinat_SweRef_E/N` (SWEREF99 TM, matches this repo's existing
    `data/sweden/*` layers — no reprojection needed to join against
    `noise_barriers`/`network`) and `Koordinat_WGS84_Lat/Lng`. Every school
    checked had populated coordinates — unlike Florida's `schools` source,
    which needed a separate NCES EDGE geocode fallback, this API appears to
    geocode every record itself.
  - **Grade span**: `Skolformer[].Ak1..Ak9` booleans (confirmed on a
    grundskola record: `Ak4..Ak9=true` for a 4–9 school) — the Swedish
    analogue of Florida's MSID `GRADE_CODE` decode. Gymnasieskola records use
    program-track booleans instead (`NA`/`SA`/`TE`/… = Naturvetenskap/
    Samhällsvetenskap/Teknik/…), not a grade-number span.
  - **Operator** (`Huvudman`: `PeOrgNr`, `Namn`, `Typ` ∈ {`Kommun`,
    `Enskild`, …}), **municipality** (`Kommun.Kommunkod`/`Namn`),
    **status** (`Aktiv`/`Vilande`/`Planerad`), `Startdatum`,
    `Skolenhet_ValidFrom`.
  - **No explicit close-date field** was seen on the records checked — only
    `Status`. Panel exit (a school closing) likely needs to be inferred from
    a school unit disappearing from the register between two pulls, or from
    `Status` transitioning away from `Aktiv` — **not yet confirmed which**;
    flag as an open question before building the operation panel (this is
    the Sweden analogue of Florida schools' `DATE_CLOSED` field, which had
    no direct equivalent found here).
- **Current snapshot only.** The register reflects today's organization; it
  is not itself a historical panel (`Uttagsdatum` in every response is the
  pull timestamp). For a multi-year panel, this needs to be pulled and
  archived repeatedly over time (as `noise_barriers`/`network` already do
  via dated FGDL-style releases in Florida) — Skolverket does not appear to
  publish an archived-by-year version of the register itself. Bulk download
  alternative: two daily-updated Excel files (not yet inspected) mentioned
  on <https://www.skolverket.se/skolutveckling/skolenhetsregistret>.
- API v1 is being retired (deprecation planned end of 2025/2026) in favor of
  **v2** (`https://api.skolverket.se/skolenhetsregistret/v2/...`,
  Swagger UI at `https://api.skolverket.se/skolenhetsregistret/swagger-ui/index.html`)
  — v2's exact field/path differences from v1 were **not** checked live this
  session (the Swagger UI is JS-rendered, opaque to `WebFetch`; would need a
  browser session or the raw OpenAPI JSON to inspect). Build against v2 from
  the start given the v1 sunset.

## `assemble` — school <-> barrier match: implemented 2026-09-15

`src/regions/sweden/sources/schools/assemble.py` -- `match_barriers_point`
(Florida's algorithms 1-2, `euclid_nearest` + `buffer_dose`: a dense school
x barrier distance matrix, then a pair table + per-school rollup),
`build_combined_rollup` (one row per school, `road_`/`rail_`-prefixed
columns, run separately since road and rail are different noise sources --
matches the two separate exposure rows in `sweden_noise_overview.tex`'s
Table 2). CLI: `sweden data schools assemble --max-dist 1000`. 14 tests
(`test_schools_assemble.py`), synthetic geometries built directly in
EPSG:3006 so expected distances are exact.

**Real, load-bearing finding while building this**: both barrier layers
(`data/sweden/noise_barriers/processed/{road,rail}_noise_barriers.parquet`)
are stored in EPSG:4326 (degrees) -- `assemble.py` reprojects to **EPSG:3006
(SWEREF99 TM)** before computing any distance, since computing distance
directly in degrees would silently produce nonsense (degree-magnitudes
mistaken for metres). `Skolenhetsregistret` also carries its own
`Koordinat_SweRef_E/N` columns already in this same CRS convention (see §1),
so no crosswalk was needed, just a reprojection at match time.

**Two real bugs found and fixed in `noise_barriers/preprocess.py` while
checking `built_year` was usable for treatment timing** (checked the real
distribution before trusting it, not assumed clean -- same "check every
fetched source's raw pull" lesson as
[[florida-covariate-plan]]'s CRDC-duplicate finding):
1. **`built_year` sentinels were never cleaned**: Trafikverket's own "year
   not recorded" placeholder is `1900` for road barriers -- **51% of the
   real 2,172-row dataset** (vs. a real non-sentinel range of 1950-2025) --
   and `0` for rail (vs. a real range of 1989-2025). Left unfixed, roughly
   half of all road barriers would have silently read as built in 1900.
   Fixed with a per-`dataset_kind` sentinel map (`BUILT_YEAR_SENTINEL =
   {"road": 1900, "rail": 0}`) applied right after the existing
   `pd.to_numeric` cast. Both processed parquet files were regenerated with
   the fix (`road_noise_barriers.parquet`: 1,114/2,172 rows now correctly
   `NA`; `rail_noise_barriers.parquet`: 487/1,829 now `NA`).
2. **`save_processed_noise_barriers` had a broken import**
   (`from data.noise_barriers.shared import noise_barrier_paths` -- no such
   module exists; the real module is
   `src.regions.sweden.sources.noise_barriers.shared`). This would crash
   any fresh `preprocess` run; caught only because regenerating the parquet
   files to apply fix (1) above actually exercised this code path. Fixed
   the import; both datasets now preprocess cleanly end-to-end.

**Real run, initial 4-school smoke test** (before the full national fetch):
0 schools within 1000m of a road or rail barrier -- not a bug, checked the
actual nearest distances (2.0-24.1 km, sensible for a small, geographically
scattered sample against a sparse ~4,000-segment nationwide barrier layer).

**Real run, full national dataset** (2026-09-15, all 9,520 geocoded
schools x 2,172 road + 1,829 rail barriers):

| | within 1000m | share of 9,520 geocoded schools |
|---|---|---|
| road barrier | 1,251 | 13.1% |
| rail barrier | 1,454 | 15.3% |
| **either** | **2,470** | **25.9%** |
| both | 235 | 2.5% |

`n_pairs` (school-barrier pairs within 1000m, a school can pair with
several barriers): 5,814 road, 7,910 rail. `timing_unknown`: 845/1,251
road-treated schools, 797/1,454 rail-treated schools -- a real, sizeable
share of matched schools.

**Dug into why, on request (2026-09-15) -- root cause is a legacy
bulk-import batch in Trafikverket's own barrier records, not a matching
bug, not random missingness, and not introduced by anything in this repo's
code:**

1. **Matched barriers' `built_year`-NA rate tracks the population rate almost
   exactly** (road: 49.3% of the 566 distinct barriers a school actually
   matched to, vs. 51.3% of all 2,172 road barriers nationally; rail:
   27.7% vs. 26.6%). So schools aren't disproportionately near
   unknown-year barriers -- the matching itself introduces no bias here,
   the gap is inherited straight from the source data's own coverage.
2. **That population-level gap traces to one identifiable cluster**:
   **1,064 of 2,172 road barriers (49%) share the exact same
   `valid_from = 2006-01-01`** -- clearly a bulk-import/system-epoch date,
   not 1,064 barriers that genuinely all entered service on the same New
   Year's Day. **90% of that cluster has `built_year` still `NA`**, and the
   same records are overwhelmingly also missing `owner`, `absorbent`,
   `foundation_type`, `maintenance_instruction_status`, and `height_m`
   (checked via crosstabs, not assumed) -- these read as **geometry-only
   legacy records**, distinct from a separately-attributed group added or
   updated later with full metadata. Not yet identified *why* Trafikverket
   never backfilled them (a genuinely older/paper-era survey never
   digitized with full attributes? a different, less detailed collection
   process for a specific barrier type? -- not determined this session).
3. **Practical severity differs by kind, and matters for the actual
   analysis**: of the 845 road-`timing_unknown` schools, **737 (87%)
   genuinely have no usable `first_treat_year` at all** (not just a
   cautious flag alongside a still-valid date from another nearby
   barrier) -- consistent with road's much higher 51% population NA rate.
   Rail is less severe: of 797 flagged schools, 486 (61%) are truly
   blocked, while 311 (39%) still get a valid `first_treat_year` from a
   different, dated nearby barrier despite the flag -- consistent with
   rail's lower 27% population NA rate.

**Bottom line for the analysis layer**: this is a genuine, sizeable gap in
Trafikverket's own source data (not a bug to fix in this repo), concentrated
in a specific legacy-import batch, and it materially shrinks the
road-barrier treated sample with a usable date (only 514 of 1,251
road-matched schools -- 41% -- currently have one). Worth deciding whether
to pursue the batch further (e.g. a Trafikverket data request, or
cross-referencing against `valid_to`/other Trafikverket layers for a
construction-year proxy) before treating the road-barrier design as
resting on the full 1,251-school matched set.

**Done 2026-09-16**: joining [`assessments`](../assessments/README.md)'
achievement data through this match into one event-study panel -- see the
new `panel` domain (`src/regions/sweden/sources/panel/`,
[top-level README row](../README.md)). Built without waiting on
`assessments`' own cross-era stitching decision: the panel's grain is long
(`skolenhetskod x year x era x outcome_name`), deferring which outcome to
pool rather than resolving it.

## Algorithms 4+5 (`same_route`/`same_side`): implemented 2026-09-15, both rail and road

Adds a network-aware refinement to the point-only match above, mirroring
Florida's `schools/assemble.py::match_barriers_road`. Rail first (the raw
ingredients were already sitting in `data/sweden/network/raw/`, see the
design discussion earlier this session); road followed once the user
manually downloaded NVDB's `Vägtrafiknät` GeoPackage via Lastkajen (no
automated fetch exists for it, same "place the file, I read it" pattern as
rail's own manual download) -- see
[`road_network/README.md`](../road_network/README.md) for that source's
own brief. `match_barriers_network` in `schools/assemble.py` is now one
generic function behind both `match_barriers_rail_network`/
`match_barriers_road_network`, and the geometry helpers live in one shared
`src/regions/sweden/sources/_linear_ref.py` (refactored out of
`network/linear_ref.py` when `road_network/linear_ref.py` was added, rather
than duplicating ~150 lines of identical algorithm code) -- both region
modules re-export it under their own naming (`nearest_track`/`nearest_road`
etc.) for readability at the call site.

**New code**:
- `network/preprocess.py::preprocess_network_tracks` -- builds the
  candidate track network from the fine-grained `grundegenskaper`
  GeoPackage (194,047 raw rows): keeps only **open** track with a real
  `Bandel` route id (187,882 rows survive, 269 distinct routes), parses
  Sweden's `"66+280"`-style km-notation into plain metres. CLI: `sweden
  data network preprocess-tracks`. Output:
  `data/sweden/network/processed/network_tracks.parquet`.
- `network/linear_ref.py` (new) -- `nearest_track`, `milepost_and_side`,
  `build_adjacency`, `corridor_geometry`: mirrors Florida's
  `road_network/linear_ref.py` algorithm-for-algorithm (same
  nearest-segment-then-project design, same network-distance flood fill
  for the corridor test) -- the underlying geometry problem doesn't differ
  by region, only the linear-reference field names do.
- `schools/assemble.py::match_barriers_rail_network` -- for each rail
  barrier, grows a network-distance-bounded corridor along its nearest
  track (default 800m budget + 600m buffer, both overridable); a pair is
  `same_route` when the school falls inside its barrier's corridor, and
  `school_side`/`wall_side` (signed, pairwise-only -- not a compass
  direction, same caveat Florida's own version documents) come from each
  point's own nearest-track projection. `add_rail_network_treatment_definitions`
  adds `first_treat_year_same_route`/`_same_side` tiers alongside the
  point-only tier. CLI: `sweden data schools assemble-rail-network
  --budget-m --buffer-m` (requires `schools assemble` and `network
  preprocess-tracks` to have already run).

**One real bug found while building this, fixed retroactively in
algorithms 1-2 too**: a rail barrier's `element_id` is **not** a unique
row key (mirrors the network layer's own duplication pattern -- 827
distinct ids across 1,829 rows, confirmed live). The already-shipped
`is_nearest` flag from `match_barriers_point` had a latent bug from this:
comparing on `element_id` alone could mark more than one pair row
"nearest" for a school if two different barrier rows happened to share an
id. Fixed by adding `barrier_row` (positional row index, unambiguous) to
the pair table and keying both `is_nearest` and the new network-matching
functions on that instead. Required re-running `schools assemble` once
after this change (the fix is purely additive -- real counts were
unchanged) before `assemble-rail-network` could consume the pairs file.

**Real run** (2026-09-15, full national data, default budget/buffer):

| tier | schools ever-treated, rail |
|---|---|
| point-only (algorithms 1-2) | 1,454 |
| + same route (algorithm 4) | 1,059 |
| + same side (algorithm 5) | 749 |

Each tier is a strict refinement of the last, as expected. 7,910 pairs
checked; 6,201 (78%) fall inside their barrier's corridor (`same_route`),
2,552 (32%) are also on the matching side (`same_side`). Output:
`schools_rail_pairs_network.parquet` / `schools_rail_rollup_network.parquet`
(kept separate from the algorithms-1-2 files, not overwriting them).

**Known scope gap, not attempted**: the candidate track network has no
main-line/siding filter (Florida's `arterial_subset` equivalent) -- the raw
`Bantyp` (track-type) field has no data dictionary found this session, so
every open track with a real route id is a candidate, including any
yard/siding track that happens to carry one. Not expected to change the
`same_route` results much (sidings are typically short spurs near
stations, unlikely to host a noise barrier far from the main line), but
not verified.

### Algorithms 4+5 rebuilt on `_barrier_reference.py` (2026-09-23, supersedes the sections below)

`match_barriers_network` now runs on the shared
`src/regions/sweden/sources/_barrier_reference.py`, the same code the
`grid` output uses. Full rationale and validation:
[`../barrier_matching.md`](../barrier_matching.md).

- **Which stretch.** Found by exact key join on `element_id` + measures,
  not by the barrier midpoint's nearest row.
- **Corridor.** Grown ±800m along the network, with a long neighbouring
  segment cut to fit rather than dropped.
- **Side.** Decided by the first method that applies, stored per pair as
  `side_method`: `both_sides` (road) → `osm_offset` → `geometric_offset` →
  `track_offset` (rail) → `parallel_road` (road) → `unknown`.
- **Protected (2026-09-24).** A new `protected` tier means same side *and*
  beside the barrier's own stretch (±50m, within 600m of the road). Most
  `same_side` pairs lie hundreds of metres along the road past a barrier
  that is only ~70m long. Each pair also carries `lateral_m` /
  `along_offset_m`, so the cutoff can be varied. Every barrier within 1km
  of a school is judged, so a school counts as protected if any barrier
  protects it.
- **Unknown sides.** An unknown side is never counted as `same_side`. The
  rollup's `same_side_unknown` flags schools with any such pair, and the
  panel carries it as `{kind}_same_side_unknown`.
- **Interface.** The pair columns `school_side`/`wall_side` are gone.
  `run_schools_assemble_network(kind)` replaces the two per-kind functions.
  The CLI commands `assemble-road-network` / `assemble-rail-network` now
  load the barrier references saved by `barrier-protection build` (see
  [`../barrier_protection/README.md`](../barrier_protection/README.md)),
  and run in seconds. `--budget-m` / `--buffer-m` moved to that command.

**Real run (2026-09-24, final: through-line refinements, `both_sides`,
`track_offset` and the `protected` tier; see
`docs/data/sweden/barrier_matching.md` §7):**

| | road | rail |
|---|---|---|
| `same_route` pairs | 4,832 | 6,239 |
| … barrier side from `both_sides` / `osm_offset` / `geometric_offset` / `track_offset` / `parallel_road` / `unknown` | 210 / 1,028 / 7 / — / 2,759 / 828 | — / 597 / 18 / 2,088 / — / 3,536 |
| … pairs `same_side` / `same_side_unknown`* | 2,040 / 1,216 | 1,032 / 4,052 |
| … pairs `protected` / `protected_unknown` | 201 / 73 | 155 / 475 |
| schools `ever_treated_same_route` | 1,001 (was 967) | 1,063 (was 1,059) |
| schools `ever_treated_same_side` | **548** (was 869) | **214** (was 749) |
| schools `same_side_unknown` | 572 | 945 |
| schools `ever_treated_protected` | **143** | **77** |
| schools `protected_unknown` | 63 | 287 |

\*A pair is unknown when its barrier's side is unknown, or when the school
lies beyond the end of the barrier's through-line.

Of the schools that lost `same_side`, most now have an unknown side: 296
of 362 on road and 646 of 681 on rail. Only 66 road and 35 rail schools
now test as the wrong side, and 26 road and 21 rail schools gained
`same_side`. Before the rebuild, road filled unknown sides with a "same
side" default, and rail filled them with sub-millimetre noise signs.
`same_route` rose slightly because corridors no longer stop at the first
junction. Those loss/gain counts are from the first rewrite run
(2026-09-23), which gave 568 road and 121 rail; rail `same_side` has since
recovered to 214 through `track_offset`. Previous outputs are kept in
`data/sweden/_backup_pre_barrier_reference_2026-09-23/`.

> **Correction, 2026-09-23 (later the same day).** Parts of this section
> are wrong or incomplete. See
> [`../barrier_matching.md`](../barrier_matching.md) for the measured
> numbers.
>
> - **Rail.** Rail barrier geometry is *not* offset from the track: 99.7% of
>   rail barriers sit less than 1mm from their matched track. The rail sign
>   split quoted below is the sign of floating-point noise. Only 8 of the
>   749 rail `same_side` schools are backed by a barrier with a real offset.
> - **Road.** Road `same_side` defaults to "same side" when no sibling
>   carriageway is found. 364 of its 869 schools are treated only through
>   that default.
> - **The `side` attribute.** It is still not usable, but the 2026-09-18
>   rail test below was not a valid test of it. A valid road test shows no
>   signal beyond the base rate.
> - **What still holds.** The barrier → road/track *row* matching is right,
>   and it can be made exact via the shared `element_id` / measure keys.

### Road `same_side`: broken via signed offset (2026-09-18), FIXED via carriageway identity (2026-09-23)

**Real run** (2026-09-15, full national data, default budget/buffer,
2,080,116 candidate `bilnät` road segments):

| tier | schools ever-treated, road |
|---|---|
| point-only (algorithms 1-2) | 1,251 |
| + same route (algorithm 4) | 967 |
| + same side (algorithm 5), signed-offset method | 4 -- broken, see below |
| + same side (algorithm 5), carriageway-identity method | **869** -- current, see below |

**Why the signed-offset method (rail's own approach) fails for road.** Not a
matching bug -- a real, checked-not-assumed property of how road barrier
geometry is stored. Traced it by inspecting actual coordinates: **a road
barrier's own `LineString` shares exact vertices with its nearest
road-network segment** (confirmed live: barrier coordinate
`(632837.527, 6722447.406, 13.627)` appears verbatim inside the matched
road element's own coordinate list). Road barrier geometry is not an
independently-surveyed wall position offset to one side of the road -- it
reads as a copy of a stretch of the road centerline itself. Consequence:
`wall_side`'s signed offset is `0.0` (i.e. "on the centerline") for
**4,603 of 4,610 (99.8%)** same-route pairs -- the side comparison is
measuring noise, not a real left/right distinction, for road.

Checked rail for the same problem before trusting its own numbers -- it
doesn't have it: rail barriers' `wall_side` has a real three-way split
(`+1`: 2,645 / `-1`: 2,331 / `0`: 1,225 among same-route pairs -- mostly
genuine nonzero offset), confirming rail barrier geometry *is*
independently digitized, offset from the track. Rail's same_side result
(749 schools) was never affected by any of this; only road needed a
different approach.

**Candidate fix tried and REFUTED, 2026-09-18**: the barrier's own recorded
`side`/`side_code` attribute (see `noise_barriers/preprocess.py` -- 100%
populated for road) was floated as a substitute, unaffected by the
centerline-coincidence issue since it's a separate categorical field
Trafikverket assigns regardless of how the geometry is stored. Validated
at scale using rail as an independent check (rail carries the identical
`side` field, but rail's `wall_side` is genuinely non-degenerate -- see
above): across 949 rail barriers with a real geometric `wall_side`,
`side="left"` splits 227/245 and `side="right"` splits 228/246 between the
two geometric signs -- an almost exact coin flip, **no usable
correlation**. Checked and ruled out digitizing-direction inconsistency
(`network_tracks.parquet`'s own `start_measure`/`km_from_m` ordering is
~100%/98.8% monotonic, so reversed segments aren't the explanation) and
`side_code` (a redundant, sometimes-inconsistent duplicate of `side`, no
extra signal). Full analysis in
[`src/experiments/sweden/schools.ipynb`](../../../../src/experiments/sweden/schools.ipynb) §3.

**Real fix, 2026-09-23: carriageway identity instead of a signed offset.**
NVDB's own `Vägtrafiknät` spec states the reference line "follows the outer
lane on a divided road" -- i.e. a divided highway's two carriageways are
each digitized as their own separate line, not one shared centerline.
Checked directly against `road_network.parquet`: **100% of the 2,172 road
barriers sit <1m from some network row** (the centerline-coincidence
finding above, now understood as "snapped onto a specific carriageway's
line" rather than "no side information exists"), stable at 5 sample points
along **97.7%** of barriers' own length. **60.8%** of barriers have a
second, near-parallel (`|cos angle| > 0.9`), similar-length (`0.4x`-`2.5x`)
"sibling" row within 30m (median separation 9.6m, a plausible median-strip
width) -- geographically confirmed as real: reverse-geocoding two sampled
sibling-pair locations both landed on real numbered motorways (E18; a
named road near Kristianstad). A **reciprocal** check (candidate's own best
match must point back) keeps this honest -- only ~54% of one-directional
matches among barrier-touched rows are actually reciprocal, the rest
discarded as noise (ramps/frontage roads that look parallel from one side
only).

New `school_side`/`wall_side` semantics for road (see
`schools/assemble.py::match_barriers_network`'s docstring for the full
method): both columns hold a **network row index**, not a sign. `wall_side`
is the barrier's own exact-matched row. `school_side` is whichever of
{that row, its verified reciprocal sibling} the school point is physically
closer to -- or the wall's own row again (forcing equality) when no
verified sibling exists, i.e. an undivided road with nothing to be on the
wrong side of. Tested first with the school's own generic nearest-network
match (asking "is the school's nearest ANY road the wall's road or its
sibling") -- **refuted**: schools are typically well off the highway, so
their unconstrained nearest match is almost always some unrelated local
street (2,956 of 4,610 same-route pairs landed on a third element, only 2
directly on the wall's own row). Fixed by asking the *targeted* question
instead -- given the wall's specific carriageway pair, which of the two
specific lines is the school physically nearer to -- which is what ships.
Real result: among the 2,958 same-route pairs whose wall has a verified
sibling, a genuine **56%/44%** split (not the old method's near-total
collapse to "never same side").

**Bottom line**: `ever_treated_same_route` (967 schools) is still the most
inclusive road tier; `ever_treated_same_side` is now **869 schools** (up
from the broken method's 4, comparable in scale to rail's own 749/1,059)
and safe to use. `schools_road_pairs_network.parquet` /
`schools_road_rollup_network.parquet` regenerated 2026-09-23, plus
`schools_vanished_road_rollup_network.parquet` (26 of the 306 recovered
vanished schools now `same_side`, up from 0 -- see "Vanished-schools
coordinate recovery" below). `event_study_panel.parquet` re-joined the
same day -- `road_same_side` in the outcome panel is now **188
ever-treated schools** (previously a near-zero handful under the broken
signed-offset method, exact prior panel figure not re-checked this session
since `data/` isn't under version control -- the school-rollup-level 4 ->
869 comparison above is the directly-verified number), now on the same
order as `rail_same_side`'s 167.

## `build-lineage` — `skolenhetskod` reorg-lineage crosswalk: implemented 2026-09-22

`Skolenhetskod` is **not stable across school reorganizations**, and no
official crosswalk exists to fix it. When a school splits, merges, or is
renamed, `Skolenhetsregistret` retires the old unit (`Status=Vilande`) and
issues a brand-new `Skolenhetskod` for the successor at the same
coordinates — with no link between them, even in the raw API response.
Checked directly against Skolverket's own 2023 hemställan (Dnr 2022:854,
request to government to expand the register): it confirms more detailed
reorganization data is kept internally but **not published via the API**
("Registret innehåller i dag vissa detaljer som inte publiceras i API:et,
t.ex. mer detaljerade uppgifter om omorganisationer"). This isn't cosmetic
to `schools.csv` alone — SIRIS assessment history (`assessments/`) is keyed
by the same `skolenhetskod`, so a reorganized school's real outcome
history genuinely splits across old/new IDs.

`sweden data schools build-lineage` (`schools/lineage.py`) resolves the
unambiguous, high-confidence subset of that churn: 145 co-located location
groups nationally mix a `Vilande` unit with an `Aktiv`/`Planerad` one (the
churn signature); mutual-best normalized-name matching, requiring
`name_sim >= 0.8` and excluding "bare-digit twin" false positives
(`Vasaskolan 1`/`Vasaskolan 2` — two co-located sibling units sharing a
`startdatum`, not a rename, found by checking overlap with the regression
panel), resolves 40 of them into a crosswalk
(`schools/processed/skolenhetskod_lineage.csv`). `norm_name` also treats
Sweden's real särskola/grundsärskola -> anpassad grundskola/anpassad
gymnasieskola special-education terminology reform as one equivalence
class (`Vegalyckan särskola` <-> `Vegalyckan`) -- found by inspecting the
`0.5-0.8` review band directly rather than writing it off; net effect on
the national crosswalk was +6 (not the naively-expected +8: rebuilding
from scratch also demoted 2 links that had only cleared 0.8 because raw
`SequenceMatcher` gave partial credit for `"särskola"`/`"skola(n)"`
sharing letters as substrings, not real equivalence). The remaining
ambiguous or low-similarity churn is deliberately left unresolved — see
`src/experiments/sweden/schools_lineage.ipynb` §1-2 for the full investigation,
including why guessing there does more harm than leaving it alone.

`panel/assemble.py` applies this crosswalk with two different merge
policies (see that module's own docstring): the barrier-distance rollup is
purely geometric, so a lineage pair's rows are expected to already agree
and get merged losslessly (`ever_treated_*` OR'd, earliest
`first_treat_year_*`); outcome rows are each school's own reported
figures, which can legitimately differ for two co-located units that
coexisted for a time (111 `(year, outcome)` keys collide live), so a
retiring unit's row is only remapped onto its successor when that would
fill a real history gap, never to silently overwrite or duplicate a year
both already report.

### Full taxonomy: where `skolenhetskod` breaks, and how much of each

Two source populations:

| Source | Count |
|---|---|
| Registry (`schools.csv`, all statuses) | 10,648 |
| Assessment data (SIRIS, distinct schools with real outcomes, 1998-2019) | 2,651 |

Of the 2,651 assessed schools, **1,848 are still in the current registry**
(churn risk, table below) and **803 are absent from it entirely**
("vanished", second table). The other 8,800 registry schools were never
assessed at all — not an error, SIRIS only covers grundskola åk9.

**Within-registry churn** (a retiring `Vilande` unit + an `Aktiv`/
`Planerad` successor at the same coordinates) is a registry-wide
phenomenon, touching 445 registry codes total — but only 51 of those are
assessed schools, the population that actually matters for the panel:

| | Count | Disposition |
|---|---:|---|
| Mixed (churn-signature) location groups | 145 | base population |
| — ambiguous ties (>=2 equally-named candidates) | 23 | left unresolved |
| — resolvable via mutual-best name match | 122 | |
| — — reject (`name_sim < 0.5`) | 27 | not real lineage, dropped |
| — — review (`0.5 <= name_sim < 0.8`) | 30 | not auto-applied |
| — — confident (`name_sim >= 0.8`) | 64 | |
| — — — bare-digit-twin false positives | 24 | rejected |
| — — — **genuine, implemented** | **40** | ✅ `schools/lineage.py` |
| — — — — of which touch an assessed school | 14 | of the 40 |
| — — — — of which have both sides assessed (real split-identity) | 3 | of the 40 |

The 40-link within-registry crosswalk is implemented (`sweden data
schools build-lineage`).

### Vanished pre-registry schools: assessed, but no registry entry at all

**Cross-registry vanishing** (assessed, but no registry entry at all — not
even `Vilande`) is a separate, larger gap than the within-registry churn
above: **803 SIRIS-assessed schools have no entry anywhere in the current
registry snapshot.** 267 carry a legacy 9-digit `Skolkod` (the pre-2013
scheme, incompatible with the modern 8-digit format); 536 are modern
8-digit codes purged outright rather than kept as `Vilande`.

Two recovery approaches exist for this population — one exploratory, one
a real pipeline stage:

**Name+kommun matching against the current registry** (exploratory only,
no pipeline stage — full derivation, including every sample inspected to
justify each row below, in
`src/experiments/sweden/schools_lineage.ipynb` §3-4) matches each vanished
code's SIRIS-reported name and kommun against `norm_name`-normalized
registry names within the same kommun:

| | Count | Disposition |
|---|---:|---|
| Vanished codes (assessed, absent from registry) | 803 | base population |
| — legacy 9-digit `Skolkod` (pre-2013 scheme) | 267 | incompatible ID format |
| — modern 8-digit codes purged outright | 536 | not kept as `Vilande` |
| — no candidate in that kommun at all | 2 | kommun-code drift (e.g. Heby's 2007 län reform) |
| — tied exact match | 104 | genuinely ambiguous, unresolved |
| — untied exact match | 284 | |
| — — nationally distinctive name (<=3 schools share it) | 250 | high confidence |
| — — borderline (4-10 schools share it) | 21 | medium confidence |
| — — generic name (>10 schools share it) | 13 | low confidence |
| — near-exact, 0.9-0.999 | 119 | weak overlap, unresolved |
| — mid, 0.5-0.9 | 276 | weak overlap, unresolved |
| — low, <0.5 | 18 | plausible genuine closures |

`norm_name` (shared with the within-registry crosswalk above) treats a
standalone h/l/m grade-level-letter token — `RONNASKOLAN H`,
`Sånnaskolan LM` (högstadiet/mellanstadiet/lågstadiet, the letter-coded
equivalent of a numeric grade range) — as an equivalence class, the same
way it already strips numeric grade ranges; this raises the trusted-match
count here without changing the within-registry crosswalk at all, since
that matching is coordinate-anchored to one small candidate group, not a
whole kommun. A similar-looking idea does **not** work and is **not**
implemented: also treating a bare `F` (no digit) as a grade-range start,
e.g. `Skolan F-9`, commonly conflates two real, currently-active
grade-band split siblings (`Skolan F-3` and `Skolan 4-9` can be two
distinct schools sharing a name) into an identical normalized name — net
negative on this population, so `norm_name`'s digit-only range regex is
left as-is. See the notebook for the full comparison and worked examples
of both.

Even at its most confident (the 250 nationally-distinctive-name matches),
this approach only recovers a name and kommun, not coordinates — it can't
feed the barrier match without further work.

**Exact-`skolenhetskod` matching against Skolkoll** (`skolkoll/`,
implemented — see `docs/data/sweden/skolkoll/README.md`) is the real
pipeline stage for this population. Skolverket's own live
`Skolenhetsregistret` API is a snapshot with no history endpoint — a
purged code returns a 404 with no trace it ever existed — but Skolkoll, a
third-party aggregator of the same underlying `api.skolverket.se` data,
retains schools the live register has since purged, under its own
`status="UPPHORT"` (ceased) value, which never appears in our own
registry fetch at all. Matching the 803 vanished codes against Skolkoll by
exact `skolenhetskod` recovers a real WGS84 coordinate for **306 (38%)**
of them, all `status="UPPHORT"` — but only within the 536 modern 8-digit
codes (0 of the 267 legacy 9-digit ones, since Skolkoll's own ids are
themselves the modern format).

`panel/vanished_recovery.py` (`sweden data panel
recover-vanished-schools`) builds a small GeoDataFrame for the 306
recovered codes and runs it through the *same* `match_barriers_point`/
`match_barriers_rail_network`/`match_barriers_road_network` functions
`schools/assemble.py` uses for the registry population — no separate
matching algorithm, a second population through the existing one. Output
(`schools_vanished_{road,rail}_rollup_network.parquet`, `schools/assembled/`)
is picked up by `panel/assemble.py::load_treatment_rollup_with_recovery`,
concatenated onto the registry rollup before the outcome join — additive
and **optional** (falls back to the registry-only rollup unchanged if this
stage hasn't been run), unlike every other panel input, since the panel
already produces a complete, working result without it.

Of the 306 recovered schools: road barriers 40 ever point-treated / 31
`same_route` / 26 `same_side` (rerun 2026-09-23 after the carriageway-identity
fix above — was 0 under the old broken signed-offset method); rail barriers 34
point-treated / 28 `same_route` / 22 `same_side`. These schools
previously had every treatment column hard-coded `False` for lack of any
coordinates — recovered ones now get a genuine `True`/`False` from real
distance, the rest genuinely (not by default) still `False`.

## Open questions (not blocking, flag for whoever builds this)

1. Confirm whether `Skolenhetsregistret` v2 differs materially from v1
   (deprecation timeline makes v2 the right build target either way).
2. ~~Confirm how school closures are represented~~ — resolved 2026-09-22:
   closures are represented (`Status=Vilande`), but reorganizations create
   a brand-new `Skolenhetskod` with no closure-to-successor link in the
   public data at all. See `build-lineage` above.

## Relationship to the existing exposure sources

`noise_barriers` (`data/sweden/noise_barriers/`) has road + rail barrier
segments (SWEREF99, matching `Skolenhetsregistret`'s own
`Koordinat_SweRef_E/N`), and `network` has the rail network for
side-of-track matching (not yet used by `assemble` -- only point-distance
algorithms 1-2 are implemented, Florida's road/rail-network-aware
algorithms 3-5 would be a future refinement, same stretch-goal status
`road_network`'s algorithm 6 has in Florida).
