# Florida — `schools` source (design & findings)

Status (2026-09-11): **`fetch`, `preprocess` (stages 1a+1b) and `assemble`
(stage 2) all implemented and passing** against the real fetched data (95 tests
green in the `311` conda env). `python -m src.cli florida data schools
preprocess` writes `school_cross_section.parquet` / `school_year_panel.parquet`;
`... schools assemble` writes `schools_treatment.parquet` +
`schools_treatment_rollup.parquet` (REQUIRES `noise-barriers preprocess`).
`src/experiments/florida/schools.ipynb` now **imports**
`schools/{preprocess,assemble}.py` (the way `assessments.ipynb` imports its
parser) and is investigation-only — the pipeline logic lives in the module,
with unit tests in `tests/regions/florida/test_schools_{preprocess,assemble}.py`.
The FLDOE MSID code tables (`schools/msid_codes.py`, from
`0101172-msid.pdf`, Appendix A/B) replaced every provisional decode. Build
order: fetch → notebook (prototype) → preprocess/assemble (**done**).

Still open, non-blocking (see [Open questions / TODO](#open-questions--todo)):
the `road_network` source for matching algorithms 3–6.

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
| Urban API endpoints & routes | `ccd_directory` → **`--via csv`** (one 1 GB all-years file). `ccd_enrollment` (`/grade-99/race/`), `crdc` (`/disability/sex/`), `edfacts` (`/grade-99/`) → **`--via api` with `?fips=12`** (their CSV flat files are 0.5–1 GB *per year*). `ccd_directory` + `ccd_enrollment` default; `crdc` + `edfacts` opt-in. |
| MSID vs CCD attribute conflict | Where a non-`in_operation` attribute (name, status, grade span) disagrees between MSID and CCD → **`NA`** + a `*_conflict` flag. |
| Year span | **1990–2026**. CCD directory/enrollment reach 1986+; CRDC is 6 biennial years (2011–2021); EDFacts 2009–2020; assessment outcomes 2015+. |
| Panel time index | **Assessment "spring year"** (2015 = the 2014–15 school year). Urban `year` conventions: **CCD directory + CCD enrollment** = fall of the school year → `spring_year = year + 1`. **CRDC** `year` = fall of the collection year → `+ 1` (**confirmed** against the Urban CRDC codebook — `year` is defined there as "Academic year (fall semester)", the same convention as CCD). **EDFacts** `year` **is** the spring year → no offset. |
| CRDC 2021 raw-pull duplicates | `crdc_2021.parquet` had **50,592 fully-duplicate rows** (63% of the file — every `disability ∈ {1,2}` row doubled, `disability == 99` clean; likely an overlapping page from `_get_all_pages` on that year's unusually large pull), which silently **doubled `pct_swd` for spring year 2022** (median 0.14 → 0.29, 3.6% of rows > 1). `_load_year_parquets` now drops exact-duplicate rows for every CCD/CRDC/EDFacts source — harmless everywhere else, since no other file has any. |
| Coordinate disagreement | When MSID and EDGE lat/lon are both present, **EDGE wins** (address-geocoded); keep `geom_disagree_m` and flag > 250 m for QA. Coordinate ladder: EDGE → MSID → (geocode, later) → none. |
| Geocoding the ~240 unplaced active schools | **Deferred** — `preprocess` leaves a `geocode_pending` flag and a placeholder; `PHYSICAL_ADDRESS` geocoding (Census batch → Nominatim) is a follow-up. |
| MSID code tables | **Resolved** — the FLDOE *MSID Application Guidelines* PDF (`0101172-msid.pdf`, at the repo root) Appendix A (record layout, per-item domain values) + Appendix B (113 grade codes) are transcribed into **`src/regions/florida/sources/schools/msid_codes.py`**: `ACTIVITY_CODE`, `SCHOOL_TYPE`, `CHARTER_STATUS`, `FUNC_SETTING`, `SERV_TYPE` (note **`B` = Alternative Education**, not "basic"), `MAGNET_STATUS`, `TITLE_I_STATUS`, `ACC_TYPE`, `REGION_CODE`, and `GRADE_CODE_COMBINATION` + `grade_code_span()` / `grade_code_serves_tested()`. |
| Grade span | From MSID `GRADE_CODE` via Appendix B (`grade_code_span`) — resolves for ~85% of rows (the rest are codes `00` / `99` = unassigned, mostly closed/future). `ccd/directory.lowest/highest_grade_offered` is the fallback. `serves_tested_grades` = the code's explicit grade set intersects 3–10. |
| Flags | `is_regular` = `serv_type == 'k12_general'` only; `is_alternative` = `'alternative_education'`; `is_charter` = `charter_kind != 'not_charter'`; `is_magnet` = magnet school-wide/program; `is_virtual` = `func_setting == 'virtual'`. Raw codes carried alongside. Flags are advisory — the analysis layer picks the estimation sample. |
| `ncessch` collision dedup (36 cases) | For the `msid → ncessch` map keep the row; for the reverse `ncessch → msid` used in the CCD join, **prefer `ACTIVITY_CODE == 'A'`, then the latest `DATE_OPENED`**. Carry `ncessch_shared` when >1 `msid` maps to the same id. |
| CCD/CRDC/EDFacts sentinels | Urban's **`−1` (missing) / `−2` (not applicable) / `−3` (suppressed)** → map the value to `NA`, and carry one companion column per covariate, `<col>_missing ∈ {ok, missing, na, suppressed}`. |
| `in_operation` rule | **Month-aware:** `open_spring = year(DATE_OPENED) + (month ≥ 7)`, `close_spring = year(DATE_CLOSED) + (month ≥ 7)`; operating ⇔ `open_spring ≤ Y ≤ close_spring`. Null open ⇒ −∞, null close ⇒ +∞. Carry `in_operation_src ∈ {dates, dates+tested, conflict}`. On a 2015+ conflict where the school appears in `assessments.parquet` but the dates say not-open/closed → **set `in_operation = True`** (a school that tested students was open), `src = conflict`. Pre-2015: date-derived only. |
| Per-year coordinates | Only if the notebook detects material relocations; otherwise one static point in the cross-section. |
| School universe | **Keep all MSID rows, add flags** (no filtering). |
| Virtual / district-wide schools | Kept, flagged `no_physical_location`. |
| Output CRS | **EPSG:3087** (matches `barriers.parquet`; no reprojection downstream). |
| Stage-2 road model | **FDOT RCI roadway network** — built as its **own source** (`road_network`, or the first step of `traffic`), reused by `traffic` / `road_projects`. `schools` stage 2 declares `REQUIRES {noise_barriers, road_network}`. Full implementation brief (source URLs, confirmed schema, the consumer contract): [`docs/data/florida/road_network/README.md`](../road_network/README.md). |
| Stage-2 grain | One row per `(msid, gcid)` candidate pair, a status column per matching algorithm; **plus** a per-school rollup (`ever_near_wall`, first `treat_year`, `n_walls_500m`, `wall_len_500m`, …). |
| Stage-2 algorithms v1 | `euclid_nearest` + `buffer_dose` only. `road_gated` / `same_segment` / `same_side` / `shielded_arc` land as **placeholders** (columns present, `NA`) until `road_network` exists. |
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
| `crdc` | `schools/crdc/enrollment/{year}/disability/sex` | **%SWD (IDEA)**, discipline (later) — **biennial** (2011, 2013, 2015, 2017, 2020, 2021), some items sampled | **no — first pass** |
| `crdc_lep` | `schools/crdc/enrollment/{year}/lep/sex` | **%ELL** — same biennial years/shape as `crdc`, implemented alongside it | **no — first pass** |
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

**Verification — `src/experiments/florida/schools.ipynb` (step 3).** The
non-Urban sections (spine, crosswalk, coordinates, flags, operation panel,
point-only barrier matching) run against the fetched data; stage-1b covariates
are a guarded cell that runs when CCD data lands. Preliminary numbers from the
build (base-interpreter dry run of the pandas-only cells):

- `0`-sentinel `ncessch`: **9.4%** overall — 0.5% of active, 22.6% of closed,
  90.1% of future schools.
- Composed `ncessch` matches an EDGE 2024–25 id for **66%** of all spine rows,
  **86%** of active schools (closed/future rows are expected to miss).
- **Collisions:** 36 composed `ncessch` land on >1 `msid` (~0.6% — the notebook
  prints them with district/open-close context to classify); `msid` itself is
  unique.
- **vs `assessments.parquet`:** 22 of 4 419 tested `msid` are absent from
  `all_schools`, all in state-district `78` — check whether they live in a
  different MSID export.
- Still needs a healthy Urban API / unthrottled link: CCD `ncessch` overlap by
  year, NCESSCH stability across years (static vs per-year crosswalk),
  MSID↔CCD coordinate distances.

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
- **Status of live verification.** `msid` + `edge` verified. **`ccd_directory`
  via `--via csv` verified end-to-end** in the `311` env (the full 1 GB
  `schools_ccd_directory.csv` downloaded, filtered to FL, split to per-year
  parquet — `route: csv`, no errors). The REST route and the
  `ccd_enrollment` / `crdc` / `edfacts` CSV filenames still need a healthy
  `/api/v1/` (it 502s for hours at a time; there is **no official Python
  client**, only the R `educationdata` package, which the same outage breaks).
  The `ccd/directory` schema is 52 columns incl. `ncessch`,
  `latitude`/`longitude`, `enrollment`, `teachers_fte`,
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

## Output schema (target for `preprocess.py`)

Column dictionary the notebook prototype settled on. Types: `str`, `Int`
(nullable), `float`, `bool` (nullable `boolean`), `cat`, `date`, `geom`.

### `processed/school_cross_section.parquet` — one row per `msid`

| column | type | source | notes |
|---|---|---|---|
| `msid` | str(6) | MSID `DISTRICT.zfill(2)+SCHOOL.zfill(4)` | primary key; unique |
| `ncessch` | str(12) | `FEDERAL_DIST_NO.zfill(7)+FEDERAL_SCHL_NO.zfill(5)` | `NA` when either part is `"0"` (~9.4%) |
| `ncessch_shared` | bool | derived | >1 `msid` composes this `ncessch` (36 cases) |
| `name` | str | MSID `SCHOOL_NAME_LONG` | |
| `district` / `school` | str | MSID | zero-padded parts of `msid` |
| `district_name` | str | MSID `DISTRICT_NAME` | |
| `geometry` | geom(Point, EPSG:3087) | coord ladder | may be empty when `geom_source == "none"` |
| `geom_source` | cat | derived | `edge` \| `msid` \| `geocode` \| `none` |
| `geom_disagree_m` | float | derived | EDGE↔MSID haversine where both exist |
| `geocode_pending` | bool | derived | active school, no coordinate — geocode later |
| `date_opened` / `date_closed` | date | MSID | null = predates tracking / still open |
| `activity_code` | cat | MSID `ACTIVITY_CODE` | `A` active / `C` closed / `F` future |
| `type_code` | str | MSID `TYPE` | raw (code table TODO) |
| `func_setting` | str | MSID `SCHL_FUNC_SETTING` | raw |
| `serv_type` | str | MSID `PRIMARY_SERV_TYPE` | raw |
| `charter_stat` / `magnet_stat` | str | MSID | raw |
| `grade_code` | str | MSID `GRADE_CODE` | raw |
| `grade_code_unreliable` | bool | derived | MSID parse disagrees with CCD grade span |
| `grade_low` / `grade_high` | Int | **CCD `lowest/highest_grade_offered`**, MSID fallback | −1/PK → 0 |
| `is_regular` / `is_charter` / `is_magnet` / `is_virtual` | bool | derived (provisional) | advisory flags |
| `no_physical_location` | bool | derived | virtual, or geometry from a district-office address |
| `serves_tested_grades` | bool | derived | grade span overlaps 3–10 |
| `in_assessments_ever` | bool | vs `assessments.parquet` | appears ≥1 year (non-state-total) |

### `processed/school_year_panel.parquet` — one row per `(msid, year)`

`year` = assessment **spring year**, 1990–2026. Carries the cross-section
identity + geometry (static) plus:

| column | type | source | notes |
|---|---|---|---|
| `in_operation` | bool | month-aware open/close rule | `True` on a 2015+ assessment-appearance conflict |
| `in_operation_src` | cat | derived | `dates` \| `dates+tested` \| `conflict` |
| `in_assessments` | bool | `assessments.parquet` | tested that year |
| `enrollment` | Int | `ccd_directory` (`year+1`→spring) | `<0` → `NA` |
| `frpl_n` | Int | `ccd_directory` `free_or_reduced_price_lunch` | `<0` → `NA`; **CEP caveat post-2015** |
| `teachers_fte` | float | `ccd_directory` | `<0` → `NA` |
| `pupil_teacher_ratio` | float | `enrollment / teachers_fte` | |
| `title_i_status` / `ccd_charter` / `ccd_magnet` / `ccd_virtual` / `ccd_status` | cat | `ccd_directory` | |
| `ccd_grade_low` / `ccd_grade_high` | Int | `ccd_directory` | feeds the cross-section grade span |
| `pct_white … pct_multiracial`, `enr_total` | float / Int | `ccd_enrollment` `/race/` | share = race `k` / race `99` |
| `pct_swd` | float | `crdc` `/disability/sex/` (biennial) | IDEA `sex=99` / total; plain left-join on `(ncessch, year)` — `NA` off a biennial wave, no forward-fill |
| `pct_ell` | float | `crdc_lep` `/lep/sex/` (biennial) | same shape/join as `pct_swd`; `lep=1` `sex=99` / `lep=99` total |
| `read_prof_midpt` / `math_prof_midpt` | float | `edfacts` (`year` = spring, no offset) | proficiency-band midpoint — robustness outcome, not a covariate |
| `<col>_missing` | cat | derived | `ok` \| `missing` \| `na` \| `suppressed` — per sentinel-bearing covariate |

### `assembled/schools_treatment.parquet`

**Pair grain** — one row per `(msid, gcid)` within 1 000 m:

| column | type | notes |
|---|---|---|
| `msid` / `ncessch` / `gcid` | str | keys |
| `category` | cat | `fdot_barrier` \| `other_wall` |
| `dist_m` | float | school point → wall geometry |
| `built_year` / `treat_year` | Int | `treat_year = built_year` for `fdot_barrier` (original year, incl. `REPLACED`); `NA` for `other_wall` |
| `timing_unknown` | bool | `fdot_barrier` with no `built_year` (~2.7%) |
| `within_100m … within_1000m` | bool | algorithm 1 `euclid_nearest` buffer flags |
| `is_nearest_fdot` | bool | closest `fdot_barrier` for this school |
| `road_id` / `same_route` / `school_side` / `wall_side` | — | algorithms 3–5, implemented (`match_barriers_road`). ⚠️ `school_side`/`wall_side` are **not** compass directions — pairwise-only, see the warning below |
| `shielded_frac` | — | **placeholder (`NA`)** — algorithm 6, stretch goal, not implemented |

**Rollup grain** (same file or a `schools_treatment_rollup.parquet`) — one row
per `msid`: `ever_near_wall_{500,1000}m`, `first_treat_year`, `n_walls_500m`,
`wall_len_500m`, `nearest_fdot_dist_m`, `nearest_fdot_gcid`, `any_timing_unknown`.

---

## `preprocess` / `assemble` — implemented (steps 3–4)

`src/regions/florida/sources/schools/preprocess.py` (stages 1a+1b) and
`assemble.py` (stage 2) implement everything below. One deviation from the
original design: the `ncessch → msid` dedup map is computed for diagnostics
(`ncessch_shared` on the cross-section) but not applied to the covariate join —
Cluster-A tables are unique on `(ncessch, year)`, so joining the full,
un-deduplicated spine just fans the same covariate row into every `msid` that
shares a federal id, which is the conservative behaviour.

### Stage 1a — spine → `school_cross_section.parquet` + panel skeleton

1. Load MSID; build `msid`; compose `ncessch` (`NA` on the `"0"` sentinel);
   build the `ncessch → msid` dedup map (prefer `A`, then latest `DATE_OPENED`)
   and set `ncessch_shared`.
2. Coordinate ladder **EDGE → MSID → none** (EDGE wins on disagreement);
   `geom_source`, `geom_disagree_m`, `geocode_pending`; reproject to EPSG:3087.
3. Decode classification fields → **raw codes + provisional flags** (mapping is
   a documented TODO); grade span from **CCD** `lowest/highest_grade_offered`,
   MSID `GRADE_CODE` as fallback + `grade_code_unreliable`.
4. Cross-section = one row per `msid`.
5. Panel skeleton = cross-section ⨯ 1990–2026; `in_operation` by the
   **month-aware** rule; `in_operation_src`; 2015+ assessment-appearance
   conflict → `in_operation = True`.
6. **Validation** (mirror `assessments.ipynb`): no dup `msid`; no dup
   `(msid, year)`; coords inside the FL bbox; crosswalk match-rate reported
   (target ≥ 85% of active); `in_operation` vs assessment-appearance crosstab;
   `geom_source` breakdown; every assessment `msid` present **or** in the known
   exception list (districts 78/80 = state colleges).

### Stage 1b — Cluster-A covariates → merged into `school_year_panel.parquet`

Depends on 1a's panel skeleton + the `ccd_directory` / `ccd_enrollment`
(and, when enabled, `crdc` / `edfacts`) raw pulls. Isolated from 1a so
covariate-definition changes don't re-run the spine or stage 2.

1. **All Urban tables:** map `−1 / −2 / −3` → `NA` on the value, emit a
   `<col>_missing` companion (`ok`/`missing`/`na`/`suppressed`).
2. `ccd_directory` → enrollment, `frpl_n`, `teachers_fte`, `pupil_teacher_ratio`,
   Title I / charter / magnet / virtual / status, grade span. `year + 1` →
   spring year.
3. `ccd_enrollment` `/race/` → `pct_<race>` = enrolment(race `k`) /
   enrolment(race `99`); `enr_total`.
4. `crdc` `/disability/sex/` → `pct_swd` = IDEA(`sex=99`) / total(`sex=99`).
   `crdc_lep` `/lep/sex/` → `pct_ell` = LEP(`sex=99`) / total(`sex=99`), same
   shape/dedup treatment. Both left-join on `(ncessch, year)` — `NA` off a
   biennial wave, no forward-fill.
5. `edfacts` → `read_prof_midpt` / `math_prof_midpt` (spring year, **no offset**)
   — a robustness *outcome*, kept separate from the covariates.
6. Left-join onto the panel skeleton on `(ncessch, year)`. **Lag nothing** —
   t−1 lagging is an analysis-layer choice (covariates.md).
7. **Validation:** per-source panel-year coverage; `pct_<race>` row-sum ≈ 1 where
   `enr_total > 0`; `pct_swd` / `frpl_n/enrollment` in [0, 1]; `enrollment` vs
   assessment `n_students` sanity.

### Stage 2 → `schools_treatment.parquet` (REQUIRES `noise_barriers` + `road_network`)

**Pair grain** (one row per `(msid, gcid)` within 1 000 m) **plus a per-school
rollup** (`ever_near_wall_*`, `first_treat_year`, `n_walls_500m`,
`wall_len_500m`, `nearest_fdot_dist_m`, …) written in the same run — see
[Output schema](#output-schema-target-for-preprocesspy). Algorithms 1–5 are
implemented (`match_barriers_point` + `match_barriers_road`); `road_id` /
`same_route` / `school_side` / `wall_side` are populated for every pair
(99.1% get a `same_route` match, 82.3% a `same_side` match, against the
point-only baseline). Only `shielded_frac` (algorithm 6, stretch goal) stays
a documented `NA` placeholder.

**Matching algorithms — increasing rigour** (1–5 implemented; 6 a stretch goal):

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
median walls for both. **Source:** `noise_barriers` raw *does* carry a side
field — `BLOC_SIDE` (compass direction, 100% populated for present walls),
found 2026-09-11 while resolving the `FED_YRCON` question below, currently
dropped by `noise_barriers/preprocess.py` (not in `COLUMN_RENAMES`). That
only covers the **wall's** side, though — schools have no equivalent
attribute, so (b) still needs the geometric derivation: signed perpendicular
offset of the school point relative to the RCI route centerline. `BLOC_SIDE`
should be used as ground truth to validate that geometric method (and
possibly to calibrate `D`/`P`) rather than trusting it unchecked. This is
algorithm 5.

> **⚠️ The geometric sign is pairwise-only, never a compass direction.**
> Confirmed empirically once `road_network` was fetched (see
> `src/experiments/florida/schools.ipynb` §7.2 and
> [`road_network/README.md`](../road_network/README.md)'s matching warning):
> `rciroads`' digitizing direction (which end of a `ROADWAY` is milepost 0)
> is arbitrary per roadway, so a geometrically-derived `wall_side` splits
> ~87%/13% statewide among matched walls rather than ~50/50 — there is no
> absolute "left"/"right" to read off the sign. It is valid **only** when
> comparing a wall's side to a school's side matched to the **same**
> `ROADWAY` segment (algorithm 5's same-sign test). Whoever implements
> `match_barriers_road` must carry this caveat into the
> `schools_treatment.parquet` column docs/comments verbatim — the column
> name alone invites misuse. (`BLOC_SIDE`, being an absolute compass value,
> does not have this problem for the wall side specifically.)

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

- `crdc` is **biennial** (2011, 2013, 2015, 2017, 2020, 2021) with some sampled
  items — forward-fill between waves, keep `pct_swd_src_year`. `edfacts` is
  2009–2020, spring-year indexed, and is a robustness *outcome* not a covariate.
  Both `--via api` (`?fips=12`); off the default `--subsource` set but pulled.
- CCD `%FRL` reporting is distorted by CEP after ~2015 — carry the raw count
  (`frpl_n`) + a `frpl_cep_flag`, reconcile in 1b.
- The **fetch half** of the CCD/CRDC/EDFacts pull is a national dataset and may
  later move to a shared `src/core` sources area (as flagged in covariates.md for
  `staff` / `air_quality` / `neighbourhood` too). Merging now does not block that
  — the fetch functions can be lifted to `core` and called from here when the
  per-region source registry lands.

---

## Open questions / TODO

**Resolved** (see [Decisions locked](#decisions-locked-2026-09-10)): grade span →
CCD; MSID type codes → raw + provisional flags; `ncessch` collision dedup; CCD
sentinels → `NA` + `<col>_missing`; `in_operation` month-aware + conflict rule;
coordinate disagreement → EDGE; geocoding deferred; RCI → own `road_network`
source; stage-2 rollup + algorithm placeholders. Urban routes confirmed against a
healthy API (`api-downloads`): `ccd_directory` via CSV, the rest via REST+`fips`.

**Still open — not blocking `preprocess.py`:**

- **FLDOE MSID code appendix** (`GRADE_CODE` Appendix B, `TYPE`,
  `SCHL_FUNC_SETTING`, `PRIMARY_SERV_TYPE`, `CHARTER_SCHL_STAT`) — `www.fldoe.org`
  blocks scripted fetches; ask `MSID@fldoe.org`. Until then flags are provisional
  and grade span comes from CCD.
- ~~`crdc_lep` subsource for `pct_ell`~~ **resolved** (2026-09-11): wired in
  (endpoint 67, `/lep/sex/`), fetched 2011–2021, `tidy_crdc_lep` mirrors
  `tidy_crdc_swd`'s dedup treatment.
- ~~CRDC `year` → spring-year offset~~ **resolved**: `+1` confirmed against the Urban CRDC codebook. ~~`crdc_2021` raw-pull duplication~~ **resolved**: deduplicated in `_load_year_parquets`.
- NCESSCH stability across years → static vs per-year crosswalk (only matters if
  multi-year EDGE is added).
- ~~`noise_barriers` raw roadbed/side/`RID` field for algorithm 5~~ **found**
  (2026-09-11, `src/experiments/florida/schools.ipynb` §7.7): the raw GDB
  *does* carry one — `BLOC_SIDE` (compass `EAST`/`WEST`/`NORTH`/`SOUTH`,
  populated for 100% of present walls), plus `BLOC_BND` (orientation to
  traffic direction) and `BLOC_ONRTE` (mount type: shoulder/ground/median/
  structure). None of the three are in `noise_barriers/preprocess.py`'s
  `COLUMN_RENAMES` yet — silently dropped, not absent from the source.
  **This does not eliminate the need for algorithm 5's geometric derivation**
  (schools have no equivalent attribute — only walls do), but it means the
  wall side no longer needs to be *derived*, only the school side does, and
  `BLOC_SIDE` can serve as ground truth to validate (or calibrate `D`/`P`
  against) the geometric method instead of a manual visual audit. Add the
  three columns to `noise_barriers/preprocess.py`'s `COLUMN_RENAMES`/
  `OUTPUT_COLUMNS` before building `match_barriers_road`.
  **`road_network` itself: full implementation brief at
  [`docs/data/florida/road_network/README.md`](../road_network/README.md)**
  (confirmed FGDL `rciroads_<version>.zip` source, schema; `rciroads` itself
  still has no side/carriageway field, only `noise_barriers` does).
- ~~`FED_YRCON` semantics for `REPLACED` rows~~ **resolved** (2026-09-11,
  `schools.ipynb` §7.6): FGDL's own field definition is unambiguous —
  *"Year of Original Noise Barrier Construction."* The 10 `REPLACED BARRIERS`
  rows carry plausible pre-2010 years, consistent with "original." No code
  change needed; `treat_year = built_year` (original year, incl. `REPLACED`)
  was already correct.
- ~~The naive `same_segment` design (exact `ROADWAY`-string equality between
  independently nearest-matched wall and school) badly under-recovers the
  algorithm 1/2 baseline~~ **resolved** (2026-09-11, `schools.ipynb`
  §7.3-7.4): confirmed the diagnosis — only ~20% of `ever_near_wall_500m`
  schools got a same-`ROADWAY` same-side match even at a generous `D=1.0` mi
  tolerance (`ROADWAY` is a fine RCI segmentation, 18,373 ids statewide,
  ~2.2 segments/id, closer to a "control section" than a continuous route)
  — and fixed it: redesigned `same_segment` as a **network-distance-bounded
  corridor test**. From the wall's point, flood-fill outward along the
  arterial-only network's actual connectivity (shared segment endpoints),
  consuming true path distance up to a budget, buffer into a corridor
  polygon, test whether the school falls inside — no `ROADWAY` identity
  involved. **Recovery: 99.1%** (algorithms 3/4 alone, `budget=800 m,
  buffer=600 m`) and **83.2%** (+ algorithm 5's same-side test; the ~17-point
  drop is schools on the opposite carriageway, the false positives algorithm
  5 exists to remove). Two bugs found and fixed along the way, both from the
  same root cause — assuming RCI's segmentation is regular enough for a
  count/length proxy to stand in for true distance, when some segments run
  30-57 km unbroken: (a) checking the distance budget once per BFS hop-layer
  instead of per segment let one corridor overshoot to 10.5 km on a 3.2 km
  budget; (b) leaving the seed segment un-trimmed let another reach 24 km.
  Full writeup and the resolved algorithm-4 design note in
  [`road_network/README.md`](../road_network/README.md), Open Question 7.
  ~~Still needed: move this from notebook prototype into pipeline code.~~
  **Done** (2026-09-11): `road_network/linear_ref.py` (arterial-subset
  filter, nearest-road match, linear referencing, adjacency graph, corridor
  flood-fill) + `schools/assemble.py`'s `match_barriers_road`, wired into
  `florida data schools assemble` (`--corridor-budget`/`--corridor-buffer`
  flags, defaults 800 m/600 m) with unit tests in
  `test_road_network_linear_ref.py` / `test_schools_assemble.py`. Real run:
  99.1% same-route / 82.3% same-side recovery, `road_id`/`same_route`/
  `school_side`/`wall_side` populated for all 2,173 pairs (including
  `other_wall` rows, not just `fdot_barrier`).
- `DataSource` base class — deferred; `preprocess` is hand-wired like the others.

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
