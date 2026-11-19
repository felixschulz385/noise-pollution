# Prompt 2: check our claims and our data (Claude Code, this repository)

Run after prompt 1, in a Claude Code session in this repository. Paste everything below the
line.

---

## Context

On 25 November 2026 we meet Trafikverket to ask for data. The slides are
`output/presentations/2026-11-trafikverket/trafikverket-meeting.tex`; the questions are also
listed under "Open questions" in `docs/data/sweden/noise_barriers/README.md`. Before the call I
want every statement the slides make about our existing data verified, and I want to know
whether we have missed anything we already hold or could order ourselves.

Inputs:
- `output/presentations/2026-11-trafikverket/prep/01-lastkajen-catalogue-report.md`: what
  Lastkajen offers (from a browser session). If it is missing, stop and tell me.
- Raw data under `data/sweden/`, e.g. `data/sweden/noise_barriers/raw/` (two GeoPackages and
  their order receipts), the traffic and road-network orders, and the processed and assembled
  files. Each source's page is `docs/data/sweden/<source>/README.md`.
- `AGENTS.md` for the repository's rules.

## Task 1: verify each claim

Check each claim against the data or the docs. For each, give the claim, how you checked it (file
and code, or doc and line), and one of: **verified**, **corrected** (with the right statement),
**cannot check here** (e.g. facts from the register data), with a note.

From the slides:
1. The registers come from Lastkajen posts 630 and 991 (and which is road, which is rail).
2. 2,172 road and 1,829 rail records.
3. Matched to every school and to the 100 m grid.
4. The side was checked by hand on aerial imagery for about 2,600 barriers, and the automatic
   methods agree with that in 95–98% of cases (`docs/data/sweden/barrier_audit/README.md`).
5. No construction year for half of the road records and a quarter of the rail records.
6. Road barriers are drawn on the centreline, so side and distance are missing. Also check: does
   either file's `SIDE`, rail's `Sida_h_v_b` or rail's `Avstand_fr_sparmitt_m` give the side or the
   distance, and for how many records? (The road `SIDE` attribute was found unusable on
   2026-09-18; see `docs/data/sweden/road_network/README.md`.)
7. Height is missing for 62% of road records.
8. The bar chart's counts of records by construction year: unknown 1,114 / 487; before 1996
   47 / 15; 1996–2005 81 / 349; 2006–2014 174 / 249; 2015–2022 510 / 527; 2023 on 246 / 202
   (road / rail).
9. Most undated road records were loaded when the register started in 2006.
10. The exports list only barriers standing today (every `VALID_TO` is 9999-12-31).
11. Our road traffic history (NVDB ÅDT) matches about 30–40% of segments over 1998–2019, and we
    have no train counts.
12. A first school-level analysis kept 55 schools behind dated barriers and dropped 58 behind
    undated ones (`docs/lines/sweden-schools/results.md`).
13. The windows on the "Why construction years matter" slide: walls built 2000–2005 (birth to
    grade 9), 2001–2019 (first years after), 2014–2021 (same child before and after), given
    grade-9 results 1996–2022 and grades 3 and 6 from 2012. The data years themselves come from
    the register data and cannot be checked here; check only the arithmetic.

## Task 2: what have we missed?

1. **Columns we drop.** Compare the raw GeoPackage columns with what
   `src/noise_pollution/regions/sweden/sources/noise_barriers/preprocess.py` keeps. For each
   unused column, say what it holds and whether it could help. In particular:
   - rail `Inkopplingsdatum`: 538 records carry a real date (2019–2026), the rest
     `<20190405`; 36 of them have no `Byggar`. Is it a construction or commissioning date,
     or a database date? Compare it with `Byggar` where both exist;
   - rail `Typ`, `Besiktningsklass`, `Bisobjektnr`, `Typritningsnr`, `Kmtal`;
   - road `Materialtyp`, `Pa_bro`;
   - whether anything could date the undated walls, even roughly.
2. **What Lastkajen offers that we have not ordered.** Compare prompt 1's report with our
   orders (the `*_delivery_info.txt` receipts under `data/sweden/*/raw/`). Could an order with an
   earlier reference date return removed barriers, as it did for traffic history? List what we
   could order ourselves.
3. **Consistency.** The raw file names look swapped: `highway_noise_barriers.gpkg` holds the
   rail order (`BIS_DK_O_10006_Bullerskydd`), and `railway_noise_barriers.gpkg` the road order.
   Confirm that preprocessing still assigns road and rail correctly, and say where this should
   be documented. Note anything else that looks inconsistent between the data and the docs.

## Rules

- Read-only on data. Do not edit the slides, the docs or the code; propose changes in the report.
- Report only aggregates (counts, shares), never individual records beyond the barrier IDs the
  slides already name.
- Do not commit. Do not contact any outside service; Lastkajen is covered by prompt 1.

## Output

Write `output/presentations/2026-11-trafikverket/prep/02-local-data-check-report.md` with:
1. **Claims**: the table from task 1.
2. **Missed data**: findings from task 2, most useful first.
3. **Proposed changes**: to the slides and to the question list (questions to drop because
   Lastkajen or our data already answer them, questions to add or sharpen), as concrete text.
4. **Open points** you could not settle.
