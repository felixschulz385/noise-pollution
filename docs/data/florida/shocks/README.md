# Florida — `shocks` source: requirements for implementation

**Status: all three stages (`fetch`, `preprocess`, `assemble`) implemented
and run 2026-09-14, joined into `panel`.** This page is a self-contained
implementation brief in the same style as
[`road_projects/README.md`](../road_projects/README.md) — read it plus the
files linked in [Read first](#read-first) for full context.

**Real run** (2026-09-14): `fetch` pulled all **2,794** FL disaster-
declaration rows in one request, matching the live count checked ahead of
time. `preprocess` produced **2,794** tidy rows (1:1, no collapsing) — 1,432
hurricane rows, 24 statewide, `assessment_year` spanning 1954–2026.
`assemble` rolled these up to **1,774** `(county_name, assessment_year)`
rows, all **67** real counties matched (`unmapped_county_rows`: 65, all from
the 10 tribal-reservation/trust-land names — real, expected, not a bug).
Joined into `panel/assemble.py`'s `event_study_panel.parquet` via an exact
`(district_name, year)` match (`attach_shocks`) — **295,517 of 660,681 panel
rows (44.7%)** matched at least one declaration that year, 235,152 (35.6%) a
hurricane specifically, 217,658 (32.9%) a major (`DR`) disaster — a
substantially higher match rate than `traffic`/`road_projects` since
disaster declarations are common, statewide-relevant events, not tied to a
specific school's roadway proximity.

## Why this source exists

Covariate Cluster G (`docs/data/florida/covariates.md`): county-level shocks
(hurricanes, severe weather, state-of-emergency declarations) disrupt
schooling — testing delays, displacement, attendance loss — independent of
any noise wall. Without controlling for these, a wall built shortly before
or after a major hurricane year in that county could have its effect
confounded with storm disruption. Most of Cluster G's rows are `baseline`
role per `covariates.md`'s own tags, and — per this project's ranking this
session — `shocks` is the cheapest remaining covariate module to build: its
primary variable (hurricane/disaster declarations) has a clean, no-auth,
single-request REST API, unlike `staff`/`neighbourhood`'s per-year Excel
exports.

## Read first

1. `docs/data/florida/covariates.md`, Cluster G section — the seven planned
   variables and their `Role` tags.
2. `src/regions/florida/sources/schools/shared.py` /
   `processed_cross_section_path` — `school_cross_section.parquet`'s
   `district`/`district_name` fields are this source's join key (see
   [The county join](#the-county-join-district-not-fips) below).
3. `docs/data/florida/road_projects/README.md` — the pattern to mirror for
   a small, live-verified REST source with a school-side join.

## The data source (researched and verified live 2026-09-14, not guessed)

**Primary: OpenFEMA `DisasterDeclarationsSummaries` v2**
(`https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries`) — no
auth, no rate-limit trouble hit. **The entire Florida disaster-declaration
history fits in ONE request**: confirmed live,
`$filter=state eq 'FL'&$top=5000` returns all **2,794** rows in a single
response (no pagination loop needed — `$top=2000` genuinely returns 2000
rows, not a silently-capped subset, and `$top=5000` returns every row; no
`$skip` looping required, unlike every other Florida source's archive).
Confirmed field schema from live sample rows:

| field | type | meaning |
|---|---|---|
| `disasterNumber` | int | FEMA disaster number |
| `femaDeclarationString` | string | e.g. `"DR-4337-FL"` |
| `declarationType` | string | `DR` (major disaster, 1,629 FL rows) / `EM` (emergency, 1,004) / `FM` (fire management, 161) |
| `declarationDate` | date (ISO) | the actual declaration date — use this for year derivation, not `fyDeclared` (see below) |
| `fyDeclared` | int | FEMA's own fiscal year — **not used**, see below |
| `incidentType` | string | confirmed live distribution for FL: `Hurricane` 1,432, `Severe Storm` 376, `Fire` 280, `Tropical Storm` 266, `Biological` 150 (COVID-19 `EM` declarations land here), `Freezing` 147, `Flood` 74, `Tornado` 38, `Coastal Storm` 25, `Human Cause` 4, `Other` 2 |
| `declarationTitle` | string | free text, e.g. `"HURRICANE IRMA"` |
| `incidentBeginDate` / `incidentEndDate` | date | when present (not every row has both) |
| `designatedArea` | string | county or special-area name — **the join key**, see below |
| `fipsStateCode` / `fipsCountyCode` | string | present but **not needed** for the join (see below); kept for provenance/cross-check only |
| `paProgramDeclared` / `ihProgramDeclared` / `iaProgramDeclared` / `hmProgramDeclared` | bool | which FEMA assistance programs were activated — not scoped for v1, kept raw |

**`fyDeclared` vs. `declarationDate`**: FEMA's own fiscal year (Oct–Sep) does
not obviously align with either the calendar year or the FLDOE spring
assessment year — use `declarationDate`'s actual calendar date and derive
the assessment year from it directly (see below), not `fyDeclared`.

## The county join: `district`, not FIPS

`designatedArea` is a **county name string** (`"Broward (County)"`), not
just a FIPS code — this matters because FLDOE's own school spine
(`school_cross_section.parquet`'s `district`/`district_name`) is *also*
county-name-keyed: **Florida has exactly one school district per county**
(confirmed empirically: districts `01`–`67` in `school_cross_section.parquet`
have real county names — `01 ALACHUA`, `02 BAKER`, ... — one-to-one with
Florida's 67 counties; districts `68`+ are special entities — lab schools,
DJJ, charter consortiums, virtual schools — that don't map to one county).
**So the join is a normalized county-NAME match, not a FIPS crosswalk
table** — simpler and less error-prone than hand-typing a 67-row
name→FIPS table.

Checked the live `designatedArea` value set (79 distinct strings across all
2,794 FL rows) before committing to this design:

- **67 real counties**, suffixed `" (County)"` — strip the suffix, uppercase,
  and it string-matches `district_name` directly for 66 of them.
- **One naming alias needed**: `"Dade (County)"` (pre-1997 name) and
  `"Miami-Dade (County)"` (current name) both appear — older declarations
  use the retired name. Map `DADE` → `MIAMI-DADE` explicitly.
- **10 non-county areas**: `"Statewide"` (real signal — a statewide
  declaration should count for every county, not be dropped) and 10 tribal
  reservation/trust-land names (`Big Cypress Indian Reservation`,
  `Seminole Tribe of Florida`, `Miccosukee Tribe of Indians of Florida`,
  etc. — FL tribal members generally attend county public schools, which
  aren't separately identifiable in `school_cross_section.parquet`, so these
  rows get `county_name = NA` and are excluded from the per-school join,
  kept in the processed table for completeness rather than dropped from the
  raw data).

## Assessment-year derivation (a documented assumption, not a guess)

A hurricane's *calendar* date needs mapping to the FLDOE *spring assessment
year* it's most likely to have disrupted. Mirror the month-aware convention
`schools/preprocess.py` already uses for `in_operation`
(`open_spring = year + (month >= 7)`): a declaration in the second half of
the calendar year (July–December, i.e. during hurricane season and the fall
semester) is attributed to the **following** spring's assessment year; a
declaration in the first half (January–June) is attributed to that **same**
spring. This is a real modeling assumption — flag it as such in code and
docs, not a silent default — and matches Florida's actual hurricane-season
climatology (June–November) closely enough that nearly every hurricane
declaration falls on the "next spring" side of the rule.

## Scope for a first pass

Ship the **hurricane/disaster-declaration** variable (`covariates.md`'s
first and most concretely-specified Cluster G row) end-to-end: `fetch` (one
request) → `preprocess` (tidy + county-name normalize + assessment-year
derive) → `assemble` (county × assessment-year rollup, joined onto every
school in that county via `district_name`, unioned with any `Statewide`
declaration that year). Treat the other Cluster G rows as **out of scope for
v1**, same posture `road_projects` took toward its lower-priority Work
Program phases:

- **Class-Size-Reduction compliance (2003–2010)** and **School Grades
  archives** — both FLDOE per-year Excel exports, no REST API found; expect
  the same `www.fldoe.org` scripted-client friction `assessments/fetch.py`
  already works around (manual-download orchestrator pattern). Not
  researched yet — flag as a follow-up brief of its own before starting,
  don't assume the `assessments` pattern transfers without checking.
- **Storm track / wind swath (NOAA HURDAT2/IBTrACS)** — `selection` role,
  finer-than-county exposure; a genuine stretch goal (needs wind-swath
  geometry, not just a county flag) — leave `NA`/unbuilt, same posture as
  `schools/assemble.py`'s algorithm 6.
- **Test regime, COVID 2020/2021, test participation rate** — **no new
  source needed at all**: `regime`, `n_students`, and participation columns
  already live in `assessments.parquet`. These are pure analysis-layer
  decisions (drop 2020, flag/trim 2021, weight by `z_mss_w`) already noted
  in `covariates.md`'s "Bad-control / estimation notes" — don't build a
  `shocks` fetch step for data that's already fetched.

## Suggested layout (mirror `road_projects`)

```
src/regions/florida/sources/shocks/
    __init__.py       # module docstring
    shared.py          # DOMAIN="shocks", paths, OpenFEMA endpoint constant,
                        #   the county-name normalization helper (incl. the
                        #   DADE -> MIAMI-DADE alias)
    fetch.py           # fetch_disaster_declarations() -- one GET, no pagination
    preprocess.py       # tidy + county_name normalize + assessment_year derive
    assemble.py         # county x assessment_year rollup, joined onto schools
                        #   via district_name, Statewide unioned into every county
tests/regions/florida/test_shocks_preprocess.py
tests/regions/florida/test_shocks_assemble.py
docs/data/florida/shocks/README.md   # this file
```

`data/florida/shocks/{raw,processed,assembled}/` via the existing
`domain_dirs("shocks")` helper — no new plumbing needed.

**CLI**: `florida data shocks {fetch,preprocess,assemble}`, registered the
same way `_register_road_projects` is in `cli.py`/`handlers.py`.

**Panel join**: `panel/assemble.py`'s `attach_shocks` — an exact
`(district_name, year)` join directly against `assessments`' own
`district_name` column (no per-school intermediate file, no interval-overlap
or nearest-year machinery, since `assessment_year` derivation already
resolves each declaration to one exact spring and `district_name` already
upper-cases to the same convention `shocks` normalizes to).

## Definition of done

- ~~`fetch.py` pulls the full FL disaster-declaration history in one
  request.~~ **done** (2026-09-14) — `src/regions/florida/sources/shocks/
  {shared,fetch}.py`, real run: 2,794 rows in one request. CLI:
  `florida data shocks fetch`.
- ~~`preprocess.py` normalizes `designatedArea` → `county_name` (with the
  `DADE`→`MIAMI-DADE` alias), derives `assessment_year` via the month-aware
  rule above, and keeps `Statewide`/tribal rows (not dropped).~~ **done**
  (2026-09-14) — real run: 2,794 rows, 1,432 hurricane, 24 statewide. CLI:
  `florida data shocks preprocess`.
- ~~`assemble.py` joins the county × assessment-year rollup, `Statewide`
  declarations unioned into every county's year.~~ **done** (2026-09-14) —
  1,774 county-year rows, all 67 real counties matched. CLI:
  `florida data shocks assemble`.
- ~~Wire this source into `panel/assemble.py`'s `event_study_panel.parquet`.~~
  **done** (2026-09-14) — `attach_shocks`, real run: 295,517/660,681 panel
  rows (44.7%) matched a declaration. 16 new tests across
  `test_shocks_preprocess.py`/`test_shocks_assemble.py`/
  `test_panel_assemble.py`, 230/230 Florida tests pass.
- ~~`covariates.md`'s Cluster G table's hurricane-declaration row updated
  from "planned" to "implemented" with real numbers, same convention as
  `traffic`/`road_projects`.~~ **done** (2026-09-14).
