---
type: note
state: current
updated: 2026-11-19
summary: "Lastkajen products that bear on the barrier design, downloaded and inspected but not in the pipeline: Vägombyggnad, Vägnybyggnad, Inspire Noise (2016), and the earlier-date barrier snapshots"
---

# Lastkajen products we have not used

**Purpose.** A record of what Lastkajen offers beyond the sources in this folder, found on
2026-11-19 while preparing the call with Trafikverket (25 November). Nothing here is in the
pipeline yet; each entry says what it holds, what we would use it for, and how to get it. Facts
are from Lastkajen's own catalogue pages and the road barrier specification, read in a browser
session; the full report with URLs is
[`01-lastkajen-catalogue-report.md`](../../../output/presentations/2026-11-trafikverket/prep/01-lastkajen-catalogue-report.md).
"Inferred" marks anything not written on a Lastkajen page.

What we already use from Lastkajen: `noise_barriers` (Bullerskydd - väg, ID 63; Bullerskydd, rail,
ID 10006), `road_network`, `traffic`. IDs are the ones in the catalogue URLs
(`/aboutdataroad/100002/<id>`, `/aboutdatarailway/100201/<id>`), not the "630" and "991" used
earlier.

## 1. Vägombyggnad (road rebuilds), ID 96, downloaded 2026-11-19

- **Holds:** the year a rebuild was completed (`Ombyggnadsår`); the kind of rebuild
  (`Vägkroppsåtgärd`: change to the road body along a stretch, not point measures; `Breddning`:
  widening enough to add a lane; `Ombyggnad till mötesfri`: conversion to 1+1 or 2+1);
  **`Väsentlig ombyggnad`**: a classification of a stretch that brings a substantial increase in
  noise or vibration, defined as physical changes to the road since 1997 that substantially and
  permanently change it, or measures that allow traffic changes; the source type (`Ursprung`);
  the project's object number (`Objekt nr`), name (`Objektnamn`) and archive reference
  (`ID i fysiskt arkiv`).
- **Coverage:** state car, cycle and foot network, plus municipal or private roads that are part of
  a state rebuild project. Segments on the linear road element; overlapping objects allowed
  (`Samtidig` = Ja). History: **Historik = Ja**.
- **Use for us:** the road works that come with a wall (Cluster D in
  [`covariates.md`](covariates.md)) as a dated covariate, which the `Situation` API could not
  supply (its retention is about a year). A project number and name to join walls to the road
  project behind them. `Väsentlig ombyggnad` is the road authority's own noise-relevant rebuild
  flag.
- **Limits:** years only, no start or announcement date; completeness before registration is not
  stated; how `Objekt nr` links to Trafikverket's project register is not stated.
- **Downloaded** (order 121412, Sweden, GeoPackage, EPSG:3006, reference date today, with
  Vägnybyggnad in one file): `data/sweden/road_projects/raw/order_121412/`, layer
  `VIS_DK_O_96_Vagombyggnad`, 7,457 records on 6,191 road elements, 20,831 km, EPSG:3006,
  `ELEMENT_ID` and `START/END_MEASURE` on the same NVDB links as the barrier file.
- **What is in it** (checked 2026-11-19): `Ombyggnadsår` 1951 to 2025 (6 records read 9999);
  by decade 1950s 192, 60s 980, 70s 1,423, 80s 723, 90s 792, 2000s 1,483, 2010s 784, 2020s
  1,074. **`Väsentlig ombyggnad` is `Okänt` for 7,101 of 7,457 records** (Nej 335, Ja 21), so the
  noise-relevant flag is nearly empty; `Vägkroppsåtgärd`, `Breddning` and `Ombyggnad till
  mötesfri` are mostly `Okänt` too (`Ombyggnad till mötesfri`: Ja 1,480). `Objekt nr` is filled
  for 19% of records, `Objektnamn` for 12% (175 distinct names), the archive reference for 0%.
  `Ursprung`: 6,541 "taken from an existing road database 2022", 892 "relation or construction
  document", 24 unknown.
- **History:** `VALID_FROM` is 2023 for 6,713 records (the bulk load from the 2022 database) and
  2021 to 2026 for the rest; every `VALID_TO` is 9999-12-31. An earlier reference date probably
  returns little before 2021 (inferred; not ordered).
