# Data status — Florida & Sweden (as of 2026-09-18)

Both pipelines study the same design: a staggered event study of road noise-barrier construction on school achievement, school/time fixed effects, so the open work is chiefly **time-varying confounders correlated with barrier timing**. Florida is the mature pipeline (outcome panel + 3 covariate clusters built and joined); Sweden's outcome panel, traffic, and neighbourhood (income/education/employment) are now built and joined, the rest of its covariate catalogue is research-only.

## Florida

- **Grain**: one row per `(msid, grade, subject, year)` — **660,681 rows, 5,039 distinct schools, years 2003–2026** (2020 excluded, no spring testing that year).
- **Subjects & grades tested**: ELA (grades 3–10), Mathematics (grades 3–8), Statewide Science (grades 5 & 8), and End-of-Course exams (Algebra 1, Geometry, Biology 1, Civics, U.S. History). ELA covers **~3,000 schools/year in 2003 rising to ~3,800 by 2025–26**; Math **~2,600 → ~3,200**; Science close behind both. The EOCs are far thinner and only exist from 2011 on — Algebra 1 **~1,200–1,900 schools/year**, U.S. History (a single high-school course) **under 1,000**. 
- **Matched schools**: of 5,984 placed schools, 5,366 (89.7%) matched to a roadway for the traffic covariate. Barrier-treatment timing has three parallel matching tiers, each a strict refinement of the last: **513 ever-treated schools** under point-matching (`_point`) → **293** under `_same_route` → **221** under the strictest `_same_side` definition (the recommended baseline).

| Cluster / module | Status | Notes |
|------------------------|------------------------|------------------------|
| `assessments` (outcome) | **Done** | 435 files, 2003–2026 (no 2020), 661k rows, 5,039 schools. `z_mss`/`z_mss_w` differences out FCAT→FCAT 2.0→FSA→FAST regime breaks. |
| `schools` + `noise_barriers` + `road_network` (spine, treatment) | **Done** | 3 parallel treatment-timing tiers (`_point`/`_same_route`/`_same_side`); `_same_side` recommended baseline. |
| `panel` (final join) | **Done, first-pass** | 660,681 rows, 5,039 schools, 2003–2026. Missing `staff` and `neighbourhood` covariates. |
| Cluster C — Traffic (AADT) | **Built + joined** | 71.3% panel match; pre-2016 coverage weaker (FGDL field sparsity, confirmed real, not a bug). |
| Cluster D — Road-works | **Built + joined** | 4.5% panel match (small — services are current-window only, pre-2019 archive gap). |
| Cluster G — Shocks (hurricanes) | **Built + joined** | 44.7% panel match (county-wide declarations, high hit rate by nature). |
| Cluster B — Staff/fiscal | **Not started** | FLDOE Staff SIS + Teacher Salary Data identified, per-year XLSX, not fetched. |
| Cluster F — Neighbourhood/housing | **Not started** | Census ACS + Zillow ZHVI identified, not fetched. |
| Cluster E — Air quality | **Deprioritized** | Co-treatment/mediator, not a baseline control by design. |

## Sweden

