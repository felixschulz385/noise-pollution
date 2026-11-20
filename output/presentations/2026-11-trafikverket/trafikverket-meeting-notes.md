# Trafikverket call, 25 November 2026: notes to the slides

Companion to [`trafikverket-meeting.pdf`](trafikverket-meeting.pdf) (source `trafikverket-meeting.tex`). For
the four of us presenting: what stands behind each slide, what we found on Lastkajen, and the full list of
questions, in more detail than the slides show. Written 2026-11-20.

- Call: Trafikverket, noise and vibration, 15:00–16:00, in English.
- Plan: about 5 minutes of core slides (4 after the title), then the questions. The appendix is for
  questions that come up.
- Numbers come from the Lastkajen exports of July 2026, the checks of 2026-11-19
  (`prep/01-lastkajen-catalogue-report.md`, `prep/02-local-data-check-report.md`,
  `scripts/checks/2026-11-lastkajen/`) and the docs named in each section. None of them uses an outcome.

## 1. What we want to leave the call with

In order of value to the project:

1. **Construction years** for the undated barriers, or the name of whoever holds the project archives.
   This is the largest single gain for the cohort design (section 4, appendix slide 2).
2. **The facade insulation register**: who holds it and whether researchers can get it.
3. **Exact barrier positions** (side and distance), or confirmation that they do not exist.
4. **Project start or decision dates** for the road and rail works that came with the barriers.
5. For each source: the holder, the format and the access route (data use agreement or not).

If time runs short, questions A1, A2, B1 and D1 below are the ones to get through.

## 2. Slide by slide

### What we want to learn

- The two references are Lindgren (2021), "A sound investment? Traffic noise mitigation and property
  values" (Journal of Environmental Economics and Policy), and Lindgren (2021), "A sound environment: health
  effects of traffic noise mitigation" (working paper). The health paper uses the national facade
  mitigation programme and finds a 10% lower risk of cardiovascular disease after seven years, driven by
  hypertension. The property-value paper used the register we ask about under question B1, and the health
  paper the same programme, so Trafikverket may know them.
- The point to make: we would deliver an estimate of the long-term impact of Trafikverket's noise
  protection on the children who grow up behind it, from school results to adult outcomes. It adds to
  the existing evidence on property values and health.

### The idea

- Points dropped from the slide that may come up:
  - Each child is placed at the family's address three years before the barrier, before the project
    could make families move, and followed wherever the family moves.
  - Facade measures allow the same comparison, insulated dwellings against similar dwellings insulated
    later.
- The opposite side is not always unprotected: about 40% of dated barriers built by 2007 have the
  opposite side largely walled too (road 37%, rail 42%). We also use a band of cells 600–1500 m from the
  barrier as a second comparison.

### What we have

| Slide claim | Behind it |
|---|---|
| Products 63 (road) and 10006 (rail) | Lastkajen catalogue IDs; the layers are `VIS_DK_O_63_Bullerskydd_vag` and `BIS_DK_O_10006_Bullerskydd`. The road data product specification is document 1051 (v6.0, 2021-11-02). Earlier drafts said "posts 630 and 991"; where those came from is not known, so do not use them. |
| 2,172 road and 1,829 rail records | Row counts of the two exports (July 2026). |
| Every school with coordinates | 10,531 of the 12,037 units in the school register (API v2). |
| 100 m cells near each barrier | 832,221 cells in a 1.6 km corridor around the barriers, keyed to SCB's cell code (lower-left corner) but built by us. Not all of Sweden. |
| Side checked by hand on aerial imagery | 2,827 barriers answered, 2,616 used in the build. Two coders on a blind sample agreed with kappa 0.68. Automatic methods agree with the hand coding in 95–98% of cases (OSM wall offset 98%, n = 165; parallel road 95%, n = 755; rail track offset 95.5%, n = 512). |
| No year for half of road, a quarter of rail | Road `Byggår` = 1900 (the "unknown" code) on 1,114 records (51.3%); rail `Byggår` = 0 on 487 (26.6%). |
| Road on the centreline, no distance, unreliable side | 99.8% of road and 99.7% of rail geometry lies within 1 mm of the road or track line. The road `Sidoläge` field (right or left) failed our test on divided roads (n = 377), so we do not use it. The road product has no distance field. |
| Rail distance for 44% | `Avstånd_fr_spårmitt_m` is filled for 796 of 1,829 records (median 4.6 m, range 0–50 m); 999 means not recorded. 91 records read exactly 0 m, which we have not checked. Rail's two side fields (`SIDE`, `Sida_h_v_b`) agree on 99.5%, so they are one signal, and we have not tested whether it is right. |
| No height for 62% of road | `Höjd` = 0 on 1,351 of 2,172 road records (62.2%). |
| Chart | Road: unknown 1,114, before 1996 47, 1996–2005 81, 2006–14 174, 2015–22 510, 2023+ 246. Rail: 487, 15, 349, 249, 527, 202. Dark part of the "unknown" bars: 978 undated road records have `VALID_FROM` in 2006 (959 exactly 2006-01-01); 451 undated rail records have the connection date "<20190405". |

