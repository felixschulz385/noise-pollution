# Florida — `road_projects` source: requirements for implementation

**Status: all three stages (`fetch`, `preprocess`, `assemble`) implemented
and run 2026-09-14.** This page is a self-contained implementation brief in
the same style as [`road_network/README.md`](../road_network/README.md) —
read it plus the files linked in [Read first](#read-first) for full context.

**Real run** (2026-09-14): `fetch` pulled all three raw extracts —
Work Program Construction (96,494 rows), Work Program PD&E (19,092 rows),
Active Construction Projects (2,428 rows, matching the `outStatistics` count
checked ahead of time in Open Question 1). `preprocess` stacked and tidied
them into **118,014 project-item rows across 4,676 distinct `roadway_id`s**
(`data/florida/road_projects/processed/road_projects.parquet`): `fiscal_year`
range **2023–2030** (Work Program rows, confirms the current-window-only
finding), `start_date` range **2009-03-03 to 2026-02-09** (Active
Construction rows, confirms the 2009 floor). The `is_wall_project` keyword
scan flagged **164 rows** (`WALL`/`BARRIER`/`NOISE` in the description) —
a cheap starting signal for the treatment-split question, not a validated
one; see the module docstring for caveats.

`assemble` matches schools to a roadway **+ milepost** (not just
`roadway_id` — a roadway can span many kilometres, so `roadway_id` alone
would over-attach distant projects) and joins to `road_projects.parquet` via
milepost-range overlap (± a 0.25 mi tolerance). Before relying on this join,
checked empirically (not assumed) that `road_projects`' mileposts and
`road_network`'s really are on the same reference frame: of the 115,375
`road_projects` rows whose `roadway_id` exists in `road_network` (97.8%),
**99.96%** fall within that roadway's own milepost extent. Real run: 5,984
placed schools → 5,366 matched to a roadway (89.7%, same rate as `traffic`,
expected — same underlying nearest-arterial match), **40,729
school↔project pairs**, **2,586 schools** (48.2% of matched) have at least
one nearby logged project, **8 schools** have a nearby project flagged by
the wall/barrier keyword scan.

**Joined into `panel/assemble.py`'s `event_study_panel.parquet` 2026-09-14.**
A project's timing is an interval (`fiscal_year` or `[start_date,
end_date]`), so `attach_road_projects` first explodes each
`school_road_projects.parquet` pair into one row per calendar year the
project spans, then does a plain exact-`(msid, year)` left join — unlike
`traffic`'s nearest-year `merge_asof` tolerance. Real run: **29,515 of
660,681 panel rows (4.5%)** matched an active road project; 30 rows hit the
`road_project_is_wall` keyword flag, 3,344 the `road_project_is_widening`
flag.

## Why this source exists

Covariate Cluster D (`docs/data/florida/covariates.md`): a noise wall is
frequently one line item inside a widening, resurfacing, or PD&E project.
The widening itself adds capacity (→ more traffic → more noise, the opposite
of what the wall is meant to fix) and the construction itself is disruptive
(lane closures, dust, noise) — both coincide with the wall's completion date
and would otherwise get soaked up into the "wall" treatment effect. Need this
source to (a) control for co-timed road work as a confounder and (b) split
"wall built as part of a widening" vs. "standalone barrier retrofit," which
are plausibly different treatments. Ranked directly behind `traffic` in this
project's own confounder-priority ranking (see the memory file's ranking
rationale) — together `traffic` and `road_projects` are the two
identification-driver covariates FDOT's own siting practice makes essential:
FDOT builds walls where a project's modelled noise impact crosses a
threshold, and that almost always happens inside a capital project.

## Read first

1. `docs/data/florida/covariates.md`, Cluster D section — the four planned
   variables and their `Role` tags (baseline / treatment-split / selection).
2. `docs/data/florida/road_network/README.md` — **the pattern to mirror** for
   how a design brief turns into working `fetch`/`preprocess`/`assemble`
   stages, and because this source's join strategy (below) is unusually
   clean specifically *because* `road_network` already exists.
3. `src/regions/florida/sources/road_network/shared.py` — `ROADWAY` id
   conventions this source's `RDWYID`/`RoadwayId` fields share.
4. `src/regions/florida/sources/_layout.py`, `_http.py` — shared path/HTTP
   helpers every Florida source uses.

## The data sources (researched and verified live 2026-09-14, not guessed)

Two live FDOT ArcGIS REST services, both under `gis.fdot.gov/arcgis/rest/
services/`, plus one downloadable historical archive. **Neither live service
has a real historical archive** — this is the central open question for this
source, see [Open questions](#open-questions).

### 1. `Work_Program_Current` (primary — the Five-Year Work Program extract)

`https://gis.fdot.gov/arcgis/rest/services/Work_Program_Current/FeatureServer`
— "created from an extract of FDOT's Work Program Administration system."
**21 sublayers**, one per work-program phase, all `esriGeometryPolyline`,
CRS **EPSG:3087** (confirmed, same as `road_network`/`noise_barriers` —
no reprojection needed), `maxRecordCount=20000`:

