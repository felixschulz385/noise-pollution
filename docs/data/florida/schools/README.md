# Florida — `schools` source (design & findings)

Status: **design** (2026-09-10). Nothing implemented yet. This page is the
step-1 findings dump; implementation follows in the order fetch → notebook →
preprocess.

## Purpose

Build the **school spine** for the barrier-construction event study: a stable
per-school identity keyed on the FLDOE **`msid`** (2-digit `DISTRICT` + 4-digit
`SCHOOL` = 6 chars — the key the assessment workbooks use), carrying geometry,
the NCES `NCESSCH` crosswalk, an operation (open/close) panel, and school-type
classification. Then, in a second stage, the school ↔ barrier ↔ road-network
match that produces per-school treatment timing.

`schools` **absorbs the former `master_file` source** (see
[Migration](#migration-removing-master_file)) **and the planned `school_panel`
module**: because the time-varying school covariates of
[covariates.md](../covariates.md) Cluster A (enrollment, %FRL, race shares,
%ELL, %SWD, pupil–teacher ratio, charter/magnet/Title I) share this source's key
(`NCESSCH`), access method (Urban Institute Education Data API), grain
(school-year), and year span, they are produced here rather than in a separate
module that would only re-cross the same dependency. See
[Combining `school_panel`](#combining-school_panel).

### Outputs

| File | Layout | Grain | Requires | Written by |
|---|---|---|---|---|
| `processed/school_cross_section.parquet` | GeoParquet, EPSG:3087 | one row per `msid` | — | preprocess stage 1a |
| `processed/school_year_panel.parquet` | GeoParquet, EPSG:3087 | one row per `msid × year` (identity + operation + Cluster-A covariates) | — | preprocess stage 1a (spine) + 1b (covariates) |
| `assembled/schools_treatment.parquet` | Parquet | one row per `(msid, gcid)` candidate pair | `noise_barriers` | preprocess stage 2 |
| `processed/schools.json` | JSON | — | — | provenance sidecar (mirrors `barriers.json`) |

`schools_treatment.parquet` is the file joined onto `assessments.parquet` later
(on `msid`, then collapsed to a per-school treatment definition in the analysis
layer).

---

## Decisions locked (2026-09-10)

| Question | Decision |
|---|---|
| Coordinate source | **MSID `LATITUDE`/`LONGITUDE` primary**, EDGE via crosswalk as fill + QA, geocoded `PHYSICAL_ADDRESS` last. Not redundant with the API — see below. |
| `master_file` | **Removed**; its MSID fetch becomes the `msid` subsource of `schools`. |
| `school_panel` (covariates.md Cluster A) | **Merged into `schools`** — same key / API / grain / year span. Produced by `preprocess` stage 1b into `school_year_panel.parquet`. `school_panel` drops out of covariates.md as a separate module. |
| MSID issues | **One current issue** for now. Caveat documented: no per-year status history. |
| Urban API endpoints | `ccd/directory` + `ccd/enrollment` **run by default**; `crdc` + `edfacts` are subsources too but **off by default** for the first pass (biennial / different structure — add once CCD works). `fetch --subsource` selectable. |
| Year span | **1990–2026** where available (CCD directory reaches back to the late 1980s; assessment outcomes currently only 2015+). |
| Panel time index | **Assessment "spring year"** (e.g. 2015 = 2014–15 school year). CCD/Urban `year` = fall of that school year, so `spring_year − 1`. |
| Attribute disagreement | **Set `NA`** (applies to `in_operation` and to conflicting attributes). |
| Per-year coordinates | Only if the notebook detects material relocations; otherwise one static point in the cross-section. |
| School universe | **Keep all MSID rows, add flags** (no filtering). |
| Virtual / district-wide schools | Kept, flagged `no_physical_location`. |
| Output CRS | **EPSG:3087** (matches `barriers.parquet`; no reprojection downstream). |
| Stage-2 road model | **FDOT RCI roadway network** (aligns with barrier `fed_route` linear referencing), not OSM. |
| Stage-2 grain | One row per `(msid, gcid)`; a treatment-status column per matching algorithm. |
| `built_year` unknown | `treat_year = NA`, `timing_unknown = True`. |
| `REPLACED` walls | Use the **original** construction year (`built_year` as carried from `FED_YRCON`). |
| Non-FDOT `other_wall` | `treat_year = NA`; carried as a shielding covariate, never as treatment. |

---

## Inputs / subsources

`fetch` runs these sequentially. `--subsource` selects; **default = `msid`,
`edge`, `ccd_directory`, `ccd_enrollment`**. `crdc` and `edfacts` are wired but
**not in the default set** (see [Combining `school_panel`](#combining-school_panel)).

### `msid` — FLDOE Master School ID (folded in from `master_file`)

FLDOE EDS ColdFusion app, empty POST to `Downloads/All_schools.cfm`, browser
User-Agent only (`eds.fldoe.org` has no bot wall). Body is TSV despite the
`.xls` label. Writes `raw/MSID_all_schools.tsv`.

**Findings from the fetched `all_schools` (7 204 rows × 77 cols, active + closed + future):**

| Field(s) | Finding | Use |
|---|---|---|
| `DISTRICT` (2) + `SCHOOL` (4) | the `msid` key; no year stamp on the file | spine key |
| `FEDERAL_DIST_NO`, `FEDERAL_SCHL_NO` | **100% populated**; `FEDERAL_DIST_NO` is the 7-digit NCES `LEAID` (`12` + 5), `FEDERAL_SCHL_NO` the in-district school number. `0` sentinel in **676 rows (9.4%)** | **crosswalk to `NCESSCH`** — see below |
| `LATITUDE`, `LONGITUDE` | `0.0`/`0.01` sentinels in ~18% overall — but **6% of `ACTIVITY_CODE=A` (active), 38% of `C` (closed), 89% of `F` (future)** | primary coordinate, gap filled from EDGE |
| `ACTIVITY_CODE` | `A` active 4 783 / `C` closed 2 270 / `F` future 151 — a clean current status, but a snapshot, not per-year | operation flag (current) |
| `DATE_OPENED` / `DATE_CLOSED` | `DATE_OPENED` null for 4 453 (opened before tracking); `DATE_CLOSED` null for 5 003 | operation windows for the panel |
| `TYPE` (0–7), `GRADE_CODE` (81 coded values), `SCHL_FUNC_SETTING` (Z/D/V/B/P/T/N/H…), `PRIMARY_SERV_TYPE` (R/B/O/S/A/V), `CHARTER_SCHL_STAT`, `MAGNET_STATUS` | classification fields — **need the MSID code dictionary** to label | school-type flags |
| `TITLE_I_STATUS` | **entirely null** in this export | Title I must come from CCD/EDFacts, not MSID |
| `SCHOOL_NAME_LONG` / `_SHORT` | name (not `SCHOOL_NAME`) | label, fuzzy-match fallback |

### `edge` — NCES EDGE public-school geocode

Already downloaded: `data/florida/schools/EDGE_GEOCODE_PUBLICSCH_2425.zip`
(`Shapefile_SCH.zip` + xlsx + txt + sas7bdat). Keyed on `NCESSCH`, address-
geocoded lat/lon with a precision flag. `fetch` registers the local zip (and can
pull additional vintages from the NCES EDGE site — files exist per school year
from ~2015-16; earlier coordinates come from CCD directory `LATCOD`/`LONCOD`
instead, sparser).

### `ccd_directory`, `ccd_enrollment`, `crdc`, `edfacts` — Urban Institute Education Data API

`https://educationdata.urban.org/api/v1/schools/{source}/{endpoint}/{year}/?fips=12`
— no key, JSON, paginated, one record per school-year (`NCESSCH`). Cache each
pulled year to `raw/<source>_<endpoint>_<year>.parquet` plus a `raw/api_query.json`
sidecar (source, endpoint, years, filters, pull date) so `preprocess` is
offline-reproducible.

| Subsource | Endpoint(s) | Supplies | Default? |
|---|---|---|---|
| `ccd_directory` | `schools/ccd/directory` | name, status, charter/magnet, **Title I**, locale, grade span, lat/lon, `state_leaid`/`state_school_id` (crosswalk QA) | yes |
| `ccd_enrollment` | `schools/ccd/enrollment` (+ `race`/`sex`/`grade` disaggregations) | annual membership; race shares; **pupil–teacher ratio** (teacher FTE ÷ membership) | yes |
| `crdc` | `schools/crdc/enrollment`, `.../directory` | **%ELL, %SWD (IDEA), %gifted**, discipline (later) — **biennial** (2000, 2004, 2006, 2009-10, 2011-12, … 2020-21), some items sampled | **no — first pass** |
| `edfacts` | `schools/edfacts/...` | LEP / IDEA subgroup counts, proficiency (robustness cross-check) — its own subgroup structure | **no — first pass** |

**Annual grain confirmed** for CCD (one base record per school-year). `crdc` /
`edfacts` are deferred from the default set for the first implementation pass —
add them once CCD directory + enrollment are working end to end. `%FRL` note:
CCD FRPL counts moved to CEP-affected reporting after ~2015; carry the raw count
+ a `frpl_cep_flag`, defer the reconciliation to stage 1b.

Cluster-A covariates from these subsources are tidied in `preprocess` **stage 1b**
and written into `school_year_panel.parquet` — no separate `school_panel`
module. Membership/FRPL suppression and imputation flags are handled there.

### Stage-2 only: `noise_barriers` + FDOT RCI network

`noise_barriers/processed/barriers.parquet` (GeoParquet, EPSG:3087, one row per
`gcid`, `built_year`, `category ∈ {fdot_barrier, other_wall}`, `height_m`,
`fed_route`, …). Plus the **FDOT RCI roadway network** (a new small fetch, or
reuse from a future `traffic` source) for linear referencing — same system the
barriers' `fed_route` uses.

---

## The crosswalk: `msid` ↔ `NCESSCH`

**Primary path (embedded in MSID, no external matching):**

```
ncessch = FEDERAL_DIST_NO.zfill(7) + FEDERAL_SCHL_NO.zfill(5)     # 12 chars
valid when FEDERAL_DIST_NO != "0" and FEDERAL_SCHL_NO != "0"
```

Verified against `school_barrier_features.parquet`: MSID `DISTRICT=1 SCHOOL=31`,
`FEDERAL_DIST_NO=1200030 FEDERAL_SCHL_NO=2` → `120003000002` = the EDGE `NCESSCH`
for "Carolyn Beatrice Parker Elementary". ~9.4% of rows carry the `0` sentinel
(expected: closed / pre-NCES / non-reporting) and fall to the fallback.

**Fallback ladder for `0`-sentinel and any unmatched rows:**

1. CCD directory match on `state_school_id` (FL `ST_SCHID`) → `NCESSCH`, per year.
2. Name + district + coordinate-proximity fuzzy match to CCD.
3. No NCES linkage — row kept in the spine, `ncessch = NA`, excluded from any
   NCES-covariate join downstream.

**Verification plan (notebook, step 3) — "how to check all crosswalk requirements":**

- Compose `ncessch` as above; tabulate the `0`-sentinel / NA rate by
  `ACTIVITY_CODE` and by `DATE_OPENED` decade.
- Pull CCD directory FL for 1990 / 2000 / 2010 / 2015 / 2023; measure overlap of
  the composed IDs with CCD `ncessch`; inspect unmatched (type, era).
- **NCESSCH stability:** for schools in ≥2 EDGE/CCD years, does `ncessch` ever
  change for a fixed `msid`? (decides static vs per-year crosswalk).
- **Collisions:** duplicate composed `ncessch` within MSID (a few `FEDERAL_SCHL_NO`
  values repeat — check district disambiguation); duplicate `msid`.
- **Coordinates:** haversine(MSID, CCD) for matched rows; flag > 250 m; count
  MSID `0.0` nulls that EDGE fills.
- **Against `assessments.parquet`:** every assessment `msid` present in the
  spine; dump the residual list.

---

## Coordinates — source ladder

Per school: (1) MSID `LATITUDE`/`LONGITUDE` if `> 1` (drops the `0.0`/`0.01`
sentinels); else (2) EDGE `LAT`/`LON` via `ncessch`; else (3) CCD directory
lat/lon via `ncessch`; else (4) geocoded `PHYSICAL_ADDRESS` (Census batch →
Nominatim); else (5) `NA`, flagged. Record `geom_source` and, where available,
the EDGE precision flag. Store as an EPSG:3087 point.

**Is MSID coordinate redundant given the Urban API?** No. MSID covers 94% of
*active* schools directly and includes closed/historical schools that never
appear in a recent EDGE file; the API/EDGE coordinates mainly *fill the
closed-school gap* and serve as a cross-check. They are complementary, not
substitutes.

**School polygons (future refinement, not v1):** point geometry ships in v1.
Candidates for footprints later, best first:
- **Florida statewide parcels** (FL Dept. of Revenue cadastral, published via
  **FGDL** — same host as `noise_barriers`), filtered to institutional / school
  DOR use codes (83xx). Authoritative site boundaries, statewide, historical
  vintages.
- **Microsoft US Building Footprints** (open, ML-derived) — building-level, no
  school attribute; spatial-join to the school point.
- **OSM** `amenity=school` ways/relations via Overpass — mixed footprint/site,
  uneven coverage.
- NCES EDGE is points only (its SABS attendance-boundary one-off is catchment,
  not the building).

---

## Panel semantics

- **Time index** = assessment *spring year*. Panel year `Y` ↔ school year
  `Y−1/Y` ↔ Urban/CCD `year = Y−1`. Document this offset at the join.
- **Span** = 1990–2026, parameterised. Outcomes currently exist only 2015+; the
  earlier years are pre-provisioned for a longer pre-period / SEDA robustness.
- **`in_operation[msid, year]`** derived from `DATE_OPENED`/`DATE_CLOSED`,
  cross-checked against CCD `SY_STATUS` and against whether the `msid` appears in
  that year's assessment file. **Disagreement → `NA`** (not a guess).
- **Time-varying columns:** with a single MSID issue, genuinely time-varying =
  `{in_operation}` + anything sourced from CCD directory year-by-year (status,
  charter/magnet, Title I, grade span, name). MSID contributes the static spine
  (identity, `msid`↔`ncessch`, best coordinate, open/close dates, type flags).
  On MSID-vs-CCD conflict for a static attribute → `NA` + a `*_conflict` flag.
- **Coordinates in the panel:** static (from the cross-section) unless the
  notebook finds material moves, then per-year.
- **Caveat (single MSID issue):** charter/magnet/Title-I/type *changes* before
  the issue date are only visible through CCD, and a school's pre-issue type is
  taken as its current type. Collecting an annual MSID series (FLDOE reissues
  yearly; older issues on request) is the fix, deferred.

---

## School universe — keep all, flag

No filtering. Add boolean/categorical flags from the classification fields
(pending the MSID code dictionary for exact labels):

- `is_regular` — regular school (vs alternative / ESE centre / DJJ / hospital-
  homebound / adult), from `PRIMARY_SERV_TYPE` / `SCHL_FUNC_SETTING` / `TYPE`.
- `is_charter` — `CHARTER_SCHL_STAT != 'Z'`.
- `is_magnet` — `MAGNET_STATUS in {'P','S'}`.
- `is_virtual` / `no_physical_location` — `SCHL_FUNC_SETTING`/`PRIMARY_SERV_TYPE`
  virtual codes; also set when geometry falls back to a district-office address.
- `grade_low` / `grade_high` — decoded from `GRADE_CODE`.
- `serves_tested_grades` — grade span overlaps 3–10.
- `activity_code`, `type_code` — carried raw alongside the decoded flags.

The analysis layer chooses the estimation sample from these; the source keeps
everyone.

---

## `fetch` — implemented (step 2)

`python -m src.cli florida data schools fetch` — module at
`src/regions/florida/sources/schools/{shared,fetch}.py`, handler
`command_schools_fetch`. Hand-wired (no `DataSource` base yet — deferred; this
would be the first source to need it).

- **`--subsource`** repeatable, `choices = msid, edge, ccd_directory,
  ccd_enrollment, crdc, edfacts, all`. No flag → default set
  (`msid, edge, ccd_directory, ccd_enrollment`); `all` → every one. Runs in
  `SUBSOURCES` order regardless of flag order. (In code, `subsources=None` →
  default, `[]` → nothing.)
- **`msid`** — `_msid_post_download`: empty POST to the EDS ColdFusion endpoint
  with a browser UA, validates the `DISTRICT\t` prefix, writes
  `raw/MSID_<dataset>.tsv`. `--msid-dataset` repeatable (default `all_schools`).
  **Verified working** from this environment.
- **`edge`** — `_fetch_edge`: if `raw/EDGE_GEOCODE_PUBLICSCH_<vintage>.zip`
  exists → `already-present`; else adopt a hand-placed zip sitting in
  `data/florida/schools/` → move into `raw/`; else best-effort download from
  `nces.ed.gov`. Validates the `PK\x03\x04` zip magic. `--edge-vintage`
  (default `2425`). **Verified** (adopts the existing local zip).
- **`ccd_directory` / `ccd_enrollment` / `crdc` / `edfacts`** —
  `_fetch_api_subsource`, `--years LO:HI` (default `1990:2026`), one
  `raw/<subsource>_<year>.parquet` per year, plus `raw/api_query.json`
  (pulled_at, base, range, per-subsource route/path/params/years/rows). Skip
  years already in `raw/` unless `--refresh`. **`--via {auto,api,csv}`**
  (default `auto`) picks the route:
  - **`csv`** — `_fetch_api_via_csv`: download the static flat file(s) under
    `educationdata.urban.org/csv/<class>/<file>` to `raw/_csv_source/` (one file
    can be ~1 GB — all years, all states; `_download_with_resume` does Range
    resume + retry), then chunk-read, keep `fips == 12` in the year range, split
    to per-year parquet. **Survives `/api/v1/` outages** (the CDN files stay up).
    Known file: `ccd_directory` → `schools_ccd_directory.csv`; the others need
    their filenames from `/api/v1/api-downloads/?endpoint_id=…` (API must be up)
    — until then `--via csv` for them records an error and `auto` falls through
    to REST.
  - **`api`** — `_fetch_api_via_rest`: paginate the JSON API (`_get_all_pages`
    follows `next`, `_get_json` retries 429/5xx/transport 4× with backoff),
    filtered `?fips=12` server-side.
  - **`auto`** — CSV first, REST for the years CSV didn't produce.
  - Per-year HTTP 404 / empty → `years_unavailable` (not an error); other
    failures → `errors`, year skipped. Result carries `route` (`csv` / `api` /
    `csv+api`).
- **Status of live verification.** `msid` + `edge` verified working. The API
  subsources are **unverified end-to-end**: there is **no official Python
  client** (only the R `educationdata` package), Urban's entire `/api/v1/` (data
  *and* metadata) was returning **HTTP 502 for hours** during step 2 — which also
  breaks the R client — and the ~1 GB CSV flat file was truncated by this
  sandbox's egress limits. Both routes will work from an unthrottled machine.
  The **real `ccd/directory` schema was captured** from the CSV header: 52
  columns incl. `ncessch`, `latitude`/`longitude`, `enrollment`, `teachers_fte`,
  `free_lunch`/`reduced_price_lunch`/`free_or_reduced_price_lunch`,
  `title_i_status`, `charter`, `magnet`, `virtual`, `lowest_grade_offered`/
  `highest_grade_offered`, `seasch`, `county_code`, `cbsa`,
  `urban_centric_locale`, `school_status` — so `ccd_directory` alone covers most
  of Cluster A; `ccd_enrollment` is only needed for race/sex shares. See the
  column notes in `API_SUBSOURCES` (`schools/shared.py`).
- **`--from-file`** — copies a hand-downloaded file into `raw/` (skips if it is
  already the destination); subsource inferred from the name by `scan_raw`.
- `fetch` never calls another source's fetch. Return JSON carries per-subsource
  results, `errors`, `present` (`scan_raw`), and `state`
  (`present` / `partial` / `missing`); `state == missing` attaches
  `MANUAL_DOWNLOAD_STEPS`.

**Runtime note.** `--via csv` (default preference): each flat file is a
one-time ~1 GB download to `raw/_csv_source/` (cached, reused unless
`--refresh`), then seconds to filter/split. `--via api`: a full 1990–2026 pull
is ~thousands of paginated requests (FL ~4–5k schools/year, page size 100, not
adjustable) — minutes to tens of minutes, cached per year. Narrow with
`--years` for a quick pass either way.

---

## `preprocess` design (steps 3–4)

### Stage 1a — spine → `school_cross_section.parquet` + panel skeleton

1. Load MSID; build `msid`, compose `ncessch`, run the fallback ladder.
2. Resolve the coordinate ladder → EPSG:3087 point + `geom_source`.
3. Decode classification fields → flags.
4. Cross-section = one row per `msid` (identity, ncessch, geometry, dates, flags,
   static CCD attributes as of the latest CCD year).
5. Panel skeleton = cross-section ⨯ years 1990–2026, add `in_operation` and the
   year-varying CCD *directory* attributes (status, charter/magnet, Title I,
   grade span, name). Keep `in_operation == NA` rows, flagged.
6. **Validation** (mirror `assessments.ipynb`): no dup `msid`; no dup
   `(msid, year)`; coords inside the FL bbox; crosswalk match-rate reported;
   `in_operation` vs assessment-appearance agreement; `geom_source` breakdown;
   every assessment `msid` present.

### Stage 1b — Cluster-A covariates → merged into `school_year_panel.parquet`

Depends on 1a's panel skeleton + the `ccd_enrollment` (and, when enabled, `crdc`
/ `edfacts`) raw pulls. Isolated from 1a so covariate-definition changes don't
re-run the spine (or stage 2).

1. Tidy `ccd_enrollment` → total membership, race shares, teacher FTE,
   pupil–teacher ratio; `%FRL` with `frpl_cep_flag`.
2. When enabled: `crdc` → `%ELL`, `%SWD`, `%gifted` (biennial → forward-fill to
   the next CRDC wave, flagged `crdc_year`); `edfacts` → LEP/IDEA counts,
   proficiency cross-check.
3. Left-join onto the panel skeleton on `(ncessch, year)`; carry suppression /
   imputation flags; **lag nothing here** — lagging to t−1 is an analysis-layer
   choice (see covariates.md).
4. **Validation:** join rate onto the skeleton; race shares sum ≈ 1; `%FRL` and
   `%SWD` in [0, 1]; membership vs assessment `n_students` sanity.

### Stage 2 → `schools_treatment.parquet` (REQUIRES `noise_barriers`)

One row per `(msid, gcid)` candidate pair (a school × a nearby wall), with a
treatment column per matching algorithm plus shared geometry columns
(`dist_m`, `road_id`, `same_route`, `school_side`, `wall_side`, `built_year`,
`treat_year`, `timing_unknown`, `category`). Collapsing to a per-school
treatment (ever-treated, first `treat_year`, dose) happens in the analysis layer
after the join to `assessments.parquet`.

**Matching algorithms — increasing rigour** (v1 = 1–3; 4–6 staged):

| # | Name | Definition | Needs |
|---|---|---|---|
| 1 | `euclid_nearest` | straight-line school→wall distance; treated if ≤ B, B ∈ {100,200,300,500,1000} m | points only |
| 2 | `buffer_dose` | Σ wall length & count within B; continuous | points only |
| 3 | `road_gated` | nearest RCI major road to school (≤ R); treated only if a wall on *that* road is ≤ B from the school | RCI network |
| 4 | `same_segment` | project school & wall to RCI; same `ROADWAY`/route within ±D milepost AND school perpendicular offset ≤ P | RCI linear ref |
| 5 | `same_side` | (4) + wall between school and carriageway (signed-offset test); median walls count both sides | RCI centerline + geometry |
| 6 | `shielded_arc` | fraction of the school→road sightline arc blocked by walls, optionally weighted by `height_m` / barrier-attenuation geometry (ISO 9613-2) | (5) + carriageway geometry, DEM optional |

**Side-of-road / carriageway — what it means.** Divided highways have two
directional roadbeds separated by a median; a noise wall runs along one outer
edge (rarely, the median). A school is shielded only by a wall on **its** side —
a wall on the far carriageway can be just as close in straight-line distance
(narrow highway, school near the ROW) yet give that school zero attenuation.
Correct assignment therefore needs (a) which side/carriageway each wall is on,
(b) which side of the road the school is on, (c) count only same-side walls, plus
median walls for both. **Source:** check whether `noise_barriers` raw carries a
roadbed / side / RCI `RID` field (`noise_barriers preprocess` currently keeps
`fed_route` but not a side field — TODO). If absent, derive both from geometry:
signed perpendicular offset of the wall and of the school point relative to the
RCI route centerline; equal sign ⇒ same side. This is algorithm 5.

**Treatment-timing rules:**

- `treat_year = built_year` of the matched wall. `built_year` is the **original**
  construction year (`FED_YRCON` per the barriers field dictionary), windowed
  1990–2026 by `noise_barriers preprocess`.
- `built_year` is `NA` → `treat_year = NA`, `timing_unknown = True`. The pair is
  kept (usable in cross-sectional "ever near a wall" specs) but excluded from
  event-time estimation until dated. Dating `NA` walls via FGDL release-diffing
  is a later robustness step (noted in `noise_barriers`).
- `REPLACED BARRIERS` → original year (`built_year` as carried). **TODO:** confirm
  `FED_YRCON` is not overwritten with the replacement date for these rows.
- `category == 'other_wall'` (private / perimeter, non-FDOT) → `treat_year = NA`;
  carried as a potential noise-shielding **covariate**, never as treatment.
- `REMOVED` / `RECOMMENDED` / `PLANNED` never reach here (dropped in
  `noise_barriers preprocess`).

---

## Combining `school_panel`

`school_panel` (covariates.md Cluster A — time-varying school covariates) is
**not built as a separate module**; it is `preprocess` stage 1b here. Rationale:

- Identical **key** (`NCESSCH`, from the MSID-embedded crosswalk), **access
  method** (Urban Institute Education Data API), **grain** (school-year), and
  **year span** (1990–2026) as this source.
- A separate module would `REQUIRES schools` for the spine, the crosswalk and the
  operation panel — an artificial boundary immediately re-crossed.
- `schools` already pulls `ccd_enrollment`; `crdc` / `edfacts` are just more
  endpoints on the same API → more subsources, not a new source.
- The covariates land in `school_year_panel.parquet`, which this source already
  emits. Two sources writing overlapping columns into school-year panels is worse.

**Isolation guarantees the merge is free:** stage 1a (spine) → 1b (covariates) →
2 (barrier treatment) are separate steps with separate inputs. Editing a
covariate definition re-runs 1b only — never the spine or the expensive
geospatial stage 2.

**Caveats recorded:**

- `crdc` is **biennial** with some sampled items; `edfacts` has its own subgroup
  structure. Both are **off by default** for the first implementation pass — wire
  them, enable once CCD directory + enrollment work end to end.
- CCD `%FRL` reporting is distorted by CEP after ~2015 — carry the raw count +
  `frpl_cep_flag`, reconcile in 1b.
- The **fetch half** of the CCD/CRDC/EDFacts pull is a national dataset and may
  later move to a shared `src/core` sources area (as flagged in covariates.md for
  `staff` / `air_quality` / `neighbourhood` too). Merging now does not block that
  — the fetch functions can be lifted to `core` and called from here when the
  per-region source registry lands.

---

## Open questions / TODO

- MSID code dictionary for `TYPE`, `GRADE_CODE`, `SCHL_FUNC_SETTING`,
  `PRIMARY_SERV_TYPE`, `CHARTER_SCHL_STAT` (FLDOE MSID appendix).
- Urban data: `ccd/directory` schema is known (52 cols, see `API_SUBSOURCES`).
  Still to confirm on a healthy API/machine — the `ccd/enrollment`, `crdc`,
  `edfacts` CSV filenames (from `/api/v1/api-downloads/?endpoint_id=…`), their
  column names, the REST-route disaggregation params, and the earliest FL year
  with data. Do a full `--via csv` run once (the ~1 GB flat file was truncated
  by the sandbox here) to confirm the split. Edit `API_SUBSOURCES` in
  `schools/shared.py`, not the fetch loop.
- `ccd_directory` vs `ccd_enrollment` overlap: directory already carries
  enrollment/FRPL/FTE/Title I — decide in the notebook whether `ccd_enrollment`
  is worth pulling at all beyond race/sex shares.
- NCESSCH stability across years → static vs per-year crosswalk.
- `noise_barriers` raw: is there a roadbed/side/`RID` field to lift into
  `barriers.parquet` for algorithms 5–6?
- `FED_YRCON` semantics for `REPLACED` rows.
- FDOT RCI network: standalone fetch here, or wait for a `traffic` source and
  share it?
- `DataSource` base class now vs later.

---

## Migration: removing `master_file`

`master_file` had `fetch` only (`preprocess` was always "TBD in notebook"), so
folding it in is low-cost:

1. Move `src/regions/florida/sources/master_file/{fetch,shared}.py` logic into
   `schools/` as the `msid` subsource; delete the `master_file` package.
2. Remove the `florida data master-file` CLI subtree; add `florida data schools`.
3. Repoint: `assessments`' prerequisite `master_file` → `schools`; update
   `docs/data/florida/README.md` (drop the `master_file` row, rewrite the
   `schools` row), `docs/data/florida/covariates.md` (the `schools` module row —
   note the crosswalk is embedded in MSID), and `.github/CODEOWNERS` if it names
   the path.
4. `data/florida/master_file/raw/MSID_all_schools.tsv` moves to
   `data/florida/schools/raw/`.
