# Florida — data sources

Index of every data domain in the Florida pipeline. Maintained by hand from
`src/regions/florida/cli.py` and the modules under
`src/regions/florida/sources/` until the per-region source registry
(template `docs/02`, see also [`../../design/01-multi-region-layout.md`](../../design/01-multi-region-layout.md))
is in place.

| Domain | Steps implemented | Prerequisites | Module |
|---|---|---|---|
| `noise_barriers` | `list-versions`, `fetch` (`preprocess` not written yet) | — | `src/regions/florida/sources/noise_barriers/` |
| `assessments` | `list-years`, `fetch` (manual-download orchestrator; **raw stage complete 2015–2026**, 231 files; `preprocess` TBD in notebook) | `master_file` crosswalk | `src/regions/florida/sources/assessments/` |
| `master_file` | `fetch` (real download from the FLDOE EDS app; `preprocess` TBD in notebook) | — | `src/regions/florida/sources/master_file/` |
| `schools` | none yet — NCES EDGE geocode, manual download (`data/florida/schools/`); **may be unnecessary**, see `master_file` | — | _not created_ |

On-disk output lands under `data/florida/<domain>/{raw,processed,assembled}/`.

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
- CRS EPSG:3087 (Florida GDL Albers, metres); `jul26` has ~1 880
  `MultiLineString-M` features across ~63 columns (the schema drifts between
  releases — e.g. `jul26` dropped `TBR` / `BEGIN_POST` and added `PERIMETER
  WALL` as a `TYPE`). The zip's internal layout also varies (`.gdb` at the root
  in `apr23`, one folder down in `jul26`); `fetch` handles both. See the
  notebook for the field dictionary and cleaning rules a future `preprocess`
  step will crystallize.

```bash
python -m src.cli florida data noise-barriers list-versions
python -m src.cli florida data noise-barriers fetch                 # -> data/florida/noise_barriers/raw/noise_barriers_jul26.gdb
python -m src.cli florida data noise-barriers fetch --version apr23 --keep-zip
```

**TODO (needs live data):** row/feature counts, date coverage and on-disk sizes
once a full run completes; `preprocess` (translate + clean to GeoParquet).

## `assessments` — `fetch` only; `preprocess` deferred to the notebook

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
- **2015 has no scale-score scale of its own.** The sheets state *"2015 FSA
  scores were reported to students as percentile scores."* Treat 2015 ELA/Math
  as its own regime break, or keep only the statewide z-score for that year and
  drop it from any raw-scale-score robustness series.
- **2025 file host changed** to `https://www.fldoe.org/file/5668/…` from the
  older `…/core/fileparse.php/5668/urlt/…` pattern. Cosmetic — the payloads are
  the same `.xls` format. Recorded per file in `SOURCE_MANIFEST.tsv`.
- Every file is the legacy **`.xls` (OLE2)** format, so `preprocess` will need
  `xlrd >= 2.0.1` (`pandas.read_excel(..., engine="xlrd")`). It is **not** in
  `environment.yml` yet — add it when the parsing step lands. `fetch` itself
  never opens the workbooks, so the CLI does not need it.

### `preprocess` — deferred

Parsing / harmonisation is **not implemented**; it is being worked out in
`src/experiments/florida/`. When settled it should produce a tidy
school × year × grade × subject Parquet with the within grade × subject × year
z-score outcome and a stable join key (`NCESSCH`, via the `master_file` /
`schools` crosswalk described above), then move into a `preprocess` step here.

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
