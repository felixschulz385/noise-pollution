# Florida — data sources

Index of every data domain in the Florida pipeline. Maintained by hand from
`src/regions/florida/cli.py` and the modules under
`src/regions/florida/sources/` until the per-region source registry
(template `docs/02`, see also [`../../design/01-multi-region-layout.md`](../../design/01-multi-region-layout.md))
is in place.

| Domain | Steps implemented | Prerequisites | Module |
|---|---|---|---|
| `noise_barriers` | `list-versions`, `fetch`, `preprocess` (clean one FGDL release → tidy GeoParquet barrier layer) | — | `src/regions/florida/sources/noise_barriers/` |
| `assessments` | `list-years`, `fetch` (manual-download orchestrator; **raw stage complete 2015–2026**, 231 files), `preprocess` (merge raw workbooks → tidy `assessments.parquet`, indexed on school × grade × subject × year, with the within-cell z-score) | `schools` crosswalk | `src/regions/florida/sources/assessments/` |
| `schools` | `fetch` (subsources `msid`, `edge`, `ccd_directory`, `ccd_enrollment` default; `crdc`, `crdc_lep`, `edfacts` opt-in — MSID from the FLDOE EDS app + NCES EDGE geocode + Urban Institute Education Data API); `preprocess` (spine + operation panel + Cluster-A covariates → `school_cross_section.parquet` / `school_year_panel.parquet`); `assemble` (school↔barrier point-only match → `schools_treatment.parquet` + rollup) — all implemented, see [`schools/README.md`](schools/README.md). Absorbs the former `master_file` source and `school_panel` (covariates.md Cluster A). Crosswalk to `NCESSCH` embedded in MSID (`FEDERAL_DIST_NO`/`FEDERAL_SCHL_NO`); classification codes from `msid_codes.py` (FLDOE MSID Application Guidelines). `assemble`'s matching algorithms 3–6 (road-network-dependent) are placeholder columns pending `road_network`. | `noise_barriers` (`assemble`) | `src/regions/florida/sources/schools/` |
| `road_network` | `list-versions`, `fetch`, `preprocess` (clean one FGDL `rciroads` release → tidy GeoParquet `road_network.parquet`) — all implemented; the `schools assemble` matching-algorithm extension (3–5) is still a notebook prototype, not wired into the pipeline, see [`road_network/README.md`](road_network/README.md). Unlocks `schools assemble`'s matching algorithms 3–6 (side-of-road treatment assignment) and will underpin the planned `traffic` / `road_projects` sources. Primary data: FGDL `rciroads_<version>.zip` (same provider/index scheme as `noise_barriers`, archived back to `jun04`; unlike `noise_barriers` it's a zipped Shapefile, not a Geodatabase). | — (feeds `schools assemble`, `traffic`, `road_projects`) | `src/regions/florida/sources/road_network/` |

On-disk output lands under `data/florida/<domain>/{raw,processed,assembled}/`.

**Control variables for the main analysis** (traffic, road-works, school panel,
staff, air co-pollution, neighbourhood, shocks) and the source modules that would
supply them are catalogued in [`covariates.md`](covariates.md).

## `noise_barriers`

FDOT statewide noise-barrier inventory (constructed, replaced, recommended and
removed walls along state highways and toll roads), published as a zipped Esri
File Geodatabase through the **Florida Geographic Data Library (FGDL)**,
maintained by the University of Florida GeoPlan Center. Public HTTPS download,
no authentication.

- Archive index: <https://fgdl.org/zips/geospatial_data/archive/>
  (`noise_barriers_<mon><yy>.zip`, e.g. `noise_barriers_apr23.zip`)
- Metadata: `https://fgdl.org/zips/metadata/xml/noise_barriers_<mon><yy>.xml`
- Releases are irregular (~annual); `list-versions` scrapes the archive index.
  `fetch` defaults to **`jul26`**, the release the exploratory notebook
  (`src/experiments/florida/barriers.ipynb`) is built against.