- **Against the barriers** (same `ELEMENT_ID` and overlapping measure; 2,172 road records):
  **501 (23%)** lie on a rebuilt stretch. Of the 307 of those with a build year, `Byggår` equals
  the rebuild year for 217 of the single-year cases, and is within one year for 81%. So walls
  are built with road rebuilds. 194 undated barriers (137 from the 2006 batch) lie on a rebuilt
  stretch; for 45 of the 2006 batch the rebuild year is 2000 to 2006, a bracket of at most six
  years, 23 of them at most three. 24 of the 137 have a rebuild year after 2006, which
  contradicts "built by 2006". No barrier lies on a `Väsentlig ombyggnad = Ja` stretch.
  Records with an `Objekt nr` overlap 124 barriers.

## 2. Vägnybyggnad (new roads), ID 97, downloaded 2026-11-19

- **Holds:** `Nybyggnadsår`, the year the road structure in its present alignment was completed
  (9999 = unknown); `Ursprung` (type of source of the year); `Objekt nr`, `Objektnamn`, and
  `ID i fysiskt arkiv` as above.
- **Coverage:** all state roads (car, cycle, foot), and sections built as state roads that have
  since passed to a municipality or private keeper. Historik = Ja, Sidoläge = Nej.
- **Use for us:** the year a road was built, for walls built with a new road, and a project name.
  Roads rebuilt in place are in Vägombyggnad, not here.
- **Downloaded** with Vägombyggnad (same order): layer `VIS_DK_O_97_Vagnybyggnad`, 83,475 records
  on 77,532 road elements, 114,788 km.
- **What is in it:** `Nybyggnadsår` is 9999 (unknown) for 38,608 records (46%); known years by
  decade 1950s 1,909, 60s 4,978, 70s 5,345, 80s 3,423, 90s 4,017, 2000s 8,043, 2010s 11,474,
  2020s 5,678 (59% of the known are 1996 or later). `Objekt nr` is filled for 22% of records,
  `Objektnamn` for 4% (293 names), the archive reference for 0%. `VALID_FROM` is 2023 for 78,984
  records.
- **Against the barriers:** 2,152 of 2,172 road barriers (99%) lie on a new-build record, 1,760
  (81%) with a known year. Of the 902 dated barriers with a year, `Byggår` equals the road's year
  for 493 (55%) and is six or more years later for 289 (a wall added to an existing road). For
  the undated barriers the road is mostly old (727 of the 769 undated 2006-batch barriers with a
  road year are on roads built in 1999 or earlier), so it gives no useful bracket: only 19
  within three years of 2006. Records with an `Objekt nr` overlap 699 barriers; with the
  rebuild records, 810 barriers (37%) have a project number.

## 3. Inspire "Noise" ready package, ID 10088, downloaded 2026-11-19

- **Where:** *Färdiga datapaket* → 4. Inspire → HH - Human health and safety → Noise
  (`/productpackages/10088`). A ready package, no order needed.
- **Holds:** six GeoPackage zips, `Hh_noise_{air,rail,road}_{lden,lnight}_gpkg.zip`; files dated
  2024-09-04; sizes air 0.1 MB, rail 24 MB and 23 MB, road 78 MB and 65 MB.
- **Inferred:** the European noise-mapping format (Lden and Lnight, day-evening-night and night
  levels); the data are the strategic noise maps. No description page was read, so the
  reference year, the modelled area (agglomerations and major roads and railways only?), the
  data model and whether earlier mapping rounds exist are open.
- **Use for us:** a calculated noise level at the address, a first answer to the question of
  levels before and after a measure (question 9 on the slides), if the maps predate and follow the
  walls. One vintage in the package, so on its own no before and after.
- **Downloaded** to `data/sweden/inspire_noise/raw/<air|rail|road>_<lden|lnight>/` (six zips,
  unpacked; 0.2 to 187 MB per GeoPackage). **What is in it** (checked 2026-11-19): one layer
  per file, EPSG:3006, dB-contour polygons (mostly MultiPolygon) with `measure` = the dB level,
  `type` = noise, `namespace` SE-TRV, `location` = a GML point per feature. **Reference year
  2016** (`beginMeasureTime` 2016-01-01 to `endMeasureTime` 2016-12-31), `validFrom`
  2017-01-01, record version 2024-09-04: the maps are for 2016 only, so for walls built after
  2016 they show the state before, and for earlier walls the state after. Levels: road and rail
  Lden 50 to 75 dB (road 1,095 polygons, rail 454), Lnight 45 to 70 dB (road 1,070, rail 447);
  air 18 and 19 polygons (Lden 55 to 75, Lnight 50 to 70). Total polygon area by Lden band,
  road: 50 dB 2,370 km², 55 dB 1,384, 60 dB 762, 65 dB 415, 70 dB 226, 75 dB 202; rail 993 /
  681 / 394 / 199 / 94 / 63 (whether the bands are nested or exclusive is not stated). 12 road
  and 8 rail Lden polygons are invalid geometries.
