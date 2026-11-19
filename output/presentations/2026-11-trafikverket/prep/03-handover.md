# Handover: Trafikverket call preparation, 2026-11-19

For the call on **25 November 2026** (Trafikverket, noise and vibration; slides
`output/presentations/2026-11-trafikverket/trafikverket-meeting.tex`). Written 2026-11-19 at the end of
a working session; the next step (editing the slides) is yours. Committed on 2026-11-19 (section 5).

## 1. State at a glance

| | |
|---|---|
| Prompt 01 (what Lastkajen offers) | Done, report `prep/01-lastkajen-catalogue-report.md` (sections 1 to 7) |
| Prompt 02 (check claims and data) | Done, report `prep/02-local-data-check-report.md` |
| New data ordered and downloaded | Yes: 3 earlier-date road snapshots, Vägombyggnad and Vägnybyggnad, Inspire Noise (all raw, no pipeline) |
| Docs | Updated; `python scripts/docs.py check`: 46 docs, 0 problems |
| Slides | **Not edited.** Proposed wording is in report 02 §3.1 |
| Git | Branch `line/sweden-residents` (fast-forwarded to `master`), three commits, not pushed; working tree clean |

## 2. What was done, in order

1. Ran prompt 01 in your logged-in Chrome, read only: Lastkajen's catalogue, the road barrier
   specification (PDF, 15 pages), the order-wizard help, *Mina beställningar*. Report written.
2. On your go-ahead placed and downloaded a test order for the road barrier product with reference date
   2015-01-01, then 2019-01-01 and 2022-01-01, and compared all four road snapshots (July 2026 included).
3. Ran prompt 02: 13 claims checked against the raw data and docs, missed data, proposed changes. Report
   written.
4. Documented the products we had not used (`docs/data/sweden/lastkajen-unused-products.md`).
5. On your go-ahead ordered Vägombyggnad and Vägnybyggnad (one order), downloaded them and the six Inspire
   Noise files, and inspected them.
6. Documented the remainder: scripts saved, `noise_barriers` README updated, two source pages added, stale
   lines fixed, memory note written.

## 3. Findings that matter for the call

Numbers are from the checks of 2026-11-19; scripts in `scripts/checks/2026-11-lastkajen/`.

**Corrections to the slides** (details and replacement text in report 02):
- Lastkajen IDs are **63 (road) and 10006 (rail)**, not "posts 630 and 991" (where 630/991 came from is not in
  the repository).
- "Matched to every school": every school **with coordinates** (10,531 of 12,037); the 100 m cells cover only the
  1.6 km corridor around barriers (832,221 cells).
- "Side and distance are missing": true for road; **rail has a distance for 44%** of records (796 of 1,829).
- "Removed barriers are not available": **an earlier reference date returns older road versions** (2015: 1,277
  records, 124 later closed). Slide question 3 should say so.
- The 30-40% traffic match is of school-years, not segments.
- The short window "2001-2019" is K = 5; the pre-spec's recommended K = 4 gives 2000-2019.
- Verified without change: record counts (2,172 / 1,829), the half and quarter without a year (51.3%, 26.6%),
  62% without a road height, all twelve bar-chart numbers, 55 / 58 schools, about 2,600 audited barriers with
  95-98% agreement (2,616 used), the full window 2000-2005.

**History and dating** (road): the register keeps versions; removals are rare (36 of 1,118 `ELEMENT_ID` ever seen
are absent from July, about 3%); `Höjd` and `Byggår` never change on an existing record. For barriers registered
since 2015, `VALID_FROM` is close to the build year (equal for 67%, one year later for 25%). The undated,
unmeasured walls are the 2006 legacy batch (85% of pre-2015 records have no year; none has a height), and snapshots
cannot date them.

**One lead, untested out of sample:** rail `Bisobjektnr` follows the build year (rank correlation 0.85); neighbouring
objects bracket the year within 2 years for 309 of 487 undated rail records. It needs a check that numeric
neighbours are not only spatial neighbours and a pre-spec entry before any use.

**New products:**
- Vägombyggnad / Vägnybyggnad: completion years and project numbers; 23% / 99% of road barriers lie on a record;
  `Väsentlig ombyggnad` unknown for 95%; `Objekt nr` filled for about 20%; 45 undated 2006-batch walls get a
  bracket of at most six years from a rebuild year.
- Inspire Noise: strategic noise contours for **2016 only**; 60% of road and 54% of rail barriers inside a
  contour of 50 dB or more.

## 4. What is left (your list for tomorrow)

1. **Edit the slides** (`trafikverket-meeting.tex`) with the wording in report 02 §3.1: the "What we have" frame
   (IDs, school matching, side and distance), the K = 4 window label, and detailed questions 1 to 5, 8, 9. Questions
   13 to 15 (Bisobjektnr, Inkopplingsdatum, 2006-01-01 date) exist only in the `noise_barriers` README so far.
   Decide whether the slide questions should mention what we already know (history by reference date, the
   2016 noise maps) or keep them as questions only.