- CRS EPSG:3087 (Florida GDL Albers, metres); `jul26` has 1 883
  `MultiLineString-M` features across 63 columns (the schema drifts between
  releases — e.g. `jul26` dropped `TBR` / `BEGIN_POST` and added `PERIMETER
  WALL` as a `TYPE`). The zip's internal layout also varies (`.gdb` at the root
  in `apr23`, one folder down in `jul26`); `fetch` handles both. The field
  dictionary is in the exploratory notebook.

```bash
python -m src.cli florida data noise-barriers list-versions
python -m src.cli florida data noise-barriers fetch                 # -> data/florida/noise_barriers/raw/noise_barriers_jul26.gdb
python -m src.cli florida data noise-barriers fetch --version apr23 --keep-zip
python -m src.cli florida data noise-barriers preprocess            # -> data/florida/noise_barriers/processed/barriers.parquet (+ barriers.json)
```

### `preprocess` — clean one release to a tidy barrier layer

`preprocess` reads one local `noise_barriers_<version>.gdb` from `raw/` and
writes, into `processed/`:

- **`barriers.parquet`** — GeoParquet, **EPSG:3087** (metres preserved, so the
  downstream distance / buffer / network join needs no reprojection). One row
  per wall segment (`gcid` is 1:1 with rows), columns:
  `gcid, category, type, flag, is_programmed, built_year, fdot_distr,
  fed_route, fed_county, bloc_side, bloc_bnd, bloc_onrte, fed_nac, fed_anr,
  ben_rcptrs, tot_rcptrs, fed_materl, fhwa_sub_notes, height_m, length_m,
  seg_len_m, geometry`. `bloc_side`/`bloc_bnd`/`bloc_onrte` (compass side,
  traffic-direction orientation, mount type — found 2026-09-11 while
  investigating `road_network`'s side-of-road question, see
  [`schools/README.md`](schools/README.md)) are the wall's own side-of-road
  attribute, a ground-truth input for `schools assemble`'s algorithm 5.
  Only columns present in the given release are emitted (schema-drift tolerant).
- **`barriers.json`** — provenance sidecar: release tag, source `.gdb`, FGDL
  title / publication date, row counts by category, duplicates dropped,
  `built_year` coverage, and the column list.

Cleaning rules (crystallized from `src/experiments/florida/barriers.ipynb`):

1. **Physically-present walls only.** `TYPE ∈ {CONSTRUCTED BARRIERS, REPLACED
   BARRIERS}` → `category = "fdot_barrier"`; `TYPE ∈ {PRIVATE WALL, PERIMETER
   WALL}` → `category = "other_wall"` (non-FDOT screening, kept in the same
   file as potential noise-shielding confounders). `RECOMMENDED` / `PLANNED` /
   `REMOVED` are dropped.
2. **Deduplicate** on exact geometry (WKB).
3. **`built_year`** from `FED_YRCON`, kept only inside the fixed window
   **1990–2026** (the `9999` / `0` sentinels and any out-of-range value →
   `NA`). `built_year` is the intended treatment-timing input for the event
   study; dating the `NA` rows is left to the downstream step. Timing comes
   from **one snapshot's construction year**, not from diffing successive FGDL
   releases (a possible later robustness check).
4. **`is_programmed`** = `FLAG == "FNV"` — programmed / under-construction at
   snapshot time. These rows are kept (flagged), not dropped.
5. **Units:** `height_m`, `length_m` converted from feet; `seg_len_m` is the
   geometry-true length (`SHAPE_Length`, already metres).

The school ↔ barrier ↔ street-network merge that turns this into per-school
barrier treatment timing lives in the `schools` source, not here.

## `road_network` — `fetch` + `preprocess` implemented

