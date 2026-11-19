# Local data check: claims and missed data

Run 2026-11-19 in this repository. Read-only: no slide, doc, code or data file was edited, and nothing
was committed. Aggregates only; the only barrier rows named are the two the slides name. Inputs:
the raw GeoPackages under `data/sweden/noise_barriers/raw/`, the processed and assembled files,
the docs cited per row, and `prep/01-lastkajen-catalogue-report.md`.

Two terms used below: **road file** = the order "Sound Barriers - Road" (447607, layer
`VIS_DK_O_63_Bullerskydd_vag`); **rail file** = "Sound Barriers - Rail" (451138, layer
`BIS_DK_O_10006_Bullerskydd`). On disk their names are swapped (section 2.5).

## 1. Claims

| # | Claim | How checked | Verdict |
|---|---|---|---|
| 1 | Lastkajen posts 630 and 991 | Catalogue URLs on Lastkajen (prompt 1): road product is **63** (`/aboutdataroad/100002/63`), rail is **10006** (`/aboutdatarailway/100201/10006`); the layer names `VIS_DK_O_63`, `BIS_DK_O_10006` agree. `grep` for 630/991 in `docs/` and the barrier source finds no mention. | **Corrected.** Road = 63, rail = 10006. Where 630/991 came from is not in the repository (the road data product *specification* is document 1051). |
| 2 | 2,172 road and 1,829 rail records | Row counts of the two raw layers; the processed parquets also hold 2,172 / 1,829. | **Verified.** |
| 3 | Matched to every school and to the 100 m grid | `data/sweden/schools/assembled/schools_barrier_rollup.parquet`: 10,531 schools. `schools.csv`: 12,037 units, **10,531 with coordinates**. Grid: `grid_treatment_protected.parquet` has 832,221 cells, a corridor around the barriers, not all of Sweden (`docs/data/sweden/grid/README.md` §tiling). | **Corrected.** Every school *with coordinates* (10,531 of 12,037 in the register); the 100 m cells cover only the 1.6 km corridor around barriers (832,221 cells), keyed to SCB's cell code but self-built, not SCB's grid. |
| 4 | Side checked by hand for about 2,600 barriers; automatic methods agree in 95-98% | `docs/data/sweden/barrier_audit/README.md` lines 13-20: 2,827 answered, **2,616 used by the build**; agreement `osm_offset` 98% (n=165), `parallel_road` 95% (755), `track_offset` 95.5% (512). | **Verified** (2,616 used; 2,827 answered; the 95-98% is per automatic method). |
| 5 | No construction year for half the road and a quarter of the rail records | Raw: road `Byggar` = 1900 on **1,114 (51.3%)**; rail `Byggar` = 0 on **487 (26.6%)**. | **Verified** (rail is a little over a quarter). |
| 6 | Road barriers are on the centreline, so side and distance are missing | Raw fields below; `docs/data/sweden/barrier_matching.md` §3a (99.8% of road and 99.7% of rail geometry within 1 mm of the road or track). | **Corrected** for rail; **verified** for road. See the field table. |
| 7 | Height missing for 62% of road records | Road `Hojd` = 0 on 1,351 of 2,172 (**62.2%**). | **Verified.** |
| 8 | Bar chart counts | Recomputed from `Byggar` (road sentinel 1900, rail 0): road unknown 1,114, <1996 47, 1996-2005 81, 2006-14 174, 2015-22 510, 2023+ 246 (sum 2,172); rail 487 / 15 / 349 / 249 / 527 / 202 (sum 1,829). The dark segments: 978 road unknowns have `VALID_FROM` in 2006 (959 exactly 2006-01-01); 451 rail unknowns read `<20190405`. | **Verified**, all twelve numbers and both splits. |
| 9 | Most undated road records were loaded when the register started in 2006 | 978 of 1,114 undated (88%) have `VALID_FROM` in 2006. | **Verified** as data; "register started in 2006" is an inference: Lastkajen's spec says the first load was a conversion from the old regional databases and gives coverage "from 2015-01-01", not 2006. |
| 10 | Exports list only barriers standing today (every `VALID_TO` is 9999-12-31) | Both raw files: all 2,172 and 1,829 `VALID_TO` = 99991231. | **Verified for our exports.** The inference "older versions cannot be had" is **corrected**: a road order with reference date 2015-01-01 returns 124 records with `VALID_TO` before 9999 (prompt 1 report, section 6). |
| 11 | ÅDT history matches about 30-40% over 1998-2019; no train counts | `docs/data/sweden/traffic/README.md` line 174: ~30-40% of **school-years** (läsår) 1998-2019, ~50% for 2022-25; 90.6% of geocoded schools match a segment within 1 km. Train counts: `data/sweden/timetable/` holds one night of train announcements (2026-06-25 to 26, 3,551 rows), not counts; `docs/data/sweden/covariates.md` line 68 lists rail traffic volume as "unconfirmed". | **Corrected:** 30-40% of *school-years*, not segments. "No train counts" **verified**. |
| 12 | 55 schools kept behind dated barriers, 58 dropped | `docs/lines/sweden-schools/results.md` §1: "55 treated schools have a construction year. Dropped: 58 treated schools with no construction year". | **Verified** (exploratory run of 2026-10-22, before pre-specification). |
| 13 | Windows on the "Why construction years matter" slide | Arithmetic against `prespec-cohort-exposure.tex` (grade-9 data 1996-2022): full window 1996+4 = 2000 to 2022-17 = **2005** ✓. Short window: the slide shows 2001-2019 (e = -5...3, 1996+5); the pre-spec's recommended K = 4 gives **2000-2019** (its own table, line 358). Within child: 2014-2021 matches the pre-spec text (line 695), but I cannot derive it from the stated rule (children born 2002-06, grade 3 in 2012-16, grade 9 in 2018-22 allow 2013-2022 at the loosest). | **Full window verified; short window corrected** (2000-2019 for K = 4, or label it K = 5); **within-child cannot be reproduced** from the stated rule. Data years themselves: cannot check here. |

