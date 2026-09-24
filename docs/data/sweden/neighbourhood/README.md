# `neighbourhood`

SCB DeSO-grain small-area statistics — Covariate Cluster F
(`docs/data/sweden/covariates.md`). Sorting/gentrification diagnostic for
the barrier event study (`selection` role, not baseline: a wall that moves
nearby property values makes neighbourhood composition a post-treatment
mediator, not an independent confounder) and a genuinely useful, fully
open substitute for the individual-level RTB/population-register
covariates `sweden_noise_overview.tex`'s Table 2 flags as MONA-gated.

**Status (2026-09-17): all three planned subsources — income, education,
employment — are built, run against real national data, and joined into
`panel`.** `fetch-boundaries`/`preprocess-boundaries` (SCB geoserver WFS,
DeSO 2018 polygons), `fetch-income`/`preprocess-income`
(`Tab2InkDesoRegso`, mean net income), `fetch-education`/
`preprocess-education` (`UtbSUNBefDesoRegso`, population by education
level), `fetch-employment`/`preprocess-employment` (`ArRegDesoStatusN`,
employment status) all implemented, plus `assemble` (point-in-polygon
school↔DeSO match, outer-merge the three DeSO-grain time series on
`(desokod, year)`, then attach the merged panel to every matched school)
and `panel/assemble.py::attach_neighbourhood` (a plain `(skolenhetskod,
year)` merge onto the long event-study table, see "Joined into `panel`"
below).
`Tab1`/`Tab3`/`Tab4InkDesoRegso` (finer income-distribution tables in the
same PxWeb folder as the mean-income table already built) remain
identified but not fetched — the mean alone was judged sufficient for a
v1 income covariate.

## Design, and the one thing genuinely different from every other Sweden covariate module

Every other assemble module in this pipeline (`traffic`, `schools`'
barrier match, the road/rail network algorithms) matches a school to its
**nearest line feature**, with a distance cutoff and a real "beyond max
distance, no match" case. DeSO is different: it's a **polygon tiling that
covers the whole country with no gaps**, so the match is point-in-polygon
containment (`gpd.sjoin(predicate="within")`), not nearest-neighbour —
essentially every geocoded school matches (see real numbers below), and a
non-match means the school's own coordinate is bad, not that it's far from
anything.

The DeSO match itself is static (one boundary vintage). All the year
variation lives in the three PxWeb tables, each joined by a plain
`(desokod, year)` merge — no interval-overlap logic needed, unlike
`panel/assemble.py::attach_traffic`, since DeSO boundaries within one
vintage don't move year to year. **The three tables have different real
coverage windows** (income 2011-2023, education 2015-2023, employment
2020-2023 — see below for why each stops at 2023, not each table's own
nominal end year), so `assemble.py::merge_deso_panels` does an **outer**
merge on `(desokod, year)`: a year covered by only one or two of the three
tables gets real `NA` in the others' columns, not a dropped row.

## DeSO was redrawn in 2025 — this module uses the 2018 vintage throughout