- **Grain**: `panel` is long — one row per `(skolenhetskod, year, era, outcome_name)` — **437,948 rows, 2,651 distinct schools, läsår 1998–2019** (SIRIS's own span; `kvalitetssystem` excluded from this join, see below).

- **Matched schools**: barrier-treatment-tier counts (point/`same_route`/`same_side`) are computed against the full 9,520-geocoded-school universe, not split by era — road **1,251 → 967 → 4 (do not use, see below)**; rail **1,454 → 1,059 → 749**. Within the SIRIS-restricted outcome panel: 146,596 rows (33.5%, 1,023 schools) have a real traffic match; 152,768 rows (34.9%, 1,672 schools) have a real neighbourhood match.

| Cluster / module | Status | Notes |
|------------------------|------------------------|------------------------|
| `assessments` (outcome) | **Done, full scale** | `kvalitetssystem` PxWeb (2022/23–2025/26, 1.07M rows) + SIRIS archive (1998–2019). Cross-era stitching **decided 2026-09-17**: `kvalitetssystem` dropped from the panel join (kept as a standalone module); SIRIS's own pre-/post-2014/15 grading-scale reform stitched into one continuous `meritvärde_z` via within-side z-scoring. |
| `schools` + `noise_barriers` + `network`/`road_network` (spine, treatment) | **Done** | Point/`same_route` reliable; road `same_side` confirmed unreliable (barrier geometry coincides with the road centerline), `same_route` used instead. **A candidate fix (the barrier's own recorded `side` attribute) was tried and refuted 2026-09-18** — validated at scale using rail as an independent ground truth (949 barriers), `side` shows no usable correlation with the geometrically-derived side (an almost exact coin flip); see [`schools/README.md`](sweden/schools/README.md) and [`src/experiments/sweden/schools.ipynb`](../src/experiments/sweden/schools.ipynb) §3. No attribute-based substitute exists for road `same_side`. |
| `panel` (final join) | **Done, SIRIS-only** | Joins SIRIS (1998–2019) only — `kvalitetssystem` excluded (see cross-era note below). **437,948 rows, 2,651 schools, 1998–2019.** Long grain (raw per-measure rows + the stitched `meritvärde_z` series), plus traffic (interval-overlap join) and neighbourhood (plain year merge) covariates attached. |
| Cluster C — Traffic (ÅDT) | **Built + joined** | Real multi-vintage historical panel via `Betraktelsedatum` orders, now **8 orders** (1999/2003/2007/2011/2015/2019/2022/2026) — 295,696 windows/77,485 elements, spanning 1984–2026. Panel traffic match rate **~30–40%, roughly uniform across 1998–2019** (up from a thin pre-2011/~70%-by-2022 shape with only 2 orders). |
| Cluster D — Road-works | **Not viable as scoped** | `Situation` API confirmed live but \~1yr retention only — can't support historical co-timing; needs a different source. |
| Cluster F — Neighbourhood/SES | **Built + joined** | SCB DeSO-grain small-area stats (income/education/employment via PxWebApi, boundaries via geoserver WFS), point-in-polygon matched to schools (9,519/9,520, 99.99%). 133,267 assembled panel rows; joined into `panel` via a plain `(skolenhetskod, year)` merge. **`employment_rate` has 0% real coverage inside the SIRIS-restricted panel** — its real floor (2020) never overlaps 1998–2019 — income (floor 2011) and education (floor 2015) do show real values. DeSO's 2025 boundary redraw caps this module's own coverage at 2023 regardless. |
| Cluster B — Staff | **Mostly already covered** | 2022+ inside `assessments`' `kvalitetssystem` measures already; pre-2022 SIRIS staff series not yet located. |
| Cluster G — Shocks | **Weakest research result** | No confirmed analogue to FEMA declarations; MSB IDA / SMHI warnings are candidates, not verified. |
| Cluster E — Air quality | **Deprioritized** | Same non-baseline rationale as Florida; SMHI Luftwebb confirmed open but not scoped further. |

### Sweden `assessments` — cross-era stitching, decided 2026-09-17

The Sweden outcome panel used to have two open seams; both are now resolved by a judgment call rather than further research:

1. **The `kvalitetssystem` vintage is dropped from the panel join, kept separate.** A December 2019 court ruling on school-level data confidentiality forced Skolverket to stop publishing any school-unit statistics from September 2020 until a July 2021 law restored it — a genuine hole around läsår 2019/20–2021/22 — and the two vintages either side of it don't share a common outcome anyway: pre-2020 **SIRIS** (1998–2019) reports a continuous `meritvärde` (grade-point value, 0–320/340), while post-2022 **`kvalitetssystem`** (2022/23–2025/26, checked live against its full 51-measure codelist) has **no `meritvärde`-equivalent at all**, only pass/eligibility-rate shares. Rather than force these together, `kvalitetssystem` is excluded from `panel/assemble.py`'s join for now — its `fetch`/`preprocess`/`kvalitetssystem_to_long` code is untouched for a possible future standalone analysis.
2. **The grading-scale reform inside the SIRIS era itself is stitched, not left as a break.** Sweden's 2011 law replaced the old IG/G/VG/MVG scale with the current A–F scale, phased in so the last old-scale åk9 grades were spring 2014 — visible directly in the raw SIRIS files as a `(16)`→`(17)` column-label switch at that exact year. `stitch_meritvarde` (`panel/assemble.py`) now z-scores `meritvärde` separately on each side of that break and stacks the result into one continuous `meritvärde_z` outcome column, joined into the panel alongside the raw per-measure long rows.

A literature check (Böhlmark & Lindahl, Hinnerich & Vlachos, a 2022 *European Sociological Review* paper on an earlier 1997/98 Swedish grading reform, and a brand-new September 2026 RFBerlin discussion paper by Lundborg & Nieto using the same Grade-9 register) found **no paper that merges across a Swedish grading-scale reform** — the consistent practice is either z-standardizing within era and treating the reform as a discontinuity (the approach picked here), or restricting the analysis sample to one side of the boundary entirely. No paper was found using `kvalitetssystem` at all yet (it's too new). Treat "no precedent for merging" as provisional pending a further paper search — not yet a final conclusion; the within-side z-score doesn't resolve the deeper content-validity concern (grading *criteria*, not just the points scale, changed at the reform).

## Model
Both designs have **staggered treatment adoption** (walls built in different years across 1998–2026) with plausibly **heterogeneous treatment effects** across cohorts. The **Callaway–Sant'Anna (CS) estimator** is the natural fit. It also supports **covariate-conditional parallel trends** (doubly-robust estimator), given our potential barrier timing confounders.

