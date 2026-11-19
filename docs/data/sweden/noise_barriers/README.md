---
type: source
state: current
updated: 2026-11-19
summary: "Sweden noise_barriers: what Trafikverket's road and rail registers record, and their attribute coverage"
---

# `noise_barriers`

Trafikverket's register of noise barriers along state roads and railways,
ordered from Lastkajen: `Bullerskydd - väg` (road, ordered 2026-07-06) and
`Bullerskydd` (rail, ordered 2026-07-07), both GeoPackage in EPSG:3006. The
order receipts are next to the raw files in `data/sweden/noise_barriers/raw/`.

`preprocess` writes `data/sweden/noise_barriers/processed/{road,rail}_noise_barriers.parquet`
(`src/noise_pollution/regions/sweden/sources/noise_barriers/`). Side matching and protected
areas are built from these files in [`../barrier_protection/README.md`](../barrier_protection/README.md);
the method is in [`../barrier_matching.md`](../barrier_matching.md).

## What the register is

- **One record per stretch of uniform wall**, not per wall. The register
  splits a wall wherever the road link, track element, height or material
  changes; `barrier_protection` joins the pieces into walls (`chain_id`).
- **Current walls only.** Every record has `is_current = True` and no
  `valid_to`. Walls that were demolished or replaced are not in it, and
  there is no history of earlier versions in our extract. **Road history can be
  ordered:** a reference date (*Betraktelsedatum*) of 2015-01-01 returns 124 records
  closed later; three snapshots (2015, 2019, 2022) are saved under `raw/road_ref_*`
  but not processed. Rail is flagged without history. See
  [`../lastkajen-unused-products.md`](../lastkajen-unused-products.md) §4.
- **Geometry sits on the road or track centreline** (road 99.8%, rail
  99.7% of records), so it says where along the road a wall stands, not how
  far from the road. The `side` attribute carries no signal. See
  [`../barrier_matching.md`](../barrier_matching.md) §3.

## Raw files (names are swapped)

In `data/sweden/noise_barriers/raw/`:

| File | Holds | Order |
|---|---|---|
| `railway_noise_barriers.gpkg` (+ `_delivery_info.txt`, `_license.txt`) | the **road** layer `VIS_DK_O_63_Bullerskydd_vag`, 2,172 records | "Sound Barriers - Road", 447607, 2026-07-06 |
| `highway_noise_barriers.gpkg` (+ receipts) | the **rail** layer `BIS_DK_O_10006_Bullerskydd`, 1,829 records | "Sound Barriers - Rail", 451138, 2026-07-07 |
| `road_ref_2015-01-01/`, `road_ref_2019-01-01/`, `road_ref_2022-01-01/` | earlier-date road snapshots (zip, GeoPackage, receipt); not processed | "Sound Barriers - Road 150101 / 190101 / 220101", 2026-11-19 |

The names are swapped (the source labels `railway` and `highway` were given to the other file). The
pipeline is not affected: `find_local_noise_barrier_bundle` pairs a GeoPackage with its receipt by the
order name inside `*_delivery_info.txt`, and `infer_dataset_kind` reads "road" or "rail" from that name,
so `processed/road_noise_barriers.parquet` (2,172 rows, `height_m`, no distance) and
`rail_noise_barriers.parquet` (1,829 rows, `distance_from_track_center_m`, `connection_date`) are
correct. Only the file names mislead; checked 2026-11-19. The loader reads only the top level of `raw/`,
so the snapshot folders do not touch `preprocess`.

## Sentinels

| column | sentinel | cleaned in `preprocess`? |
|---|---|---|
| `built_year` (road) | `1900` | yes, to NA (2026-09-15) |
| `built_year` (rail) | `0` | yes, to NA (2026-09-15) |
| `distance_from_track_center_m` (rail) | `999` | yes, to NA (2026-09-23) |
| `height_m` (road) | `0` (62% of records) | **no**: treat `0` as missing |
| `height_above_rail_top_m` (rail) | `999` (16% of records); also `0` (5%) | **no**: treat both as missing |

One road record has `height_m = 102.9` (an earth berm built 2020), an entry
error; the next highest is 11.6 m.

## Coverage of the attributes the design needs (checked 2026-11-02)

Records, not walls. The empirical strategy
(now [`prespec-cohort-exposure.tex`](../../../lines/sweden-residents/prespec-cohort-exposure.tex)) needs, per
wall, a construction year (for the event time) and, for its intensity
tests, the wall's height and its distance from the road.

| | road | rail |
|---|---|---|
| records | 2,172 | 1,829 |
| total length | 251 km | 275 km |
| `built_year` present | 49% (52% of length) | 73% (68% of length) |
| height present (neither `0` nor `999`) | 38% | 79% |
| distance from road / track present | none (geometry on the centreline) | 44% |
| dated records built 2015 or later | 71% | 54% |
| records built 2007 or earlier | 140 | 414 |
| ... of those with a height | **2** | 323 |

