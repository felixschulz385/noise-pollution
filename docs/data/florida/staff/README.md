# Florida — `staff` source: implementation brief (Cluster B)

**Status: all three stages (`fetch`, `preprocess`, `assemble`) implemented
and run 2026-09-17, joined into `panel`.** This page is a self-contained
brief in the same style as
[`shocks/README.md`](../shocks/README.md)/[`road_projects/README.md`](../road_projects/README.md)
— read it plus the files linked in [Read first](#read-first) for full
context.

**Real run** (2026-09-17): `district_finance` fetched cleanly for all **26**
years (1995–2020) in one pass — no auth, no errors, the Urban Institute CCD
F-33 API. `teacher_salary`/`out_of_field` (the two FLDOE workbooks) hit a
genuine, live Internet Archive outage (`Internet Archive: Temporarily
Offline`, a real-if-infrequent full-service outage, confirmed via repeated
`503`s across the whole session, not a bug in this module) partway through
verification — **2025 was downloaded and parsed successfully before the
outage** (confirming the whole design end-to-end on real data), the
remaining 11–12 registered years are structurally verified (real links found
on FLDOE's own archive page, see below) but not yet individually
re-downloaded. Re-running `florida data staff fetch` once the Internet
Archive recovers will backfill them with no code changes. `preprocess` on
what's cached today: **78** districts (`teacher_salary`, 2025 only), **4,093**
real school-level out-of-field rows (2025 only), **1,856** district-year
`district_finance` rows (26 years). `assemble`: **84** districts got a
`leaid` crosswalk entry (min coverage 88.5%, median 100%, see below),
**1,904** district-staff-panel rows, **4,093** school-staff-panel rows.
Joined into `panel/assemble.py`'s `event_study_panel.parquet` — **35,453**
of 660,681 panel rows (5.4%, effectively all of assessment-year-2025) got a
salary/experience match, **398,189** (60.3%, spanning 1995–2020) got a
per-pupil-expenditure match, **35,308** (5.3%, 2025 only) got an
out-of-field match. Sanity-checked the real numbers before writing them down
here: average teacher salary $45.6k–$73.1k (median $56.7k), per-pupil
expenditure $5.9k–$14.4k (median $8.8k), out-of-field share 0–100% (median
9.2%), average experience 4.8–15.4 years (median 12.1) — all in a plausible
range, no negative/infinite values.

## Why this source exists

Covariate Cluster B (`docs/data/florida/covariates.md`): teacher quality and
district resourcing shift over the panel and could co-move with barrier
timing (e.g. noise → teacher turnover/attrition, or a district's fiscal
response to growth). Most Cluster B rows are `selection`/`keep-out` role —
useful for a robustness/mechanism check, not the baseline spec — which is
why this module was built after the `baseline`-role Clusters C/D/G
(`traffic`/`road_projects`/`shocks`).

## Read first

1. `docs/data/florida/covariates.md`, Cluster B section — the four planned
   variables and their `Role` tags.
2. `src/regions/florida/sources/schools/preprocess.py`'s `compose_ncessch` —
   `msid = district.zfill(2) + school.zfill(4)`; the two FLDOE workbooks use
   this exact numbering already (see below), so no crosswalk is needed for
   them.
3. `src/regions/florida/sources/_http.py`'s `wayback_download` — the new,
   reusable "download via the Internet Archive when the origin blocks
   scripted clients" helper this module introduced. `assessments/fetch.py`
   predates it and still uses a pure manual-download workflow; retrofitting
   it to try Wayback first is a plausible, low-risk follow-up (not attempted
   here — out of scope for this task) since `assessments`' FLDOE workbooks
   are exactly the kind of file Wayback has been shown to mirror.

## The data sources (researched and verified live 2026-09-17, not guessed)

`www.fldoe.org` returns HTTP 403 (Akamai bot protection) for **every** file
path style tried — `/core/fileparse.php/...` and the newer `/file/...` CMS
path alike — confirmed directly with both `curl` and the `WebFetch` tool,
matching `assessments/fetch.py`'s long-standing finding for its own
workbooks. The current `staff.stml` page itself is also 403'd, so its full
back-catalogue was read from the Internet Archive's own crawl of
`.../pk-12-public-school-data-pubs-reports/archive.stml` instead (`curl -sL
"https://web.archive.org/web/2025/<page>"`) — every filename in
`shared.py`'s `TEACHER_SALARY_FILES`/`OUT_OF_FIELD_FILES` registries is a
real link found on that captured page, not a guessed pattern (FLDOE did not
settle on one consistent naming scheme across 13 years).

**The key unlock: `web.archive.org` itself has no such block**, and it has
independently crawled and archived many of these exact files. The Wayback
CDX index (`https://web.archive.org/cdx/search/cdx?url=<url>&output=json`)
resolves a capture timestamp for a given original URL; downloading
`https://web.archive.org/web/<timestamp>id_/<url>` (the `id_` suffix
suppresses the toolbar/link-rewrite wrapper) serves the raw archived bytes.
Confirmed directly: `2425TeacherSalaryData.xlsx` and `IFOFFTeach2425.xlsx`
both downloaded and parsed cleanly this way. `_http.wayback_download` wraps
this as a general, reusable helper (CDX lookup with retry/backoff, then a
plain download) — not staff-specific, since the same trick should work for
any other `fldoe.org` file a future source needs.

### `teacher_salary` — FLDOE "Average Salaries for Teachers", district-level

One workbook per year, 3 sheets, confirmed live on the real 2024-25 file:

| Sheet | Columns (after `DISTRICT #`/`DISTRICT NAME`) |
|---|---|
| `Teachers` | `AVERAGE SALARY`, `NUMBER EMPLOYED`, `EMPLOYMENT LENGTH (in Months)` |
| `Average Yrs Experience` | `NUMBER OF TEACHERS`, `AVERAGE YEARS' EXPERIENCE` |
| `Median Salary` | `NUMBER OF TEACHERS`, `MEDIAN SALARY` |

`DISTRICT #` runs `0`–`67`+ (`0` = Florida state total), matching
`school_cross_section.parquet`'s `district` field exactly (confirmed: `1` =
ALACHUA in both). 13 years registered, 2013-14 through 2025-26 — real,
irregular filenames (`1314teachsalarydata.xls`,
`2014-15-Teacher-Salaries-Survey-3-Web.xls`,
`1516TeachersSalariesSurvey.xls`, then the modern
`<yy><yy+1>TeacherSalaryData.xlsx`), see `shared.py`'s `TEACHER_SALARY_FILES`.

### `out_of_field` — FLDOE in-field/out-of-field teaching, **school-level**

The only Cluster B/C/D/G source whose FLDOE workbook is natively
school-level, not district-level: `District #`, `District Name`, `School #`,
`School Name`, `Total Classes Taught`, `# In-Field`, `# Out-of-Field`, `%
In-Field`, `% Out-of-Field`. Confirmed empirically against
`school_cross_section.parquet`: district `1`/school `22` is "EARLY LEARNING
ACADEMY AT DUVAL" in **both** — the workbook's own numbering already IS
`schools`' `district`/`school` numbering, so `msid` composes directly with
zero crosswalk. Each workbook also carries `"STATE TOTALS"` (`School # = 0`,
`District # = 0`) and `"DISTRICT TOTALS"` (`School # = 0`) rows —
`preprocess_out_of_field` drops both, keeping only real schools
(`school_number > 0`). 12 years registered, 2014-15 through 2025-26
(`IFOFTeach1415.xls`/`IFOFTeach1516.xls` — single `F` — through
`IFOFFTeach2526.xlsx` — double `F` from 2016-17 on), see `shared.py`'s
`OUT_OF_FIELD_FILES`.

### `district_finance` — NCES CCD F-33 per-pupil expenditure, via the Urban API

No `fldoe.org` involved at all — the same no-auth Urban Institute Education
Data API `schools` already uses for CCD/CRDC/EDFacts
(`https://educationdata.urban.org/api/v1/school-districts/ccd/finance/<year>/?fips=12`).
Confirmed live: real, non-trivial FL data for **1995–2020** (`count` 67–78
districts/year); 2021 and 2022 both return `count: 0` (not yet ingested by
Urban as of this check — a real gap in Urban's own pipeline, not a query
bug). `per_pupil_expenditure = exp_current_elsec_total /
enrollment_fall_responsible` — the standard NCES per-pupil definition
(current elementary-secondary expenditure, excludes capital outlay/debt
service, over fall enrollment); a suppressed/negative CCD sentinel (`-1`,
`-2`, ...) or zero enrollment yields `NA`, not a nonsensical ratio.

**No `+1` fall-semester offset here, unlike `schools`' other CCD/CRDC
pulls.** Those surveys are fall-semester snapshots (Urban's own CRDC
codebook: `"Academic year (fall semester)"`), so `schools/preprocess.py`
adds `+1` to reach the spring/assessment year. F-33 finance data instead
uses NCES's *fiscal-year* label, which is already the ending/spring calendar
year — confirmed directly against NCES's own F-33 page
(`nces.ed.gov/ccd/f33agency.asp`, which pairs `"2017-18" (Fiscal Year
2018)"`). So `assessment_year == ccd_finance_year` directly — checking this
rather than assuming the same `+1` rule transferred was the one place this
module could have silently mis-dated 26 years of data.

## The `district -> leaid` crosswalk: a MODAL join, not a strict 1:1 one

`district_finance` keys by NCES `leaid` (`FEDERAL_DIST_NO`, the first 7
digits of `ncessch`), a different id system from FLDOE's own `DISTRICT #`.
Checked empirically before committing to a join design (real
`school_cross_section.parquet`, 2026-09): **83 of 84** FLDOE districts map
to exactly **one** `leaid` among their own schools; district `01` (Alachua)
has **9** distinct `leaid`s because several individual charter schools got
their own NCES `leaid` despite reporting through the county district for
FLDOE's own accounting — a known, general CCD quirk (an NCES `leaid` can be
assigned per charter authorizer, not just per FLDOE district), not a
Florida-specific bug. The **modal** `leaid` per district still captures the
large majority of each district's schools — **min 88.5%, median 100%**,
across all 84 districts — so `build_district_leaid_crosswalk` picks that
modal id and reports `leaid_coverage_frac` per district rather than silently
assuming a clean 1:1 map, the same "verify, don't assume" bar
`shocks/assemble.py` set for its own county-name join.