### Field table for claim 6 (what the side and distance fields hold)

| Field | Records with a value | What it holds | Usable? |
|---|---|---|---|
| Road `SIDE` | 2,172 of 2,172 | Höger 1,732, Vänster 436, both 4 | No: left/right of the road link's direction; refuted 2026-09-18 and again in `barrier_matching.md` §3b (valid test on divided roads, n=377) |
| Rail `SIDE` | 1,829 of 1,829 | Höger 938, Vänster 878, both 10, Mitt 3 | Same attribute logic as road; not independent of the next row |
| Rail `Sida_h_v_b` | 1,796 of 1,829 (98%) | h 920, v 857, b 19, empty 33 | **Equal to rail `SIDE` on 99.5% of the 1,796**, so it is the same information, not a second source |
| Rail `Avstand_fr_sparmitt_m` | **796 of 1,829 (43.5%)** real; 1,033 (56.5%) are 999 = not recorded | Distance 0 to 50 m, median 4.6 m; 91 records read exactly 0 | Yes for 44% (preprocess already sets 999 to NA); the 0 m values are suspect and unchecked |
| Road distance | none | no such field | n/a |

So the slide's "side and distance are missing" is right for road and half-right for rail: rail has a
distance for 44% of records.

## 2. Missed data

Most useful first.

### 2.1 Rail `Bisobjektnr` may date most undated rail walls (new, exploratory)

`Bisobjektnr` is kept by `preprocess` (as `bis_object_number`) but not used anywhere in the analysis.
Among the 1,342 dated rail records the rank correlation between `Bisobjektnr` and `Byggar` is **0.85**.
Dating each of the 1,069 dated objects from its two neighbours in `Bisobjektnr` order (leave one out)
puts the true year between the neighbours' years 93% of the time, with a median bracket width of 0 years
and brackets of at most 2 years for 92%. Applied to the 487 undated rail records (348 objects):
**309 records (63%) get a bracket of at most 2 years, 394 (81%) at most 5 years.** No dated record shares a
`Bisobjektnr` with an undated one, so there is no direct fill.