Confirmed live 2026-09-17: SCB's geoserver (`geodata.scb.se/geoserver/stat/wfs`)
exposes **`stat:DeSO_2018`** and **`stat:DeSO_2025`** as two separate WFS
layers — **5,984** vs. **6,160** areas (`numberMatched`, checked directly,
not estimated). Every PxWeb table's `Region` dimension carries both
vintages side by side for the same underlying area (e.g. `0114C1010` and
`0114C1010_DeSO2025`). This module uses **DeSO2018 throughout** (explicit
user decision 2026-09-17, matching most of the panel's own years), and
treats the 2025 redraw as a known future gap — same shape as the
`assessments` grading-reform cross-era stitching decision, not resolved
here either.

**Real, direct consequence for coverage — checked per table, not
assumed**:

| Table | Nominal range | Real DeSO2018 coverage | Why |
|---|---|---|---|
| Income (`Tab2InkDesoRegso`) | 2011-2024 | **2011-2023** | 2024 rows exist under DeSO2018 codes but return a genuine suppressed `None`/`".."` — confirmed 100% suppressed at full scale, not partial |
| Education (`UtbSUNBefDesoRegso`) | 2015-2023 | **2015-2023** (no gap) | This table itself is frozen ("uppdateras ej") at 2023; its 2024-2025 successor (`UtbSUNBefDesoRegsoN`) uses **only** `_DeSO2025`-suffixed codes — no DeSO2018 alternative exists for those years *at all* (a harder break than income's "exists but suppressed"), so this build doesn't fetch the successor table |
| Employment (`ArRegDesoStatusN`) | 2020-2024 | **2020-2023** | Same "exists but 100% suppressed" shape as income, confirmed live |

## How to get it

### Boundaries (WFS, no auth)

```bash
python -m src.cli sweden data neighbourhood fetch-boundaries   # ~15-20 min, resumable
python -m src.cli sweden data neighbourhood preprocess-boundaries
```

**Genuinely slow, confirmed by direct timing**: ~90 seconds per 500
features (full-resolution national boundary geometry — no simplified/
generalized DeSO layer exists on this geoserver, checked the full WFS
`GetCapabilities` layer list). `fetch-boundaries` pages (`--page-size`,
default 1000, run at 500 for the real fetch below) and saves each page to
disk as it's fetched, same resumable-batch discipline as `assessments/
kvalitetssystem.py` — a page already on disk is skipped unless `--force`.

### Income / education / employment (SCB PxWebApi, no auth)

```bash
python -m src.cli sweden data neighbourhood fetch-income        # ~80s for all DeSO2018 codes
python -m src.cli sweden data neighbourhood preprocess-income
python -m src.cli sweden data neighbourhood fetch-education      # ~60s
python -m src.cli sweden data neighbourhood preprocess-education
python -m src.cli sweden data neighbourhood fetch-employment     # ~75s
python -m src.cli sweden data neighbourhood preprocess-employment
```

All three share one batched-by-region PxWeb fetch helper
(`fetch.py::_fetch_batched_by_region`) — only the fixed dimensions differ:

- **Income** `Tab2InkDesoRegso` (`HE/HE0110/HE0110I`): `nettoinkomst`
  (net income, component `240`), `kön=1+2` (totalt), content `000008A4`
  ("Medelvärde för samtliga, tkr" — mean, thousand SEK).
- **Education** `UtbSUNBefDesoRegso` (`UF/UF0506/UF0506D`): every
  `UtbildningsNiva` level and every `Tid` year via PxWeb's
  `{"filter": "all", "values": ["*"]}` wildcard (confirmed live to return
  every real value without enumerating either by hand), content
  `000005MO` ("Befolkning" — population count per level).
- **Employment** `ArRegDesoStatusN` (`AM/AM0210/AM0210G`): `kön=1+2`,
  `ålder=16-64`, content `0000089X`/`0000089Y` ("antal sysselsatta" /
  "antal totalt").

All batched over the real DeSO2018 code list recovered from the boundary
fetch (`--batch-size`, default 500) — much faster than the boundary WFS,
the whole country in ~60-80 seconds each, 12 batches.

### Assemble

```bash
python -m src.cli sweden data neighbourhood assemble
```

## Real schema, confirmed live 2026-09-17

**DeSO 2018 WFS feature**: `desokod` (e.g. `1273C1050`), `regsokod`,
`lanskod`, `kommunkod`, plus `version`/`referensdatum`/`objektidentitet`
(kept on disk, not used downstream). `EPSG:3006` (SWEREF99 TM), same CRS
convention as every other Sweden geospatial layer here.

**Two real bugs caught by live-testing against actual data, not by a code
read**:
1. The DeSO code's area-density letter is **not always `C`** — SCB uses
   `A`/`B`/`C` (a real 30-area WFS sample returned all three, e.g.
   `0840A0010`, `1273B2010`, `1273C1050`). An early version of
   `preprocess.py`'s DeSO2018-code regex hardcoded `C`, which — caught
   before the full-scale run, not after — would have silently dropped
   most of the country's real rows in every one of the three tables.
   Fixed to `^\d{4}[ABC]\d{4}$`; a regression test locks this in.
2. `pandas.pivot_table`'s default `dropna=True` silently **drops an
   entire `(desokod, year)` row** when every pivoted column for it is
   `NaN` — caught by the real 2024 employment case (both "sysselsatta"
   and "totalt" suppressed that year), which disappeared from the output
   entirely instead of surviving as a real `NaN` row. Fixed with
   `dropna=False` on both `preprocess_education`'s and
   `preprocess_employment`'s pivots; a regression test locks this in too.

## `fetch-boundaries` / `preprocess-boundaries` — real run 2026-09-17

12 pages (`--page-size 500`) → **5,984 DeSO areas**, **290 distinct
kommun** (Sweden has exactly 290 municipalities — an exact match, a strong
correctness signal on its own) → `data/sweden/neighbourhood/processed/
deso_2018_boundaries.parquet` (41MB; raw pages 104MB).

## `fetch-income` / `preprocess-income` — real run 2026-09-17

12 batches, all 5,984 DeSO2018 codes → **83,776 rows** (5,984 x 14 nominal
years, 2011-2024). Real per-year coverage: 99.9% (2011-2013) / 100.0%
(2014-2023) / **0.0%** (2024, fully suppressed, kept as real `NaN`).
77,778 of 83,776 rows (92.8%) carry a real value.
→ `data/sweden/neighbourhood/processed/income_net_income_structure.parquet`
(196KB).

## `fetch-education` / `preprocess-education` — real run 2026-09-17

12 batches, all 5,984 DeSO2018 codes → **53,856 rows** exactly (5,984 x 9
years, 2015-2023, no suppressed year at all — 100.0% real coverage every
year). Mean population share with `eftergymnasial` (post-secondary)
education across all DeSO-years: **42.8%** (range 11.4%-93.2% across
areas — real, plausible neighbourhood variation).
→ `data/sweden/neighbourhood/processed/education_by_level.parquet`
(904KB).

## `fetch-employment` / `preprocess-employment` — real run 2026-09-17

12 batches, all 5,984 DeSO2018 codes → **29,920 rows** exactly (5,984 x 5
nominal years, 2020-2024). Real per-year coverage: 100.0% (2020-2023) /
**0.0%** (2024, fully suppressed, kept as real `NaN` after the
`pivot_table` fix above — an earlier version silently dropped these rows
instead).
→ `data/sweden/neighbourhood/processed/employment_status.parquet` (348KB).

## `assemble` — real run 2026-09-17

Point-in-polygon match against 9,520 geocoded schools: **9,519 matched
(99.99%)**, 1 unmatched. The one unmatched school (`skolenhetskod
48508176`) has a geocoded coordinate at roughly `(2.6°E, 59.7°N)` in the
North Sea, nowhere near Sweden — a real upstream geocoding error in
`schools.geojson`, not a bug in this module; a point-in-polygon match
correctly reports "no match" for it rather than snapping to an arbitrary
nearest DeSO the way a distance-threshold match might. Not fixed here
(out of scope for this source), flagged for whoever next touches
`schools/preprocess.py`'s geocoding.

**133,267 panel rows** (9,519 matched schools x income's own 14-year span,
2011-2024 + 1 NA row for the unmatched school — the widest of the three
tables' spans, since the merge is an outer join) →
`data/sweden/neighbourhood/assembled/school_neighbourhood.parquet`
(1.7MB). A real, fully-populated example row (skolenhetskod `10017830`,
year 2020): mean net income 286.3 tkr, post-secondary share 22.8%,
employment rate 71.8% — all three subsources present and sensible
together. Per-column real coverage across the whole panel: income 92.9%,
education 64.3% (its narrower 2015-2023 window inside income's wider
span), employment 28.6% (its narrowest 2020-2023 window).

## Joined into `panel` — real run 2026-09-17

`panel/assemble.py::attach_neighbourhood` merges this module's output onto
every outcome row by a plain `(skolenhetskod, year)` merge — no
interval-overlap logic needed, unlike `attach_traffic`, since a DeSO
match doesn't change year to year within one vintage.

**Real, non-obvious consequence of the panel's own SIRIS-only span
(1998-2019, see the `panel` row in `docs/data/sweden/README.md`) meeting
this module's per-table coverage floors**: of 437,948 panel rows, 152,768
(34.9%, 1,672 schools) get a real neighbourhood match — but **the
`neighbourhood_employment_rate` column is 0% real everywhere in the
joined panel**. Employment's own real coverage floor is 2020 (see above);
the panel's outcome years never reach past 2019 at all, so the two
windows have **zero overlap**, confirmed directly by checking the column,
not assumed from the coverage tables alone. Income (real floor 2011) and
education (real floor 2015) both genuinely overlap SIRIS's later years
and show real values (152,768 and 91,350 real rows respectively) — this
is a real gap specific to employment's later start, not a bug in the
join itself.

## Not yet done

- **`Tab1`/`Tab3`/`Tab4InkDesoRegso`** (income-class shares, economic
  standard) — same PxWeb folder as the mean-income table already built,
  confirmed live, not fetched.
- **The DeSO2025 redraw** — not stitched; a school's DeSO membership and
  all three time series stop at the 2018 vintage's own real coverage
  (2023 for all three, once income's 2024 row's real suppression is
  accounted for).
- **Education's 2024-2025 successor table** — genuinely can't be added
  under DeSO2018 codes at all (no such codes exist in it), not just
  deferred; would need the DeSO2025 boundary vintage to use.