## Scope for a first pass: what's built vs. deferred

Built: **teacher salary + years-experience + median salary** (district),
**in-field/out-of-field teaching** (school), **per-pupil current
expenditure** (district, via CCD). Deferred, flagged rather than attempted:

- **Teacher turnover / share new to school** (`keep-out` role per
  `covariates.md` — a mechanism variable anyway, excluded from baseline)
  needs individual-level year-over-year staff matching; FLDOE's aggregate
  publications don't support this without a records request for
  student/staff microdata, the same class of gap `road_projects`' pre-2019
  Work-Program coverage hit. Not pursued.
- **% advanced/graduate degree** and a full **teacher-experience
  distribution** (`covariates.md`'s Cluster B row 1 asks for a distribution,
  not just the mean) — not found among the FLDOE workbooks linked from
  `archive.stml` in this pass (only the mean `AVERAGE YEARS' EXPERIENCE` and
  a separate `MEDIAN SALARY`, no degree-attainment breakdown). Flagged as an
  open question for a follow-up brief, mirroring how `shocks/README.md`
  flagged Class-Size-Reduction/School-Grades as deferred rather than
  guessed at.
- **`AR*DistStaff` workbooks** (Admin/FullTime/Instructional/Support
  district staff *counts*, also found on `archive.stml`) were deliberately
  **not** pulled — they overlap with Cluster A's teacher FTE (already
  covered via CCD directory/enrollment inside `schools`), and pulling them
  too would duplicate a covariate cluster rather than add a new one.

