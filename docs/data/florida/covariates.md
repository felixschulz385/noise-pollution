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

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Teacher experience distribution, % advanced degree, % out-of-field | selection / keep-out | Y | teacher quality shifts; partly a mediator (noise → turnover) | FLDOE **Staff Information System** ("Staff in Florida's Public Schools") | FLDOE Staff pubs (per-year Excel) |
| Teacher turnover / share new to school | keep-out | Y | mechanism channel | FLDOE Staff SIS (year-over-year match) | derived |
| Average teacher salary | selection | Y | resource level / labour market | FLDOE **Teacher Salary Data** | direct XLSX: `fldoe.org/core/fileparse.php/7584/urlt/<yy>TeacherSalaryData.xlsx` |
| Per-pupil expenditure | selection / keep-out | Y | resource response | NCES CCD fiscal (F-33); FLDOE district financial reports | Urban API `school-districts/ccd/finance`; NCES |

Turnover and spending can respond *to* the barrier (or to the disruption that
precedes it), so they belong in the mechanism spec, not the baseline. CCD staff
FTE is a fallback where FLDOE SIS panels are hard to assemble.

- FLDOE Staff: <https://www.fldoe.org/accountability/data-sys/edu-info-accountability-services/pk-12-public-school-data-pubs-reports/staff.stml>

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

Walls are frequently one line item in a widening or PD&E project. The widening
adds capacity (→ traffic) and the construction itself is disruptive; both
coincide with wall completion. Need this to (a) control for it and (b) split
"wall as part of a widening" vs standalone walls.

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Adjacent widening / resurfacing / interchange / PD&E project — presence & dates | baseline / treatment-split | Y | co-timed confounder | FDOT **Five-Year Work Program** / Work Program Administration extract | Open Data Hub: *Work Program Current*, *Current Active Construction Projects*, *Construction Phase* <https://gis-fdot.opendata.arcgis.com/search?categories=projects> |
| Construction start / end / letting dates | baseline | Y | timing alignment | FDOT Work Program (FM/Financial-Management number keyed); SCO Construction <https://scoc.fdot.gov/> | Open Data Hub; `data.fdot.gov/road/projects/` |
| Project type / scope code | treatment-split | Y | widening vs standalone barrier vs resurfacing | FDOT Work Program | same |
| Quieter-pavement resurfacing (OGFC / open-graded) | selection | Y | a *different* noise reduction, could be attributed to the wall | FDOT RCI pavement / resurfacing contracts | FDOT Data portal |

Pre-~2010 history may need a manual pull from Work Program archives or an FDOT
data request; the Open Data Hub extract is current/recent.

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

| Variable | Role | TV? | Why it matters | Source | Access |
|---|---|---|---|---|---|
| Tract median household income, poverty rate, % owner-occ., educ. attainment, % moved in last year | selection / keep-out | Y | gentrification / sorting | Census **Decennial 2000** + **ACS 5-year** (2005–09 →) | Census API <https://api.census.gov/data.html> |
| Typical home value (monthly, 2000→) | selection | Y | capitalisation & siting pre-trend | **Zillow ZHVI** (ZIP / neighbourhood / tract) | public CSV, no key: <https://www.zillow.com/research/data/> |
| Packaged tract SES / greenspace / walkability | selection | Y | convenience bundle | **NaNDA** (National Neighborhood Data Archive) | ICPSR openICPSR |

---

## Cluster G — Shocks & policy

Mostly analysis-side indicator controls; some overlap with FE.

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
| `traffic` | AADT + Truck AADT segment panel, joined to schools by buffer | C | `schools`, `road_network` | FDOT Open Data Hub ArcGIS REST + `FTI.mdb` download — public, no auth |
| `road_projects` | Work-Program construction/widening/PD&E projects with dates, roadway-linked | D | `noise_barriers`, `road_network` | FDOT Open Data Hub (`Work Program Current`, `Current Active Construction Projects`) + FM database; possible manual pull for pre-2010 |
| `staff` | Teacher experience / degree / out-of-field / turnover / salary; per-pupil spend | B | `schools` | FLDOE Staff SIS + Teacher Salary Data (per-year XLSX); CCD fiscal via Urban API |
| `shocks` | Hurricane declarations (county×year), class-size compliance, school grades | G | — | OpenFEMA API (no auth); FLDOE per-year Excel |
| `air_quality` | Tract/1-km PM2.5, O3, NO2 daily+annual, matched to school buffers | E | `schools` | EPA FAQSD + Requia SEDAC/Dataverse downloads; EPA AQS files |
| `neighbourhood` | Tract ACS/decennial SES + Zillow ZHVI, matched to school tracts/ZIPs | F | `schools` | Census API + Zillow public CSV |

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
