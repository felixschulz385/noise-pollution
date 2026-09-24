"""Florida `staff` source (covariate Cluster B): staff & fiscal resources
that shift over the panel and could co-move with barrier timing (teacher
quality/turnover, resource level).

v1 scope, confirmed live 2026-09 (see `docs/data/florida/staff/README.md`
for the full brief): **teacher salary + years-experience** (FLDOE "Average
Salaries for Teachers" workbook, district-level), **in-field/out-of-field
teaching** (FLDOE `IFOFFTeach` workbook, SCHOOL-level — the only Cluster B
row with a school-level source), and **per-pupil current expenditure**
(NCES CCD F-33 fiscal survey via the Urban Institute API, district-level, no
auth). Teacher turnover (needs individual-level year-over-year staff
matching FLDOE doesn't publish in aggregate form) and % advanced/graduate
degree (not found among the live-verified downloadable FLDOE workbooks in
this pass) are documented open questions, not built.

`www.fldoe.org` blocks scripted downloads outright (Akamai bot protection,
same 403 `assessments/fetch.py` already documented) — but the Internet
Archive's Wayback Machine has independently crawled many of these exact
workbooks, and `web.archive.org` has no such block. `fetch.py` downloads via
`src.regions.florida.sources._http.wayback_download` first, falling back to
the same `--from-file`/`--file-url` manual-import path `assessments` uses
when a given year isn't archived (or the Internet Archive itself is
temporarily down — a real, if infrequent, outage observed directly while
building this module).

Stages: `fetch` (download each sub-source's per-year workbook / call the
Urban API) -> `preprocess` (tidy each of the three sub-sources to one row per
their native grain — district-year, school-year, district-year) -> `assemble`
(build the district->leaid crosswalk needed only for the CCD fiscal join,
REQUIRES `schools preprocess`).
"""