- **Coverage against our data:** **60% of road barriers (1,300 of 2,172) lie inside a road Lden
  contour of 50 dB or more, 53% at 65 dB or more; 54% of rail barriers (985 of 1,829) inside a rail
  contour, 49% at 65 dB.** 1,055 of the 10,531 schools with coordinates lie inside a road or rail
  Lden contour of 55 dB or more, 111 at 65 dB or more. So the maps cover about half the barriers,
  the mapped areas (inferred: agglomerations and the major roads and railways), not all.

## 4. Barrier snapshots at earlier reference dates, ordered, not processed

Orders "Sound Barriers - Road 150101 / 190101 / 220101" (Bullerskydd - väg, Sweden, GeoPackage,
EPSG:3006, reference dates 2015-01-01, 2019-01-01, 2022-01-01) were placed on 2026-11-19 and
downloaded to `data/sweden/noise_barriers/raw/road_ref_<date>/` (git-ignored; each folder holds
the zip, the GeoPackage and its receipt). The loader reads only the top level of `raw/`, so they
do not touch `preprocess`.

- **What they show** (compared with the July 2026 road file; the numbers are in the prompt 1 report,
  section 6): the road register keeps versions. Records 1,277 / 1,563 / 1,869 / 2,172
  (2015 / 2019 / 2022 / July 2026); closed records (`VALID_TO` before 9999-12-31) 124 / 74 / 43 /
  0; 36 of 1,118 `ELEMENT_ID` seen in any snapshot are absent from July. `Höjd` and `Byggår` did
  not change on any of the 1,157 segments shared by 2015 and July. Heights are unknown in every
  2015 record.
- **Use:** barriers that were later removed or replaced (about 3% of elements), and an upper bound
  on when an undated barrier existed (present on a date means built by then).
- **Not done:** the snapshots are not in the pipeline, the rail product (Historik = Nej) was not
  tested, and the spec gives temporal coverage "from 2015-01-01" while `VALID_FROM` runs from
  2006-01-01 (an earlier date was not ordered).

## 5. Looked at, not relevant

| Product | Why not |
|---|---|
| Barriärkartor (ready package, folder 3) | Wildlife barrier maps for larger mammals |
| Sverigefiler utvalda NVDB-data | Function class, speed limit, surface, width, road keeper, network; no noise content |
| Sverigepaket Drift och underhåll (ready package) | A national package of maintenance data; contents not opened (inferred: the barrier layer we already have) |
| Trafikeringssystem (rail, ID 32) | A track classification (E1 to S), not train counts |
| Miljözon, Konstruktion, Bro och tunnel | Traffic rule, bridge and tunnel data |

## 6. Not on Lastkajen

Facade or window measures (the road barrier description says window measures are held in the
national noise database, *nationella bullerdatabasen*, which is not a Lastkajen product), train
counts, project start or announcement dates, calculated noise before and after a measure. These
are questions 8 to 11 for Trafikverket.

## 7. How to order a road product

1. Lastkajen → *Skapa egen beställning* → *Väg* (`/orderdata/vag`). Wait for the page to finish
   loading before clicking; the list loads slowly.
2. Switch the product list to *Bokstavsordning*, tick the product (the filter box found nothing
   for "Bullerskydd"; scroll the list).
3. Select the area: click *Sverige*, then click the highlighted map area (the button alone only
   draws the outline).
4. *Nästa*. Name the order, set the reference date (*Betraktelsedatum*, `yyyy-mm-dd`; empty
   means the order day), format *Geopackage*, *EPSG:3006*.
5. *Hantera* → *Spara och skicka*. The order runs in about 20 seconds; the file is under *Mina
   beställningar* → the order → *Visa* → the file name. Lastkajen limits saved orders to 10 in its
   help text, but the eleventh to thirteenth were accepted.

## Open questions

1. Is Vägombyggnad's `Objekt nr` (filled for 19% of rebuilds, 22% of new builds) the key to a
   project register with start or decision dates, and is there a rail equivalent?
2. The Inspire Noise maps are for 2016 and cover about half the barriers: do maps for other
   years (earlier mapping rounds) exist, and how was the 2016 model built (are existing barriers
   in it)?
3. Does the barrier snapshot's temporal coverage start in 2015 or 2006, and are barriers removed
   before 2015 kept?