| id | phase | relevance |
|---|---|---|
| 2 | **Construction Phase** | primary — actual construction, not just planning |
| 13 | **PD&E Phase** | Project Development & Environment studies — the widening/interchange scoping stage, often years before construction |
| 1 | Capital Phase | funded capital items |
| 10 | Maintenance of Traffic Phase | lane-closure/detour-relevant, lower priority |
| 11 | Maintenance Phase | resurfacing-adjacent, check overlap with Construction |
| 0, 3–9, 12, 14–20 | Administration, Construction Support, Emergency (×5), Environmental, Operations, Planning, Preliminary Engineering, Research, ROW, Service Patrol, Sign Repair, Item Segments | lower priority / not obviously relevant |

Confirmed fields on layer 2 (`Construction Phase`), same schema across
sibling phase layers:

| field | type | meaning |
|---|---|---|
| `RDWYID` | string | **the FDOT `ROADWAY` id — same 8-digit-family format as `road_network.roadway_id`**, confirmed by live sample (`"26030000"`, `"13075000"`, `"13160000"`) matching `road_network.README.md`'s documented `ROADWAY` format exactly |
| `BEGSECPT` / `ENDSECPT` | double | linear-reference mileposts — **same scheme as `road_network`'s `BEGIN_POST`/`END_POST`**, confirmed comparable magnitudes in the live sample |
| `WPITEM` / `WPITMSEG` / `ITMSEG` | string | work-program item / item-segment identifiers |
| `FINPROJ` / `FINPRJSQ` | string | Financial Management (FM) project number + sequence — the standard FDOT project key, also used by SCO/Site Manager, useful as a cross-source join key |
| `FISCALYR` | integer | fiscal year of this phase record (sample values: 2024, 2027) |
| `WPWKMIX` / `WPWKMIXN` | string | work-mix code / name — **this is the project-type/scope field** Cluster D's "Project type / scope code" row wants (sample values: `"RESURFACING"`, `"ADD LANES & RECONSTR"`, `"INTERCHANGE - ADD LA"`) |
| `WPITSTAT` / `WPITSTNM` | string | item status code / name (sample: `"CONST.COMPLETE"`, `"ROW ACQUISITION BEG."`, `"BIDS RECEIVED"`, `"PLANS&ROW IN TALLA."`) — needed to distinguish completed vs. still-planned work |
| `WPPHAZGP` / `WPPHAZTP` | string | phase group / phase type codes — redundant with which of the 21 sublayers a row came from, keep for provenance |
| `RDWYSIDE` | string | **unverified** — worth checking whether this is a real carriageway/side attribute (would be new information `road_network` itself lacks) or another code table; don't assume |
| `MANDISDV` / `CONTYDOT` / `CONTYNAM` | string | managing district/division, county DOT number/name |
| `LOCALFULL` | string | free-text project description (sample: `"SR26 CORRIDOR FROM GILCHRIST C/L TO CR26A E OF NEWBERRY"`) — human-readable, useful for spot-checking, not for joining |
| `LOC_ERROR` | string | unverified — check whether non-null values flag geocoding problems worth filtering |

### 2. `Active_Construction_Projects` (secondary — Site Manager contract extract)