FDOT RCI-derived roadway centerlines, published through the same **FGDL**
archive as `noise_barriers` (same publisher, same versioned-archive index and
naming scheme) but as a zipped **Esri Shapefile**, not a zipped Geodatabase —
confirmed by fetching, see [`road_network/README.md`](road_network/README.md#fetch--whats-implemented)
for the full brief.

- Archive index: <https://fgdl.org/zips/geospatial_data/archive/>
  (`rciroads_<mon><yy>.zip`, e.g. `rciroads_jul26.zip`)
- Metadata: `https://fgdl.org/zips/metadata/xml/rciroads_<mon><yy>.xml`
- **57 releases**, `jun04` → `jul26`; `fetch` defaults to **`jul26`**,
  version-matched to the `noise_barriers` snapshot already fetched.
- CRS EPSG:3087 (Florida GDL Albers, metres, same as `noise_barriers`);
  `jul26` has 40,357 `LineString`/`MultiLineString` features across 16
  columns (`ROADWAY, BEGIN_POST, END_POST, YEAR_, AADT, FUNCLASSCO, FUNCLASS,
  LANE_CNT, SEGMENTID, DESCRIPT, FGDLAQDATE, RTLENGTH, RCILENGTH, ARCLENGTH,
  AUTOID, SHAPE_LEN` + geometry).

```bash
python -m src.cli florida data road-network list-versions
python -m src.cli florida data road-network fetch                 # -> data/florida/road_network/raw/rciroads_jul26/rciroads_jul26.shp
python -m src.cli florida data road-network fetch --version apr23 --keep-zip
python -m src.cli florida data road-network preprocess            # -> data/florida/road_network/processed/road_network.parquet (+ road_network.json)
```

### `preprocess` — clean one release to a tidy roadway-segment layer

`preprocess` reads one local `rciroads_<version>.shp` from `raw/` and writes,
into `processed/`:

- **`road_network.parquet`** — GeoParquet, **EPSG:3087**. One row per
  roadway segment (40,357 for `jul26`), columns: `roadway_id, segmentid,
  begin_post, end_post, year, funclassco, funclass, lane_cnt, aadt,
  rtlength_m, rcilength_m, arclength_m, shape_len_m, autoid, fgdlaqdate,
  geometry`. No row filtering (unlike `noise_barriers`, there is no
  analogous "not really built" status); `DESCRIPT` is dropped (confirmed to
  duplicate `funclass` exactly, not a route name); every `MultiLineString`
  (37 of 40,357 — non-contiguous multi-part geometries) is flattened to a
  plain `LineString` so downstream linear-referencing code never has to
  handle it; `year`'s `0` sentinel (~16% of rows) becomes `NA`.
- **`road_network.json`** — provenance sidecar: release tag, source
  shapefile, FGDL title/publication date, row/roadway counts, count of
  flattened `MultiLineString`s, `year` coverage, and the column list.

The `schools`-side matching algorithms 3–5 that consume this layer are still
a notebook prototype (`src/experiments/florida/schools.ipynb` §7), not wired
into `schools/assemble.py` yet — see the `road_network` README's "Open
questions" for why (the naive same-`ROADWAY`-id matching under-recovers the
point-only baseline and needs a corridor-based redesign first).

## `assessments` — `fetch` (manual) + `preprocess` (merge to a tidy panel)

**Decision (2026-09):** the downstream barrier-construction **event study** will
use the **FLDOE annual school-level assessment result files** as the achievement
outcome. This is a deliberate choice over SEDA v6 (whose school files are pooled
2009–2019, no annual dimension) and over the federal EDFacts proficiency panel
(kept only as a robustness cross-check). Rationale and the full option
comparison live in the chat log; the essentials:

- **What:** one workbook per year from the FLDOE K-12 assessment results pages
  (<https://www.fldoe.org/accountability/assessments/k-12-student-assessment/results/>
  and the FCAT / FCAT 2.0 / FSA archives). Rows are school × grade × subject ×
  year (plus demographic subgroup), carrying **mean scale score** and **percent
  at each achievement level**. School-level coverage runs 1998–99 → present.