2. **Decide on the `Bisobjektnr` lead:** validate it (spatial check, out-of-sample on the 451 `<20190405` records)
   and write a pre-spec entry if it will date walls for `sweden-residents`; or only ask Trafikverket.
3. **Decide what enters the pipeline:** the three snapshots, Vägombyggnad and Vägnybyggnad, Inspire Noise are all
   raw only. Each needs a `fetch`/`preprocess` module, tests and a pre-spec step before an estimate uses it.
4. **Optional orders:** more road reference dates; a rail order with an earlier date (rail is flagged "no history",
   untested); the Inspire description page and earlier mapping rounds were not looked at.
5. **Rename or annotate the raw files** whose names are swapped (`highway_` = rail, `railway_` = road); the scripts
   and the README name them as they are.

## 5. Repository state

Branch `line/sweden-residents` (it was already merged, so I fast-forwarded it to `master` at 247509c and
committed on it, as `AGENTS.md` asks for non-documentation changes). **Not pushed.** Three commits, in an order
that keeps each commit's links valid:

| Commit | Content |
|---|---|
| `32900ba` | `scripts/checks/2026-11-lastkajen/` (10 scripts and a README) |
| `66d1b47` | the three prep reports (`01-…-report.md`, `02-…-report.md`, `03-handover.md`) |
| `231e6b5` | docs: `lastkajen-unused-products.md`, the `road_projects` and `inspire_noise` source pages, the `noise_barriers`, `covariates`, `schools` and Sweden index updates, regenerated tables, and `AGENTS.md` (raw-only domains, `scripts/checks/`) |

A fourth small commit updates this file. Commit messages follow the repository's style (one long first line, then
`- docs:` lines) and carry no co-author line, as in the existing history. `python scripts/docs.py check` passes
(46 docs, 0 problems); no git hook is installed, so it is run by hand.

Data stays out of git: `data/sweden/noise_barriers/raw/road_ref_<date>/` (3 folders, about 4 MB),
`data/sweden/road_projects/` (272 MB) and `data/sweden/inspire_noise/` (645 MB) are ignored. The two prep prompts
(`01-lastkajen-catalogue.md`, `02-local-data-check.md`) were already in the folder and are untouched.

## 6. Actions outside the repository

- **Lastkajen (your account, felix.schulz@unibas.ch):** five orders placed, all Klar:
  "Sound Barriers - Road 150101" (121409), "… 190101" (121410), "… 220101" (121411), "Road Projects (Rebuild and
  New Build)" (121412). Mina beställningar now lists 14 saved orders; the help text says 10 is the limit, but they
  were accepted. Delete or keep as you prefer; none runs on a schedule.
- **Downloads:** each file was moved out of `~/Downloads` into its own folder under `data/sweden/` and unpacked.
  Nothing from this work remains in `~/Downloads`.
- **Chrome:** the tabs I opened were closed. Login was yours; I entered no credentials.
- **Memory:** `lastkajen-products-2026-11.md` and an index line (outside the repository).
- **Temp:** two pickles in `/tmp` (`om.pkl`, `ny.pkl`), written by `road_projects_profile.py` and read by
  `road_projects_vs_barriers.py`.

## 7. Caveats and open points

- **Not verifiable here:** the data years behind the windows slide (grade 9 1996-2022, grades 3 and 6 from 2012,
  addresses from 1980); the within-child window 2014-2021 cannot be rebuilt from the pre-spec's stated rule.
- **Inferences, not Lastkajen statements:** that 2006-01-01 is the conversion date; that Inspire Noise is the
  strategic noise map set and covers agglomerations and major roads; that an earlier reference date returns little
  for Vägombyggnad / Vägnybyggnad (their `VALID_FROM` is mostly 2023); that a dropped `ELEMENT_ID` may be a retired
  road element rather than a removed wall.
- **Open:** whether rail history works; what happened to the 36 dropped `ELEMENT_ID`; whether the Inspire bands are
  nested; how the 2016 model treats existing walls; how `Objekt nr` links to a project register; where "630 and 991"
  came from.
- **Rail `Sida_h_v_b` and `SIDE`** agree on 99.5%, so they are one signal; whether it is right for rail has not been
  tested with the divided-road test used for road.
- **Scope of the checks:** they load no outcome and are not pre-specified steps; none feeds an estimate.

## 8. Where to start tomorrow

1. Read this file, then report 02 §3.
2. Edit the slides; rebuild the PDF.
3. Run `python scripts/docs.py check`, commit the slide edit on `line/sweden-residents`, and merge to `master` when you are happy (not pushed yet).
4. Reproduce a number if in doubt: `scripts/checks/2026-11-lastkajen/README.md` says which script gives which result.
