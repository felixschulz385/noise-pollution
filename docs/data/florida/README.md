# Florida — data sources

Index of every data domain in the Florida pipeline. Maintained by hand from
`src/regions/florida/cli.py` and the modules under
`src/regions/florida/sources/` until the per-region source registry
(template `docs/02`, see also [`../../design/01-multi-region-layout.md`](../../design/01-multi-region-layout.md))
is in place.

| Domain | Steps implemented | Prerequisites | Module |
|---|---|---|---|
| `noise_barriers` | `list-versions`, `fetch`, `preprocess` (clean one FGDL release → tidy GeoParquet barrier layer) | — | `src/regions/florida/sources/noise_barriers/` |
| `assessments` | `list-years`, `fetch` (manual-download orchestrator; **raw stage complete 2003–2026**, 435 files — plain FCAT + FCAT 2.0 + FSA + FAST/B.E.S.T.), `preprocess` (merge raw workbooks → tidy `assessments.parquet`, indexed on school × grade × subject × year, with the within-cell z-score) | `schools` crosswalk | `src/regions/florida/sources/assessments/` |
| `schools` | `fetch` (subsources `msid`, `edge`, `ccd_directory`, `ccd_enrollment` default; `crdc`, `crdc_lep`, `edfacts` opt-in — MSID from the FLDOE EDS app + NCES EDGE geocode + Urban Institute Education Data API); `preprocess` (spine + operation panel + Cluster-A covariates → `school_cross_section.parquet` / `school_year_panel.parquet`); `assemble` (school↔barrier match, algorithms 1–5 → `schools_treatment.parquet` + rollup) — all implemented, see [`schools/README.md`](schools/README.md). Absorbs the former `master_file` source and `school_panel` (covariates.md Cluster A). Crosswalk to `NCESSCH` embedded in MSID (`FEDERAL_DIST_NO`/`FEDERAL_SCHL_NO`); classification codes from `msid_codes.py` (FLDOE MSID Application Guidelines). `assemble`'s algorithm 6 (`shielded_arc`) is a stretch goal, left `NA`. | `noise_barriers` (`assemble`), `road_network` (`assemble`) | `src/regions/florida/sources/schools/` |
| `road_network` | `list-versions`, `fetch`, `preprocess` (clean one FGDL `rciroads` release → tidy GeoParquet `road_network.parquet`) — all implemented, see [`road_network/README.md`](road_network/README.md). Feeds `schools assemble`'s matching algorithms 3–5 (`road_gated`/`same_segment`/`same_side`, implemented via `road_network/linear_ref.py`; 6 is a stretch goal) and underpins `traffic`. Primary data: FGDL `rciroads_<version>.zip` (same provider/index scheme as `noise_barriers`, archived back to `jun04`; unlike `noise_barriers` it's a zipped Shapefile, not a Geodatabase). | — (feeds `schools assemble`, `traffic`, planned `road_projects`) | `src/regions/florida/sources/road_network/` |
| `barrier_protection` | `build` (new 2026-09-24: each FDOT wall's reference arterial road, side (from the wall's own geometry, checked against `BLOC_SIDE`) and protected area, computed once and saved, plus a **statewide protection-zone layer**, one polygon per wall. Built on the region-agnostic `src/core/barrier_geometry/`, shared with Sweden. See [`barrier_protection.md`](barrier_protection.md)) | `noise_barriers`, `road_network` | `src/regions/florida/sources/barrier_protection/` |
| `traffic` | `list-versions`, `fetch`, `preprocess` (fetch many FGDL `rciroads` releases' `AADT` field and stack into `aadt_panel.parquet`, one row per `roadway_id × release_year`), `assemble` (match schools to a roadway, join its AADT time series → `school_aadt_panel.parquet`, 89.7% match rate) — all implemented, see [`traffic/README.md`](traffic/README.md). Covariate Cluster C. **Joined into `panel`'s final event-study table** (nearest-release-year match, 71.3% of rows matched). | `road_network`'s fetch machinery (reused directly), `schools preprocess` + `road_network preprocess` (`assemble`) | `src/regions/florida/sources/traffic/` |
| `panel` | `assemble` (join `assessments` + `schools` + `traffic` + `road_projects` + `shocks` + `staff` + `neighbourhood` into one msid × grade × subject × year analysis panel, `event_study_panel.parquet`) — implemented. No `fetch`/`preprocess` of its own. **First-pass panel**: carries Cluster A covariates, all three barrier-treatment-timing definitions, `traffic` (nearest-release-year match, 71.3% of rows matched), `road_projects` (year-interval-overlap match, 4.5% of rows matched an active project), `shocks` (exact county-year match, 44.7% of rows matched a disaster declaration), `staff` (two exact-key joins — salary/experience 5.4%, per-pupil expenditure 60.3%, out-of-field 5.3%), and now `neighbourhood` (two exact-key joins — ACS demographics 68.0% matched, ZHVI home values 98.6% matched, see the sections below), but doesn't yet carry the remaining covariate module (`air_quality` — see [`covariates.md`](covariates.md)). | `assessments` (`preprocess`), `schools` (`preprocess` + `assemble`), `traffic` (`fetch` + `preprocess` + `assemble`), `road_projects` (`fetch` + `preprocess` + `assemble`), `shocks` (`fetch` + `preprocess` + `assemble`), `staff` (`fetch` + `preprocess` + `assemble`), `neighbourhood` (`fetch` + `preprocess` + `assemble`) | `src/regions/florida/sources/panel/` |
| `road_projects` | `fetch`, `preprocess`, `assemble` — all implemented and run 2026-09-14, see [`road_projects/README.md`](road_projects/README.md). Covariate Cluster D (widening/PD&E/construction projects co-timed with a wall). Pulls FDOT `Work_Program_Current` layers 2/13 + `Active_Construction_Projects` ArcGIS REST services (both keyed by the same `ROADWAY` id format as `road_network.roadway_id`, confirmed live) into `road_projects.parquet` (118,014 project-item rows, 4,676 distinct roadways). `assemble` matches schools to a roadway + milepost and joins nearby projects via milepost-range overlap (5,366/5,984 schools matched, 40,729 school↔project pairs, 2,586 schools with ≥1 nearby project). **Joined into `panel`'s `event_study_panel.parquet`** via a year-interval-overlap match (4.5% of panel rows matched an active project). | `schools` (`preprocess`), `road_network` (`preprocess`) | `src/regions/florida/sources/road_projects/` |
| `shocks` | `fetch`, `preprocess`, `assemble` — all implemented and run 2026-09-14, see [`shocks/README.md`](shocks/README.md). Covariate Cluster G (county-level hurricane/disaster declarations). Pulls OpenFEMA `DisasterDeclarationsSummaries` v2 (entire FL history, 2,794 rows, in one request — no pagination needed) into `disaster_declarations.parquet`. `assemble` rolls up to `county_name x assessment_year` (1,774 rows) and validates the join against the real 67-county FLDOE district roster — a name join, not FIPS, since Florida has one district per county. **Joined into `panel`'s `event_study_panel.parquet`** via an exact `(district_name, year)` match (44.7% of panel rows matched a declaration, 35.6% a hurricane). | `schools` (`preprocess`) | `src/regions/florida/sources/shocks/` |
| `staff` | `fetch`, `preprocess`, `assemble` — all implemented and run 2026-09-17, see [`staff/README.md`](staff/README.md). Covariate Cluster B (teacher salary/experience, in-field/out-of-field teaching, per-pupil expenditure). Two FLDOE workbooks (`teacher_salary` district-level, `out_of_field` SCHOOL-level) fetched via their Wayback Machine archive (`www.fldoe.org` itself blocks scripted clients, same as `assessments`) — FLDOE's own numbering matches `schools`' `district`/`school` fields directly, no crosswalk needed there. `district_finance` (per-pupil expenditure) via NCES CCD F-33, Urban API, 1995-2020, joined through a modal `district->leaid` crosswalk (min 88.5%/median 100% coverage). **Joined into `panel`'s `event_study_panel.parquet`** via two exact-key matches (salary/experience 5.4% of rows — historical backfill paused on a live Internet Archive outage, mechanically ready; per-pupil expenditure 60.3%; out-of-field 5.3%). Teacher turnover / % advanced degree not built (no aggregate FLDOE source found). | `schools` (`preprocess`) | `src/regions/florida/sources/staff/` |
| `neighbourhood` | `fetch`, `preprocess`, `assemble` — all implemented and run 2026-09-17, see [`neighbourhood/README.md`](neighbourhood/README.md). Covariate Cluster F (tract ACS demographics + Zillow ZHVI home values). The only Florida source doing a point-in-polygon spatial join (school -> Census tract/ZCTA via cartographic boundary files) rather than a linear-referencing one; two tract-boundary vintages (2010/2020) handled since ACS5 switched vintage at its "2020" release. Zillow ZHVI (ZIP-level, no auth) and ACS demographics (Census Data API, key-required since a 2026-05 policy change — `CENSUS_API_KEY` env var, user-supplied) both live: 5,984/5,984 schools matched to both a tract and a ZIP, 16/16 ACS years (2009-2024) fetched clean. **Joined into `panel`'s `event_study_panel.parquet`**: 68.0% of rows matched ACS demographics, 98.6% matched a ZHVI value. | `schools` (`preprocess`) | `src/regions/florida/sources/neighbourhood/` |

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

The `schools`-side matching algorithms 3–5 that consume this layer are
implemented in `road_network/linear_ref.py` + `schools/assemble.py`'s
`match_barriers_road` — a network-distance-bounded corridor test, not
`ROADWAY`-id equality (design validated first in
`src/experiments/florida/schools.ipynb` §7), recovering 99.1%/82.3% of the
point-only baseline on the real fetched data. See the `road_network`
README's Open Question 7 for the full design writeup.

## `traffic` — `fetch` + `preprocess` implemented, no `assemble` yet

An AADT (Annual Average Daily Traffic) panel — covariate Cluster C, the core
confounder set (`covariates.md`): FDOT sites noise walls by modelled noise
level, which tracks traffic growth, so a traffic trend at a soon-to-be-treated
road is the identification risk this covariate is meant to absorb.

Built entirely from FGDL `rciroads` releases `road_network` already fetches —
one release's `AADT` field is a cross-section, but fetching **many** releases
(the archive holds 57, `jun04` → `jul26`, ~3/year) turns it into a real panel.
Full design brief: [`traffic/README.md`](traffic/README.md).

```bash
python -m src.cli florida data traffic list-versions
python -m src.cli florida data traffic fetch                       # every archived release (57 downloads)
python -m src.cli florida data traffic fetch --version jul26 --version jan19
python -m src.cli florida data traffic fetch --limit 5             # smoke test: 5 most recent releases only
python -m src.cli florida data traffic preprocess                  # -> data/florida/traffic/processed/aadt_panel.parquet (+ traffic.json)
```

`fetch` reuses `road_network.fetch.fetch_road_network` for each requested
version (sharing one copy of the release with `road_network` if it's already
there) rather than duplicating the download/zip logic, keeps only the
attribute columns this source needs, and by default deletes the ~34 MB of
extracted geometry again afterwards (`--keep-road-network-raw` to keep it).
Idempotent — re-running `fetch` skips a version whose attribute table is
already on disk unless `--force`.

**`preprocess`'s row grain is `roadway_id × release_year`, not `roadway_id ×
segmentid` — verified against live data, not assumed.** Comparing `jul26`
against `jan19` showed FGDL re-segments each `ROADWAY` differently release to
release (only 5 of ~40k `jul26` segment-ids matched `jan19`'s, and even
milepost breakpoints for the same stretch of road shift), while `roadway_id`
itself is stable (84% overlap). So `preprocess` aggregates each release's
segments within a `roadway_id` into one row — AADT as the **length-weighted**
mean (`aadt_min`/`aadt_max`/`segment_count`/`length_mi` alongside it, so a
consumer can see how much within-roadway heterogeneity that's smoothing
over). Confirmed the aggregate still carries real time variation: `jul26` vs
`jan19` (2026 vs 2019) shows a +10% median AADT change across ~15.5k shared
roadways, ~51/49 up/down — consistent with traffic growth, not noise.

`assemble` matches every placed school to its nearest arterial `roadway_id`
(reusing `road_network/linear_ref.py`'s nearest-road matcher, the same
helper `schools/assemble.py`'s `match_barriers_road` uses for walls) and
left-joins `aadt_panel` onto it → `school_road_match.parquet` +
`school_aadt_panel.parquet`. Real run: 5,984 placed schools → 5,366 matched
(89.7%) within 1000 m; `school_aadt_panel.parquet` 91,431 rows, `aadt`
known for ~89%. **Not yet wired into `panel`'s `event_study_panel.parquet`**
— left at `msid × release_year` grain deliberately, since matching a
`release_year` to an assessment year needs a nearest-year join that's
`panel/assemble.py`'s job, not this source's.

## `panel` — the final event-study join (`assemble` only)

Joins `assessments` (outcome) + `schools` (spine identity, Cluster A
covariates, barrier-treatment timing) into one analysis-ready table. No
`fetch`/`preprocess` — purely a local join of already-processed artifacts,
kept as its own module (not folded into `schools/assemble.py`) for the same
isolation reason `schools`' own stages are split: editing an outcome-panel
filter should never re-run the geospatial barrier match.

```bash
python -m src.cli florida data panel assemble   # -> data/florida/panel/assembled/event_study_panel.parquet (+ .json)
```

- **Grain**: one row per `(msid, grade, subject, year)` — the `assessments`
  grain. Every join is a **left join anchored on `assessments`**: a school
  with no covariate row or no nearby wall keeps its outcome row, with the
  covariate columns `NA` or the treatment columns `ever_treated_* = False`
  (a real value, not a missing one) — no outcome row is ever silently
  dropped.
- **Treatment timing is four parallel columns, not one.** `schools
  assemble` computes four matching-rigour tiers side by side
  (`_point`/`_same_route`/`_same_side`/`_protected`, algorithms 1–2 / 4 / 5
  and the protected area) rather than
  collapsing to a single "the" treatment definition — `first_treat_year_*`,
  `ever_treated_*`, `timing_unknown_*` for each, plus `event_time_* = year -
  first_treat_year_*` computed here. The analysis layer picks a baseline
  (now `_protected`, the most rigorous) and the others as robustness
  checks. **Update 2026-09-24:** a fourth tier, `_protected`
  (same side *and* beside the wall's own stretch), was added, and
  `_same_side` is now a true side test against one reference line. Before,
  two-thirds of pairs compared signs from different road segments. The
  analysis notebook now uses `_protected`. See
  [`barrier_protection.md`](barrier_protection.md).
- **Real run**: 660,681 rows, 5,039 distinct schools, years 2003–2026.
  `ever_treated` schools (2026-09-24): 513 (`_point`) → 303
  (`_same_route`) → 228 (`_same_side`) → 116 (`_protected`), each tier a
  strict refinement of the last. Before 2026-09-24: 513 → 293 → 221.
- **Traffic (Cluster C) is joined in**: `traffic_roadway_id`,
  `traffic_release_year`, `traffic_aadt`, `traffic_match_dist_m`, via
  `attach_traffic` — a `pd.merge_asof(direction="nearest",
  tolerance=MAX_TRAFFIC_YEAR_GAP=2)` per `msid`, matching each
  `(msid, year)` row to the nearest FGDL release year for that school's
  matched roadway (`traffic assemble`'s `school_aadt_panel.parquet`). A row
  beyond the tolerance keeps `NA` traffic columns rather than a stale match.
  **Real run**: 470,763 of 660,681 rows (71.3%) got a traffic match;
  coverage is markedly lower in the earlier panel (~46% for 2003–2010) than
  the later panel (~83–88% from 2014 on). **Resolved** (2026-09-14): not a
  matching bug (school→roadway matching is 89.7%, year-invariant) — FGDL's
  own `AADT` field was sparsely populated on arterial roads before ~2016
  (~63–64% coverage 2004–2010 vs. ~98–99% 2016 on, checked directly), a
  genuine characteristic of the source. See
  [`traffic/README.md`](traffic/README.md)'s real-run section for the full
  investigation.
- **Road-works (Cluster D) is joined in**: `n_road_projects_active`,
  `road_project_is_wall`, `road_project_is_widening`, via
  `attach_road_projects` — a project's timing is a *year interval*
  (`fiscal_year` or `[start_date, end_date]`), not a single value, so this
  first explodes `road_projects assemble`'s `school_road_projects.parquet`
  pairs to one row per calendar year the project spans, then does a plain
  exact-`(msid, year)` left join — no nearest-value tolerance like traffic's.
  A school-year with nothing logged gets `n_road_projects_active=0` / the
  flags `False` (a real value). **Real run**: **29,515 of 660,681 rows
  (4.5%)** matched an active road project; 30 rows hit the
  `road_project_is_wall` keyword flag, 3,344 the `road_project_is_widening`
  flag — small relative to the full panel, consistent with `road_projects`'
  own coverage gaps (Work Program layers current-window only, Active
  Construction only back to 2009 — see
  [`road_projects/README.md`](road_projects/README.md)).
- **Shocks (Cluster G) is joined in**: `shock_n_declarations`,
  `shock_n_hurricane_declarations`, `shock_any_major_disaster`, via
  `attach_shocks` — the simplest join in this module: `shocks assemble`
  already resolves each declaration to one exact assessment year and
  county, so this is a plain exact `(district_name, year)` left join
  against `assessments`' own district-name column, no per-school
  intermediate file or match tolerance needed. **Real run**: **295,517 of
  660,681 rows (44.7%)** matched at least one declaration that year, 235,152
  (35.6%) a hurricane specifically, 217,658 (32.9%) a major (`DR`) disaster
  — a much higher match rate than `traffic`/`road_projects` since disaster
  declarations are common, county-wide events rather than tied to a
  specific school's roadway proximity (see
  [`shocks/README.md`](shocks/README.md)).
- **Staff (Cluster B) is joined in**: `staff_avg_teacher_salary`,
  `staff_avg_employment_length_months`, `staff_avg_teacher_experience_years`,
  `staff_median_teacher_salary`, `staff_per_pupil_expenditure` (all
  district-broadcast), plus `staff_pct_out_of_field_classes`/
  `staff_n_classes_total` (school-level, no broadcast), via `attach_staff` —
  two exact-key left joins (`(district_name, year)` then `(msid, year)`), no
  tolerance or interval explosion needed. Unlike `shocks`/`road_projects`, an
  unmatched row is left `NA`, not zero-filled — there's no sensible "zero"
  for an average salary. **Real run**: **35,453 of 660,681 rows (5.4%)**
  matched salary/experience, **398,189 (60.3%)** matched per-pupil
  expenditure, **35,308 (5.3%)** matched out-of-field — the two FLDOE
  workbooks' low match rate reflects only assessment-year 2025 being loaded
  so far (a live Internet Archive outage paused the historical backfill
  mid-verification, see [`staff/README.md`](staff/README.md)), not a join
  bug; per-pupil expenditure's much higher rate reflects its full 1995-2020
  CCD coverage.
- **Neighbourhood (Cluster F) is joined in**: `nbhd_median_household_income`,
  `nbhd_poverty_rate`, `nbhd_pct_owner_occupied`, `nbhd_pct_bachelors_plus`,
  `nbhd_pct_moved_last_year` (ACS, tract), `nbhd_zhvi` (Zillow, ZIP), via
  `attach_neighbourhood` — two exact `(msid, year)` joins, no tolerance
  needed since `neighbourhood/assemble.py` already resolved the
  point-in-polygon school->tract/ZIP match ahead of time (the only Florida
  source using polygon containment rather than a nearest-roadway or name
  match). **Real run**: **449,178 of 660,681 rows (68.0%)** matched ACS
  demographics (0% for 2003–2008, before ACS5 existed; 99–100% for
  2010–2024; 0% for 2025–2026, not yet published — a real coverage shape,
  not a bug) and **651,266 (98.6%)** matched a ZHVI home-value figure
  ($25.9k–$3.1M, median $216.6k — realistic Florida range). The Census Data
  API required a user-supplied key to reach this point (a real 2026-05
  policy change — see [`neighbourhood/README.md`](neighbourhood/README.md)).
- **Known gap:** still a **first-pass panel** for the remaining covariate
  module — see the domain table above and [`covariates.md`](covariates.md)
  for `air_quality` (explicitly non-baseline, the only Florida covariate
  cluster with no implementation yet). Treat it as sufficient for a
  first-pass / robustness-limited specification, not the paper's baseline
  spec, until that exists too.

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

- `list-years` prints the results-page registry (spring years **2003–2026**,
  minus the COVID gap year 2020 — confirmed 2026-09 that the same
  `results/<year>.stml` page pattern covers the FCAT 2.0 years 2011–2014, not
  just FSA/FAST; 2003–2010 plain FCAT uses a different, also-confirmed
  directory-per-year archive pattern, `archive/fcat/scores-reports/<year>/`)
  plus the pre-2003 FCAT archive hub URL (not yet a fetch target — existence
  itself unconfirmed), and scans `data/florida/assessments/raw/` for what has
  been collected.
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

Integrity checks run at import (all 231 pass for 2015-2026; the 204 FCAT /
FCAT 2.0 files (2003-2014) passed the same checks via
`organize_fldoe_downloads.py`, extended to also recognize the 2004-05
Science files' Excel-HTML export format rather than flag them as blocked):

- Every file is a real OLE2 `.xls` binary, or a recognized Excel-HTML export —
  no HTML/403 error page saved under an `.xls` name.
- No two files share a sha256 — so no link resolved to the wrong file
  (a district report, or a prior year's copy).
- Live in-sheet titles spot-checked across 2015/2019/2022/2023/2025/2026 — year
  and subject in the sheet match the filename.

### 2011–2014 (FCAT 2.0) — collected and merged (2026-09)

`results/2011.stml` … `results/2014.stml` turned out to be live on the exact
same page pattern as 2015–2026 (confirmed by web search after the shared.py
code wrongly assumed a differently-structured archive) — no new fetch code
needed, just the same manual-download workflow one regime earlier. Pulled with
a Claude-for-Chrome browser session (same bot-wall workaround as 2015–2026),
organized into `raw/<year>/` + `SOURCE_MANIFEST.tsv` by
`organize_fldoe_downloads.py` (one-off script, not in the repo — driven by 4
`SOURCE_MANIFEST_<year>.tsv` drop files).

Per-year counts (EOCs phased in: Algebra 1 from 2011; Geometry + Biology 1
from 2012; U.S. History from 2013; Civics from 2014 — `EOC_FIRST_YEAR` in
`shared.py`):

| Year | ELA | Math | Science | EOC | Total |
|---|---|---|---|---|---|
| 2011 | 8 | 6 | 2 | 0 (Algebra 1 EOC had no school-level file that year — district/state only) | 16 |
| 2012 | 8 | 6 | 2 | 3 (ALG1, GEO, BIO1) | 19 |
| 2013 | 8 | 6 | 2 | 4 (+ USHIST) | 20 |
| 2014 | 8 | 6 | 2 | 5 (+ CIVICS) | 21 |

FLDOE labels the ELA-equivalent test "Reading" in these years, renamed to the
canonical `FL<year>_ELA_G<NN>_school.xls` on import like every other year.

**Two real parsing bugs surfaced by the first FCAT 2.0 import** (the
wide-standard/science-legacy layout detection had only ever been exercised on
2015–2026 files):

1. **2011 ELA/Math workbooks carry two scale-score columns**, `Mean FCAT
   Equivalent Developmental Scale Score` and `Mean FCAT Equivalent Scale Score
   (100-500)` — both matched `_norm_col`'s original `"mean" in s and "scale
   score" in s` rule, and the column-collection loop silently kept whichever
   came first (the Developmental one, range ~1000-2000), producing
   `mean_scale_score` values ~8x too large for 2011 only. Fixed: `_norm_col`
   now tags the developmental variant separately
   (`mean_scale_score_dev`); `parse_sheet` prefers the non-developmental
   column when both exist, falls back to the developmental one when it's the
   *only* scale-score column present (true for 2012-14, where FLDOE reports
   just `Mean Developmental Scale Score` as the sole/native score — despite
   the name, that one *is* the usable column there). Both 2011 columns are
   explicitly "**FCAT Equivalent**" — a one-year crosswalk onto the legacy
   (pre-2.0) FCAT scale for transition continuity, not FCAT 2.0's own native
   per-grade scale. So even after picking the right 2011 column, its raw
   `mean_scale_score` is **not** on the same scale as 2012-14's native one —
   flagged via a new `fcat_equivalent_2011` column (same pattern as
   `retrofitted_2015` below), not silently blended into the `"FCAT 2.0"`
   regime. The within-year z-score (`z_mss`/`z_mss_w`) is unaffected either
   way since it's computed fresh per `year × subject × grade` regardless of
   which raw scale underlies it.
2. **`FL2011_MATH_G07_school.xls` appends a second, partial pass** over
   districts 59-75 after the full state run — a late-district resubmission
   FLDOE appended instead of replacing in place (confirmed: only that tail of
   districts repeats, each with different `Number of Students` / scores the
   second time, not an identical copy). `parse_sheet` now does
   `drop_duplicates(subset="msid", keep="last")` per sheet, same convention as
   `schools/preprocess.py`'s `drop_duplicates(..., keep="last")`. Checked: the
   only file of the 76 with this issue.

Both fixes are covered by `test_assessments_preprocess.py` (`test_regime_map`
FCAT 2.0 cases) and verified by re-parsing all 76 FCAT 2.0 files cleanly and
re-running the full merge (see `preprocess` numbers below).

### 2003–2010 (plain FCAT) — collected and merged (2026-09)

Confirmed (web search) that this era is genuinely NOT on the `results/<year>.stml`
pattern — it lives at `archive/fcat/scores-reports/<year>/` (a directory-style
archive page, 2003–2010 only; no evidence 1998–2002 is digitized anywhere on
fldoe.org). Same manual-download workflow otherwise: pulled via a
Claude-for-Chrome session, organized with the same `organize_fldoe_downloads.py` /
`SOURCE_MANIFEST_<year>.tsv` pattern as FCAT 2.0. No EOCs in this era
(Algebra 1 etc. started in 2011) — Reading, Math, Science (grades 5 & 8) only,
16 files/year × 8 years = 128 files. FCAT-era Writing (grades 4/8/10) was
skipped, matching the exclusion rule used for every other era.

**Four more real parsing issues, all found by actually running the parser
against these files (every prior layout assumption had only ever been
exercised on 2011–2026 data):**

1. **2004–05 Science school reports are SAS-generated "Excel HTML" exports**,
   not OLE2 binaries, despite the `.xls` extension (Excel opens them fine
   either way — this is a real FLDOE export quirk, not a bot-block page; the
   organize script's OLE2-magic-byte integrity check initially flagged these
   4 files as blocked downloads until it learned to recognize the
   `ProgId content=Excel` HTML-export marker too). `pd.read_html` produces the
   same header-less grid shape as `pd.ExcelFile(...).parse(0, header=None)`,
   so `parse_workbook` now sniffs the real file format (OLE2 magic bytes vs.
   not) and dispatches to the matching reader — everything downstream
   (header detection, column mapping) is unchanged either way.
2. **2004–07 grades 4–10 label the school-name column just `"School"`**, not
   `"School Name"` — the exact-match rule in `_norm_col` missed it entirely
   (`KeyError: 'school_name'`). Fixed by accepting the bare label too.
3. **2003 grades 4–10 have NO header text at all for the District/School
   NUMBER columns** — only bare `"District"` / `"School"` (meaning the *name*
   columns), and merged header cells shift where that text lands
   column-to-column inconsistently across files, so position relative to the
   label can't be trusted. The underlying data is always laid out
   `[district_number, district_name, school_number, school_name]` in the
   first 4 columns regardless (confirmed across multiple files) — `parse_sheet`
   now detects this template (bare `"district"` + `"school"` cells
   co-occurring with a scale-score label) and uses that fixed positional
   layout instead of hunting for a label that may not exist.
4. **The STATE TOTALS row is sometimes missing pieces of its own identity**:
   some files leave its `school_name` cell blank (no `"RESULTS FOR GRADE"`-
   style placeholder), which the `school_name.notna()` filter was silently
   dropping the row for; 2006–08 Math grade 3 additionally leaves
   `district_number`/`school_number` blank (not even `"00"`/`"0000"`) on that
   row. Fixed by detecting the totals row from `district_name` text alone
   (`str.contains("STATE")` — no real Florida county name contains "state")
   and filling blank IDs to the usual `"00"`/`"0000"` so `msid` still resolves
   to `"000000"`. Before this fix, 17 of the 435 files across the whole panel
   (not just 2003–10) were silently missing their single STATE TOTALS
   provenance row; now `state_total_rows == n_files` exactly, for every year.

A fifth thing that looked like a bug but isn't: **2003–05 Science rows have no
achievement-level percentages at all** (`pct_l1..pct_l5`, `pct_level3_plus` all
blank) — the raw cell for those columns literally reads `"To Be Determined"`,
and the HTML files' own footnote says *"Science Achievement Levels have not
been determined"*. FLDOE hadn't yet set Science cut scores this early. This
isn't suppression or a parsing gap — the data genuinely doesn't exist — so the
two achievement-level consistency checks in `build_assessments_table` (`L1..L5`
sum ≈100, `L3+L4+L5 == pct_level3_plus`) now exclude rows with no level data
at all from their denominator, rather than counting an all-NaN row (which
pandas `.sum()` silently turns into 0) as a violation.

All five issues are covered by new tests in `test_assessments_preprocess.py`
and verified by re-parsing all 128 plain-FCAT files cleanly and re-running the
full merge (see `preprocess` numbers below): 435 files total (2003–2026,
skipping the 2020 gap year), 661k rows, 5,039 distinct schools, both
achievement-level consistency checks back at 1.0, `state_total_rows == n_files`
for the first time across the whole panel.

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
  `regime` (`FCAT` / `SSS Science` · `FCAT 2.0` · `FSA` / `FAST` · `FSA` /
  `B.E.S.T.` · `NGSSS Science` · `NGSSS EOC`), `retrofitted_2015`,
  `fcat_equivalent_2011`, `district_number` / `district_name` / `school_number` /
  `school_name`, `is_state_total`, `suppressed`, `n_students`,
  `mean_scale_score`, `pct_level3_plus`, `pct_l1..pct_l5`, `source_file`, and the
  primary outcome **`z_mss` / `z_mss_w`** — the school mean scale score
  standardised within each `year × subject × grade` cell (unweighted /
  `n_students`-weighted), which differences every regime scale break (FCAT ->
  FCAT 2.0 -> FSA -> FAST/B.E.S.T., plus the 2011-internal FCAT-equivalent
  break) out.
  Nullable dtypes, so suppression / state-total `NaN`s round-trip. One
  `STATE TOTALS` row per file is kept and flagged (`msid == "000000"`),
  excluded from the z-score moments.
- **`assessments.json`** — provenance + validation sidecar: years, file count,
  row / school counts, rows by subject, suppressed share, and the
  achievement-level consistency checks (`L1..L5` sum, `L3+L4+L5 ==
  pct_level3_plus`).

Current run: **435 files → 661k rows, ~5.0k distinct schools** (years 2003-2026,
skipping 2020), suppressed share ≈ 0.10, both achievement-level consistency
checks at 1.0, `state_total_rows == n_files` exactly.
`src/experiments/florida/assessments.ipynb`
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