How to describe the dark bars: these barriers were in the register when it was first loaded, so they were
built by then. That 2006-01-01 is the date of the conversion from the old regional databases is our
reading. The specification only says the first load was a conversion, and gives the register's history
"from 2015-01-01" (question A6).

### What we would like to ask

Each bullet maps to a question in section 4:

| Bullet | Question |
|---|---|
| Years for the road barriers loaded in 2006 and the rail barriers entered before 2019 | A1, A9 |
| Heights of the older road barriers | A1 |
| Side and distance from the road or track | A3 |
| Does *Byggår* mark completion? Does a rebuild overwrite it? | A2 |
| Older versions of the rail register | A4 |
| Are rail BIS numbers assigned in registration order? | A5 |
| Facade: properties considered, measure, type, year, cost, position | B1 |
| Start or decision dates for road and rail projects | C1 |
| Noise levels before and after a measure | C2 |
| Strategic noise maps before 2016 | C3 |
| Train counts, road traffic counts before NVDB's history | C4 |
| Barriers planned but never built | A8 |
| Who holds these data, and how could researchers apply? | D1 |

### Appendix: Design

- K = 4: each barrier's stack compares the four test cohorts before it with the four from the barrier year on
  (event times −4 to 3).
- The step comes with the first cohort that spends its last school year behind the barrier. Longer
  exposure may add to it.
- Power (pre-spec `docs/lines/sweden-residents/prespec-cohort-exposure.tex`, power section; open population
  data, optimistic): short-run minimum detectable effect about 0.25 SD for rail and 0.46 SD for road with the
  opposite side alone, 0.15 and 0.22 SD with the 600–1500 m band added.

### Appendix: Why construction years matter

- Windows, from grade-9 data for 1996–2022: the birth-to-grade-9 comparison needs barriers built 2000–2005;
  the short-run comparison (four cohorts before and after) needs 2000–2019. The 2014–2021 window for the same
  child before and after is the pre-spec's; we could not rebuild it from the stated rule, so do not defend
  its end points.
- 55 kept and 58 dropped schools are from the school-level run of 2026-10-22, which was exploratory and
  ran before the pre-specification rules existed. Say so if asked, and do not present its estimate as a
  result.
- "About twice as many children": with every rail year known, rail's protected children in usable stacks
  roughly double in the short window. The road years of the 2006 load matter most for the full window,
  where road barriers are not estimable today (4 usable stacks). Minimum detectable effects with all years
  (pre-spec, "expected" scenario, opposite side / band / both): rail short-run 0.17 / 0.12 / 0.10 SD
  instead of 0.25 / 0.18 / 0.15; road full window 0.53 / 0.36 / 0.31 instead of not estimable.
- Of the dated barriers in the 2006 load, 57% were built before 2000, outside every window. So not every
  date we get will help.

### Appendix: Why exact positions matter

- The predicted noise reduction needs the distance between source, barrier and receiver, and the
  barrier height.
- "About 2,600" is the 2,616 hand-coded barriers used in the build.

### Appendix: Why facade measures matter

- An insulated home on the opposite side lowers the contrast between the sides, so without the records our
  barrier estimates are likely biased toward zero.
- Properties assessed but not insulated are a comparison group for the facade treatment itself.

## 3. What we found on Lastkajen

Background for the discussion; this was on a slide that has been dropped. Details in
`docs/data/sweden/lastkajen-unused-products.md` and `prep/01-lastkajen-catalogue-report.md`.

### Older versions of the road register

- The road product is marked "Historik: Ja". An order with an earlier reference date returns the register
  as it stood that day. We ordered 2015-01-01, 2019-01-01 and 2022-01-01.

  | Reference date | Records | Road links | km | Closed later | `Byggår` unknown | `Höjd` unknown |
  |---|---|---|---|---|---|---|
  | 2015-01-01 | 1,277 | 680 | 141 | 124 | 86% | 100% |
  | 2019-01-01 | 1,563 | 806 | 178 | 74 | 70% | 84% |
  | 2022-01-01 | 1,869 | 955 | 216 | 43 | 61% | 72% |
  | July 2026 | 2,172 | 1,082 | 251 | 0 | 51% | 62% |

- Removals are rare: 36 of the 1,118 road links (`ELEMENT_ID`) seen in any version have no barrier in July
  2026, about 3%. Whether these are removed barriers or retired road links we do not know.
