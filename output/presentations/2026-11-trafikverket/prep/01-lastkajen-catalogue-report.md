# Lastkajen catalogue report

Run on 2026-11-19 in Claude in Chrome, logged in as the user, read only: nothing ordered, saved,
downloaded or changed. Swedish pages were read in Swedish and are reported in English. "Inferred"
marks anything not written on a page.

## 1. Answers, points 1-7

| # | Point | Verdict | Where / what |
|---|---|---|---|
| 1 | Construction year | **Partly available** | Both barrier products have `Byggår`. Road: "year of construction; unknown is set as 1900" (`/aboutdataroad/100002/63`). The road spec lists `Byggår` as mandatory with a 0% tolerance for missing values, which is not what your 50% missing suggests (see section 2). Separate road products give the build or rebuild year of the *road section*, not the barrier: **Vägnybyggnad** (ID 97) and **Vägombyggnad** (ID 96). No other source of barrier build years found. |
| 2 | Side, offset from road, height | **Partly available** | Road: side exists (`Sidoläge`, Right/Left). No offset or distance attribute in the road product. Height: `Höjd`, 0 means unknown. The spec says the geometry is the road reference line (linear segment); the product once carried a link to a "real geometry" elsewhere (`Verklig geometri ID/dimension/längd`, discontinued 2021-11-02). Rail: has `Avstånd_fr_spårmitt_m` (distance from track centre) and `Höjd_över_rök_m`, but the catalogue gives no definitions for them. |
| 3 | Removed barriers / history | **Available for road, by reference date (tested)** | Road product catalogue header: **Historik = Ja**. Rail product: **Historik = Nej** (rail not tested). The road spec gives temporal coverage "from 2015-01-01". The docs do not say how far back a reference date reaches, so I ordered one: with reference date 2015-01-01 the road product returns the state of the register on that day, **including 124 records with a `VALID_TO` before 9999-12-31** (barriers later changed or removed). See section 6. |
| 4 | Facade / window insulation | **Not available** | Not found in the road list, the rail tree or the ready packages (searched *buller* in ready packages; *fasad* and *åtgärd* in rail). The road product description itself says it does not contain "surrounding data such as window measures (*fönsteråtgärder*), which are stored in the national noise database (*den nationella bullerdatabasen*)". That database is a lead for Trafikverket, not on Lastkajen. |
| 5 | Project start / announcement dates | **Partly available** | **Vägombyggnad** (ID 96) has `Ombyggnadsår` (completion year), `Objekt nr`, `Objektnamn` (project name), `ID i fysiskt arkiv` (archive reference) and a flag `Väsentlig ombyggnad` (substantial rebuild since 1997 that significantly increases noise or vibration). **Vägnybyggnad** (ID 97) has the same project fields for new roads. Years only; no start or announcement date. Rail: nothing found (searched *projekt*, *åtgärd*, *objekt*). |
| 6 | Train counts | **Not available** | Rail catalogue searched with *tåg*, *trafik*, *objekt* (full tree). Closest hit is **Trafikeringssystem** (ID 32), a track classification (E1, E2, E3, F, H, M, R, S), not counts. |
| 7 | Calculated noise levels | **Partly available** | Ready package **Inspire → HH → Noise** (`/productpackages/10088`): six GeoPackages, `Hh_noise_{air,rail,road}_{lden,lnight}_gpkg.zip`, files dated 2024-09-04 (air 0.1 MB, rail 24 MB and 23 MB, road 78 MB and 65 MB). Inspire "Noise" with Lden/Lnight is the EU noise-mapping format (inferred; I did not open the files or any description). One vintage only; no before/after for a measure. |

## 2. Our two products

### Bullerskydd - väg (road)

- **ID: 63** (not 630). URL `/aboutdataroad/100002/63`; your layer `VIS_DK_O_63_...` agrees. The data product
  specification is a separate PDF numbered 1051 (`.../DPS_A-B/1051Bullerskydd - väg.pdf`), version 6.0, 2021-11-02, 15 pages.