- **Test-regime breaks:** FCAT (–2010), FCAT 2.0 (2011–14), FSA (2015–22),
  FAST / B.E.S.T. (2022–23 →). Scale scores and "% Level 3+" are **not**
  comparable across regimes. `preprocess` should therefore emit, as the primary
  outcome, a **within grade × subject × year z-score** against the statewide
  distribution, so regime breaks difference out against not-yet-treated schools;
  keep the raw mean scale score for within-regime robustness. No spring-2020
  testing (gap year in every source).
- **Suppression:** small cells withheld (n < 10, sometimes < 20).

### Does this need a school directory? Is the manual download still required?

The assessment workbooks are **not** a geocoded school database — every row keys
on the Florida **District Number + School Number** and the school name only. The
directory comes from the **`master_file` (MSID)** source instead:

- **Primary path:** the MSID `all_schools` export keys on the same
  District+School number and already carries `LATITUDE` / `LONGITUDE` for every
  row, plus `DATE_OPENED` / `DATE_CLOSED` and school-type flags. So the join is
  assessment row → MSID (District+School) → coordinates + status, with **no NCES
  file and no crosswalk**. Historical schools are included, which covers a long
  panel better than a single EDGE snapshot.
- **If MSID coordinates prove unreliable** for some rows, geocode the MSID
  `PHYSICAL_ADDRESS` (US Census batch geocoder first, then Nominatim) — still on
  the FL number, still no NCES.
- **Only if the `NCESSCH` key is wanted** (to join CCD covariates or SEDA):
  bridge FL District+School number → `NCESSCH` via the NCES CCD school directory
  file (`ST_SCHID` field), then optionally to EDGE lat/lon. The manual
  `EDGE_GEOCODE_PUBLICSCH_2425` download is a fallback for this case, not a
  requirement.
- The `schools` domain (EDGE + CCD directory fetch) is therefore **deferred** —
  build it only if the `NCESSCH` linkage turns out to be needed.

### `fetch` — what it does (and doesn't)

`www.fldoe.org` blocks automated clients (HTTP 403 / bot protection), so there
is **no unattended download**. `fetch` is a manual-download orchestrator:

- `list-years` prints the results-page registry (spring years 2015–2026, minus
  the COVID gap year 2020) plus the FCAT / FCAT 2.0 / FSA archive hub URLs, and
  scans `data/florida/assessments/raw/` for what has been collected.
- `fetch` creates the `raw/<year>/` drop folders, reports each year's status
  (`present` / `missing`), and echoes step-by-step download instructions.
- `fetch --year <YYYY> --from-file <path>` imports a workbook you downloaded in a
  browser into `raw/<year>/` (repeat `--from-file` for several files).
- `fetch --year <YYYY> --file-url <url>` makes a best-effort HTTP attempt for a
  direct link — expect it to 403 unless your network is exempt.

```bash
python -m src.cli florida data assessments list-years
python -m src.cli florida data assessments fetch                       # lay out folders + status
python -m src.cli florida data assessments fetch --year 2024 --from-file ~/Downloads/FL24_ELA_sch.xlsx
```

### Collected so far — full raw stage, 2015–2026 (2026-09)

`raw/` now holds every year in the registry: **11 year folders × 21 workbooks =
231 `.xls` files**, downloaded with the Claude-for-Chrome browser agent (the
FLDOE bot wall stops scripted clients but not a real browser session) and then
sorted / renamed / verified locally. `list-years` reports `missing: []`;
`fetch --year <y>` reports `present` for all 11.

Per year, the 21 workbooks are:

| Group | Files | Naming |
|---|---|---|
| ELA, grades 3–10 | 8 | `FL<year>_ELA_G03_school.xls` … `_G10_school.xls` |
| Mathematics, grades 3–8 | 6 | `FL<year>_MATH_G03_school.xls` … `_G08_school.xls` |
| Statewide Science, grades 5 & 8 | 2 | `FL<year>_SCI_G05_school.xls`, `_SCI_G08_school.xls` |
| EOC (Algebra 1, Geometry, Biology 1, Civics, U.S. History), Spring admin | 5 | `FL<year>_ALG1_EOC_spring_school.xls`, `_GEO_`, `_BIO1_`, `_CIVICS_`, `_USHIST_` |