## Suggested layout (mirror `shocks`)

```
src/regions/florida/sources/staff/
    __init__.py       # module docstring
    shared.py          # DOMAIN="staff", paths, the two FLDOE per-year URL
                        #   registries, the CCD finance URL builder + year range
    fetch.py           # fetch_teacher_salary / fetch_out_of_field (Wayback,
                        #   falling back to --from-file/--file-url) +
                        #   fetch_district_finance (plain Urban API call)
    preprocess.py       # generic "DISTRICT #" header-row + positional
                        #   value-column reader, shared across all 3 sheets/
                        #   workbooks; per_pupil_expenditure calc
    assemble.py         # district->leaid crosswalk (modal join) + the two
                        #   panels panel/assemble.py joins
tests/regions/florida/test_staff_preprocess.py
tests/regions/florida/test_staff_assemble.py
docs/data/florida/staff/README.md   # this file
```

`data/florida/staff/{raw,processed,assembled}/` via the existing
`domain_dirs("staff")` helper, with `raw/{teacher_salary,out_of_field,
district_finance}/` subfolders (one file per year) — no new plumbing needed.

**CLI**: `florida data staff {fetch,preprocess,assemble}`, registered the
same way `_register_shocks` is in `cli.py`/`handlers.py`. `fetch` takes
`--subsource {teacher-salary,out-of-field,district-finance}` (default: all
three) plus `--year` (repeatable) and, for the two FLDOE sub-sources,
`--from-file`/`--file-url` for the same manual fallback `assessments/fetch
.py` offers when a year isn't archived or the Internet Archive is down.