- **Description:** a device along the road built to dampen traffic noise. Holds location and properties of each barrier.
  Excludes naturally occurring or non-noise-purpose objects and surrounding data such as window measures (held in the
  national noise database).
- **Purpose in the spec:** locate barriers for operation and maintenance (*drift och underhåll*). Open data, CC0.
- **Scope:** state road network (car network); also municipal or private owners in rare cases. A barrier is registered if
  Trafikverket is or was responsible for it, and linked to the nearest state road first.
- **Catalogue header:** Historik Ja, Sidoläge Ja, Riktning Nej, Samtidig Nej, Ordnade nätreferenser Nej, extent type
  "segment on linear element".
- **Data source (spec §8):** initial load by conversion from RFT (the old regional enterprise databases), which had only been
  kept up to date for some of the former Vägverket regions. Barriers are since registered successively through inventories
  in the operations and maintenance handover process, so the product is fully loaded only after a whole procurement cycle
  (5-7 years). Updating is continuous.
- **Field definitions found:**
  - `Byggår`: "build year; unknown set as 1900". The page does not say "year of completion" and does not say whether a
    rebuild overwrites it. Spec: mandatory, 0% tolerance for gaps, 2% for classification errors.
  - `Höjd`: average height from lower edge to upper edge, metres with one decimal. For earth embankments (*jordvall*) the
    road-surface edge is the lower reference. If height varies a lot the barrier is split into several objects. **0 = unknown
    or missing.** Spec: mandatory, 0% tolerance for gaps.
  - `Sidoläge` (your `SIDE`): valid values Right or Left. A barrier is described side-divided with extent along the road.
    Spec: mandatory. The page does not state the reference direction; right/left of the reference line is inferred.
  - `Absorbent`, `Grundläggningstyp` (earth anchor / concrete wall / separate foundations), `Materialtyp` (main material
    if mixed), `På bro` (on bridge incl. pipe bridges over 2 m; barriers spanning bridge and ground are split), `Ägare`,
    `Skötselansvarig`, `Skötselanvisning`.
  - Discontinued 2021-11-02: `Verklig geometri ID` (links the object to the real geometry stored elsewhere, in STVDB),
    `Verklig geometri dimension` (2D/3D), `Verklig geometri längd`.
  - `VALID_FROM`, `VALID_TO`, `START_MEASURE`, `END_MEASURE`, `EXTENT_LENGTH`: **not found** in the catalogue or spec;
    they are delivery fields.
- **Reference date / history:** Historik = Ja. Reference date is chosen at order step 3 and defaults to today; your
  "Sound Barriers - Road" and "- Rail" orders have an **empty** reference date column in *Mina beställningar*, so both
  were taken as of order day (2026-07-06 / 07-07). Your Traffic orders went from 1999-01-01 to 2026-09-16. The spec's
  temporal coverage starts 2015-01-01.
- **Relation to NVDB:** the spec carries the NVDB seal and is a road data product (*Vägdataprodukter*), and the delivery
  reference is the Swedish road network; it also mentions STVDB (state road database) for real geometry and updates. I did
  not check which order-tree category it sits in.
- **Formats offered (spec §11):** File geodatabase, Shape, GeoPackage, MID/MIF, OpenTNF, SS-XML; Lastkajen API. No format
  carries more attributes.
- **Docs:** https://bransch.trafikverket.se/TrvSeFiler/Dataproduktspecifikationer/V%C3%A4gdataprodukter/DPS_A-B/1051Bullerskydd%20-%20v%C3%A4g.pdf
  and the catalogue page above.

### Bullerskydd (rail)

- **ID: 10006** (not 991). URL `/aboutdatarailway/100201/10006`; your layer `BIS_DK_O_10006_...` agrees. Listed under
  Trafikverkets data på statlig järnväg (StJDB) → Fysiska objekt.
