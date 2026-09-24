# `assessments`

Self-contained implementation brief, mirroring the `road_network`/
`road_projects`/`shocks` README-first pattern used in the Florida pipeline.
Everything below was checked live against the real Skolverket API/database
on 2026-09-15, not guessed — see the curl/fetch calls inline.

**Scope**: school-level achievement data — the outcome variable for a
school-exposure event study. Split out from [`schools`](../schools/README.md)
2026-09-15 to mirror Florida's `schools` (identity/geocoding/treatment
timing) vs. `assessments` (outcome) separation — independently-changing
concerns, joined by the `panel` domain (built 2026-09-16, see
[`../README.md`](../README.md)) against `schools`' `assemble` output (barrier-treatment timing per
`skolenhetskod`).

**Status (2026-09-17): both vintages (`kvalitetssystem` and `siris`) have
`fetch` + `preprocess` implemented and run at full national scale**
(2026-09-15 was smoke-test scale only; 2026-09-16 was the full run — see
§1/§2 below). The cross-era stitching question (§4) is now **decided**:
`kvalitetssystem` is kept out of the joined `panel` for now (its nearest
`meritvärde` analogue is a pass-rate share, not a continuous score, and it
doesn't even abut the SIRIS era), and the two SIRIS-internal grading-scale
sub-eras (pre-/post-2014/15 reform) are stitched into one continuous
`meritvärde_z` outcome by z-scoring each side of the break separately —
option (a) from §4, restricted to the two SIRIS sub-eras since
`kvalitetssystem` isn't pooled in. Implemented in
`src/regions/sweden/sources/panel/assemble.py`'s `stitch_meritvarde`.

**Key finding, the whole reason this needs a brief before building:** Sweden
had a real ~2-year *legal* interruption of school-level statistics
publication, and the modern machine-readable API only covers a short recent
window — so unlike Florida (one FLDOE workbook format, continuous
2003–2026), Sweden's school-level achievement panel has a genuine seam that
needs a design decision, not just more fetch code.

## 1. `kvalitetssystem` — live PxWeb API, school-unit grain, **2022/23 → 2025/26 only**: implemented

`src/regions/sweden/sources/assessments/kvalitetssystem.py` --
`fetch_kvalitetssystem` (metadata -> full `level` codelist via the
`top`-filter trick -> batched measure-value POSTs), `preprocess_kvalitetssystem`
(flattens json-stat2's `id`/`size`/`value`/`status` arrays -- confirmed
row-major with the *last* `id` dimension fastest, verified against a real
payload, not assumed). CLI: `sweden data assessments
{fetch-kvalitetssystem,preprocess-kvalitetssystem}`. **One real bug found
while building the `parse_school_level_codes` filter**: the obvious
approach -- checking whether a `level` label contains the literal word
"SKOLENHET" -- is a false friend. It only catches schools whose own *name*
happens to contain "skolenhet" (a common Swedish split-campus naming
pattern, e.g. "ALLÉSKOLAN SKOLENHET ASK") and silently drops every
normally-named school (e.g. "FJÄLLSKOLAN F-6"). Fixed to the real
discriminator: a school-unit row's *code* is the compound
`orgnr-skolenhetskod` key (contains a hyphen); a huvudman-only row's code
is a bare org number. **Real run** (`--limit-schools 5` smoke test): 5,238
real schools in the Grundskola codelist; fetched 51 measures x 5 schools x
4 years = 1,020 tidy rows, several genuinely suppressed (`status="."`) as
expected. Tests: `test_assessments_kvalitetssystem.py` (8), including a
regression test built directly from the real payload fetched live.

Skolverket's statistics database (`statistikdatabasen.skolverket.se`) is a
standard **PxWeb** instance (same tech SCB and other Nordic stat agencies
use) with exactly two top-level branches (confirmed live — the whole
database, not just what's discoverable in the web UI):

```
GET https://statistikdatabasen.skolverket.se/PxWeb/api/v1/sv/Skolverkets_statistikdatabas
→ [Kommunala_jamforelsetal, Underlag_for_analys_inom_det_nationella_kvalitetssystemet]
```

- **`Underlag_for_analys_inom_det_nationella_kvalitetssystemet`** (basis for
  analysis within the national quality system) has one table per school
  form (`Forskola`, `Grundskola`, `Gymnasieskola`, …). Confirmed metadata
  for `Grundskola.px`
  (`.../Underlag_for_analys_inom_det_nationella_kvalitetssystemet/Grundskola/Grundskola.px`):
  - **`level` variable = `huvudman/skolenhet`** — i.e. this table IS
    queryable down to individual school unit, not just the operator. This is
    the source to build the school-level panel from.
  - **`time` variable covers only 4 school years: 2022/23, 2023/24, 2024/25,
    2025/26** — this system is new (matches the "spring 2025 confidentiality
    markers" finding below; the national quality system itself appears to
    date to the 2022/23 school year).
  - **51 measures** (`mått`), spanning: student counts/demographics; staff
    counts and qualification rates; per-student cost; **grade point
    averages at åk6 and åk9 by subject** (`Delmål 1`); **national-test pass
    rates at åk3 in Swedish and Math** (`Delmål 5`/`6`, "andel elever som
    uppnår kravnivån på samtliga delprov"); **åk6/åk9 subject grades in
    Swedish and Math** specifically flagged as their own measures; plus
    survey-based measures (student/staff perceived safety, `studiero`,
    stimulans, stöd — means, not shares).
  - **`level` query contract — resolved 2026-09-15, confirmed live**: the
    plain metadata GET returns no `values` for `level` (it's too large to
    inline), but a POST with `{"code":"level","selection":{"filter":"top","values":["20000"]}}`
    returns the **full codelist exhaustively** — only 6,115 entries for
    Grundskola (huvudman rows + skolenhet rows mixed in one flat
    dimension), well within one request. **The code for a school-unit row
    is a compound key `"{huvudman_orgnr}-{skolenhetskod}"`** (e.g.
    `"2120001355-53332364"` → `"GÖTEBORGS KOMMUN (2120001355): FJÄLLSKOLAN
    F-6 (53332364)"`) — the bare `skolenhetskod` alone is rejected (400).
    Confirmed a real item-filtered query on that compound key returns real,
    multi-year values (`{"query":[{"code":"variable","selection":{"filter":"item","values":["26","27"]}},{"code":"level","selection":{"filter":"item","values":["2120001355-53332364"]}},{"code":"time","selection":{"filter":"item","values":["2022","2023","2024"]}}],"response":{"format":"json-stat2"}}`
    → åk6 pass rate 71.6/75/76.9 across the three years). **Practical
    `fetch` design**: pull the `level` codelist once via `top` (cheap, one
    call per school form), filter to `SKOLENHET` labels to build the
    skolenhetskod↔huvudman-orgnr↔compound-code map (also cross-checks
    against `Skolenhetsregistret`'s own codes), then query data either
    per-school or — worth trying first, likely simpler — with
    `{"filter":"all"}` on `level` in one shot per (measure-batch, year)
    given the whole codelist is only ~6k entries, not the tens of
    thousands a naive worst case might have suggested.
  - **Full national fetch, real run 2026-09-16**: 5,238 school-unit codes
    (Grundskola), 51 measures, 4 läsår -> 27 batches of 200. **Two real
    bugs found and fixed while running it at full scale** (both covered by
    regression tests):
    1. **PxWeb throttles bursts of POSTs with a bare `429`** ("Too many
       requests in too short timeframe", no `Retry-After` header) -- the
       first full-scale attempt died after exactly one batch. Fixed with
       fixed-schedule retry/backoff in `_read_json`
       (`RATE_LIMIT_BACKOFF_S = (5, 15, 30, 60, 120)`) plus a 2s delay
       between newly-fetched batches, and made `fetch_measure_values` save
       + skip **per batch** (not just at the very end) so a resumed run
       after a failure doesn't re-pay for already-fetched batches.
    2. **The naive "skip if the batch file already exists" resume check was
       itself a trap**: a stale `batch_0000.json` left on disk from an
       earlier 5-school smoke test got silently "resumed" as the real
       first 200-school batch -- a well-formed payload, just for the
       wrong, smaller query, so nothing errored anywhere. Result: 195 real
       schools silently missing from `preprocess`'s output (1,028,772 rows
       instead of the expected 5,238x51x4 = 1,068,552; 5,031 distinct
       `skolenhetskod` instead of 5,224). Caught by checking the row count
       against the expected combo count, not assumed correct. Fixed by
       validating a cached batch's own `level` dimension actually covers
       every code the current call expects at that index before trusting
       it as "already fetched" -- a stale/partial batch now gets
       transparently re-fetched and overwritten. `--force` still available
       to force a full re-fetch regardless.
    - **Clean real run after the fixes**: 27/27 batches fetched fresh, 0
      incorrectly skipped. `preprocess`: **1,068,552 rows exactly**
      (5,238 x 51 x 4, matches the combo count precisely), **5,224
      distinct `skolenhetskod`** (5,238 level codes minus 14 legitimate
      cases of one `skolenhetskod` recurring under two different
      `huvudman_orgnr` -- checked directly, a real code-reuse pattern, not
      a bug). `status` breakdown: 622,404 `.` (not applicable), 366,106
      non-suppressed (a real reported value), 38,228 `..` + 31,239 `...` +
      10,575 `-` (suppression/rounding sentinels) -- **34.3% of all cells
      carry a real value**, the rest genuinely not applicable/suppressed
      for that measure x school x year combination (e.g. a measure that
      only exists at åk6 has no value for a school with no åk6). Output:
      `data/sweden/assessments/processed/kvalitetssystem_grundskola.parquet`.
  - **One real, unexplained finding while testing this**: Fjällskolan i
    Uddevalla (skolenhetskod `57004269`, a real `schools` record — see
    `schools/README.md` §1) does **not** appear anywhere in this table's
    6,115-entry codelist, while a different, unrelated "Fjällskolan" in
    Göteborg does. Likely because it's flagged `Resursskola: true` in the
    register (a special-needs unit, plausibly out of scope for the
    mainstream national quality system's grade-based indicators) — but this
    is a guess, not confirmed; worth checking whether `Resursskola`/other
    school-type flags predict absence from this table before assuming every
    active grundskola has a row here.

## 2. `siris` — Skolverket's archived pre-2020 exports on S3, school-unit grain, 1998–2019: implemented

`src/regions/sweden/sources/assessments/siris.py` --
`fetch_siris_dataset` (downloads `datasets.csv`, resolves one confirmed
school-grain series' per-year URLs, idempotent per year), `parse_siris_csv`
(banner-skip + one/two-row header detection + Swedish-locale numeric
coercion), `preprocess_siris_dataset` (stacks every fetched year, `year`
column from the filename, not the in-file "Valt läsår" banner text). CLI:
`sweden data assessments {fetch-siris,preprocess-siris} --dataset-key
{slutbetyg_arskurs9,salsa}`. **Two real bugs found running it against live
data** (both now covered by regression tests): (1) **the encoding claim
below was wrong** -- an earlier research-only pass (no code, no real bytes
inspected) assumed ISO-8859-1 from a terminal `iconv` round-trip that
happened to render plausibly; actually inspecting the real fetched bytes
(`\xef\xbb\xbf...` at the start) showed **UTF-8 with a BOM** -- decoding as
ISO-8859-1 silently produced mojibake column names
(`fã_rã_ldrarnas_genomsnittliga...` instead of `föräldrarnas_...`) rather
than an error, so this could easily have gone unnoticed without checking
real output; fixed to `utf-8-sig`. (2) a column blank on every row of a
given year can come back from `pd.DataFrame.from_records` already coerced
to float `NaN` rather than staying `None`/`str`, crashing
`_parse_numeric_se`'s `.strip()` call -- fixed with an explicit
`pd.isna()`/`str()` guard. **Real run**: fetched läsår 2018/19 and 2017/18
(`år` 2018/2019) of the SALSA series live, 2,990 tidy rows, real Swedish
column names confirmed correct after the encoding fix
(`genomsnittligt_meritvärde_faktiskt_värde_f`, etc.), sensible-looking
residual values. Tests: `test_assessments_siris.py` (10).

- **`Kommunala_jamforelsetal`** (the live PxWeb branch) is municipal/county/
  national only (confirmed: its `Grundskola/Betyg/Grundskola_betyg.px`
  table's `level` values are all municipality/county codes + `Riket
  totalt`), back to school year 2012/13 — of no use for a school-level
  design on its own, and nothing else lives in this PxWeb instance.
- **The real answer: Skolverket's pre-2020 SIRIS exports are still
  publicly downloadable**, straight from Skolverket's own S3 bucket
  (`skolverket-statistik.s3.eu-north-1.amazonaws.com`), preserved (not
  hosted fresh) by the datajournalist project
  **`jplusplus/skolstatistik`** (<https://github.com/jplusplus/skolstatistik>).
  The live SIRIS web tool itself (`siris.skolverket.se`) is gone (404,
  confirmed live), but every file it used to export is still sitting at a
  fixed, guessable S3 path and returns HTTP 200 with real data when
  fetched directly (confirmed live, several files, several years) — no
  authentication, no rate limiting hit.
  - **Index**: the repo's `datasets.csv` (6,787 rows) is a full manifest —
    columns `databas, skolnivå, dataset, år, uttag, format, url` — for
    every `(school form × topic × year × format)` combination Skolverket
    ever exported through SIRIS. Fetch it once
    (`raw.githubusercontent.com/jplusplus/skolstatistik/master/datasets.csv`)
    and treat it as the fetch plan; don't re-derive URLs by hand, the
    filenames have Swedish special characters requiring exact matches.
  - **Year coverage confirmed**: `år` values in `datasets.csv` range
    **1997–2020**; the school-unit-grain datasets checked (below) run
    **school years 1997/98 → 2018/19** (`år` column = the *first* calendar
    year of the läsår, so `år=2019` means läsår 2018/19 — one year short of
    the Sept-2020 cutoff, i.e. läsår 2019/20's results, normally published
    ~autumn 2020, were never captured).
  - **Grain is per-dataset-ID, not per-topic** — Skolverket published the
    same topic at multiple aggregation levels as separate numbered
    datasets sharing a near-identical title, and only checking the actual
    file header tells you which. Confirmed live by downloading real CSVs:
    - `139-Slutbetyg årskurs 9, samtliga elever` = **school-unit grain**
      (header: `Skola;Skol-enhetskod;Skolkommun;Kommun-kod;Typ av
      huvudman;Huvudman;Huvudman orgnr;Antal elever;Andel som uppnått
      kunskapskraven i alla ämnen;Andel (%) behörig yrkesprog.;
      Genomsnittligt meritvärde (17)`) — average grade-point merit value,
      eligibility rate, and pass rate, **per school**, 1998–2019.
    - `138-Slutbetyg årskurs 9, samtliga elever` (same title!) is the
      **kommun-grain** sibling of 139 — confirmed by header diff, no
      `Skol-enhetskod` column. A trap for a careless fetch script.
    - `95-Salsa, skolenheters resultat av slutbetygen i årskurs 9 med
      hänsyn till elevsammansättningen` — also **school-unit grain**
      (`Skola;Skol-enhetskod;...`), 1998–2019: SALSA is Skolverket's own
      composition-adjusted model (actual vs. predicted grade outcome given
      each school's parental-education/newly-arrived/sex mix) — genuinely
      useful as a covariate or a robustness outcome, not just raw grades.
    - `92`/`93`/`148` (`Slutbetyg per ämne årskurs 9`, per-subject grades)
      checked and are **kommun**-grain, not school-grain, in the IDs
      sampled — **a school-unit-grain sibling for per-subject grades was
      not located this session**; worth a systematic pass through
      `datasets.csv`'s full ID list per topic (grep for `Skol-enhetskod` in
      each candidate file's header, not just trust the title) before
      concluding it doesn't exist.
    - The `Skol-enhetskod` join key in these files is **the same code**
      `Skolenhetsregistret` uses (spot-checked: `71387206` "Ahlafors Fria
      skola" appears in both `95` and `139` with the same code) — so this
      archive joins cleanly to `schools`' geocoding without any crosswalk.
  - **Files are Swedish-locale**: `;`-delimited, decimal comma,
    `.`/`..`/`~100` as suppression/rounding sentinels (small-cell
    suppression already present in this era's exports too, same spirit as
    the modern rule in §3).
- **Full national fetch, real run 2026-09-16** (both series, all läsår
  1997/98-2018/19, år 1998-2019, no gaps -- the idempotent per-year fetch
  confirmed every year present on the first full run): `slutbetyg_arskurs9`
  -- **34,666 rows, 3,070 distinct schools**; `salsa` -- **29,971 rows, 2,542
  distinct schools**. år 2016's one-year-only doubled-header anomaly (§4)
  parsed cleanly (1,700 / 1,476 rows that year respectively -- in line with
  neighbouring years, not truncated or duplicated). Outputs:
  `data/sweden/assessments/processed/siris_{slutbetyg_arskurs9,salsa}.parquet`.
- **Net effect — no longer a blocking gap, but two seams remain**:
  1. A clean school-unit panel is buildable end-to-end as **1998–2019
     (this SIRIS S3 archive) + a likely-unrecoverable few läsår around
     2019/20–2021/22 (the suppression window itself) + 2022/23–2025/26
     (the live PxWeb API)** — i.e. a ~2–3 year notch, not the previously
     assumed "everything before 2022 is missing."
  2. This SIRIS archive is a **third-party-preserved copy of a
     Skolverket-published export**, not a Skolverket-maintained live
     endpoint — treat its continued availability as not guaranteed
     (mirror it into this repo's own `raw/` on first fetch rather than
     re-pulling from GitHub/S3 every run, the same "don't depend on
     someone else's archive staying up" caution Florida's
     `road_projects/README.md` flags for its own historical-archive gap).
  Whether the 2019/20–2021/22 notch is recoverable at all (e.g. via the
  retroactive July-2021 republishing mentioned in §3 possibly having landed
  in a location not yet found) is still open, but is a 2–3 year notch to
  chase, not a multi-decade gap.

## 3. Legal history of school-level statistics — resolves the doc's stale footnote

Researched because `sweden_noise_overview.tex`'s Table 2 footnote had the
direction backwards. Actual sequence (confirmed via Riksdagen written
Q&A and contemporary press coverage, cross-checked against Skolverket's own
news post):

1. **December 2019**: Kammarrätten i Göteborg ruled that SCB-held data on
   independent ("fristående") schools' throughput, grade distributions and
   student composition could be commercially sensitive to the operator and
   thus covered by trade-secret confidentiality.
2. **From 1 September 2020**: Skolverket, citing that ruling and an
   equal-treatment principle (can't publish municipal schools' data but not
   independent schools'), stopped publishing **any** school-unit-level
   statistics — grades, national test results, student composition — for
   **all** schools, public and independent alike. Only national-level
   statistics remained public. (This is the event the `skolstatistik`
   GitHub archive exists to preserve a copy of.)
3. **1 July 2021**: a *temporary* legislative carve-out (new §24:8a,
   Offentlighets- och sekretesslagen (2009:400)) restored publication of
   school-unit- and huvudman-level statistics, initially slated to run only
   through 30 June 2023, with everything that should have been published
   since Sept 2020 released retroactively.
4. **Since**: publication has continued (this session confirmed
   school-unit-level statistics are live today, 2026-09-15, via the PxWeb
   API in §1) — the exact permanent legal basis that replaced the 2023
   sunset was **not independently confirmed** this session (found only that
   the 2021 change was explicitly temporary; did not verify the follow-up
   legislation). Treat "currently public" as confirmed-by-direct-API-check,
   but "on a stable permanent legal footing" as unconfirmed.
5. **Since spring 2025**: a *new* small-cell suppression rule appeared
   (confirmed via Skolverket's own "Om Skolverkets statistik" page) —
   **staff/personnel counts** (teacher credential rates, counsellor and
   rector counts) are masked with "··" when fewer than 3 FTE positions exist
   at a school, to prevent identifying individual staff members. This is
   specifically a *personnel*-data rule; nothing found suggests grade/test
   results themselves carry an analogous small-cell mask, but that was not
   independently stress-tested against real low-enrollment-school data this
   session.

## 4. Open design question: stitching the two eras into one outcome — researched 2026-09-15, partially resolved

**Sweden's grading-scale reform, confirmed both from secondary sources and
by directly inspecting real SIRIS file headers across 2003–2019** (not
just web research — checking the actual government export is the
authoritative source here):

- **Timeline**: the old scale (Lpo94 curriculum: IG/G/VG/MVG, four levels)
  was replaced by the current scale (Lgr11 curriculum: A–F, six levels),
  new law from 1 July 2011, phased in by grade/cohort. **The last åk9
  slutbetyg under the old scale was spring 2014**; åk9 slutbetyg from
  läsår 2014/15 onward are fully on the new A–F scale (Skolverket
  publications + press coverage, cross-checked, not independently
  re-derived from first principles).
- **This exact boundary is directly visible in the raw SIRIS files**:
  dataset `139`'s `Genomsnittligt meritvärde` column is labeled `(16)`
  in every year checked from 2003 through **år 2014** (läsår …–2013/14),
  then switches to `(17)` starting **år 2015** (läsår 2014/15) and stays
  `(17)` through 2019. The "16 vs. 17" is nominally about a *different*
  rule (whether a modern-language elective counts as a bonus 17th
  subject, raising the max from 320 to 340), but it lands on **exactly**
  the same year boundary as the grading-scale switch — a real, checkable
  marker in the data itself for a regime an analyst might otherwise have
  to infer indirectly.
- **Reassuring structural finding: the numeric *range* didn't change at
  the reform**, only the number of discrete steps within it. Both scales
  map to the same points endpoints per subject (old: IG=0/G=10/VG=15/
  MVG=20; new: F=0/E=10/D=12.5/C=15/B=17.5/A=20), so `meritvärde` stayed a
  0–320 (later 0–340) continuous-ish figure throughout — a *milder* break
  than Florida's FCAT→FSA, which changed the test's entire numeric scale.
  What the raw number doesn't capture is that the underlying **grading
  criteria** (what knowledge earns each level) changed with the Lgr11
  curriculum — a content-validity difference, not visible in the points
  alone. Spot-checking one real school's `meritvärde` across 2003–2019
  (Aroseniusskolan i Ale: 214.5 → 217.4 → 197.3 → 201.8 → 199.4 → 198.0 →
  … → 218.3 → 226.2 → 233.8) shows no dramatic single-year jump right at
  the 2014/15 boundary — suggestive of rough comparability, not proof; a
  real matched-school before/after continuity check is still worth doing
  before trusting a z-score across the break, but it's now a well-scoped
  next analysis step rather than an open unknown.
- **Incidental finding, a parsing wrinkle not a regime**: år **2016** has a
  one-year-only anomalous header (`Inklusive okänd bakgrund` /
  `Exklusive okänd bakgrund` duplicate column sets, doubling the field
  count) that reverts to the normal single-set format by 2017. Handle as
  a per-year schema-drift case in `parse_siris_csv`-style parsing (already
  built to detect the header row dynamically, but not yet tested against
  this specific doubled-column shape), not as a real third era.

**Net effect**: there are still genuinely **two seams**, but they're now
characterized rather than unknowns:
1. The already-confirmed 1998–2019 ↔ 2022–2025 structural gap (§2) — a
   real, likely-unrecoverable notch around läsår 2019/20–2021/22.
2. The 2011-law/2014-cohort grading-scale reform *within* the SIRIS era —
   milder than initially feared (same numeric range both sides), visible
   in the data via the `(16)`→`(17)` label switch, but still a curriculum
   content change the raw meritvärde number doesn't fully paper over.

**Decided (2026-09-17)**: option (a) — z-score `meritvärde` within each
side of the 2014/15 break — but restricted to the two SIRIS sub-eras only.
`kvalitetssystem` is kept out of the pooled outcome and out of the joined
`panel` entirely for now (option (b)/(c)'s "pool `kvalitetssystem` in" and
"treat as a third era" branches are both shelved, not chosen — see the
`panel/assemble.py` module docstring for the current reasoning: no
continuous `meritvärde`-equivalent exists in `kvalitetssystem` at all, and
the 2020–21 legal gap means it wouldn't even abut the SIRIS era cleanly).
`kvalitetssystem_to_long`/`load_kvalitetssystem` are kept in the codebase
for a possible future standalone `kvalitetssystem`-only analysis — just
not called from `run_panel_assemble` anymore. Still open, independent of
this decision: whether `kvalitetssystem`'s 4-school-year span
(2022/23–2025/26) is long enough post-period on its own for a standalone
event study.

**Literature check (2026-09-16)**: Arensmeier, C. (2022), "Three Decades
of School Failure in Swedish Compulsory School," *Scandinavian Journal of
Educational Research*, 66(1), 14–27
([open access](https://www.tandfonline.com/doi/pdf/10.1080/00313831.2020.1833235)),
independently reproduces the same point-equivalence table found above in
its Table 1 (old: G=10/VG=15/MVG=20; new: E=10/D=12.5/C=15/B=17.5/A=20) —
confirming it's the actual legislated conversion, not just an artifact of
inspecting the raw files. But the paper itself sidesteps the continuity
question: it studies national grade-9 failure *rates* (share with a
failing grade) across 1990–2017, a discrete pass/fail indicator that's
comparably defined pre/post-reform by construction, not a pooled
continuous `meritvärde` series. No paper was found that empirically
validates or adjusts raw-point comparability across the 2011/2014 break
(e.g. via equipercentile matching) — the (a)/(b)/(c) choice above is a
judgment call this literature hasn't resolved either, not something to
defer to a citable method.

## Relationship to `schools`

`schools`' `Skolenhetsregistret` (`skolenhetskod`) is the join key both
vintages here already use directly — no crosswalk needed, confirmed by
spot-checking the same code across `schools`, `siris`, and
`kvalitetssystem`. **The panel join is built** (2026-09-16, updated
2026-09-17 for the stitching decision, `src/regions/sweden/sources/panel/
assemble.py`, mirrors Florida's `panel/assemble.py`): `schools assemble`'s
barrier-treatment timing (per `skolenhetskod`) × SIRIS's real observed
outcome values (per `skolenhetskod` × year × era × outcome_name — still
**long**, since SIRIS's own raw measures don't share one definition
either), now including `stitch_meritvarde`'s derived continuous
`meritvärde_z` series alongside the raw melt. `kvalitetssystem` is no
longer joined in at all (§4's decision) — the row/school counts below
predate that change and will shrink once the panel is rebuilt without it.
Old real run (both vintages pooled): 773,613 rows, 6,083 distinct schools,
1998–2025. See [`../README.md`](../README.md)'s `panel` row.
