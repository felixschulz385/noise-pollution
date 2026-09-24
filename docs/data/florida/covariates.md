# Florida — covariates for the barrier-construction event study

Catalogue of control / covariate variables for the **main analysis**: a staggered
difference-in-differences / event study of **FDOT noise-barrier construction** on
**school achievement**, where the outcome is the within `year × subject × grade`
z-score of the school mean scale score (`z_mss` / `z_mss_w`, see
[`README.md`](README.md#assessments--fetch-only-preprocess-deferred-to-the-notebook))
and the panel unit is `school × year × subject × grade`.

## How to read this

The design carries **school fixed effects** and **time fixed effects**
(`year × subject × grade`, plus a district- or county-`× year` layer), so every
*time-invariant* school/neighbourhood confounder — baseline SES, distance to the
road, catchment, building, principal culture, the achievement *level* — is
already differenced out. What is left to worry about is **time-varying** variables
correlated with *barrier timing*. FDOT prioritises walls by modelled noise level,
which tracks traffic growth and roadside residential density, and walls are very
often built *inside* a road-widening / PD&E project — that selection is where the
identification risk sits, and it drives most of the list below.

**Role** column:

| Role | Meaning |
|---|---|
| `FE` | absorbed by design; listed for completeness, not a regressor |
| `baseline` | include as a covariate in the main specification |
| `selection` | add in a robustness spec to probe barrier-siting endogeneity / pre-trends; not in baseline |
| `keep-out` | post-treatment mediator — **exclude** from baseline, use only in a separate mechanism analysis |
| `treatment` | used to define exposure intensity or split the sample, not a control |
| `filter` | sample-construction rule, not a regressor |

`TV?` = does it vary over the panel (Y) or is it effectively fixed at the school
level (N, → absorbed by school FE).

---

## Cluster A — School panel characteristics

Time-varying school composition and structure. Main use: guard against
compositional change coinciding with barrier completion. **Caveat:** if walls
capitalise into house prices and sort families in, composition becomes a
*mediator* — hence several `keep-out` / `selection` roles. Enter these lagged
(t−1) in any baseline spec to reduce the mediator problem.

**Produced by the `schools` source** (`preprocess` stage 1b), not a separate
`school_panel` module — same key / API / grain / year span. See
[`schools/README.md`](schools/README.md#combining-school_panel).

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Total enrollment / membership | baseline | Y | scale; sanity vs test-taker weights | NCES CCD *Universe*; FLDOE Membership (Survey 2/3) | Urban Inst. Education Data API `schools/ccd/enrollment`; NCES flat files |
| Grade span (lowest/highest grade offered) | filter | Y | drop schools that add/drop tested grades mid-panel | CCD *Directory* | Urban API `schools/ccd/directory` |
| % free/reduced-price lunch eligible | baseline / keep-out | Y | poverty proxy; strongest single achievement predictor. Mediator if gentrification | CCD *Universe* (FRPL counts); FLDOE Student demographics (Survey 5) | Urban API `schools/ccd/enrollment` (by `lunch`); FLDOE PK-12 pubs |
| Race/ethnicity shares | baseline / keep-out | Y | composition; mediator caution | CCD by race | Urban API `schools/ccd/enrollment` (by `race`) |
| % English-language learners (ELL/LEP) | baseline | Y | test performance & participation | EDFacts LEP; CRDC; FLDOE | Urban API `schools/edfacts/...`, `schools/crdc/enrollment`; FLDOE |
| % students with disabilities (IEP/IDEA) | baseline | Y | performance & participation; suppression | EDFacts IDEA; CRDC; FLDOE ESE | Urban API; FLDOE |
| % gifted | selection | Y | composition | CRDC | Urban API `schools/crdc/enrollment` |
| Charter / magnet / Title I status | baseline / filter | Y | policy regime; often excluded from sample | CCD *Directory* (Title I — MSID's `TITLE_I_STATUS` is empty); MSID `CHARTER_SCHL_STAT` / `MAGNET_STATUS` | `schools` source (MSID + `ccd_directory`) |
| Pupil–teacher ratio, teacher FTE | baseline / keep-out | Y | resource level; mild mediator (noise → retention) | CCD *Universe* (teacher FTE) | Urban API `schools/ccd/enrollment` |
| Urban-centric locale code | FE | ~N | mostly fixed; absorbed | CCD / NCES EDGE | Urban API `schools/ccd/directory` |

**Access notes.** The **Urban Institute Education Data Portal API**
(`https://educationdata.urban.org/api/v1/`, no key, JSON, one row per
`school-year`, keyed on `NCESSCH`) is the cleanest programmatic route and already
harmonises CCD + CRDC + EDFacts. The **FL `msid` ↔ `NCESSCH`** bridge is
**embedded in MSID** (`FEDERAL_DIST_NO`/`FEDERAL_SCHL_NO`) — no CCD `ST_SCHID`
matching for the primary path; the `schools` source builds it. FLDOE's own
**PK-12 Public School Data Publications & Reports**
(`fldoe.org/accountability/data-sys/...`) give native FL
keys and sometimes finer subgroups but are per-year Excel / interactive-portal
exports and messier to panel.

- Urban API docs: <https://educationdata.urban.org/documentation/>
- NCES CCD files: <https://nces.ed.gov/ccd/files.asp>
- FLDOE PK-12 pubs: <https://www.fldoe.org/accountability/data-sys/edu-info-accountability-services/pk-12-public-school-data-pubs-reports/index.stml>

---

## Cluster B — Staff & fiscal resources

**Status: `teacher_salary` (avg salary + avg years' experience + median
salary, district-level) + `out_of_field` (in-field/out-of-field teaching,
SCHOOL-level) + `district_finance` (per-pupil expenditure, via NCES CCD F-33)
implemented and joined into `panel` 2026-09-17** — the two FLDOE workbooks
downloaded via their Wayback Machine archive (`www.fldoe.org` itself blocks
scripted clients, same as `assessments`), the CCD finance pull a plain
no-auth API call (26/26 years fetched cleanly). Real numbers: 35,453/660,681
panel rows (5.4%, effectively all of assessment-year-2025 — the two FLDOE
workbooks' historical backfill is mechanically ready but paused on a live
Internet Archive outage) matched salary/experience, 398,189 (60.3%, spanning
1995–2020) matched per-pupil expenditure, 35,308 (5.3%) matched
out-of-field. Teacher turnover and % advanced degree remain unbuilt (see
below). Full implementation brief: [`staff/README.md`](staff/README.md).

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Teacher experience (mean, district-level), % out-of-field (SCHOOL-level) | selection / keep-out | Y | teacher quality shifts; partly a mediator (noise → turnover) | FLDOE **Staff Information System** ("Staff in Florida's Public Schools") | FLDOE Staff pubs (per-year Excel), fetched via Wayback Machine archive |
| Teacher turnover / share new to school | keep-out | Y | mechanism channel — **not built**, needs individual-level year-over-year staff matching FLDOE's aggregate publications don't support | FLDOE Staff SIS (year-over-year match) | derived |
| Average / median teacher salary | selection | Y | resource level / labour market | FLDOE **Teacher Salary Data** | real confirmed link pattern: `fldoe.org/core/fileparse.php/7584/urlt/<yy><yy+1>TeacherSalaryData.xlsx` (irregular before ~2017), fetched via Wayback Machine archive |
| Per-pupil expenditure | selection / keep-out | Y | resource response | NCES CCD fiscal (F-33) | Urban API `school-districts/ccd/finance`, confirmed live 1995-2020 |

Turnover and spending can respond *to* the barrier (or to the disruption that
precedes it), so they belong in the mechanism spec, not the baseline. CCD staff
FTE is a fallback where FLDOE SIS panels are hard to assemble.

- FLDOE Staff: <https://www.fldoe.org/accountability/data-sys/edu-info-accountability-services/pk-12-public-school-data-pubs-reports/staff.stml> (blocks scripted access directly — see `staff/README.md` for the Wayback Machine workaround)

---

## Cluster C — Traffic & acoustic exposure

The core confounder set: noise scales with traffic volume and heavy-vehicle
share, so a traffic trend at a to-be-treated road masquerades as a wall effect.

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Annual Average Daily Traffic (AADT) on the adjacent segment | baseline | Y | direct noise driver | FDOT **Transportation Data & Analytics** — *Annual Average Daily Traffic (Historical TDA)* feature class (5 rolling years) | FDOT Open Data Hub (ArcGIS): <https://gis-fdot.opendata.arcgis.com/datasets/fdot::annual-average-daily-traffic-historical-tda> |
| Long historical AADT panel (pre-2011) | baseline | Y | covers the FCAT era | FDOT **Florida Traffic Information (FTI) database** (`FTI.mdb`, ~97 MB zip) | <https://www.fdot.gov/statistics/trafficinfo/default.shtm>; Florida Traffic Online <https://tdaappsprod.dot.state.fl.us/fto/> |
| Truck AADT / T-factor (heavy-vehicle %) | baseline | Y | trucks dominate roadside L~eq~ | FDOT Truck AADT shapefile / FTI | same as above |
| Posted speed, K/D factors | selection | Y | tyre/engine noise; peak-hour share | FDOT RCI (Roadway Characteristics Inventory) | FDOT Data portal `data.fdot.gov` |
| School↔road distance, exposure buffer | treatment | N | defines treatment intensity; absorbed as level | derived (school coords × FDOT roadway network) | spatial join |

Join by nearest count station / RCI roadway segment to each school within an
exposure buffer; `ROADWAY`/`RCI` id links AADT → the FDOT roadway network and →
the barrier layer.

---

## Cluster D — Road-works / construction projects

**Status: fully implemented and joined into `panel` 2026-09-14** — `fetch` +
`preprocess` + `assemble` (118,014 project-item rows / 4,676 roadways;
5,366/5,984 schools matched to a roadway+milepost, 40,729 school↔project
pairs, 2,586 schools with ≥1 nearby project) plus the final panel join
(`attach_road_projects`, a year-interval-overlap match — 4.5% of the
660,681-row event-study panel matched an active project). Full
implementation brief, live-verified schema, and the join strategy:
[`road_projects/README.md`](road_projects/README.md).

Walls are frequently one line item in a widening or PD&E project. The widening
adds capacity (→ traffic) and the construction itself is disruptive; both
coincide with wall completion. Need this to (a) control for it and (b) split
"wall as part of a widening" vs standalone walls.

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Adjacent widening / resurfacing / interchange / PD&E project — presence & dates | baseline / treatment-split | Y | co-timed confounder | FDOT **Five-Year Work Program** / Work Program Administration extract | live REST, confirmed: `Work_Program_Current` FeatureServer (21 phase layers, `RDWYID`+milepost keyed — same id format as `road_network.roadway_id`), layers 2 (Construction) + 13 (PD&E) prioritized |
| Construction start / end / letting dates | baseline | Y | timing alignment | `Active_Construction_Projects` FeatureServer (Site Manager extract) — has real `StartDate`/`EstEndDate`, `Work_Program_Current` only has fiscal-year grain | live REST, confirmed field schema |
| Project type / scope code | treatment-split | Y | widening vs standalone barrier vs resurfacing | `Work_Program_Current.WPWKMIXN` (confirmed values incl. `"RESURFACING"`, `"ADD LANES & RECONSTR"`, `"INTERCHANGE - ADD LA"`) | same |
| Quieter-pavement resurfacing (OGFC / open-graded) | selection | Y | a *different* noise reduction, could be attributed to the wall | FDOT RCI pavement / resurfacing contracts | not found in either live service checked — open question, see README |

**Real, unresolved gap**: both live services are current-only; the one
downloadable historical archive found (`fdotewp1.dot.state.fl.us`) only
reaches back to adoption year **2019** — well short of this study's 1998–2026
wall cohort. See `road_projects/README.md`'s Open Question 1 for the scoping
decision this forces (accept 2019+ coverage / pursue an FDOT records request
/ restrict the road-works control to recent wall cohorts).

---

## Cluster E — Air co-pollution

Barriers also cut near-road NO₂ / PM / ultrafines. For a reduced-form "living
near a noisy road" effect, **leave this inside the treatment** and address it in
mechanisms; only bring in an air-quality control if the paper claims to isolate
the *acoustic* channel. Not a baseline control.

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Tract daily/annual PM2.5, O3 | keep-out / mechanism | Y | co-treatment | EPA **FAQSD** (Fused Air Quality Surface Using Downscaling), census tract, 2002–2020 | EPA; mirror at USC CDR <https://gero.usc.edu/cbph/cdr/air-pollution-o2-and-pm2-5/> |
| 1-km daily PM2.5 / O3 / **NO2** | keep-out / mechanism | Y | NO2 is the near-road traffic marker | Requia et al. ensemble, CONUS 1 km, 2000–2016 | SEDAC/NASA & Harvard Dataverse <https://data.nasa.gov/dataset/daily-and-annual-pm2-5-o3-and-no2-concentrations-at-zip-codes-for-the-contiguous-u-s-2000-> |
| Monitor observations (ground truth) | selection | Y | validate the surfaces near schools | EPA **AQS / AirData** | <https://aqs.epa.gov/aqsweb/airdata/download_files.html> |
| Traffic-proximity index | treatment | ~N | alt. exposure proxy | EPA **EJScreen** (tract) | EPA EJScreen data |

---

## Cluster F — Neighbourhood & housing

Diagnostics for sorting / capitalisation, **not** baseline controls (a wall that
raises prices makes these mediators). Also: a **pre-trend in home values** at
to-be-treated vs not-yet-treated roads is a direct test of barrier-siting
endogeneity → `selection`.

**Status: ACS tract demographics + Zillow ZHVI fully implemented and joined
into `panel` 2026-09-17** — the spatial school→tract/ZIP match, ZHVI, and
ACS (once the user supplied a `CENSUS_API_KEY` — the Census Data API now
requires one for every request, a real 2026-05 policy change unlike when
this table was first written) are all live: 449,178/660,681 rows (68.0%)
matched ACS demographics, 651,266 (98.6%) matched a ZHVI home-value figure.
Full brief: [`neighbourhood/README.md`](neighbourhood/README.md).

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Tract median household income, poverty rate, % owner-occ., % bachelor's+, % moved in last year | selection / keep-out | Y | gentrification / sorting | Census **ACS 5-year** (2005–09 →, `B19013`/`B17001`/`B25003`/`B15003` or `B15002` pre-2012/`B07003`, all confirmed live) | Census API, **now requires a free key** (`CENSUS_API_KEY` env var) — <https://api.census.gov/data/key_signup.html> |
| Typical home value (annual snapshot, 2000→) | selection | Y | capitalisation & siting pre-trend | **Zillow ZHVI** (ZIP-level, mid-tier SFR+condo) | public CSV, no key, confirmed live: <https://www.zillow.com/research/data/> |
| Packaged tract SES / greenspace / walkability | selection | Y | convenience bundle — **not built**, ships via ICPSR openICPSR (needs an account, not a plain URL fetch) | **NaNDA** (National Neighborhood Data Archive) | ICPSR openICPSR |

---

## Cluster G — Shocks & policy

Mostly analysis-side indicator controls; some overlap with FE.

**Status: hurricane/disaster-declaration row fully implemented and joined
into `panel` 2026-09-14** — `fetch` + `preprocess` + `assemble` (2,794
OpenFEMA rows fetched in one request, 1,774 county × assessment-year rollup
rows, all 67 real counties matched) plus the final panel join
(`attach_shocks`, exact `(district_name, year)` match — 44.7% of the
660,681-row event-study panel matched at least one declaration, 35.6% a
hurricane specifically). Full implementation brief:
[`shocks/README.md`](shocks/README.md). The other six Cluster G rows below
remain unimplemented — see that README's "Scope for a first pass" for what's
deferred and why.

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Hurricane disaster declaration (county × year) — 2004 quad, 2005 Wilma, 2017 Irma, 2018 Michael | baseline | Y | testing disruption, displacement | **OpenFEMA** *Disaster Declarations Summaries v2* (county 1964→, no auth) | API: <https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2> |
| Storm track / wind swath (finer than county) | selection | Y | sharper exposure | NOAA **HURDAT2** / IBTrACS | NOAA NHC |
| Class-Size-Reduction compliance (2003–2010 phase-in) | baseline | Y | mechanical achievement confounder, exactly the FCAT window | FLDOE **Class Size** reports | FLDOE Accountability |
| School grade / accountability pressure (A+ plan, school-recognition $) | selection / keep-out | Y | incentive shock; partly an *outcome* | FLDOE **School Grades archives**, 1999-00 → 2024-25 (per-year Excel) | <https://www.fldoe.org/accountability/accountability-reporting/school-grades/archives.stml> |
| Test regime (FCAT / FCAT 2.0 / FSA / FAST-B.E.S.T.) | FE | Y | scale breaks | already in `assessments` (`regime` label) | — |
| COVID: 2020 spring gap (no test); 2021 depressed scores + low participation | filter | Y | drop 2020 (already absent); flag/trim 2021 | `assessments` participation / `n_students` fields | already fetched |
| Test participation rate / % tested | baseline | Y | selective testing biases means; changes with ELL/SWD rules | FLDOE assessment files (participation columns) | in `assessments` raw |

---

## Bad-control / estimation notes

- **Do not** put post-treatment composition, teacher turnover, spending,
  attendance, discipline, health, or home values in the baseline spec — they are
  channels or consequences. Lag Cluster A covariates to t−1 in the baseline.
- Staggered adoption 1998–2026 with plausibly heterogeneous effects → use a
  modern DiD estimator (Callaway–Sant'Anna, Sun–Abraham, de
  Chaisemartin–D'Haultfœuille, Borusyak–Jaravel–Spiess) with not-yet-/never-
  treated controls, not plain two-way FE.
- Cluster SEs at the **barrier / roadway-segment** level (treatment is assigned
  there); consider two-way school × segment.
- Weight by test-takers (`z_mss_w`); restrict to regular schools with stable
  grade spans; handle school open/close (MSID `DATE_OPENED` / `DATE_CLOSED`).

---

## Proposed source-module clustering

New modules under `src/regions/florida/sources/`, each a `DataSource` with
`fetch` / `preprocess` (and `assemble` where a spatial join to schools is
needed). Ordered roughly by priority for the main analysis.

| Module | Produces | Cluster | Prereq | Access method |
|---|---|---|---|---|
| `schools` **(implemented)** | `msid` ↔ `NCESSCH` ↔ lat/lon crosswalk; regular-school flags; open/close panel; **Cluster A covariates** (was `school_panel`); stage-2 barrier treatment matching, algorithms 1–5 | `noise_barriers` (stage 2), `road_network` (algorithms 3–5) | absorbs `master_file` (MSID); crosswalk **embedded in MSID** (`FEDERAL_DIST_NO`/`FEDERAL_SCHL_NO`), no CCD `ST_SCHID` matching for the primary path. CCD/CRDC/EDFacts via Urban Institute Education Data API. Full design: [`schools/README.md`](schools/README.md) |
| `road_network` **(implemented)** | Roadway centerlines + linear referencing; nearest-road / side-of-centerline / corridor-match helpers consumed by `schools` stage 2 | — (feeds `schools`, `traffic`, `road_projects`) | FGDL `rciroads` — public, no auth. Full design: [`road_network/README.md`](road_network/README.md) |
| `panel` **(implemented, first-pass)** | Final `msid × grade × subject × year` join of `assessments` + `schools` — **not** yet a covariate module itself, just the assembly point the other modules below would feed into once built | `assessments`, `schools` | pure local join, no fetch. See [`README.md`](README.md#panel--the-final-event-study-join-assemble-only) |
| `traffic` **(implemented: fetch, preprocess, assemble; joined into `panel`)** | AADT panel (`roadway_id × release_year`, length-weighted across segments pooled from every FGDL release sharing a year), from many `road-network` FGDL `rciroads` releases rather than a new provider; schools matched to a roadway and joined to its AADT time series (`school_aadt_panel.parquet`, 89.7% match rate) — plus `aadt_local`, a current-snapshot local-intensity-scaled, school-specific estimate (median 13% deviation from the roadway-wide mean); now left-joined into `event_study_panel.parquet` by nearest release year as both `traffic_aadt`/`traffic_aadt_local` (71.3% of rows matched, markedly lower in 2003–2010 than 2014+ — flagged, not yet explained). Truck AADT still open. Full design: [`traffic/README.md`](traffic/README.md) | C | `road_network` (fetch machinery reused directly), `schools` (`assemble`) | FGDL `rciroads` archive (57 releases, `jun04`→`jul26`) — public, no auth |
| `road_projects` | Work-Program construction/widening/PD&E projects with dates, roadway-linked | D | `noise_barriers`, `road_network` | FDOT Open Data Hub (`Work Program Current`, `Current Active Construction Projects`) + FM database; possible manual pull for pre-2010 |
| `staff` **(implemented: fetch, preprocess, assemble; joined into `panel`)** | Teacher salary/experience/median-salary (district) + in-field/out-of-field teaching (SCHOOL-level) from two FLDOE workbooks fetched via their Wayback Machine archive (`www.fldoe.org` itself blocks scripted clients); per-pupil expenditure (district, via NCES CCD F-33, Urban API, 1995-2020) joined through a modal `district->leaid` crosswalk (min 88.5%/median 100% coverage). Turnover and % advanced degree not built (no aggregate FLDOE source found). Full design: [`staff/README.md`](staff/README.md) | B | `schools` | FLDOE Staff/Salary workbooks via Wayback Machine; Urban API `school-districts/ccd/finance` (no auth) |
| `shocks` | Hurricane declarations (county×year), class-size compliance, school grades | G | — | OpenFEMA API (no auth); FLDOE per-year Excel |
| `air_quality` | Tract/1-km PM2.5, O3, NO2 daily+annual, matched to school buffers | E | `schools` | EPA FAQSD + Requia SEDAC/Dataverse downloads; EPA AQS files |
| `neighbourhood` **(implemented: fetch, preprocess, assemble; joined into `panel`)** | Tract ACS demographics (income/poverty/tenure/education/mobility, 16 years 2009-2024) + Zillow ZHVI home values, matched to schools via a point-in-polygon spatial join (the only Florida source doing polygon containment, not linear referencing) against two tract-boundary vintages (2010/2020, since ACS5 switched vintage at its "2020" release) + one ZCTA layer. 68.0% of panel rows matched ACS, 98.6% matched ZHVI. Full design: [`neighbourhood/README.md`](neighbourhood/README.md) | F | `schools` | Census API (key required, user-supplied) + Zillow public CSV + Census TIGER cartographic boundaries (no auth) |

**`panel` is a join point, not a covariate cluster of its own** — it exists
so `traffic`/`road_projects`/`staff`/`shocks`/`air_quality`/`neighbourhood`
each have one place to land their columns once built (a left join onto
`event_study_panel.parquet` by `msid`, or `msid`+`year` for time-varying
ones), rather than each needing its own final-join logic.

**Region-agnostic candidates.** The CCD/CRDC/EDFacts pull inside `schools`,
`staff` (via CCD), `shocks` (OpenFEMA), `air_quality`, and `neighbourhood` all
pull *national* datasets and only the school/tract match is Florida-specific —
when the per-region source registry lands (design `docs/02`), the fetch halves of
these likely belong in a shared `src/core` sources area with a thin Florida
`assemble` on top. `traffic` and `road_projects` are genuinely FDOT-specific and
stay under `florida/`.