- `Byggår` and `Höjd` changed on none of the 1,157 segments present in both 2015 and 2026. Missing values
  are never filled in later, so older versions cannot date the 2006 load. Present in 2015 does mean built
  by 2015.
- Barriers registered since 2015 are well documented: 87% have a year, and the registration year equals it
  for 67% of those and is one year later for 25%. Of the 1,158 records registered before 2015, 85% have no
  year and none has a height. The gap is the legacy stock, not current practice.
- Earlier reference dates than 2015 were not tested. The register's records start in 2006, so a date such
  as 2010 could add at most the roughly 80 records registered in 2008–2014. Barriers removed before 2006
  never entered the register (question A4).

### Rail register

- Marked "Historik: Nej" (not tested). Every rail `VALID_FROM` falls in 2025–2026, so it carries no
  information on timing.
- `Inkopplingsdatum` reads "<20190405" for 1,291 records (BIS's first load) and has a real date for 538.
  Where both exist, its year equals `Byggår` for 56% and is one year later for 24%. It looks like the date
  the record entered BIS, not a construction date. 36 undated records have a real connection date and could
  be dated from it.
- `Bisobjektnr` (question A5): among the 1,342 dated rail records its rank correlation with `Byggår` is
  0.85. Dating each undated record from its neighbours in number order gives a bracket of at most 2 years
  for 309 of the 487 undated records (63%) and at most 5 years for 394 (81%). Leaving one dated object
  out at a time, the true year falls inside the neighbours' bracket 93% of the time. Exploratory only: the
  numbers may follow lines or projects rather than time, and we would need a pre-spec entry before using
  it.
- No rail product specification exists on Lastkajen, and the catalogue gives no field definitions.

### Road projects (Vägombyggnad, ID 96; Vägnybyggnad, ID 97)

- Completion year, project number (`Objekt nr`), project name and an archive reference for rebuilt and new
  road sections. 7,457 rebuild and 83,475 new-build records.
- 23% of road barriers lie on a rebuilt section. 810 road barriers (37%) lie on a record with a project
  number; `Objekt nr` is filled for about 20% of records overall.
- `Väsentlig ombyggnad` (a rebuild since 1997 that substantially raises noise or vibration) is unknown for
  95% of rebuilds.
- 45 undated barriers from the 2006 load lie on a section rebuilt in 2000–2006, which brackets their year
  to at most six years.
- Completion years only. No start, decision or announcement dates (question C1).

### Noise maps (Inspire package 10088)

- Lden and Lnight contour polygons for road, rail and air. The files are dated 2024-09-04 but hold the 2016
  mapping round (from the file contents; the catalogue page does not say).
- 60% of road and 54% of rail barriers lie inside a contour of 50 dB or more.
- One round only, and no levels before or after a measure (questions C2, C3).

### Not on Lastkajen

- Facade or window measures. The road product description says window measures (*fönsteråtgärder*) are
  kept in the national noise database (*nationella bullerdatabasen*).
- Train counts. The nearest product, Trafikeringssystem (rail ID 32), classifies tracks, it does not count
  trains.
- Project start dates for road or rail.

## 4. All questions

What we know already is given with each question, so we can show we have done the reading and avoid
asking for what Lastkajen already offers. The numbering follows the "Open questions" of
`docs/data/sweden/noise_barriers/README.md` where noted (README #).

### A. Noise barriers

**A1. Construction years and heights for the undated barriers** (README 1). Do older registers or project
archives hold them?
- Road: 978 of the 1,114 undated records came in the 2006 load. None of the pre-2015 records has a height.
- Rail: 451 of the 487 undated records were entered before 5 April 2019.
- Why: an undated barrier cannot be used at all. Rail years add most to the short window, road years open
  the birth-to-grade-9 window to road barriers.
- Also ask: the specification says `Byggår` and `Höjd` are mandatory with 0% tolerance for gaps. Is the
  gap known, and is 1900 the official "unknown" code?

**A2. What `Byggår` records** (README 2). Is it the year the barrier was completed? Does a rebuild or
replacement overwrite it? For rail, is it defined the same way?

**A3. Exact position** (README 4).
- Road: is the "real geometry" that the attributes `Verklig geometri ID/dimension/längd` pointed to (removed
  2021-11-02, stored in STVDB) still held, and can we have it?
- Road: what does `Sidoläge` refer to (right or left of the reference line's direction)? It failed our test.
- Rail: `Avstånd_fr_spårmitt_m` is recorded for 44%; is it held for the rest? Are the 91 zeros real?
- Rail: what do `Sida_h_v_b` and `Höjd_över_rök_m` mean exactly?

**A4. History and removed barriers** (README 3).
- Rail: can older versions of the rail register be ordered, as for road?
- Road (if time): are barriers removed before 2006 recorded anywhere? What happened to the 36 road links that
  lost their barrier between 2015 and 2026?

**A5. Rail BIS object numbers** (README 13). Are they assigned in order of registration, and was
registration close to construction? Or were they assigned in one batch (for example at the 2019 load) in
some other order, such as by line? See section 3 for why it matters.

**A6. Register dates** (README 14, 15).
- Is 2006-01-01 the date of the conversion from the old regional databases, and why does the
  specification give coverage "from 2015-01-01"?
- Rail `Inkopplingsdatum`: is it the date the object was connected in BIS? Is "<20190405" BIS's first load?

**A7. Specific barriers** (README 6). Two barriers dated 2001 carry the school-level estimate. Can their
year be confirmed from the project files?
- Road: `ELEMENT_ID` 10376:49, measures 0.888–0.987, 353 m, wood, kommun 1880 (Örebro), `Byggår` 2001,
  height unknown, `VALID_FROM` 2006-01-01.
- Rail: BIS object 9888, km 11+145 to 11+365, 202 m, wood, 2.0 m, kommun 1293 (Hässleholm), `Byggår`
  2001, connected before 2019-04-05.
- And the undated barriers beside 58 schools (list in `docs/lines/sweden-schools/`, can be sent after the
  call).

**A8. Planned barriers** (README 7). Are barriers that were planned or proposed but never built recorded
anywhere? They would be a comparison group of places that were candidates for a barrier.

**A9. The rules over time** (README 11). Which noise levels qualified a stretch for a barrier, or a property
for a facade measure, and since when? This tells us which places were candidates at a given time.

### B. Facade measures

**B1. The insulation register** (README 8). Is the register of properties considered for noise mitigation
available to researchers? It is the data Lindgren (2021) used.
- Fields we need: whether a measure was carried out, its type, year and cost, and the SCB 100 m cell. Exact
  addresses are not needed.
- Is it the national noise database (*nationella bullerdatabasen*) that the road register's description
  mentions for window measures? Who holds it today?
- Does it include properties assessed but not treated?

### C. Construction and context

**C1. Project dates** (README 5). Is there a project register with start, decision or announcement dates
behind the `Objekt nr` in Vägombyggnad and Vägnybyggnad? Is there one for rail projects?
- Why: we place families at their address before the project, so we need to know when a project became
  known. Completion years alone are not enough.
- What we know: the traffic-information API keeps finished roadworks for only about a year.

**C2. Calculated noise levels** (README 9). Are levels calculated for a property or a barrier, before and
after a measure, kept, for example in the measure's documentation?

**C3. Strategic noise maps** (README 9). Do mapping rounds other than 2016 exist, and in what form? Does the
2016 model include the barriers standing at the time?

**C4. Traffic** (README 10).
- Train counts before the barriers were built: which years and lines exist? We hold none.
- Road traffic (ÅDT) for years or sections that NVDB's history does not cover. Our traffic panel matches
  about 30–40% of school-years in 1998–2019.

### D. Access

**D1. Access** (README 12). For each source: who holds it, in what format, on what terms, and whether a data
use agreement is needed. Is there a contact person for follow-up questions?

## 5. Careful with

- **Inferences, not Trafikverket statements:** that 2006-01-01 is the conversion date; that the Inspire
  files are the 2016 round (read from the files); that a dropped `ELEMENT_ID` is a removed barrier.
- **Exploratory, not results:** the school-level run of 2026-10-22 (before pre-specification), the
  `Bisobjektnr` dating, all counts in section 3.
- **Not checked here:** the data years on the windows slide (grade 9 1996–2022, grades 3 and 6 from 2012,
  addresses from 1980) and the 2014–2021 within-child window.
- **Counts are provisional:** construction years and heights may change with Trafikverket's reply, and
  every barrier count with them.

## 6. Sources

- Slides: `trafikverket-meeting.tex`
- Lastkajen catalogue and test orders: `prep/01-lastkajen-catalogue-report.md`
- Checks of slide claims and missed data: `prep/02-local-data-check-report.md`; scripts in
  `scripts/checks/2026-11-lastkajen/`
- Handover of 2026-11-19: `prep/03-handover.md`
- Barrier register and open questions: `docs/data/sweden/noise_barriers/README.md`
- Products not used before: `docs/data/sweden/lastkajen-unused-products.md`
- Barrier audit: `docs/data/sweden/barrier_audit/README.md`
- Power and windows: `docs/lines/sweden-residents/prespec-cohort-exposure.tex`
- School-level run: `docs/lines/sweden-schools/results.md`