`https://gis.fdot.gov/arcgis/rest/services/Active_Construction_Projects/
FeatureServer/1` (note: layer id is **1**, not 0 — the FeatureServer's own
layer 0 doesn't resolve; discovered by querying the FeatureServer root)
— "Active Construction Contracts... updated with execution and completion
dates via Site Manager." `esriGeometryPolyline`, CRS **EPSG:26917** (differs
from `Work_Program_Current` — reproject to EPSG:3087), `maxRecordCount=1000`
(small — will need pagination via `resultOffset` even for one query).

Confirmed fields:

| field | type | meaning |
|---|---|---|
| `RoadwayId` | string | same `ROADWAY`-id format, confirmed live (`"13121000"`, `"86110000"`) |
| `BeginMP` / `EndMP` / `Length` | double | linear reference, same scheme |
| `ContractId` / `FinProjNum` | string | contract + FM project number — `FinProjNum` is the natural join key back to `Work_Program_Current.FINPROJ` |
| `StartDate` / `EstEndDate` | date (epoch ms) | **actual/estimated construction dates** — this is the field Cluster D's "Construction start / end / letting dates" row wants; more concrete than the Work Program's fiscal-year-level timing. Confirmed epoch-millisecond encoding live (e.g. `1691730000000`); convert with `pd.to_datetime(..., unit="ms")` |
| `Cost` | double | contract cost |
| `Description` | string | free text — **live sample included a wall-adjacent project verbatim**: `"Design Build SR 70 from Lorraine Rd to Bournside Blvd - Peri meter Wall"` (note the FDOT export's mid-word line-wrap artifact — strip/normalize whitespace when parsing) — a promising signal that some standalone-wall contracts are distinguishable by description text alone, worth a keyword scan (`"WALL"`, `"BARRIER"`, `"NOISE"`) as a cheap treatment-split check |
| `Vendor` / `ProjectMgr` / `Website` / `District` / `County` | string | contract metadata |
| `is820days` | string | unverified — likely a contract-duration-class flag |

### 3. Historical Adopted Work Program archive (download-only, not REST)

`https://fdotewp1.dot.state.fl.us/FMSupportApps/WorkProgram/Support/
Download.aspx` — FDOT's own Office of Work Program & Budget download page.
Confirmed live: **ArcGIS Geodatabase .zip** downloads for adoption years
**2019 through 2026**, one file per adopted-Work-Program vintage (July 1 of
each fiscal year), explicitly described as built "using linear referencing,
using the Five-Year Work Program spreadsheet in conjunction with RCI Basemap
Roads" — i.e. FDOT itself keys these to the same `ROADWAY`/milepost system as
`road_network`'s `rciroads`, confirming the join strategy below is the
intended one, not a coincidence. Also offers PDF and Excel exports for the
same years. **Earliest available adoption year is 2019** — no archive
further back was found on this page (see Open Questions).

## Why this source needs no spatial-matching fallback (unlike `noise_barriers`)

`road_network/README.md`'s hardest problem was that `noise_barriers.fed_route`
is free text (`"I-95"`, `"SR 91 / Turnpike Mainline"`) that doesn't cleanly
crosswalk to `rciroads.ROADWAY`, forcing a spatial nearest-line join. **Both
`Work_Program_Current` and `Active_Construction_Projects` carry `RDWYID`/
`RoadwayId` in the exact same `ROADWAY` id format already used by
`road_network.roadway_id`** (confirmed by live sample values above, and by
FDOT's own description of the historical archive being built from "RCI
Basemap Roads"). So the join to `road_network` (and from there to
`schools`/`traffic`, which already key off `roadway_id`) should be a direct
**id + milepost-range overlap** join — `roadway_id` equality plus
`[BEGSECPT, ENDSECPT]` (or `[BeginMP, EndMP]`) overlapping the school's
matched `roadway_id`/milepost from `traffic/assemble.py`'s
`match_schools_to_roadway` — no nearest-line spatial matching needed. This
also means `road_projects` doesn't strictly need its own geometry column for
matching (though keep it for QA/plotting); the join key is attributive.

## Scope for a first pass

Mirror `traffic`'s design: **don't fetch geometry from all 21
`Work_Program_Current` phase layers** — start with layer 2 (`Construction
Phase`) and layer 13 (`PD&E Phase`), the two Cluster D actually asks for
("Adjacent widening/resurfacing/interchange/PD&E project" + "Construction
start/end/letting dates"). Add `Active_Construction_Projects` for the
concrete `StartDate`/`EstEndDate` fields the Work Program layers lack (they
only carry `FISCALYR`, a coarser fiscal-year granularity). Treat the other 19
phase layers and the "quieter pavement" resurfacing-material variable
(Cluster D's fourth row — needs FDOT RCI pavement/resurfacing contract
detail, not obviously present in either service checked here) as open/
lower-priority, same posture `road_network` took toward its own algorithm 6.

Suggested output grain: one row per `(roadway_id, fiscal_year_or_date,
work_mix)` — i.e. don't collapse phases/years the way `traffic/preprocess.py`
collapses AADT to `roadway_id × release_year`, since here the *timing and
type* of each project is the signal, not a single aggregated number. Decide
during `preprocess.py` whether `Work_Program_Current` (fiscal-year grain,
21-phase detail) and `Active_Construction_Projects` (contract-date grain,
Site-Manager scope only) should be two separate processed tables or unioned
— they have different natural grains (fiscal year vs. contract dates) and
probably shouldn't be forced into one row type.

## Open questions

1. **Historical depth — the central open question, same as `road_network`'s
   item 4 but sharper here.** **Partially resolved 2026-09-14** — checked (a)
   below empirically, changes the scope for the better:
   - **(a) RESOLVED — `Active_Construction_Projects` is NOT current-only
     despite its name.** Queried its live `min`/`max`/`count` statistics on
     `StartDate`: **2,428 total rows, `StartDate` spanning 2009-03-03 to
     2026-04-16.** It retains completed contracts for ~17 years, not just
     presently-active ones — a real, usable window that reaches well past
     the FCAT-2.0 era (2011–2014) and into the 2009-2010 range, materially
     better than the 2019 floor the downloadable historical-archive check
     below implied. Confirmed via `outStatistics` (`min`/`max`/`count` on
     `StartDate`), not by trusting the layer's name.
   - **(b) still open** — `Work_Program_Current`'s 21 phase layers (incl.
     Construction=2, PD&E=13) genuinely are current-window only: a live
     query for `FISCALYR<2020` returned **zero** rows. So the *fiscal-year
     timing/phase* detail these layers add is only available for
     ~2020-onward projects; for older walls, `Active_Construction_Projects`'
     `StartDate`/`EstEndDate`/`Description` (2009+) is the only usable
     signal from the two live services.
   - **(c) still open** — the downloadable historical archive
     (`fdotewp1.dot.state.fl.us`) only reaches adoption year 2019 for the
     Work-Program-style geodatabase snapshots; not yet checked whether an
     FDOT public-records/data request could extend `Work_Program_Current`-
     equivalent detail back past 2009, or whether `Active_Construction_
     Projects`' 2009 floor should just be the source's documented coverage
     boundary (event-study walls before ~2009 would have no road-works
     control from this source — same shape as `road_network`'s own pre-2004
     gap against 1990s barriers). **Recommendation given (a)+(b): build v1
     against `Active_Construction_Projects` as the primary timing/type
     source (2009+, `Description` keyword-scannable for widening/resurfacing/
     wall language) and treat `Work_Program_Current` layers 2/13 as a
     *supplementary* fiscal-year/phase-detail enrichment for 2020+ rows only
     — don't block v1 on resolving (c).**
2. **`RDWYSIDE` on `Work_Program_Current`** — unverified whether this is a
   real carriageway/side attribute. If it is, it would be *new* information
   (`road_network`'s `rciroads` has no side field at all, per that source's
   README) — worth checking before assuming geometric derivation is still
   necessary for anything this source touches.
3. **`Active_Construction_Projects` layer-id oddity** — its FeatureServer
   root lists one layer at id **1** ("Construction Projects"); id 0 returned
   an error when queried directly. Confirm this is stable (not a transient
   service issue) before hardcoding `/FeatureServer/1` in `fetch.py`.
4. **CRS mismatch between the two live services** (`Work_Program_Current` is
   EPSG:3087, `Active_Construction_Projects` is EPSG:26917) — straightforward
   to handle (reproject on read, same as `road_network` already does
   elsewhere) but don't forget it; a silent CRS mismatch would break any
   geometry-based QA silently.
5. **Quieter-pavement / OGFC resurfacing** (Cluster D's fourth row) — neither
   service checked here obviously carries pavement-material detail beyond
   `WPWKMIXN="RESURFACING"` (which doesn't distinguish OGFC from conventional
   mill-and-resurface). May need a separate FDOT RCI pavement layer/contract
   detail not yet researched — flag as unresolved, lowest priority of the
   four Cluster D rows per `covariates.md`'s own tags.
6. **`FINPROJ`/`FinProjNum` as a cross-source join key** — not yet tested
   whether `Work_Program_Current` and `Active_Construction_Projects` rows for
   the same real-world project actually share a `FINPROJ`/`FinProjNum` value
   consistently; verify with real fetched data before relying on it to union
   the two tables (vs. falling back to the `roadway_id` + milepost-overlap
   join both already support independently).

## Suggested layout (mirror `road_network`/`traffic`)

```
src/regions/florida/sources/road_projects/
    __init__.py       # module docstring
    shared.py          # DOMAIN="road_projects", paths, layer-id constants
    fetch.py           # fetch_work_program_phase(layer_id), fetch_active_construction_projects()
                        #   — paginate via resultOffset (small maxRecordCount, esp. layer 1's 1000)
    preprocess.py       # tidy both extracts, id/milepost-key columns aligned to road_network.roadway_id
tests/regions/florida/test_road_projects_preprocess.py
docs/data/florida/road_projects/README.md   # this file
```

`data/florida/road_projects/{raw,processed,assembled}/` via the existing
`domain_dirs("road_projects")` helper — no new plumbing needed.

**CLI** (once built): `florida data road-projects {fetch,preprocess}`,
registered the same way `_register_road_network`/`_register_traffic` are in
`cli.py`/`handlers.py`.

## Definition of done

- ~~Open Question 1 (historical depth) resolved empirically.~~ **done**
  (2026-09-14) — sub-question (a) resolved (`Active_Construction_Projects`
  reaches back to 2009, not current-only); (b)/(c) documented as known,
  non-blocking gaps (Work Program layers are current-window only;
  pre-2009 coverage remains unresolved).
- ~~`fetch.py` pulls `Work_Program_Current` layers 2 + 13 and
  `Active_Construction_Projects`.~~ **done** (2026-09-14) —
  `src/regions/florida/sources/road_projects/{shared,fetch}.py`, real run:
  96,494 + 19,092 + 2,428 rows, attributes only (`returnGeometry=false`),
  ArcGIS `resultOffset` pagination. CLI: `florida data road-projects fetch`.
- ~~`preprocess.py` produces a tidy table keyed by `roadway_id` + milepost
  range + fiscal year/date.~~ **done** (2026-09-14) —
  `road_projects/preprocess.py`, real run: 118,014 rows / 4,676 distinct
  `roadway_id`s, `road_projects.parquet` + `road_projects.json` sidecar.
  9 unit tests (`tests/regions/florida/test_road_projects_preprocess.py`),
  185/185 Florida tests pass. CLI: `florida data road-projects preprocess`.
- ~~`assemble.py` — join this table to `schools` via `roadway_id` + milepost
  overlap.~~ **done** (2026-09-14) — `road_projects/assemble.py`: real run,
  5,366/5,984 schools matched to a roadway, 40,729 school↔project pairs,
  2,586 schools with ≥1 nearby project. 9 unit tests
  (`tests/regions/florida/test_road_projects_assemble.py`), 196/196 Florida
  tests pass. CLI: `florida data road-projects assemble`.
- ~~Wire this source into `panel/assemble.py`'s `event_study_panel.parquet`.~~
  **done** (2026-09-14) — `panel/assemble.py`'s `attach_road_projects` +
  `build_road_projects_year_panel` (explodes `school_road_projects.parquet`
  to a calendar-year grain first, then an exact `(msid, year)` left join).
  Real run: 29,515/660,681 panel rows (4.5%) matched. 11 new tests in
  `tests/regions/florida/test_panel_assemble.py`, 205/205 Florida tests
  pass. CLI: `florida data panel assemble` (unchanged interface).
- ~~`covariates.md`'s Cluster D table rows updated from "planned" to
  "implemented" with real numbers, same convention as the `traffic` row.~~
  **done** (2026-09-14).