- **Description:** "a device intended to reduce noise from the infrastructure".
- **Catalogue header:** Historik **Nej**, Sidoläge Ja, Riktning Nej, Heltäckande Nej, Samtidig Nej, segment on linear element.
- **Attributes (all marked mandatory):** Kmtal, Kmtalti, Typ, Absorbent, Grundläggningstyp, Not om grundläggning,
  Avstånd fr spårmitt (m), Höjd över rök (m), Byggår, Typritningsnr, Ägare, Underhållsansvarig, Underhållsinstruktion,
  sida (h,v,b), BisObjektNr, BisObjektTypNr, Besiktningsklass, Inkopplingsdatum. **No definitions are given** (the
  description column is empty), so `Byggår`, `Inkopplingsdatum`, `Avstånd_fr_spårmitt_m` and `Sida_h_v_b` are not defined on
  Lastkajen. No separate data product specification found for rail.
- **BIS relation:** layer prefix `BIS_` and the attribute `BisObjektNr` suggest the source is BIS (inferred); the page does
  not name it.

## 3. Other relevant products

| Name | ID | What it holds | Coverage | History | URL |
|---|---|---|---|---|---|
| Vägombyggnad | 96 | Year of rebuild (road body measure, widening, conversion to 2+1/1+1), `Väsentlig ombyggnad` flag, project object nr/name, archive ID | State car/cycle/foot network; municipal/private roads in a state rebuild project | Ja | `/aboutdataroad/100002/96` |
| Vägnybyggnad | 97 | Year a new road section was completed (9999 = unknown), source type, object nr, project name, archive ID | State network; also sections since transferred to municipal/private | Ja | `/aboutdataroad/100002/97` |
| Trafik (ÅDT) | not read | Average traffic flow by vehicle class and interval, with quality measures | Already held by you | not checked | `aboutdata` list |
| Inspire Noise (ready package) | 10088 | Lden and Lnight GeoPackages for road, rail, air | Files dated 2024-09-04; geography and year not stated | Single vintage | `/productpackages/10088` |
| Trafikeringssystem (rail) | 32 | Which of the 8 TTJ traffic systems applies to a track section | Rail network | Nej | `/aboutdatarailway/100201/32` |
| Sverigepaket Drift Och Underhåll (ready package) | n/a | Two files: GeoPackage 704 MB, file geodatabase 660 MB; dated 2026-10-31 | Sweden | Latest snapshot only | `/productpackages/10085` |

Checked and not relevant: Barriärkartor (wildlife barrier maps for larger mammals, 2024), Sverigefiler utvalda NVDB-data
(function class, speed limit, surface, width, road keeper, road network), Miljözon, Konstruktion, Bro och tunnel.

## 4. What we could order ourselves, and what stays a question

**Orderable now (no question needed):**
- Vägombyggnad and Vägnybyggnad, Sweden-wide, GeoPackage: completion years and project names/numbers for road projects
  (a basis for matching wall years to projects; not start dates).
- "Bullerskydd - väg" with further reference dates (done for 2015-01-01, section 6; for example 2019-01-01 and 2022-01-01
  would show removals in between). Each order takes about 20 seconds.
- The Inspire Noise package (needs a go-ahead to download): END noise maps for road/rail, one vintage.

**Questions for Trafikverket:**
1. Real geometry and offset: where are the "real geometries" that `Verklig geometri ID` pointed to, and can we get barrier
   position or distance from the road? (Point 2.)
2. `Byggår`: what exactly does it record (completion, registration, rebuild), why is half of it missing although the spec
   says 0% tolerance, and is 1900 used as the unknown code in our file?