**The 2006 batch.** 1,092 road records have `valid_from` in 2006 (1,064 of them
exactly 2006-01-01, the date the register started, inferred: Lastkajen's
specification says the first load was a conversion from the old regional
databases and gives coverage "from 2015-01-01"). 978 of them have neither a construction year
nor a height, and no record in the batch has a height. Records added
later usually have `valid_from` within a year of `built_year` (median
difference 0, upper quartile 1 year). So the road walls without a year or height are mostly those already
standing when the register started: built in 2006 or earlier, but we do
not know when.

**Why this matters for the design.** A wall contributes a full event window
(placebo cohorts, the ramp and the plateau) only if it was built at least
17 years before the last year of grade data, which means 2007 or earlier
for grades through 2024. Those are exactly the walls where the road
register is thinnest:
- the event study on full windows rests mostly on rail walls and on the
  few old road walls with a year;
- a dB intensity measure is feasible for rail (heights for 323 of 414 old
  records), but not for old road walls (2 of 140).

Rail heights are measured above the top of the rail; road heights are
presumably above the ground or the carriageway (not documented).

## Dating the undated walls: leads and dead ends (checked 2026-11-19)

Records without a year: road 1,114 (978 of them in the 2006 batch), rail 487 (451 read
`<20190405`). Scripts: [`scripts/checks/2026-11-lastkajen/`](../../../../scripts/checks/2026-11-lastkajen/README.md).
These are data checks, not pre-specified analysis steps; nothing here enters an estimate before a
pre-spec entry (`AGENTS.md`).