**Panel join**: `panel/assemble.py`'s `attach_staff` — two exact-key left
joins, no `merge_asof` tolerance or interval explosion needed (see module
docstring): `district_staff_panel.parquet` by `(district_name, year)`
(broadcast to every school in the district, same shape as `shocks`'
county-year broadcast), then `school_staff_panel.parquet` by `(msid, year)`
(already at the right grain, no broadcast). Unlike `shocks`/`road_projects`,
an unmatched staff row is left `NA`, not zero-filled — there is no sensible
"zero" for an average salary or an out-of-field percentage the way there is
for a declaration count.

## Definition of done

- ~~`fetch.py` downloads each FLDOE workbook via Wayback (falling back to
  manual import) and calls the Urban CCD-finance API.~~ **done**
  (2026-09-17) — `district_finance`: 26/26 years fetched cleanly, no errors.
  `teacher_salary`/`out_of_field`: 2025 downloaded via Wayback and confirmed
  parseable before a live Internet Archive outage interrupted broader
  verification; the registries for the other 11-12 years are in place and
  will backfill on the next `fetch` once the outage clears. CLI:
  `florida data staff fetch`.
- ~~`preprocess.py` tidies all three sub-sources to their native grain.~~
  **done** (2026-09-17) — real run: 78 districts (`teacher_salary`), 4,093
  real school-level rows (`out_of_field`), 1,856 district-years
  (`district_finance`). CLI: `florida data staff preprocess`.
- ~~`assemble.py` builds the `district -> leaid` crosswalk and the two output
  panels.~~ **done** (2026-09-17) — 84 districts crosswalked (min coverage
  88.5%, median 100%), 1,904 district-staff-panel rows, 4,093
  school-staff-panel rows. CLI: `florida data staff assemble`.
- ~~Wire this source into `panel/assemble.py`'s `event_study_panel.parquet`.~~
  **done** (2026-09-17) — `attach_staff`, real run: 35,453/660,681 rows
  (5.4%) matched salary/experience, 398,189 (60.3%) matched per-pupil
  expenditure, 35,308 (5.3%) matched out-of-field. 17 new tests across
  `test_staff_preprocess.py`/`test_staff_assemble.py`/
  `test_panel_assemble.py`, 244/244 Florida tests pass.
- ~~`covariates.md`'s Cluster B table updated from "planned" to
  "implemented" with real numbers, same convention as
  `traffic`/`road_projects`/`shocks`.~~ **done** (2026-09-17).
- **Not done, deferred with reasons above**: teacher turnover, %
  advanced/graduate degree, the `AR*DistStaff` count workbooks. A full
  historical `teacher_salary`/`out_of_field` fetch (11-12 remaining years
  each) is mechanically ready but blocked on the Internet Archive's own
  outage clearing — re-run `florida data staff fetch` once it does.