Each year folder also has a **`SOURCE_MANIFEST.tsv`** (provenance, not data):
`new_filename, subject, grade, administration, original_filename,
matched_filename, bytes, sha256, kind, source_page`. The `original_filename`
column is the only link back to FLDOE's own inconsistent names
(`31Sp17Alg1SRS.xls`, `Spring2015CivicsSchoolReport.xls`, …).

Selection rule used for every page: school-level Excel only ("State Report of
Schools" / "School Scores for All Curriculum Groups" per grade); **Spring**
administration only for multi-window EOCs; skip all PDFs, all District/State
files, Fall/Winter/Summer EOC windows, Algebra 2 EOC, retake files, and
standalone Writing. ELA and Math were per-grade on every page 2015–2026 (no
single combined school workbook in any year).

Regime coverage:

| Years | ELA / Math | Algebra 1 / Geometry | Science gr 5/8 | Bio 1 / Civics / U.S. Hist |
|---|---|---|---|---|
| 2015 | FSA (retrofitted; see caveat) | FSA EOC | FCAT 2.0 Science | NGSSS EOC |
| 2016–2022 | FSA | FSA EOC | Statewide Science | NGSSS EOC |
| 2023–2026 | FAST | B.E.S.T. EOC | Statewide Science | NGSSS EOC (B.E.S.T. for Bio 1 from 2023) |

(2020 has no spring administration — not in the registry, no folder.)

Integrity checks run at import (all 231 pass):

- Every file is a real OLE2 `.xls` binary — no HTML/403 error page saved under an
  `.xls` name.
- No two of the 231 files share a sha256 — so no link resolved to the wrong file
  (a district report, or a prior year's copy).
- Live in-sheet titles spot-checked across 2015/2019/2022/2023/2025/2026 — year
  and subject in the sheet match the filename.

**Caveats for `preprocess`:**

- **Key the year off an in-sheet cell, never the file's document Title.** The
  FSA-era workbooks still carry a stale OLE2 Title such as `2014 FCAT 2.0 State
  Report of School Results` / `2014 EOC Biology 1 …` that FLDOE never cleared
  when they reused the template.
- **2015 retrofitted FSA is on the 2016+ scale.** The sheets carry the note
  *"2015 FSA scores were reported to students as percentile scores"* (achievement
  levels were set Jan 2016 and applied retroactively), but the retrofitted files
  still report scale scores, and `assessments.ipynb` finds the 2015→2016
  school-level means within **1.9 scale points** at every ELA/Math grade — the
  same size as ordinary year-to-year drift. Pool 2015 into the FSA regime; the
  `retrofitted_2015` flag is kept in the processed table for robustness checks.
- **2025 file host changed** to `https://www.fldoe.org/file/5668/…` from the
  older `…/core/fileparse.php/5668/urlt/…` pattern. Cosmetic — the payloads are
  the same `.xls` format. Recorded per file in `SOURCE_MANIFEST.tsv`.
- Every file is the legacy **`.xls` (OLE2)** format — reading needs
  `xlrd >= 2.0.1` (now in `environment.yml`). `fetch` itself never opens the
  workbooks, so the CLI does not need it.
- Two on-disk layouts: *wide-standard* (ELA/Math grade files, all EOC files,
  Science 2024–26) and *science-legacy* (Science 2015–23 — `Grade` column first,
  `1..5` columns before the "% level 3+" column, trailing content-area columns,
  and a "Number of Points Possible" row under the header). The parser detects the
  header row and maps columns by name rather than position.

### `preprocess` — merge the raw workbooks to one tidy table

```bash
python -m src.cli florida data assessments preprocess           # -> data/florida/assessments/processed/assessments.parquet (+ assessments.json)
python -m src.cli florida data assessments preprocess --year 2024 --year 2025
```

`preprocess` parses every `raw/<year>/*.xls` (both layouts, header found by
name) and writes, into `processed/`:

- **`assessments.parquet`** — one row per school per subject × grade × year,
  **indexed on `(msid, grade, subject, year)`**. Columns: `subject_label`,
  `regime` (`FSA` / `FAST` · `FSA` / `B.E.S.T.` · `NGSSS Science` · `NGSSS EOC`),
  `retrofitted_2015`, `district_number` / `district_name` / `school_number` /
  `school_name`, `is_state_total`, `suppressed`, `n_students`,
  `mean_scale_score`, `pct_level3_plus`, `pct_l1..pct_l5`, `source_file`, and the
  primary outcome **`z_mss` / `z_mss_w`** — the school mean scale score
  standardised within each `year × subject × grade` cell (unweighted /
  `n_students`-weighted), which differences the regime scale breaks out.
  Nullable dtypes, so suppression / state-total `NaN`s round-trip. One
  `STATE TOTALS` row per file is kept and flagged (`msid == "000000"`),
  excluded from the z-score moments.
- **`assessments.json`** — provenance + validation sidecar: years, file count,
  row / school counts, rows by subject, suppressed share, and the
  achievement-level consistency checks (`L1..L5` sum, `L3+L4+L5 ==
  pct_level3_plus`).

Current run: **231 files → 371k rows, ~4.4k distinct schools**, suppressed share
≈ 0.10, all consistency checks pass. `src/experiments/florida/assessments.ipynb`
imports this same parser and investigates the merged frame (regime breaks,
panel shape, the 2015-scale check, the z-score's continuity) — it writes
nothing. The join key is `msid` = FLDOE District + School number; the
`msid → NCESSCH` crosswalk, coordinates and the open/close + regular-school
panel filter belong to `schools` + `master_file`.

## `master_file` — `fetch` works; `preprocess` deferred to the notebook

FLDOE **Master School Identification (MSID)** file — the authoritative directory
of PK-12 public schools. The `all_schools` export is **7.2k rows × 77 columns**
(active + historical), and already carries everything the school side of the
event study needs:

- `DISTRICT` + `SCHOOL` — the join key the assessment workbooks use
- `LATITUDE` / `LONGITUDE` — populated for every row (**so NCES EDGE geocoding
  may not be needed at all**)
- `PHYSICAL_ADDRESS` / `_CITY` / `_STATE` / `_ZIP`, and `MAILING_*`
- `DATE_OPENED` / `DATE_CLOSED` — panel entry / exit
- `TYPE`, `ACTIVITY_CODE`, `CHARTER_SCHL_STAT`, `MAGNET_STATUS`, `TITLE_I_STATUS`
  — the regular-school filter

### `fetch` — automated

The EDS app (<https://eds.fldoe.org/EDS/MasterSchoolID/>) is ColdFusion; each
export is an empty POST to a `Downloads/<name>.cfm` endpoint that returns a
tab-delimited file with **no session handshake** — only a browser `User-Agent`
is required (`eds.fldoe.org` has no bot wall, unlike `www.fldoe.org`). `fetch`
does this directly and writes `data/florida/master_file/raw/MSID_<dataset>.tsv`
(the body is TSV even though the server labels it `.xls` / `application/msexcel`).

```bash
python -m src.cli florida data master-file fetch                              # all_schools (default)
python -m src.cli florida data master-file fetch --dataset all_schools --dataset active_schools
python -m src.cli florida data master-file fetch --from-file ~/Downloads/MSID.xls   # import instead
```

Datasets: `all_schools` (default), `active_schools`, `future_schools`,
`verification`, `mailing_list` (first two verified; the rest mirror the same CF
form). On any download failure `fetch` falls back to manual-download
instructions. For a long panel, collect one MSID issue per school year (FLDOE
reissues it annually; older issues on request).

### `preprocess` — deferred

Use in `preprocess` (in the notebook first): the FL District+School number ↔
school location crosswalk (from MSID's own lat/lon, or geocoded addresses, or a
CCD `ST_SCHID` ↔ `NCESSCH` bridge if the `NCESSCH` key is wanted), plus the
open/close and school-type fields for panel construction.