Caveats: the numbers are not monotone across deciles (the lowest decile has years 1994-2016), so this is
local, not global; neighbouring numbers may be spatial neighbours (same line, same project) rather than
time neighbours, which would still help but needs checking; this is an exploratory check, not a
pre-specified step, and the analysis should not use it before a pre-spec entry (AGENTS.md). The natural
question to Trafikverket: does BIS number objects in order of registration, and is registration close to
construction?

Road has no equivalent: only 25 of 1,114 undated road records share an `ELEMENT_ID` with a dated one.

### 2.2 Vägombyggnad and Vägnybyggnad: project years and names (not ordered)

Prompt 1 found two road products we have never ordered (nothing in `docs/` or `src/` mentions them):
**Vägombyggnad** (ID 96: rebuild year, `Väsentlig ombyggnad` flag for rebuilds that substantially raise
noise or vibration since 1997, project object number and name) and **Vägnybyggnad** (ID 97: completion
year of new roads, object number and name). Both have Historik = Ja. They give completion years and
project identities for the road works that came with walls, a candidate answer to question 5 and a
way to separate a wall from the road works around it. They do not give start or announcement dates.

### 2.3 Earlier reference dates return removed barriers (answers question 3)

Already ordered and compared (prompt 1 report, section 6): snapshots for 2015-01-01, 2019-01-01 and
2022-01-01 (saved under `data/sweden/noise_barriers/raw/road_ref_*`). Facts: records 1,277 / 1,563 / 1,869 /
2,172 (July 2026); 124 / 74 / 43 / 0 closed records; **36 of 1,118 `ELEMENT_ID` seen in any snapshot are
absent from the July file** (about 3%); `Höjd` and `Byggår` changed on none of the 1,157 segments shared by
2015 and July. Of the 1,014 July records with `VALID_FROM` in 2015 or later, 87% have a `Byggår`, and it
equals the registration year for 67% and is one year earlier for 25%. Of the 1,158 records from before 2015,
85% have no `Byggår` and none has a height. So the undated, unmeasured walls are the legacy stock, and
snapshots will not date them. Not yet in the pipeline; the rail product has Historik = Nej, untested.

### 2.4 Columns `preprocess` drops or we do not use

`preprocess` keeps every raw column (it renames, it does not drop); the question is which we use.

