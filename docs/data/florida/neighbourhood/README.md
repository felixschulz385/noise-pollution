# Florida — `neighbourhood` source: implementation brief (Cluster F)

**Status: `fetch`/`preprocess`/`assemble` all implemented and fully run
2026-09-17, including the ACS half — the user obtained a Census API key the
same session and provided it, so every sub-source is now live.** This page
is a self-contained brief in the same style as
[`staff/README.md`](../staff/README.md).

**Real run** (2026-09-17): `tract_boundaries` (both vintages) + `zcta_boundaries`
+ `zhvi` fetched live, no auth, no errors — **4,215** FL tracts
(2010-vintage cartographic file) / **5,122** (2020-vintage, real growth from
redistricting), **33,791** national ZCTAs, **924** FL ZIPs with ZHVI history
(**24,013** ZIP-year rows after collapsing to one value per calendar year).
`acs` (once `CENSUS_API_KEY` was set): **16/16 years fetched (2009–2024),
zero errors** — **71,404** tract-year rows. `assemble`'s spatial join:
**5,984/5,984 placed schools (100%)** matched to both a tract (both
vintages) and a ZIP — the `within`-then-nearest-fallback design (see below)
leaves nothing unmatched — **93,389** school-year ACS rows, **158,057**
school-year ZHVI rows. Joined into `panel/assemble.py`'s
`event_study_panel.parquet`: **449,178 of 660,681 rows (68.0%)** matched
ACS demographics (0% for 2003–2008, before ACS5 existed; 60% in 2009, its
partial-coverage first vintage; 99–100% for 2010–2024; 0% for 2025–2026,
genuinely not yet published) and **651,266 (98.6%)** matched a ZHVI
home-value figure, ranging realistically $25.9k–$3.1M (median $216.6k),
with match rate 91% in 2003 rising to 100% by 2016 (ZHVI's own ZIP-coverage
growing over time, not a bug). ACS values sanity-checked: median household
income $6,989–$250,001 (median $51,400 — the $250,001 ceiling is ACS's own
top-coded value, not a data error), poverty rate 0–100% (median 14%),
owner-occupied 0–100% (median 68%), bachelor's+ 0–100% (median 23%, rising
from a 2011 mean of 26% to a 2022 mean of 32% — consistent with the real
national education trend and showing no discontinuity across the
`B15002`→`B15003` table switch), moved-last-year 0–92% (median 14%).

**One real bug found and fixed during this run**: geopandas 1.0+ changed
`GeoSeries.notna()` to treat an *empty* geometry (a degenerate `Point()`,
distinct from a real `None`) as non-null. A first pass at the school-points
loader used a plain `.notna()` filter and got **7,204** "placed" schools —
every school in `school_cross_section.parquet` regardless of whether it
actually had a location, not the real **5,984** placed-schools figure every
other Florida source (`traffic`, `road_projects`) has independently
confirmed. Fixed: `placed_school_points` now excludes `~geometry.is_empty &
geometry.notna()` explicitly (geopandas' own suggested replacement), with a
regression test locking this in.

## Why this source exists

Covariate Cluster F (`docs/data/florida/covariates.md`): diagnostics for
sorting/capitalisation around a barrier, **not** baseline controls (a wall
that raises nearby home values makes these mediators) — but a pre-trend in
home values or demographics between to-be-treated and not-yet-treated roads
is a direct, useful test of barrier-siting endogeneity (`selection` role).

## Read first

1. `docs/data/florida/covariates.md`, Cluster F section.
2. `src/regions/florida/sources/neighbourhood/__init__.py` — the module
   docstring covers the two live findings that reshaped this module's
   design (Census's key requirement, the ACS tract-vintage switch).
3. `src/regions/florida/sources/traffic/assemble.py` — the closest
   precedent for "a static school-side spatial match, then time-varying
   data joined on top of it" (there: nearest-roadway; here:
   point-in-polygon).

## The Census Data API now requires a key — a real, recent policy change

`covariates.md` (written before 2026-05) assumed the Census Data API needed
no key for ordinary use, the long-standing status quo. **That changed
2026-05-11**: every unauthenticated request now returns an HTML "Missing
Key" page instead of JSON — confirmed live, repeatedly, against multiple
years/endpoints during this session. Getting a key is free and
self-service (`api.census.gov/data/key_signup.html`, ~5 minutes, any email
domain works) but requires the user's own action — this assistant does not
submit a user's email to a third-party signup form without being asked to.
**Decision (2026-09-17, user confirmed)**: the user requested a key
themselves and provided it the same session; `fetch.py`'s `fetch_acs` reads
it from the `CENSUS_API_KEY` environment variable and raises a clear,
actionable `RuntimeError` (not a cryptic HTML-parse failure) if it's unset.
Once set, `florida data neighbourhood fetch --subsource acs` needed no code
changes — it fetched all 16 years (2009-2024) cleanly on the first try. One
fix made before running it for real: `fetch_acs`'s per-year error message
otherwise embeds the raw key in the failing request URL — redacted before
it can reach a returned dict, printed output, or a saved report.

**TIGER geographic files (tract/ZCTA boundaries) need NO key** — only the
tabular Data API does; confirmed live, both boundary zips downloaded
without issue.

## ACS variable registry (every code checked live, none guessed)

| Variable | Table(s) | Notes |
|---|---|---|
| Median household income | `B19013_001E` | stable 2009–2022+, checked |
| Poverty rate | `B17001_002E` / `B17001_001E` | stable, checked |
| % owner-occupied | `B25003_002E` / `B25003_001E` | stable, checked |
| % moved in the past year | `1 - B07003_004E / B07003_001E` | table is `B07003` ("...by Sex..."), **not** `B07001` ("...by Age...") — `B07001`'s own variables are age-band splits, not moving-status categories; checked against the live `variables.json`, not assumed from the code number alone |
| % bachelor's degree or higher | `B15003_022..025E` / `B15003_001E` (2012+); `B15002_015..018E + B15002_032..035E` / `(B15002_002E + B15002_019E)` (2009–2011) | **`B15003` did not exist before the 2012 ACS5 vintage** — confirmed live: 2011's `variables.json` has no `B15003_*` keys at all, 2012's does. Pre-2012 uses the older sex-split `B15002` table instead (same universe, sum both sexes' four highest categories). `shared.education_variables(year)` picks the right table. |

