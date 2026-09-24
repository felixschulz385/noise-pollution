# Sweden — covariates for the barrier-construction event study

Catalogue of control / covariate variables for the **main analysis**: a
staggered event study of Trafikverket road/rail noise-barrier construction
on school achievement (outcome: `assessments`, panel unit
`skolenhetskod × year [× subject/measure]`, treatment: `schools assemble`'s
barrier-match/timing). Mirrors Florida's `covariates.md` in structure and
role tags — researched 2026-09-15 following the same "check live, don't
assume" discipline as the rest of this pipeline; confidence is marked per
source since several candidates below are identified but not yet verified
live. **Cluster C (traffic) was built 2026-09-16** (now an 8-order
historical panel), **Cluster F was built 2026-09-17** (DeSO2018
boundaries + mean net income, post-secondary education share, and
employment rate, see its section below); the rest remain research-only,
unlike Florida's clusters C/D/G which are all already built and joined
into a panel.

## How to read this

Same design logic as Florida: `schools`/`year` fixed effects absorb every
*time-invariant* confounder, so what's left is *time-varying* confounders
correlated with *barrier timing*. Trafikverket sites barriers by modelled
noise level, which tracks traffic growth — same core identification risk
as FDOT in Florida, driving the same priority order.

**Role** column (identical convention to Florida's):

| Role | Meaning |
|---|---|
| `FE` | absorbed by design; listed for completeness, not a regressor |
| `baseline` | include as a covariate in the main specification |
| `selection` | robustness spec, probes barrier-siting endogeneity / pre-trends |
| `keep-out` | post-treatment mediator — **exclude** from baseline |
| `treatment` | defines exposure intensity / sample split, not a control |
| `filter` | sample-construction rule, not a regressor |

**Confidence** column (new vs. Florida's — most of this catalogue is
research, not confirmed-by-fetching): `confirmed` = checked live this
session (a real API/document response, not just a product's existence
mentioned somewhere); `candidate` = a real, named product/institution
found, but the actual data (schema, coverage, access mechanism) not
verified live; `unconfirmed` = plausible based on general knowledge of
Swedish institutions, not even a specific product identified.

---

## Cluster C — Traffic & acoustic exposure — **BUILT 2026-09-16**

The core confounder, same reasoning as Florida: noise scales with traffic
volume, so a traffic trend at a to-be-treated road masquerades as a wall
effect. **Implemented and run** — see [`traffic/README.md`](traffic/README.md)
for the full real-run writeup; this section is kept as the original
research record, with the two open questions it flagged now resolved
(marked inline below) rather than rewritten.

| Variable | Role | TV? | Why it matters | Source | Confidence |
|---|---|---|---|---|---|
| ÅDT (årsdygnstrafik / AADT), all vehicles + heavy vehicles + axle pairs | baseline | Y | direct noise driver | Trafikverket NVDB **"Trafik"** data product | **confirmed** |
| Time-of-day × vehicle-class flow (light/medium/heavy × 06-18/18-22/22-06) | baseline | Y | **purpose-built for noise modelling** — see below | same product | **confirmed** |
| Measurement method / uncertainty / measurement-year flags | selection | Y | data-quality controls, same spirit as Florida's `n_students`/suppression flags | same product | **confirmed** |
| Rail traffic volume (train frequency/tonnage per Bandel) | baseline | Y | rail analogue of ÅDT | Trafikverket rail traffic data (product not identified) | unconfirmed |

**Confirmed live 2026-09-15** (Trafikverket's own "Dataproduktspecifikation
— Trafik", v4.0, fetched and read in full): the **`Trafik`** NVDB data
product is **open data, CC0 1.0, Lastkajen**, EPSG:3006, covering all of
Sweden from **1982-01-01** ("Historik: Ja"). Core attributes: `ÅDT samtliga
fordon`, `ÅDT tunga fordon`, `ÅDT axelpar` (all in vehicles/day), plus
**nine time-of-day × vehicle-class attributes**
(`ÅDT {lätta,medeltunga,tunga} fordon {06-18,18-22,22-06}`) that the spec
explicitly says were **"framtagna för att passa bullerberäkningsmodellen
Common Noise Assessment Methods in Europe (CNOSSOS-EU)"** — i.e.
Trafikverket already breaks this data out specifically to feed the EU's
official noise-calculation methodology. This is a better-suited raw
ingredient than Florida's plain AADT for a noise-pollution study
specifically. Also present: `Mätmetod` (measured whole-year / sampled /
estimated with or without support measurement), `Osäkerhet` (uncertainty,
required when sampled), `Mätårsperiod` (YYYYMM — the actual measurement
timestamp per segment, confirming this **is** a genuine time-stamped
record, not just a current snapshot label).

**Real coverage caveat, same shape as Florida's own AADT-coverage gap**:
"Resultat från mätningar levereras normalt årligen men inte för hela
vägnätet varje år" — roads numbered 1-499 (Europaväg/riksväg/primär
länsväg) remeasured **every 4 years**, roads ≥500 (other länsväg) every
**12 years**. So any single Lastkajen pull is a snapshot with per-segment
staggered vintages (`Mätårsperiod` tells you which), not a uniformly
current picture — mirrors exactly the `traffic` module's Florida lesson
("FGDL's own AADT-field coverage... not a matching bug") and the same
`aadt_panel`-style length-weighted, multi-release design would likely be
needed here too if a historical panel (not just current snapshot) is
wanted. **Resolved 2026-09-16, positively — after an intermediate wrong
conclusion that's worth recording**: Lastkajen's `Trafik` order form
carries a real `Betraktelsedatum` (as-of date) field, and it **does**
return the genuine historical `[VALID_FROM, VALID_TO)` window that was in
effect on that date. An initial test (comparing two orders joined on
`ELEMENT_ID` + `VALID_FROM`) wrongly concluded otherwise — that join
silently excluded the ~47% of segments whose window boundary actually
differed between orders, i.e. exactly the rows carrying the real signal,
and compared only the unchanged remainder. A user-provided real example
(a specific road section's historical breakdown on Trafikverket's own web
viewer) caught the error: the same section's rows in our two real orders
matched the viewer's own historical windows exactly, ÅDT and uncertainty
included. See `traffic/README.md`'s "Correction" section for the full
story. **A real historical Sweden traffic panel is achievable by ordering
more `Betraktelsedatum` snapshots** — `preprocess`/`assemble`/`panel`
were rebuilt around this (union every order's full window history,
interval-overlap join by year) and re-run. **Confirmed further
2026-09-16**: six more orders were placed (`Betraktelsedatum` 1999,
2003, 2007, 2011, 2015, 2019-01-01, spread across the analysis period at
roughly the confirmed remeasurement cadence), bringing the total to 8
orders. Combining all 8 recovers **295,696 distinct historical windows,
77,485 elements, `VALID_FROM` spanning 1984-2026**, and flattens the
joined panel's match rate from a ~0%-pre-2011-rising-to-70% shape to a
roughly uniform **~30-40% across 1998-2019, ~50% for 2022-2025** — i.e.
placing more orders is a real, working lever for extending historical
coverage, not just a theoretical one.

**Access**: Lastkajen (`lastkajen.trafikverket.se`), same
credentials/infrastructure already used for `noise_barriers`/
`road_network` — confirmed 2026-09-16 to be a custom-order product (create
selection, choose `Trafik` + `Sverige` + GeoPackage), not a ready-made
Sverigefiler package. Referenssystem: linear-referenced to **"Det svenska
vägnätet"** via `Avsnittsidentitet` (section identity). **Resolved
2026-09-16**: `ELEMENT_ID` DOES join directly to `road_network`'s own
`element_id`, no crosswalk needed — checked live, 100.0% (54,444/54,454)
of `Trafik`'s distinct element_ids found verbatim in `road_network.
parquet`.

---

## Cluster D — Road-works / construction projects — retention confirmed 2026-09-16, low

Walls are often installed as part of a larger road project; the project
itself is disruptive and frequently adds capacity (→ traffic), both
coinciding with wall completion — same Florida Cluster D logic.

| Variable | Role | TV? | Why it matters | Source | Confidence |
|---|---|---|---|---|---|
| Active/planned road work presence & dates, roadway-linked | baseline / treatment-split | Y | co-timed confounder | Trafikverket **`Situation`** object type (`road.trafficinfo` namespace) | **candidate** |
| Project type (resurfacing / widening / barrier / restriction) | treatment-split | Y | widening vs. standalone barrier | `Situation`'s own category/type fields (not inspected) | candidate |

**Confirmed live**: Trafikverket publishes open data on **all ongoing and
planned road works affecting traffic** via the exact same
`api.trafikinfo.trafikverket.se` REST API this repo **already has working
authenticated infrastructure for** (`_trafikverket.py`'s
`trafikverket_api_call_json`, currently used by `stations`/`timetable`) —
the relevant object type is **`Situation`** (namespace `road.trafficinfo`,
currently schema version 1.6), which covers traffic messages, road work,
accidents, and restrictions in one type. This is the **lowest-friction**
cluster to build of all six: no new auth, no new fetch pattern, just a new
query object type against code that already works.

**Confirmed live 2026-09-16 (not just suspected anymore)**: queried the
real API directly for `Deviation.MessageType = "Vägarbete"` (roadwork)
situations with an `EndTime` in the past, at several cutoffs. **Zero**
concluded roadworks with `EndTime` before 2025-01-01 were retrievable;
**4** situations (8 deviations) with `EndTime` before 2026-06-01 were.
So retention for a *concluded* situation runs out somewhere in roughly the
8-20 months before query time -- call it **about a year**, not multi-year.
This is exactly the same shape of gap Florida's own `road_projects` hit
(current-only services), just quantified now instead of assumed: a
roadwork project concluded near a barrier built in, say, 2015 is **not
retrievable today** -- confirmed, not hypothetical. **This rules out
`Situation` as a source for the barrier-era road-works covariate this
cluster was meant to supply.** It remains useful only for a genuinely
current/near-term "is there active road work near this school right now"
signal, not for the historical co-timing analysis `covariates.md`'s
Cluster D framing describes. Still the lowest-friction cluster to query
(reuses `_trafikverket.py` verbatim), but low friction doesn't help if the
data it returns can't answer the actual question.

---

## Cluster F — Neighbourhood & socioeconomic composition — **BUILT 2026-09-17 (income, education, employment)**

Diagnostics for sorting / capitalisation around barriers, same Florida
framing (`selection`, not baseline, since a wall that raises/lowers nearby
property values makes these mediators) — plus a genuinely useful,
**fully open** substitute for the individual-level RTB/population-register
covariates `sweden_noise_overview.tex`'s Table 2 flags as MONA-gated.

| Variable | Role | TV? | Why it matters | Source | Confidence |
|---|---|---|---|---|---|
| Mean net income per DeSO, by year | selection | Y | sorting / gentrification diagnostic | SCB `Tab2InkDesoRegso` (PxWebApi) | **confirmed, built** |
| Population share with post-secondary education per DeSO, by year | selection | Y | education-composition diagnostic | SCB `UtbSUNBefDesoRegso` (PxWebApi) | **confirmed, built** |
| Employment rate per DeSO, by year | selection | Y | labour-market composition diagnostic | SCB `ArRegDesoStatusN` (PxWebApi) | **confirmed, built** |
| Income-class shares / economic-standard tables (`Tab1`/`Tab3`/`Tab4InkDesoRegso`) | selection | Y | finer income distribution than the mean alone | same PxWebApi folder (`HE0110I`) | confirmed live, not fetched |
| Small-area boundaries for joining the above to schools | — | ~N | spatial join unit | SCB **DeSO 2018** open geodata (WFS) | **confirmed, built** |

**Implemented and run** — see [`neighbourhood/README.md`](neighbourhood/README.md)
for the full write-up; this section keeps the original research record plus
what the live build resolved.

**Confirmed live 2026-09-17** (SCB's PxWebApi `api.scb.se/OV0104/v1/doris`,
the same underlying PxWeb tech as Skolverket's, query lessons transfer
directly; a `v2beta` search endpoint at the same host, `.../v2beta/api/v2/tables?query=<table id>`,
is a much faster way to locate a table's folder path than crawling the v1
tree node by node):

- **Exact DeSO-grain table IDs located** (the open item the 2026-09-15
  research pass left unresolved): income `Tab1-4InkDesoRegso`
  (`HE/HE0110/HE0110I`, 2011-2024 nominal), education `UtbSUNBefDesoRegso`
  (2015-2023, frozen) + a 2024-2025 successor table (`UF/UF0506/UF0506D`),
  employment `TAB6680` "Arbetsmarknadsstatus ... DeSO/RegSO" (`AM/AM0210/AM0210G`,
  2020-2024).
- **DeSO was redrawn in 2025** — SCB's geoserver
  (`geodata.scb.se/geoserver/stat/wfs`) exposes `stat:DeSO_2018` (**5,984**
  areas, confirmed by `numberMatched`) and `stat:DeSO_2025` (**6,160**
  areas) as two separate WFS layers; the income table's own `Region`
  dimension likewise carries both a bare code (`0114C1010`) and a
  `_DeSO2025`-suffixed sibling (`0114C1010_DeSO2025`) side by side. Same
  "which vintage" judgment call as the assessments grading-reform
  stitching decision — resolved for this v1 build by using **DeSO2018
  throughout** (user decision 2026-09-17), with the 2025 redraw flagged as
  a known future gap, not stitched.
- **Real coverage is narrower than the nominal "2011-2024" table range**:
  a live query against a real DeSO2018 code returned a genuine
  `None`/`".."` (suppressed) value for **2024** — SCB's own table note
  confirms referensår 2024 onward is published only under the *new*
  DeSO2025 codes. So a DeSO2018-keyed pull's real usable span is
  **2011-2023**, one year short of the nominal range. Same "check the real
  values, not the table's own nominal coverage" lesson `traffic`'s AADT
  gap and the grading-reform stitching already taught.
- **A real bug caught by live-testing, not by a code read**: the DeSO
  code's area-density letter is **not** always `C` — a live 30-area WFS
  sample returned codes using `A`, `B`, *and* `C` (e.g. `0840A0010`,
  `1273B2010`), and an early version of the DeSO2018-code regex filter
  hardcoded `C`, which would have silently dropped most of the country's
  real DeSO-income rows. Caught by running the real fetch against a
  handful of live codes and checking the row count, not by assumption.
- **WFS boundary fetch is genuinely slow, no simplified layer exists**: a
  live timing test found ~90 seconds for 500 features (full-resolution
  national coastline/border detail, no generalized/simplified DeSO layer
  on this geoserver) — a full 5,984-area fetch is a real ~15-20 minute
  one-time pull, paginated and resumable (mirrors `assessments/
  kvalitetssystem.py`'s per-batch save/skip discipline), not a single
  request.

**Real full-national run, 2026-09-17** (all real, not estimated — see
[`neighbourhood/README.md`](neighbourhood/README.md) for the full
write-up): boundary fetch — 12 pages → **5,984 DeSO areas, 290 distinct
kommun** (an exact match to Sweden's real municipality count). All three
PxWeb tables fetched at full scale, 12 batches each, all 5,984 DeSO2018
codes: income **83,776 rows** (real coverage 99.9-100% for 2011-2023,
**0.0%** for 2024 — fully suppressed under DeSO2018 codes, not partial),
education **53,856 rows exactly** (100.0% real coverage every year,
2015-2023, no suppression at all — mean post-secondary-education share
42.8%, range 11.4%-93.2% across areas), employment **29,920 rows exactly**
(100.0% for 2020-2023, **0.0%** for 2024, same full-suppression shape as
income). `assemble` — point-in-polygon match against 9,520 geocoded
schools: **9,519 matched (99.99%)**, the one failure a real upstream
geocoding error (a school's coordinate lands in the North Sea, nowhere
near Sweden) rather than a distance-cutoff miss — a strong contrast with
every nearest-segment covariate module in this pipeline, since DeSO tiles
the whole country with no gaps. **133,267 panel rows**, all three
subsources outer-merged on `(desokod, year)` (real per-column coverage
across the panel: income 92.9%, education 64.3%, employment 28.6% —
each table's own real window, not a dropped row for the years it lacks).

**A second real bug caught by the full-scale run, not by a code read**:
`pandas.pivot_table`'s default `dropna=True` silently drops any
`(desokod, year)` whose every pivoted column is `NaN` — the real 2024
employment case (both "sysselsatta" and "totalt" suppressed) disappeared
entirely from an early version's output instead of surviving as a real
`NaN` row. Fixed with `dropna=False`; see `neighbourhood/README.md` for
the full story.

**Not yet built**: `Tab1`/`Tab3`/`Tab4InkDesoRegso` (income-class shares,
economic standard, same PxWeb folder as the mean-income table already
built) and education's 2024-2025 successor table (which genuinely can't
be added under DeSO2018 codes at all — no such codes exist in it, unlike
income/employment's "exists but suppressed" shape).

---

## Cluster G — Shocks

Weakest research result of the six clusters — a real institution and
several named tools were found, but **no specific downloadable product
comparable to Florida's OpenFEMA county×year declarations table was
confirmed live**.

| Variable | Role | TV? | Why it matters | Source | Confidence |
|---|---|---|---|---|---|
| Municipality/county-level major-incident or crisis declarations | baseline | Y | Florida-hurricane-declaration analogue | MSB (Myndigheten för samhällsskydd och beredskap) | unconfirmed |
| Individual rescue-service incident reports (~100k/year, geolocated) | selection | Y | finer-grained but different shape than Florida's shocks | MSB **IDA** (`ida.msb.se`) / `olyckskartan.se` | candidate |
| Severe-weather warnings (storms, extreme heat) | baseline | Y | plausible Swedish analogue to hurricane declarations | SMHI warning archive | unconfirmed |

MSB documents ~100,000 rescue-service incidents/year via
"händelserapporter" (incident reports) in its **IDA** statistics/analysis
tool, with a public map viewer at `olyckskartan.se` — but this is
routine-accident-shaped data (closer to a 911-dispatch log than a
"declared disaster"), a genuinely different shape from Florida's
county-level FEMA major-disaster declarations, and no API/bulk-download
mechanism was confirmed this session (only an interactive dashboard).
**Krisinformation.se** ("Öppen data" page found) aggregates crisis
information across Swedish authorities and may have a cleaner open-data
feed — not checked. If a Florida-style "was this county hit by a
hurricane/major flood this year" binary is the actual goal, **SMHI's
severe-weather-warning archive is probably the more direct analogue** and
wasn't investigated at all this session (only that SMHI's API
infrastructure generally exists, confirmed via the air-quality search
below).

---

## Cluster B — Staff

**Largely already covered — likely needs no new source module.** Unlike
Florida (where `staff` required a whole separate FLDOE Staff SIS pull),
Sweden's `assessments` `kvalitetssystem` table (2022/23-2025/26,
`docs/data/sweden/assessments/README.md` §1) already carries staff-related
measures among its 51 `mått` — teacher/pedagogical-staff counts,
credential-rate (`andel med behörighet`), and student-per-teacher ratios
were seen directly in the live metadata fetched for that source.

| Variable | Role | TV? | Why it matters | Source | Confidence |
|---|---|---|---|---|---|
| Teacher FTE, credential rate, student-teacher ratio | selection / keep-out | Y | teacher-quality confounder / mediator | already inside `assessments` `kvalitetssystem` | **confirmed** (already fetched) |
| Same, pre-2022 era | selection | Y | needed if the panel extends before the kvalitetssystem era | SIRIS archive — a `Personal`/staff-topic dataset series likely exists in `datasets.csv` alongside the confirmed `139`/`95` slutbetyg series | candidate, not located |

If Cluster A-style staff covariates are wanted for the pre-2022 SIRIS era
too, the `datasets.csv` manifest (`docs/data/sweden/assessments/README.md`
§2) almost certainly has a staff/personnel topic among its 6,787 rows —
not searched for specifically this session (only the achievement-outcome
series were).

---

## Cluster E — Air co-pollution

Same Florida framing: not a baseline control (barriers also cut near-road
air pollution, a co-treatment/mediator, not an independent confounder) —
lowest priority of the six, matching Florida's own non-baseline
designation for this cluster.

| Variable | Role | TV? | Why it matters | Source | Confidence |
|---|---|---|---|---|---|
| Station-level PM2.5/PM10/NO2/O3 measurements | keep-out / mechanism | Y | co-treatment, near-road marker | SMHI **Luftwebb** (national air-quality data steward for Naturvårdsverket) | **candidate** |
| Modelled dispersion surface (finer than station points) | keep-out / mechanism | Y | Requia-1km-surface analogue | SMHI **Simair** dispersion model | unconfirmed |

**Confirmed live**: SMHI is Naturvårdsverket's designated national data
steward for air-quality data, publishing both historical and real-time
measurements via a Sensor Observation Service (SOS) + REST-API, plus
WFS/WMS station metadata — genuinely open. Not investigated further given
Cluster E's low priority even in Florida's own catalogue.

---

## Bad-control / estimation notes

Same as Florida's, unchanged in substance:

- Post-treatment composition, staff turnover, spending, home values are
  channels/consequences, not baseline controls.
- Cluster SEs at the barrier / roadway-or-route level (treatment assigned
  there).
- Weight by student counts where available; restrict to schools with a
  stable grade span; handle school open/close (still an open question in
  `schools/README.md` — no `DATE_CLOSED`-equivalent field confirmed).
- The `assessments` cross-era stitching decision
  (`docs/data/sweden/assessments/README.md` §4) determines the outcome
  panel's actual span before any of this matters in practice.

---

## Proposed source-module clustering, priority order

Mirrors Florida's own priority logic (traffic > road-works > shocks >
staff > neighbourhood > air-quality) since the underlying identification
story is the same; adjusted where a cluster's real friction/confidence
this session pushes it up or down.

| Module | Produces | Cluster | Prereq | Access method | Build friction |
|---|---|---|---|---|---|
| `traffic` — **BUILT 2026-09-16, 8-order historical panel** | Real multi-vintage historical ÅDT + CNOSSOS-ready time/vehicle-class splits, matched to schools directly (nearest-segment), joined into `panel` via a real interval-overlap-by-year match | C | `schools` (`preprocess`, for coordinates) | Lastkajen `Trafik` product | Done — 8 `Betraktelsedatum` orders placed (1999, 2003, 2007, 2011, 2015, 2019, 2022, 2026) recover 295,696 windows/77,485 elements spanning 1984-2026, flattening the panel's traffic match rate to a roughly uniform ~30-40% across 1998-2019 (up from a ~0%-pre-2011 shape with 2 orders); more orders would still push it higher, no code changes needed |
| `road_projects` — **not viable as scoped** | Only a *current/near-term* road-work signal, not historical | D | — | `api.trafikinfo.trafikverket.se`, `Situation` object type | Low friction to query, but **confirmed 2026-09-16** retention for concluded situations is only ~1 year — can't answer "was there road work near this school when its barrier was built" for anything but the most recent treatments. Would need a different source for the historical version of this covariate |
| `neighbourhood` — **BUILT 2026-09-17 (income, education, employment)** | DeSO2018-grain mean net income (2011-2023), post-secondary education share (2015-2023), employment rate (2020-2023), outer-merged and point-in-polygon matched to schools | F | `schools` (`preprocess`, for coordinates) | SCB geoserver WFS (`stat:DeSO_2018` boundaries) + PxWebApi (`Tab2InkDesoRegso`/`UtbSUNBefDesoRegso`/`ArRegDesoStatusN`) | Done for all three planned subsources — see [`neighbourhood/README.md`](neighbourhood/README.md) for real match/coverage numbers. `Tab1`/`Tab3`/`Tab4InkDesoRegso` (finer income tables) remain, plus wiring into `panel` |
| `staff` | Mostly **already covered** by `assessments`' kvalitetssystem measures for 2022+; pre-2022 needs a SIRIS `datasets.csv` search, not yet done | B | `assessments` | Skolverket (already-built infra) | **Very low** for 2022+ (no new code); unknown for pre-2022 until the SIRIS series is located |
| `shocks` (new) | Municipality/county-level severe-event indicator | G | — | Not identified — MSB IDA (candidate) or SMHI warnings (unconfirmed) | **High** — the weakest research result of the six, needs another research pass before any build decision |
| `air_quality` | Station/modelled air-pollution surface, matched to schools | E | `schools` | SMHI Luftwebb (SOS/REST-API) + Simair | Low priority, not scoped further (matches Florida's own non-baseline call) |

**Not investigated this session at all**: whether any of these products'
`Avsnittsidentitet`/DeSO-code/Situation-location fields join cleanly to
the identifiers already established in `noise_barriers`/`road_network`/
`network`/`schools` — every module above needs that check live (the same
"confirm the join key before building on it" discipline that caught the
`Vägtrafiknät` route-number gap and the `element_id` non-uniqueness issue
earlier this session) before writing any fetch code.
