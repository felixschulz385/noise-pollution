"""Florida `neighbourhood` source (covariate Cluster F): tract-level
Census ACS demographics + Zillow home values, diagnostics for sorting /
capitalisation around a barrier, not baseline controls.

v1 scope (see `docs/data/florida/neighbourhood/README.md`): **ACS 5-year**
tract demographics (median household income, poverty rate, % owner-occupied,
% bachelor's+, % moved in the past year) and **Zillow ZHVI** ZIP-level home
values. **NaNDA** (the packaged SES/greenspace/walkability bundle) is
documented as an out-of-scope follow-up — it ships through ICPSR
openICPSR, which needs an account and per-dataset click-through, not a
plain URL fetch.

**The Census Data API now requires a key for every request** (a real policy
change, 2026-05 — confirmed live: every unauthenticated request returns an
HTML "Missing Key" page, not JSON). `fetch.py`'s ACS puller reads
`CENSUS_API_KEY` from the environment and raises a clear, actionable error
if it's unset — this module cannot fetch real ACS data until the user
supplies one (a free, self-service key at
`api.census.gov/data/key_signup.html`). The Zillow ZHVI and TIGER
cartographic-boundary sub-sources need no key and are fully live.

**Two Census tract boundary vintages, not one.** ACS 5-year estimates
switched from 2010-vintage to 2020-vintage census tracts at the "2020"
5-year release (confirmed against Census's own "2020 Geography Changes"
page) — an ACS5 vintage year <= 2019 needs the 2010-vintage tract polygons
for a correct spatial join, >= 2020 needs the 2020-vintage ones. Both are
fetched (`tract_boundaries_2010`/`tract_boundaries_2020`) and the spatial
join (`assemble.py`) picks the right one per ACS year.

**The %-bachelor's-or-higher variable's own table code changed too**:
`B15003` (population 25+, no sex split) didn't exist before the 2012 ACS5
vintage — confirmed live against both years' `variables.json` — years
2009-2011 use the older `B15002` (sex-split) table instead. `shared.py`'s
`education_variables(year)` picks the right table.

Stages: `fetch` (direct Census Data API calls per tract-year, requires
`CENSUS_API_KEY`; Zillow ZHVI, one CSV; the two tract-boundary cartographic
zips + one national ZCTA cartographic zip) -> `preprocess` (tidy each
sub-source to its native grain) -> `assemble` (static school->tract /
school->ZIP spatial join via `school_cross_section.parquet`'s points, then
join the time-varying ACS/ZHVI tables onto it, REQUIRES `schools
preprocess`).
"""