## Two tract-boundary vintages, resolved per ACS year

ACS 5-year estimates switched from 2010-vintage to 2020-vintage census
tracts **at the "2020" 5-year release** (Census's own "2020 Geography
Changes" documentation: the 2011–2015 release used legal boundaries as of
Jan 1 2015 — 2010 vintage — the 2016–2020 release switched to 2020-vintage
geographies). So `shared.tract_vintage_for_year(year)` returns `"2010"` for
`year < 2020`, `"2020"` otherwise, and `assemble.py` fetches/keeps BOTH
cartographic boundary layers, matching each school against both up front
(`build_school_tract_match` — one row per `(msid, tract_vintage)`), then
`build_school_acs_panel` picks the vintage-appropriate `tract_geoid` per
ACS year at join time.

**Cartographic (`cb_*_500k`) boundaries, not full-resolution TIGER** —
generalized to 1:500,000, ~2.4MB for one state vs. ~14MB for the same
state's full-precision TIGER cut (and ZCTAs are ~67MB generalized vs 528MB
full-resolution, confirmed live). A school's point is rarely close enough
to a tract/ZIP line for the generalization to matter, and this is a
diagnostic covariate, not a treatment-defining match — a documented
approximation, not oversold. ZCTAs (ZIP Code Tabulation Areas, the Census
Bureau's polygon approximation of USPS ZIP codes) are published as **one
national file only** — confirmed live, a per-state TIGER path 404s — so
only one current vintage is fetched; Zillow's own ZHVI series isn't itself
vintage-tagged, so no vintage-matching problem exists on that side.

## The spatial join: point-in-polygon, with a nearest-fallback

The only Florida source doing polygon containment rather than
linear-referencing. Primary match is `geopandas.sjoin(..., predicate=
"within")`; any school that still falls outside every polygon (a
generalized 1:500,000 shoreline can leave a coastal/barrier-island school's
exact point just outside a simplified coastline) falls back to
`sjoin_nearest` rather than being left unmatched — real run needed this for
zero schools this time (100% matched on `within` alone), but the fallback
is there for robustness, not theoretical.

## Zillow ZHVI: which cut, and the annual-collapse choice

`Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv` — Zillow's flagship
ZHVI cut (single-family + condo, mid-tier 33rd–67th percentile, smoothed &
seasonally adjusted), public, no key, confirmed live (~123MB national,
filtered to Florida's 924 ZIPs at fetch time and the national file
discarded — same "don't keep more than needed" posture `traffic/fetch.py`
takes with FGDL's full releases). Monthly columns are collapsed to one row
per `(zip_code, year)` by keeping the **last available month within that
calendar year** — a documented choice, not an average: ZHVI is already a
smoothed index, so re-averaging an already-smoothed series would double-
smooth it; a single within-year snapshot avoids that.

## Scope for a first pass: what's built vs. deferred

Built: ACS median household income / poverty rate / % owner-occupied / %
bachelor's+ / % moved in the past year (tract, pending the API key), ZHVI
home values (ZIP, live). Deferred:

- **NaNDA** (the packaged tract SES/greenspace/walkability bundle,
  `covariates.md`'s third Cluster F row) — ships through ICPSR
  openICPSR, which needs an account and per-dataset click-through, not a
  plain URL fetch (unlike every other source built so far in this repo).
  Flagged as a follow-up requiring its own access-method research, not
  attempted here.
- **Decennial 2000** (`covariates.md` mentions Decennial 2000 alongside
  ACS 5-year as a pre-ACS baseline) — the Census Decennial API uses a
  different dataset path/variable-code scheme than ACS5 and predates the
  2010-vintage tract boundaries this module's `TRACT_VINTAGE_2010` targets;
  scoped out of v1, ACS5's 2009 floor (2005-2009 5-year estimates) is
  the earliest year built.

## Suggested layout (mirror `staff`)

```
src/regions/florida/sources/neighbourhood/
    __init__.py       # module docstring
    shared.py          # DOMAIN="neighbourhood", paths, ACS variable registry
                        #   (year-aware education table), boundary/ZHVI URLs,
                        #   CENSUS_API_KEY env var + tract-vintage rule
    fetch.py           # fetch_tract_boundaries/fetch_zcta_boundaries (TIGER
                        #   cartographic zips) + fetch_zhvi (Zillow CSV,
                        #   filtered to FL) + fetch_acs (Census Data API,
                        #   requires CENSUS_API_KEY)
    preprocess.py       # tidy_tract_boundaries/tidy_zcta_boundaries
                        #   (GeoParquet, reprojected to EPSG:3087),
                        #   preprocess_acs (derive rates, year-aware table),
                        #   preprocess_zhvi (wide->long, annual collapse)
    assemble.py         # placed_school_points (excludes empty geometry, not
                        #   just None) + the point-in-polygon spatial match
                        #   (within, nearest-fallback) + the two panel joins
tests/regions/florida/test_neighbourhood_preprocess.py
tests/regions/florida/test_neighbourhood_assemble.py
docs/data/florida/neighbourhood/README.md   # this file
```

`data/florida/neighbourhood/{raw,processed,assembled}/` via the existing
`domain_dirs("neighbourhood")` helper.

**CLI**: `florida data neighbourhood {fetch,preprocess,assemble}`. `fetch`
takes `--subsource {tract-boundaries,zcta-boundaries,zhvi,acs}` (default:
all four) and `--year` (repeatable, `acs` only).

**Panel join**: `panel/assemble.py`'s `attach_neighbourhood` — two exact
`(msid, year)` left joins, no tolerance or broadcast needed (the spatial
resolution already happened in `neighbourhood/assemble.py`). An unmatched
row is left `NA` — there's no sensible "zero" for median household income
or a home-value index.

## Definition of done

- ~~`fetch.py` downloads both tract-boundary vintages, the ZCTA layer, and
  Zillow ZHVI (filtered to FL); `fetch_acs` reads `CENSUS_API_KEY`.~~
  **done** (2026-09-17) — all four sub-sources fetched live and clean,
  including `acs` (16/16 years, 2009-2024, zero errors, once the user
  provided a key).
- ~~`preprocess.py` tidies boundaries to GeoParquet and derives ACS
  rates/collapses ZHVI to one row per ZIP x year.~~ **done** (2026-09-17) —
  real run: 4,215/5,122 tracts, 33,791 ZCTAs, 71,404 ACS tract-years,
  24,013 ZHVI ZIP-years.
- ~~`assemble.py` builds the spatial school->tract/ZIP match and the two
  time-varying panels.~~ **done** (2026-09-17) — 5,984/5,984 schools
  matched to both, 93,389 ACS school-years, 158,057 ZHVI school-years;
  found and fixed a real geopandas-version empty-geometry bug along the
  way (see above).
- ~~Wire this source into `panel/assemble.py`'s `event_study_panel.parquet`.~~
  **done** (2026-09-17) — `attach_neighbourhood`, real run: 449,178/660,681
  rows (68.0%) matched ACS demographics, 651,266 (98.6%) matched ZHVI. 25
  new tests across `test_neighbourhood_preprocess.py`/
  `test_neighbourhood_assemble.py`/`test_panel_assemble.py`, 272/272
  Florida tests pass.
- ~~`covariates.md`'s Cluster F table updated with real numbers.~~ **done**
  (2026-09-17).
- **Not done, deferred with reasons above**: NaNDA (needs an ICPSR
  account), Decennial 2000.