| Candidate | Result | Verdict |
|---|---|---|
| **Rail `bis_object_number` (`Bisobjektnr`)** | Rank correlation with `built_year` among the 1,342 dated rail records is **0.85**. Leave-one-object-out, the true year lies between the neighbouring objects' years 93% of the time (median bracket width 0 years). For the 487 undated rail records the neighbours bracket the year within 2 years for 309 (63%) and within 5 years for 394 (81%). No dated record shares a number with an undated one. The numbers are not monotone across deciles (lowest decile 1994 to 2016), so the link is local. | **Lead.** Needs a check that numeric neighbours are not only spatial neighbours, an out-of-sample test on the 451 `<20190405` records, and a pre-spec entry. Ask Trafikverket whether BIS numbers objects in order of registration. |
| Rail `connection_date` (`Inkopplingsdatum`) | 1,291 records `<20190405` (BIS's first-load date), 538 real dates 2019 to 2026. Of 502 real-date records with a `built_year`: same year 281 (56%), one year later 120 (24%), two or more later 94 (19%), earlier 7. 23 real-date records were built before 2019; 5 `<20190405` records have `built_year` 2019 or later. | **A connection date, not a construction date**: it trails construction by 0 to 1 years for most. Dates only the 36 undated records that carry a real date. |
| Road `valid_from` | For the 1,014 records with `valid_from` in 2015 or later, 87% have a `built_year`, and the registration year equals it for 67% and is one year later for 25%. The 1,158 records from before 2015 have no height, and 85% no year. | **A build-year proxy for registrations since 2015**; nothing for the 2006 batch. |
| Earlier-date snapshots (2015, 2019, 2022) | `Höjd` and `Byggår` changed on none of the 1,157 segments shared with July 2026. | **No help**: attributes of a record never change; newer records are simply better registered. See [`../lastkajen-unused-products.md`](../lastkajen-unused-products.md) §4. |
| Vägombyggnad (rebuild year) | 501 road barriers (23%) lie on a rebuilt stretch; of the dated ones `Byggår` equals the rebuild year in 217 of 307. 45 undated 2006-batch walls have a rebuild year 2000 to 2006. | **Small lead**: about 4% of the 2006 batch, with a bracket of at most six years. |
| Vägnybyggnad (new-road year) | Roads under the undated 2006-batch walls are mostly older than 1999. | **Dead end** for the 2006 batch. |
| Rail `inspection_class`, `drawing_number`; road `material_type`, `on_bridge`, `owner` | Rail `inspection_class` has the same distribution for dated and undated records. No undated rail record has a `drawing_number` (166 records have one). Road `material_type` is known for 89% of undated and 98% of dated records; `on_bridge` is unknown for 91% of undated and 16% of dated records, `owner` for 95% and 12%. (Rail `barrier_type`, road `absorbent` and `foundation_type` were not compared.) | **Dead end**: the unknowns mark the legacy stock, they are not dates. |
| Rail `kilometer_from` | Position along the track, not parsed. | Not a date. |

Row 1 and the 2015 to 2022 snapshots are also the basis for the answers in
[`../../../../output/presentations/2026-11-trafikverket/prep/02-local-data-check-report.md`](../../../../output/presentations/2026-11-trafikverket/prep/02-local-data-check-report.md).

## Open questions

For Trafikverket, discussed at a call on 2026-11-25 with their noise and vibration
coordination (slides:
[`2026-11-trafikverket/`](../../../../output/presentations/2026-11-trafikverket/trafikverket-meeting.pdf)).
The register's construction years and heights may change with their reply, so every count on
this page, and the barrier counts in the line documents, are provisional until then.

Barriers and construction:

1. Do older registers or project archives hold construction years for the
   undated walls: the road walls loaded in 2006 (978 of 1,114 undated; also
   their heights) and the rail walls whose `connection_date` reads only
   "<20190405" (451 of 487 undated)? For `sweden-residents` the rail years
   add most to the short window, the road years to the full window
   ([`prespec-cohort-exposure.tex`](../../../lines/sweden-residents/prespec-cohort-exposure.tex),
   power section).
2. Is `built_year` the year a wall was completed, and does rebuilding a
   wall overwrite it with the new year?
3. Are removed walls recorded anywhere? Our July exports list only current
   records (every `VALID_TO` is 9999-12-31, checked 2026-11-18), **but an
   earlier `Betraktelsedatum` on Lastkajen returns older road versions**
   (2015: 1,277 records, 124 closed later; 36 of 1,118 `ELEMENT_ID` seen in
   any snapshot are absent from July; found 2026-11-19, see
   [`../lastkajen-unused-products.md`](../lastkajen-unused-products.md) §4).
   Still open: are removals before 2015 kept (the specification's coverage
   starts 2015-01-01), what happened to the 36 dropped `ELEMENT_ID` (a
   removed wall or a retired road element), and is the same available for
   rail (flagged "no history", not tested)?
4. Is the exact position of each wall available (the side of the road, the
   distance from it), beyond the centreline geometry? For road, is the "real
   geometry" that the discontinued `Verklig geometri` attributes pointed to
   still held (in STVDB)? For rail, `Avstånd_fr_spårmitt` is recorded for 44%
   of records; is it available for the rest?
5. Is there any source of start or announcement dates for the road projects
   that came with the walls? The traffic-information API keeps finished
   roadworks for only about a year ([`../covariates.md`](../covariates.md),
   Cluster D). Lastkajen's Vägombyggnad and Vägnybyggnad give completion
   years and an `Objekt nr` (filled for about 20% of records; 810 of our
   2,172 road barriers lie on a record with one): is there a project register
   with start or decision dates behind that number, and one for rail?
6. Construction years for specific walls: road row 1166 (kommun 1880,
   Örebro) and rail row 551 (kommun 1293, Hässleholm), the two 2001 walls
   that carry the school-level headline, and the undated walls beside the
   58 treated schools dropped for lack of a year
   ([`prespec-construction-years.md`](../../../lines/sweden-schools/prespec-construction-years.md)).
7. Are walls that were planned or proposed but never built recorded anywhere?

Facade measures and context:

8. Is the register of properties considered for noise mitigation (façade
   insulation; the data of Lindgren 2021, "A sound investment?") available to
   researchers: measure carried out, type, year, cost, and the SCB 100 m cell
   (enough; exact positions are not needed)? Who holds it today? Lastkajen's
   road barrier description says window measures (*fönsteråtgärder*) are held
   in the national noise database (*nationella bullerdatabasen*): is that the
   register, and can it be shared?
9. Are noise levels calculated for a property or a wall, before and after the
   measure, kept (in the measure's documentation or the strategic noise maps)?
   Lastkajen has the strategic noise maps for **2016 only** (Inspire Noise,
   road and rail, Lden and Lnight, covering about half of our barriers; see
   [`../lastkajen-unused-products.md`](../lastkajen-unused-products.md) §3):
   do maps for other years exist, and are existing walls in the 2016 model?
10. Train counts before the walls were built, and road ÅDT for years or
    segments NVDB's history does not cover (our traffic panel matches about
    30–40% of school-years, 1998–2019; [`traffic`](../traffic/README.md)):
    which years exist? We hold no train counts: `timetable` is a one-night
    sample (2026-06-25 to 26) of train announcements.
11. The rules over time: which noise levels qualified a property or a stretch
    for a measure, and since when?
12. Access: the format, the terms, and whether each source needs a data use
    agreement.

Added 2026-11-19 (not yet on the slides):

13. Rail: is the BIS object number (`Bisobjektnr`) assigned in order of
    registration, and is registration close to construction? Among dated rail
    walls it follows the build year closely (rank correlation 0.85; see "Dating
    the undated walls").
14. Rail `Inkopplingsdatum`: does it mean the date the object was connected in
    BIS? It trails the build year by 0 to 1 years for most records, and
    `<20190405` is BIS's first load.
15. Is 2006-01-01 the conversion date of the first road load, and why does the
    specification give coverage "from 2015-01-01"?
