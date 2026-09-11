# Florida — `road_network` source: requirements for implementation

**Status: `fetch` + `preprocess` implemented; algorithms 3–5 validated in a
notebook, not yet promoted to pipeline code.** `list-versions`, `fetch` and
`preprocess` work end to end against the live FGDL archive and produce
`road_network.parquet` (see [`fetch` — what's implemented](#fetch--whats-implemented)
below). The `schools`-side algorithms 3–5 are prototyped and validated in
`src/experiments/florida/schools.ipynb` §7 — after a corridor-based redesign
(§7.4, replacing an initial `ROADWAY`-id-equality attempt that only recovered
~20-35% of the point-only baseline), recovery reaches 99.1% (algorithms 3/4)
and 83.2% (+ algorithm 5's same-side test) — but this is **still not wired
into `schools/assemble.py`** as real pipeline code (see [Open
questions](#open-questions--resolved--remaining), item 7). This page is a
self-contained implementation brief — read it plus the three files linked in
[Read first](#read-first) and you have everything needed to build the rest of
the source without further context from this conversation.

## Why this source exists

The project is a staggered difference-in-differences event study of **FDOT
noise-barrier construction on school achievement** in Florida
(`docs/data/florida/covariates.md` has the full design). The `schools` source
(`src/regions/florida/sources/schools/`) is fully implemented and matches
schools to nearby noise walls, but only with **point-only** distance — it
cannot yet tell whether a wall is on the school's side of the road or the far
carriageway of a divided highway, which materially changes whether the wall
shields that school at all. `schools/assemble.py` already has four placeholder
columns (`road_id`, `same_route`, `school_side`, `wall_side`) waiting for a
roadway network to fill them in — see [The consumer contract](#the-consumer-contract-schoolsassemblepy).

`road_network` will also be the base layer for two **planned, not-yet-built**
sources: `traffic` (AADT / truck-share covariates) and `road_projects` (FDOT
Work Program — widenings/PD&E projects, a confounder for barrier timing). Build
this source generically enough that both can consume it later; do not couple
its schema to `schools` alone.

## Read first

1. `docs/data/florida/schools/README.md` — the `schools` source design,
   especially the "Stage 2" / matching-algorithm and "side-of-road" sections.
   It documents algorithms 1–2 (already implemented, point-only) and the
   intended shape of algorithms 3–6 (this source unlocks them).
2. `src/regions/florida/sources/schools/assemble.py` — the consumer. Read
   `match_barriers_point`, `PENDING_ROAD_COLUMNS`, and the module docstring.
3. `src/regions/florida/sources/noise_barriers/{fetch,preprocess}.py` +
   `docs/data/florida/README.md`'s `noise_barriers` section — **the pattern to
   mirror**. This source's primary data provider (FGDL, below) is the same one
   `noise_barriers` already uses, with the same versioned-archive naming/index
   scheme (`road_network/fetch.py` copies `noise_barriers/fetch.py`'s
   version-tag scheme and download/list-versions structure almost verbatim)
   — but **not** the same archive *contents*: `rciroads_<version>.zip` is a
   zipped **Shapefile**, not a zipped Geodatabase, so `fetch.py`'s extraction
   logic (`_find_shapefile_members`, `_extract_shapefile`) differs from
   `noise_barriers`' `_find_gdb_prefix`/`_extract_gdb`, see [Open questions](#open-questions--resolved--remaining).
4. `src/regions/florida/sources/_layout.py`, `_http.py` — shared path/HTTP
   helpers every Florida source uses.

## The data source (researched, not guessed — verify before building)

**Primary: FGDL `rciroads_<version>.zip`** — the same publisher as
`noise_barriers` (Florida Geographic Data Library, University of Florida
GeoPlan Center), same archive index/naming/version-tag scheme, but the
archive itself is a zipped **Shapefile**, not a zipped Geodatabase like
`noise_barriers` (confirmed by fetching; see [Open questions](#open-questions--resolved--remaining)):

- Archive index: `https://fgdl.org/zips/geospatial_data/archive/` — filenames
  `rciroads_<mon><yy>.zip` (e.g. `rciroads_jul26.zip`). Also `current/` for the
  latest. **Versioned back to `jun04`**, roughly 3 releases/year since — a much
  longer run than `noise_barriers`' archive, so a wide range of vintages is
  available if the panel ever needs period-appropriate road geometry.
- Metadata XML: `https://fgdl.org/zips/metadata/xml/rciroads_<version>.xml`
  (confirmed reachable and parseable — this is how the schema below was
  pulled). Title: *"Florida Department of Transportation RCI Derived Roads —
  <Month Year>"*.
- **Confirmed field schema** (`rciroads_jul26`, 40,357 features, one row per
  roadway/`SEGMENTID` combination):

  | field | type | meaning |
  |---|---|---|
  | `ROADWAY` | string(32) | "Road system designation used by RCI as the roadway identifier" — FDOT's 8-digit-family roadway ID (see `noise_barriers`' `fed_route`, below, for why this doesn't directly match) |
  | `BEGIN_POST` / `END_POST` | double | linear-reference mileposts, **in miles**, along the route — this is what enables algorithms 4 (`same_segment`) and 3 (`road_gated`) |
  | `YEAR_` | int | data-currency year |
  | `FUNCLASSCO` / `FUNCLASS` | string / string | federal functional classification code + label |
  | `SEGMENTID` | — | segment identifier within the roadway |
  | `LANE_CNT` | — | lane count |
  | `AADT` | — | **traffic volume is already on this layer** — a head start for the future `traffic` source; don't build road_network blind to this |
  | `RTLENGTH` / `RCILENGTH` / `ARCLENGTH` | double | length fields, three different measures |
  | `DESCRIPT` | string | free-text description — **check whether this carries a human-readable route name** (untested; see Open Questions) |
  | `FGDLAQDATE` | date | FGDL acquisition date |
  | `AUTOID` | — | present but not in the metadata excerpt below; an internal row id |
  | `SHAPE_LEN` | double | geometry-true length, metres (redundant with `ARCLENGTH`) |
  | geometry | polyline (Shapefile `.shp`) | mostly `LineString` (40,320 rows), 37 `MultiLineString`; raw type is `Measured LineString` — the `M` values are dropped on read since `BEGIN_POST`/`END_POST` carry the linear reference as attributes instead |

  **No carriageway/direction/roadbed field exists.** This is a single
  centerline per roadway, like every FDOT roadway layer checked (see
  Alternatives below) — confirms the design decision already on record in
  `schools/README.md`: derive "which side of the road" geometrically (signed
  perpendicular offset relative to this centerline), not from an attribute.

- **Companion `roadids_<version>.zip`** exists in the same archive but is
  **not** a `ROADWAY`→route-name lookup — its schema
  (`ROADWAY, MILEPOST, TYPE, MP_ID, LAT_DD, LONG_DD, MGRS, GOOGLEMAP,
  DESCRIPT`) is a **mile-marker reference-point layer**. Don't assume it solves
  the naming crosswalk; verify what `DESCRIPT` holds before relying on it.

**Alternative / supplementary: FDOT Open Data Hub (live ArcGIS REST, current
only, no archive)** — `https://services1.arcgis.com/O1JpcwDW8sjYuddV/arcgis/
rest/services/<Layer>/FeatureServer/0` (`?f=json` for schema, `/query` for
data; `maxRecordCount=2000`, paginate with `resultOffset`; CRS is
**EPSG:26917**, not 3087 — reproject). Confirmed layers and row counts:
`State_Roads_TDA` (2,198, fields `ROADWAY, RANK, ROUTE, RouteNum, BEGIN_POST,
END_POST, DISTRICT, COUNTYDOT, COUNTY, MNG_DIST`), `Interstates_TDA` (84,
same shape), `US_Routes_TDA` (660, same shape), `On_System_TDA` (1,738 — the
active State Highway System, but **confirmed to exclude Florida's Turnpike**:
`DISTRICT='TURNPIKE'` → 0 rows), `Off_System_TDA` (10,572), `Toll_Roads_TDA`
(99, fields include `LOCALNAM` — worth checking as a route-name source since
barriers include Turnpike/HEFT/Sawgrass/CFX). These are event-mapped *thematic
subsets* of the same underlying RCI, not one unified layer — recommend
`rciroads` (FGDL) as primary and treat this as a fallback / cross-check only,
since it needs unioning several layers to get full coverage and has no
historical vintages.

**Why FGDL over the Hub, concretely:** version-matching to the `noise_barriers`
snapshot (`jul26`) already fetched, one file instead of unioning ≥2 Hub layers,
an existing fetch pattern to copy, and a much longer archive.

## The consumer contract (`schools/assemble.py`)

`match_barriers_point` (already implemented, point-only) will be extended —
by whoever picks up the `schools` side of this, not necessarily you — into a
`match_barriers_road` (or the existing function gets a `road_network` param)
that fills these currently-`NA` columns on `schools_treatment.parquet`
(one row per `(msid, gcid)` candidate pair):

| column | meaning | algorithm |
|---|---|---|
| `road_id` | the `ROADWAY` (or equivalent) id both the school and the wall are being matched against | 3 (`road_gated`) |
| `same_route` | bool — school and wall project onto the same `ROADWAY` within a milepost tolerance | 4 (`same_segment`) |
| `school_side` | signed side-of-centerline for the school point — **not a compass direction, see warning below** | 5 (`same_side`) |
| `wall_side` | signed side-of-centerline for the wall — **not a compass direction, see warning below** | 5 (`same_side`) |
| `shielded_frac` | fraction of the school→road sightline arc blocked by walls, optionally height-weighted | 6 (`shielded_arc`) — **stretch goal, lowest priority of the four** |

**Matching-algorithm rigour ladder** (from `schools/README.md`, reproduced so
this page is self-contained):

| # | Name | Definition | Needs |
|---|---|---|---|
| 3 | `road_gated` | nearest road_network segment to the school (≤ R); treated only if a wall on *that same roadway* is ≤ B from the school | road_network geometry, no linear ref needed |
| 4 | `same_segment` | project school & wall onto `road_network`; same `ROADWAY` within ± D of milepost AND school's perpendicular offset ≤ P | `BEGIN_POST`/`END_POST` linear referencing |
| 5 | `same_side` | (4) + the wall lies between the school and the carriageway (signed-offset test); a wall in the median counts for both sides | signed perpendicular offset to the centerline |
| 6 | `shielded_arc` | fraction of the school→road sightline arc blocked by walls, optionally weighted by `noise_barriers.height_m` (ISO 9613-2-style) | (5) + optionally a DEM |

**Side-of-road, explained** (also in `schools/README.md` — read it there for
the full rationale): a divided highway has two directional roadbeds either
side of a median; a wall on the far carriageway can be equally close to a
school in straight-line distance yet shield it not at all. Since `rciroads`
has no side/carriageway attribute, derive it purely geometrically: project
both the school point and the wall's nearest point onto the matched `ROADWAY`
centerline, take the **signed** perpendicular offset (e.g. cross-product sign
relative to the segment's direction vector) for each, and call them "same
side" when the signs agree.

> **⚠️ `school_side` / `wall_side` are not compass directions — never read
> them that way.** The sign comes from `rciroads`' own digitizing direction
> (which end of a `ROADWAY` FGDL happened to call milepost 0), which is
> **not** consistently north/south or east/west across roadways. Confirmed
> empirically in `src/experiments/florida/schools.ipynb` §7.2 (the matching-
> algorithm prototype lives there, not in this domain's own notebook — it
> consumes `schools/assemble.py`'s point-only match as its baseline): among
> the 1,245 matched `fdot_barrier` walls, side splits **1,077 vs 168**
> (87%/13%), not ~50/50 — a real compass-relative signal would split close to
> evenly across a statewide, all-orientations road network. **The sign is
> only ever valid pairwise**, comparing a wall's side to a school's side *on
> the same matched `ROADWAY` segment* (exactly what algorithm 5's same-sign
> test does). Comparing `school_side`/`wall_side` across different schools,
> different roadways, or against any absolute notion of "left"/"right" or
> "north"/"south" is a bug, not a simplification. **Note also:** `schools.ipynb`
> §7.7 found that `noise_barriers` raw actually carries a real compass-value
> side field for the wall (`BLOC_SIDE`), currently dropped by
> `noise_barriers/preprocess.py` — use it as ground truth for the wall side
> rather than trusting this geometric derivation unchecked; schools still
> need the geometric method since they have no equivalent attribute. Carry
> this warning into whatever docstring / column-comment ends up on
> `schools_treatment.parquet` once algorithm 5 is implemented — it is exactly
> the kind of thing a future reader will
> misinterpret from the column name alone.

**Inputs `schools`/`noise_barriers` already provide, for reference:**
- `data/florida/schools/processed/school_cross_section.parquet` — school
  points, EPSG:3087, one row per `msid`, `geom_source != 'none'` for the
  placed ~5,984 (see `docs/data/florida/schools/README.md` output schema).
- `data/florida/noise_barriers/processed/barriers.parquet` — wall polylines,
  EPSG:3087, `gcid`, `category ∈ {fdot_barrier, other_wall}`, `built_year`,
  **`fed_route`** — a **free-text, human-readable** route label (e.g. `"I-95"`,
  `"SR 91 / Turnpike Mainline"`, `"SR 821 / HEFT"`, 81 distinct values across
  1,263 walls; `fdot_distr ∈ {1..7, TURNPIKE, CFX, PRIVATE}`). **This does not
  cleanly match `rciroads.ROADWAY`** (an 8-digit-family numeric-ish id) —
  recommend **spatial nearest-line matching** (project each wall's
  representative point onto the road_network, take the closest segment) as
  the primary join method rather than attempting a name↔id crosswalk table,
  which would need hand-curation for ~81 route labels and would break silently
  on any label FDOT hasn't used yet. Use `fed_county`/`FDOT_DISTR` as a sanity
  check on the spatial match, not as the join key.

## Scope for a first pass

Ship algorithms **3–5** (`road_gated`, `same_segment`, `same_side`) —
these are what the `schools` design actually needs for a materially better
treatment definition. Algorithm 6 (`shielded_arc`) is a stretch goal;
leave it as a documented TODO with the column present as `NA` if you don't
get to it, exactly like `schools/assemble.py` already does for algorithms 3–6
today. Don't block on it.

## `fetch` — what's implemented

```
src/regions/florida/sources/road_network/
    __init__.py     # module docstring: what this is, why, what it feeds
    shared.py        # DOMAIN="road_network", DATASET_PREFIX="rciroads",
                      #   paths + version-tag helpers (copy of
                      #   noise_barriers/shared.py's regex/sort pattern)
    fetch.py          # list_versions(), fetch_road_network(version)
tests/regions/florida/test_florida_cli_dispatch.py  # CLI + fetch unit tests
docs/data/florida/road_network/README.md   # this file
```

```bash
python -m src.cli florida data road-network list-versions
python -m src.cli florida data road-network fetch                 # -> data/florida/road_network/raw/rciroads_jul26/rciroads_jul26.shp
python -m src.cli florida data road-network fetch --version apr23 --keep-zip
```

`fetch` downloads one FGDL `rciroads_<version>.zip`, extracts its shapefile
parts into `raw/rciroads_<version>/`, and (by default) also downloads the
companion metadata XML — same shape as `noise-barriers fetch`, except the
extraction targets a shapefile's sidecar files (matched by basename via
`_find_shapefile_members`) rather than a `.gdb` folder, since `rciroads` is
not a geodatabase archive (see Open Question 1, resolved above). `list-versions`
confirms **57 releases**, `jun04` → `jul26`, `jul26` both `default` and
`current`.

Verified against the live archive: `jul26` extracts to **40,357 rows**,
**EPSG:3087**, columns `ROADWAY, BEGIN_POST, END_POST, YEAR_, AADT,
FUNCLASSCO, FUNCLASS, LANE_CNT, SEGMENTID, DESCRIPT, FGDLAQDATE, RTLENGTH,
RCILENGTH, ARCLENGTH, AUTOID, SHAPE_LEN, geometry` — matches the schema table
above (plus `AUTOID`/`SHAPE_LEN`, not previously listed). Geometry is almost
entirely `LineString` (40,320 rows) with 37 `MultiLineString` rows; the raw
`Measured LineString` (`M`-geometry) type is downgraded to plain `LineString`
on read (pyogrio warns; the M values — likely mileposts — are dropped, which
is fine since `BEGIN_POST`/`END_POST` are separate attribute fields).

## Suggested layout for the rest (mirror the existing sources)

```
src/regions/florida/sources/road_network/
    preprocess.py     # tidy the shapefile -> one GeoParquet, EPSG:3087, with
                      #   whatever subset of RCIROADS_JUL26's columns downstream
                      #   needs (ROADWAY, BEGIN_POST, END_POST, geometry at
                      #   minimum) + a provenance JSON sidecar (mirror
                      #   noise_barriers/preprocess.py's barriers.json)
tests/regions/florida/test_road_network_preprocess.py
```

`data/florida/road_network/{raw,processed,assembled}/` via the same
`domain_dirs("road_network")` helper every other Florida source uses
(`_layout.py`) — no new plumbing needed there.

**CLI**: `florida data road-network {list-versions,fetch,preprocess}` — the
first two are wired up (`src/regions/florida/cli.py`'s
`_register_road_network`, `handlers.py`'s `command_road_network_*`);  add a
`preprocess` subparser there matching `_register_noise_barriers`'s shape when
that stage is built.

**Output**: `data/florida/road_network/processed/road_network.parquet` (name
by analogy with `barriers.parquet`) — GeoParquet, EPSG:3087, one row per
roadway segment, at minimum `roadway_id` (renamed from `ROADWAY`),
`begin_post`, `end_post`, `geometry`; carry `aadt`/`lane_cnt`/`funclass` too
since they're free and the `traffic` source will want them later. Match the
naming conventions already used (`noise_barriers`' `gcid`/`fed_route`/
`built_year` lowercase-snake style, see `preprocess.py`'s
`COLUMN_RENAMES`/`OUTPUT_COLUMNS` pattern).

## Open questions — resolved / remaining

1. **RESOLVED — `rciroads_<version>.zip` is a Shapefile, not a Geodatabase.**
   Unlike `noise_barriers`, the archive is `<stem>.shp` + `.dbf`/`.shx`/`.prj`/
   `.sbn`/`.sbx`/`.cpg`/`.shp.xml` sidecars, confirmed flat at the zip root for
   both the current release (`jul26`) and the oldest archived one (`jun04`) —
   no `.gdb` anywhere. `road_network/fetch.py`'s `_extract_shapefile` matches
   archive members by basename (`<stem>.*`) rather than reusing
   `noise_barriers`' `_find_gdb_prefix` folder-prefix logic, so it is
   layout-agnostic if a future release nests the files one folder down (not
   observed in either release checked).
2. **RESOLVED — CRS is EPSG:3087.** The extracted `.prj` reads
   `NAD_1983_HARN_Florida_GDL_Albers`, i.e. EPSG:3087 — the same CRS
   `noise_barriers` uses. No reprojection needed; confirmed by loading the
   fetched `jul26` shapefile with geopandas (40,357 rows, `gdf.crs ==
   EPSG:3087`, columns match the table above exactly plus `AUTOID`/
   `SHAPE_LEN`).
3. **RESOLVED — `DESCRIPT` duplicates `FUNCLASS` exactly**, on every row
   (`road_network.ipynb` §2). Not a route name, carries no information
   `funclass` doesn't already have — dropped in `preprocess.py`. The spatial
   nearest-line join stays the only viable join method (no name crosswalk).
4. **Coverage for older barriers — still open, not blocking.** Some noise
   walls have `built_year` in the 1990s; `rciroads`' archive starts `jun04`.
   Decide (and document) whether the current/nearest-available vintage is an
   acceptable proxy for a road's 1990s-era geometry, or whether this is a
   robustness caveat to flag and move on — don't over-invest in solving it,
   `noise_barriers` already made the analogous call ("one snapshot, not
   diffed across releases").
5. **RESOLVED (mostly) — milepost discontinuities.** 99% of consecutive
   same-`ROADWAY` segment pairs have ~zero milepost gap (`road_network.ipynb`
   §4); one outlier (`ROADWAY 14121000`, a −4.36 mi overlap). A small `±D`
   tolerance is safe on its own terms — but see item 7, the bigger problem
   turned out to be `ROADWAY`-id granularity, not milepost continuity.
6. **RESOLVED — validated against real data.** **95.6%** of the 1,245
   `fdot_barrier` rows in `barriers.parquet` get a `road_network` match
   within 50 m (`schools.ipynb` §7.1) — passes the ≥95% target.
7. **RESOLVED — `same_segment` redesigned as a network-distance-bounded
   corridor test, not `ROADWAY`-id equality.** (`schools.ipynb` §7.4,
   2026-09-11.) The original diagnosis held: matching wall and school
   independently to their nearest `road_network` segment and requiring
   `ROADWAY_wall == ROADWAY_school` recovers only ~20-35% of the algorithm
   1/2 baseline (`ever_near_wall_500m`) because `ROADWAY` is a fine RCI
   linear-referencing segmentation (18,373 ids statewide, ~2.2 segments/id)
   closer to a "control section" than a continuous route. The fix: from the
   wall's point, flood-fill outward along the arterial-only network's
   **actual connectivity** (segments sharing an endpoint), consuming true
   path distance up to a budget (not segment count or `ROADWAY` identity),
   buffer the result into a corridor polygon, and test whether the school
   falls inside. **Recovery jumps to 93-99%** across a small
   `budget`/`buffer` grid (`budget=800 m, buffer=600 m` → 99.1%; adding the
   same-side test on top → 83.2%, the ~17-point drop being schools on the
   *opposite* carriageway — exactly the false positives algorithm 5 is
   supposed to remove, not a bug).

   **Two bugs surfaced building this, both worth remembering:** (a)
   checking the distance budget once per BFS hop-*layer* instead of per
   segment let a single hop overshoot massively on FDOT's median-852 m (but
   up to 57 km!) unsegmented stretches — one wall's corridor reached 10.5 km
   on a 3.2 km budget; (b) the seed segment itself must be trimmed
   (`shapely.ops.substring`) to the portion near the wall's point, not
   unioned in whole — skipping this let one wall's corridor reach 24 km,
   because its nearest segment *was* one of those long unsegmented
   stretches. Both are the same failure mode that broke the original
   `ROADWAY`-id design: assuming RCI's segmentation is regular enough for a
   count/length proxy to stand in for true distance, when its tail
   (57 km segments; `ROADWAY` ids as fine as one per short urban block) is
   wide enough to break that assumption. This design (arterial-only
   candidate network, network-distance-bounded corridor, `budget=800 m,
   buffer=600 m` as a starting default) is ready to move into
   `road_network/preprocess.py` (the adjacency graph + corridor helper) and
   `schools/assemble.py` (`match_barriers_road`) as real pipeline code.

## Definition of done

- ~~`python -m src.cli florida data road-network fetch` and `... preprocess`
  work end to end and produce `road_network.parquet` + a provenance
  sidecar.~~ **done** (2026-09-11) — `preprocess.py` tidies the shapefile
  (column rename, `MultiLineString` flattening, `year` sentinel → `NA`), unit
  tests in `tests/regions/florida/test_road_network_preprocess.py`.
- Unit tests (synthetic geometry, no network — mirror
  `tests/regions/florida/test_noise_barriers_preprocess.py`'s style) for the
  linear-referencing projection, the signed-side derivation, and the
  corridor flood-fill (`corridor_geometry` — including the two bugs found
  and fixed in Open Question 7: per-segment budget checking, seed-segment
  trimming) — prototyped and validated in `schools.ipynb` §7.2/§7.4, not yet
  promoted to a tested module.
- `schools/assemble.py`'s algorithms 3–5 (minimum) are implemented against
  this source, `PENDING_ROAD_COLUMNS` actually populated, and the ≥95%
  match-rate check above passes on the real fetched barriers. **Design
  validated, not yet implemented as pipeline code**: the corridor-based
  redesign (Open Question 7) recovers 99.1% (algorithms 3/4) and 83.2%
  (+ algorithm 5) of the point-only baseline in `schools.ipynb` §7.4 —
  what remains is moving the adjacency graph + `corridor_geometry` helper
  into `road_network/` and wiring `match_barriers_road` into
  `schools/assemble.py`, not further design work.
- `docs/data/florida/schools/README.md`'s "Stage 2" section and
  `PENDING_ROAD_COLUMNS`/algorithm-ladder references are updated to say
  "implemented," and this page's Status line is updated too.