| Column | Holds | Could help? |
|---|---|---|
| Rail `Inkopplingsdatum` | 1,291 records `<20190405` (BIS's first-load date), 538 real dates 2019-2026 | Not a construction date. Of the 502 real-date records that also have `Byggår`: date year = `Byggår` for 281 (56%), one year later for 120 (24%), two or more later for 94 (19%), earlier for 7. It reads as the date the record was connected in BIS, trailing construction by 0-1 years for most. 36 of the 538 have no `Byggår` and could be dated by it (date year minus 0-1). Two oddities: 23 real-date records have `Byggår` before 2019 (registered late) and 5 `<20190405` records have `Byggår` 2019 or later (inconsistent). |
| Rail `Typ` | wood 1,019, earth berm 219, metal 178, concrete 153, glass 146, unknown 59 | Material, for the noise-reduction prediction; no dating power. |
| Rail `Besiktningsklass` | b1-b5 (mixed case: `b4` and `B4`) | Same distribution among dated and undated; no dating power. Mixed case in the raw file (`b4`, `B4`); `preprocess` lower-cases it. |
| Rail `Bisobjektnr` | 1,417 distinct numbers for 1,829 records | **Dating lead, section 2.1.** `Bisobjekttypnr` is constant (10006). |
| Rail `Typritningsnr` | filled for 166 records (9%), 34 distinct, many "Se not." | Zero undated records have one; no dating power. |
| Rail `Kmtal`, `Kmtalti` | kilometre position, text like `20+901` | Not parsed; the position along the track. Could link a wall to track kilometre for joins to other Trafikverket rail data; not for dating. |
| Road `Materialtyp` | wood 1,138, earth berm 510, glass 165, unknown 144 | Material; known for 89% of undated and 98% of dated records. No dating power. |
| Road `Pa_bro` | unknown 1,185, no 871, yes 116 | Unknown for 91% of undated vs 16% of dated records: a field filled only for recent registrations, so its *missingness* mirrors the 2006 batch (a weak marker, not a date). |
| Road `Agare`, `Absorbent`, `Grundlaggningstyp` | "Okänt" for 55%, 66%, 64% | Same pattern as `Pa_bro`. |
| `VALID_FROM` (both) | road 2006 batch plus registration dates; rail only 2025-09 to 2026-06 | Road: a build-year proxy for records from 2015 on (section 2.3). Rail: useless (all 2025-26). |

Anything that could date the undated walls, roughly: rail `Bisobjektnr` (section 2.1), earlier snapshots
(no, section 2.3), `Inkopplingsdatum` (only the 36 with a real date). For the 959 road walls loaded on
2006-01-01 with no year or height, nothing in the file.

### 2.5 Consistency

- **Raw names are swapped; preprocessing is right.** `highway_noise_barriers.gpkg` holds the rail layer
  (receipt names order 451138, "Rail") and `railway_noise_barriers.gpkg` the road layer (447607, "Road").
  `find_local_noise_barrier_bundle` (`shared.py`) pairs a GeoPackage with its receipt by the order name
  inside `*_delivery_info.txt`, and `infer_dataset_kind` reads "road"/"rail" from the dataset name, so the
  processed files are correct: `road_noise_barriers.parquet` has 2,172 rows, `dataset_kind = road`, `height_m`,
  no distance column; `rail_noise_barriers.parquet` has 1,829 rows, `dataset_kind = rail`, the distance and
  connection-date columns. Only the file names mislead. Document it in
  `docs/data/sweden/noise_barriers/README.md` (a "Raw files" note) and consider renaming the files.
- **My additions to the raw folder.** The three `road_ref_*` snapshot folders are subfolders; the loader
  globs only the top level of `raw/`, so they do not affect preprocessing.
- **Docs vs data:**
  - `noise_barriers/README.md` says "1,092 road records have `valid_from` 2006-01-01"; 1,092 is the count with
    `valid_from` *in 2006*; exactly 2006-01-01 is 1,064.
  - `schools/README.md` §"Real run" still reports 10,648 units and 9,520 geocoded; the v2 register has 12,037 units,
    10,531 with coordinates (`schools/README.md` lines 34-44).
  - `noise_barriers/README.md` open question 10 says the traffic panel "matches about 30-40% of segments";
    it is school-years (`traffic/README.md` line 174).
  - `noise_barriers/README.md` "Current walls only ... no history" is true of our extract but no longer of what
    can be ordered.
  - The `timetable` and `stations` sources have no `docs/data/sweden/<source>/README.md` page, though the rule in
    AGENTS.md asks for one per source.
- **Processed road file is older than the raw order's use:** `road_noise_barriers.parquet` was written 2026-09-15
  and `rail_noise_barriers.parquet` 2026-09-23; counts and `built_year` NA counts match the raw files (1,114 / 487),
  so no stale-data effect found.

## 3. Proposed changes

### 3.1 Slides (`trafikverket-meeting.tex`)

"What we have" frame:
- Replace `Bullerskydd from Lastkajen (posts 630 and 991): 2,172 road and 1,829 rail records` with
  `Bullerskydd from Lastkajen (road: product 63, rail: product 10006): 2,172 road and 1,829 rail records`.
- Replace `Matched to every school and the 100\,m grid` with
  `Matched to every school with coordinates (10,531) and to 100\,m cells near each barrier`.
- Replace `\textbf{Where:} drawn on the centreline, so side and distance are missing` with
  `\textbf{Where:} road barriers sit on the centreline: no distance, and the side field is not reliable. Rail has a distance for 44\%`.

"Why construction years matter" (appendix): the second bar (`2001--2019`) is K = 5; the pre-spec recommends K = 4,
so change the bar and its label to `2000--2019` or add "(K = 5)". The 2014--2021 bar is the pre-spec's, but its derivation
is not stated; keep it with the pre-spec as the source.

"Our questions in detail (1/2)", replacements:

1. (sharpened) `Do older registers or project archives hold construction years for the undated barriers: the 959 road barriers loaded on 2006-01-01 (and their heights), and the 451 rail barriers dated only ``before 2019-04-05''? For rail, is the BIS object number assigned in order of registration? Among dated rail barriers it follows the construction year closely (rank correlation 0.85).`
2. (add rail) `Is the construction year the year a barrier was completed? Does a rebuild overwrite it? For rail, does ``connection date'' mean connection in BIS (it trails the construction year by 0--1 years for most)?`
3. (replace; answered in part by us) `We found that an earlier reference date on Lastkajen returns older road versions (2015: 1,277 records, 124 later closed). Does the register keep removals before 2015, where the specification's coverage starts? And is the same available for rail, where history is marked ``no''?`
4. (sharpen) `Is the exact position available: for road, the real geometry that the discontinued ``real geometry'' attributes pointed to; for rail, the distance from the track, which is recorded for 44\% of barriers?`
5. (sharpen) `Road rebuilds and new roads carry a completion year, project number and name (Lastkajen products Vägombyggnad and Vägnybyggnad). Is there a project register with start or decision dates behind these numbers, and one for rail?`

Question 8 (facade): add the pointer the Lastkajen product description itself gives:
`Lastkajen's road barrier description says window measures are held in the national noise database. Is that the register of properties considered for mitigation, and can it be shared?`
Question 9: `Strategic noise maps are on Lastkajen (Inspire, road and rail, Lden and Lnight, files from 2024). Which year do they cover, and do earlier rounds and calculations before and after a measure exist?`

### 3.2 Question list (`docs/data/sweden/noise_barriers/README.md` "Open questions", and `docs/open-questions.md`)

- **Reword 3** as above (history by reference date works for road); drop "Are removed walls recorded anywhere?" in favour of "what happened to the 36 barrier IDs that disappear between snapshots (removed barrier or retired road element)?".
- **Add** a question on `Bisobjektnr` (above), and one on rail `Inkopplingsdatum` semantics.
- **Add** a question on the "real geometry" and on the 2006-01-01 date: is 2006-01-01 the conversion date, and why does the specification say coverage from 2015-01-01?
- **Sharpen 5, 8, 9** as above.
- **Keep** 7, 10 (rephrase "segments" to "school-years"), 11, 12.
- **Docs fixes** found in section 2.5, including a note on the swapped raw file names.

## 4. Open points

- Where **630 and 991** came from: not in the repository. Possibly a different Lastkajen numbering (a post number in a product list) that I did not see; prompt 1 only saw 63 and 10006.
- **`Bisobjektnr` dating** is untested against space: whether numeric neighbours are also geographic neighbours, and how accurate it is out of sample for the 451 `<20190405` records. A pre-spec entry is needed before use.
- Whether a **dropped `ELEMENT_ID`** between snapshots is a removed barrier or a retired road element (36 cases): the docs do not say.
- **Rail history** (Historik = Nej) is untested; one rail order with an earlier reference date would settle it.
- **2,616 vs 2,827** audit counts are both right (used vs answered); the slide's "about 2,600" is the used count.
- The **within-child window** (2014-2021) cannot be rebuilt from the stated rule; it needs the pre-spec's author to confirm.
- **Data years** (grade 9 from 1996 to 2022, grades 3 and 6 from 2012, addresses from 1980) cannot be checked here.
- Rail `Sida_h_v_b` and `SIDE` agree 99.5%, so they are one signal; whether that signal is right for rail has **not** been tested with the valid divided-road test used for road.