3. Whether `VALID_FROM` is the registration/edit date (it looks so, section 6), and whether removals before 2015 are
   kept (the spec's temporal coverage starts 2015-01-01). Reference-date history itself works for road.
4. The national noise database (*nationella bullerdatabasen*): does it hold facade and window measures per property, and
   calculated levels before and after? (Points 4, 7.)
5. Project start or decision dates for the object numbers in Vägombyggnad/Vägnybyggnad, and whether `Objekt nr` joins to a
   project or investment register.
6. Rail: definitions of `Byggår`, `Inkopplingsdatum`, `Avstånd_fr_spårmitt_m`, `Sida_h_v_b`; rail history (Historik Nej).
7. Train counts before the barriers (point 6): not on Lastkajen.

## 5. Where I looked, and what I could not open

- **Looked:** home page; ready packages (all four top folders, search *buller*, folders Väg, Järnväg,
  Trafikslagsövergripande, Inspire → Noise, Sverigefiler utvalda NVDB-data, Drift och underhåll, Barriärkartor); *Läs om
  våra vägdata* (all 132 products loaded; descriptions read for Bullerskydd - väg, Vägnybyggnad, Vägombyggnad, Trafik,
  Konstruktion, Miljözon, Referenslinjetillkomst, Bro och tunnel, Slitlager; the keyword scan over all descriptions was
  cut off, so a product I did not name may be missing); *Läs om våra järnvägsdata* (full tree under *objekt*; searches
  *buller, tåg, trafik, åtgärd, projekt, fasad*); the road order wizard's alphabetical product list and its help dialog;
  *Mina beställningar*; the road spec PDF (read page by page: pages 3, 5-14).
- **Not found:** train counts, facade/window records, project start dates, any history option beyond the Historik flag, a
  Lastkajen FAQ page beyond the order-wizard help dialog.
- **Not opened:** the "Om Färdiga datapaket" panel (it would not expand), the API page and the Lastkajen API PDF,
  Länsfiler NVDB-data, Vägdata för transportplanering, spec pages 1-2, 4, 15, any rail data product specification, the
  other road products' specifications. Search terms I did not run in the rail search box: *bullerkartläggning,
  bullerberäkning, ljudnivå, entreprenad, byggstart, tågräkning, bandata, historik*; road products were checked by reading
  the full alphabetical name list instead.
- Tooltips in the order wizard were unreliable, so I used the "Läs om" catalogue pages for descriptions.

## 6. Test order placed (point 3), after the catalogue run

On the user's go-ahead on 2026-11-19 I placed one order: **"Sound Barriers - Road 150101"** (order id 121409),
product Bullerskydd - väg only, all of Sweden, GeoPackage, EPSG:3006, reference date **2015-01-01**, no reference
network. Status **Klar** at 17:29:03 (run time 17 s). The 10-saved-orders limit mentioned in the wizard help did not
block it (11 orders are now listed). Downloaded (zip 227,699 bytes) with the user's go-ahead and unpacked to
`data/sweden/noise_barriers/raw/road_ref_2015-01-01/` (git-ignored). Compared with the July road file (order 447607,
2,172 records; held as `railway_noise_barriers.gpkg`, see the naming note below). Same layer and fields.

| | Reference date 2015-01-01 | July 2026 (as of order day) |
|---|---|---|
| Records / distinct `ELEMENT_ID` | 1,277 / 680 | 2,172 / 1,082 |
| `VALID_TO` | 124 records closed (2015-2026), 1,153 open | all 9999-12-31 |
| `VALID_FROM` | 2006-01-01 to 2014-10-17 (1,206 on 2006-01-01) | 2006-01-01 to 2026-04-13 (1,092 on 2006-01-01) |
| `Byggår` = 1900 (unknown) | 1,099 (86%) | 1,114 (51%) |
| `Höjd` = 0 (unknown) | 1,277 (**100%**) | 1,351 (62%) |
| Total length | 141.3 km (10.5 km closed) | not computed |

What it shows (my reading; not confirmed by Trafikverket):
- **A reference date returns history.** The 124 closed records are barriers valid on 2015-01-01 that were later changed or
  removed; 62 of them have an `ELEMENT_ID` that no longer exists in the July file, so the July file alone misses them.
  The other closed records share an `ELEMENT_ID` with a current record but not the same segment (re-segmented or edited).
- **The register keeps versions, so `VALID_FROM` is a registration or edit date, not a construction date.** 1,092 of the
  2,172 July records still carry 2006-01-01, and 1,015 July records are not in the 2015 snapshot.
- **Attributes of existing records do not get filled in later (corrected after the 2019/2022 snapshots).** Across the 1,157
  segments shared by the 2015 and July files, `Höjd` and `Byggår` changed in **none**. The share of unknowns falls only
  because newer records are better registered (table below). A snapshot cannot recover a missing `Byggår`, but it gives an
  upper bound on when an undated barrier existed (present on 2015-01-01 means built by then).
- The 2015 date is the spec's coverage start. Earlier dates were not tested. `VALID_FROM` starts at 2006-01-01, so a date
  before 2015 can add little beyond the ~80 records with `VALID_FROM` 2008-2014; later dates (for example 2019-01-01,
  as for your Traffic orders) would show removals between 2015 and today.
- **Two more snapshots** ordered the same way (same product, Sweden, GeoPackage, EPSG:3006): "Sound Barriers - Road 190101"
  (reference date 2019-01-01, order 121410) and "Sound Barriers - Road 220101" (2022-01-01, order 121411). Downloaded and
  unpacked to `data/sweden/noise_barriers/raw/road_ref_2019-01-01/` and `road_ref_2022-01-01/`. All four snapshots have
  the same layer and fields:

| Snapshot | Records | Elements | km | Closed (`VALID_TO` < 9999) | `Byggår` unknown | `Höjd` unknown |
|---|---|---|---|---|---|---|
| 2015-01-01 | 1,277 | 680 | 141 | 124 | 86% | 100% |
| 2019-01-01 | 1,563 | 806 | 178 | 74 | 70% | 84% |
| 2022-01-01 | 1,869 | 955 | 216 | 43 | 61% | 72% |
| July 2026 | 2,172 | 1,082 | 251 | 0 | 51% | 62% |

- **Removals are rare; growth is large.** Of the 1,118 `ELEMENT_ID`s seen in any snapshot, **36 are absent from the July
  file** (about 3%); each step drops 10-14 elements and adds 136-162. So the July file loses few barriers, and the register
  grows by about 36 km per 3-4 years. Whether a dropped `ELEMENT_ID` is a removed barrier or a retired road element is
  not stated (inferred: either).
- **For barriers registered since 2015, `VALID_FROM` is close to the build year.** Of the 1,014 July records with
  `VALID_FROM` in 2015 or later, 87% have a known `Byggår`; registration year equals `Byggår` for 67% of those and is one
  year later for another 25%. Of the 1,158 records with `VALID_FROM` before 2015 (mostly 2006-01-01), **85% have no
  `Byggår` and none has a height**. Heights are known for 81% of the post-2015 records. The undated, unmeasured barriers are
  essentially the 2006-and-earlier stock, so the problem is the legacy stock, not recent registration.
- **Naming note (cosmetic):** in `data/sweden/noise_barriers/raw/` the file `highway_noise_barriers.gpkg` holds the **rail**
  layer (order 451138) and `railway_noise_barriers.gpkg` holds the **road** layer (order 447607). The loader matches
  bundles by the order name inside each `_delivery_info.txt`, so results are not affected, but the file names are swapped.

## 7. Follow-up (2026-11-19, after the report was written): downloaded and inspected

On the user's go-ahead the products this report lists as "not ordered" or "not downloaded" were
downloaded and inspected; this section supersedes those statements in sections 3 and 4.

- **Vägombyggnad (96) and Vägnybyggnad (97):** ordered together as "Road Projects (Rebuild and New
  Build)" (order 121412, Sweden, GeoPackage, EPSG:3006, reference date today), 82 MB zip, under
  `data/sweden/road_projects/raw/order_121412/`. 7,457 rebuild and 83,475 new-build records.
  `Väsentlig ombyggnad` is unknown for 95% of rebuilds; `Objekt nr` is filled for about 20%. 23% of road
  barriers lie on a rebuilt stretch and 99% on a new-build record; 810 barriers (37%) have a project number.
  45 undated 2006-batch walls have a rebuild year 2000 to 2006.
- **Inspire Noise (10088):** all six files downloaded to `data/sweden/inspire_noise/raw/`. They are for
  **2016** (not stated on Lastkajen's catalogue page), dB contour polygons; 60% of road barriers and 54% of
  rail barriers lie inside a contour of 50 dB or more.
- Details, checks and the order steps: `docs/data/sweden/lastkajen-unused-products.md`; source pages
  `docs/data/sweden/road_projects/README.md` and `docs/data/sweden/inspire_noise/README.md`; scripts in
  `scripts/checks/2026-11-lastkajen/`.
