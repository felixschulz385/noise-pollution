# Florida — `traffic` source: an AADT panel from FGDL `rciroads`

**Status: `fetch`, `preprocess`, `assemble` (incl. the current-snapshot
local-intensity scaling), and the `panel/assemble.py` join are all
implemented and run against real data** — see
[Real run](#real-run-2026-09-14),
[Local-intensity scaling](#local-intensity-scaling-aadt_local--implemented-2026-09-14),
and [What's next](#whats-next). The 2003–2010 vs. 2014+ match-rate gap the
panel-level join surfaced is now resolved (root cause: FGDL's own AADT-field
coverage, not a matching bug — see the real-run section below).

## Why this source exists

The project is a staggered difference-in-differences event study of **FDOT
noise-barrier construction on school achievement** in Florida
(`docs/data/florida/covariates.md` has the full design). FDOT sites noise
walls by **modelled noise level**, which tracks traffic volume and
heavy-vehicle share — so a traffic *trend* at a soon-to-be-treated road looks
like a wall effect unless it's controlled for. `covariates.md`'s Cluster C
("Traffic & acoustic exposure") calls this the core confounder set, and the
project's own identification narrative names traffic + road-works as the
priority confounders (ahead of school-composition, staff, air-quality, and
neighbourhood covariates).

## The data, and why it didn't need a new fetch pipeline

`road_network` (`src/regions/florida/sources/road_network/`, fully
implemented — see [`../road_network/README.md`](../road_network/README.md))
already fetches FGDL's `rciroads_<version>.zip` releases, and that layer
carries an **`AADT`** field per roadway segment straight from FDOT's RCI
(Roadway Characteristics Inventory) — flagged in the `road_network` README as
"a head start for the future `traffic` source" back when it was written. One
release's `AADT` is a cross-section, though; a panel needs many releases. The
FGDL archive holds **57 releases**, `jun04` → `jul26` (~3/year;
`road_network.fetch.list_versions()` lists them), so `traffic` gets a
7-per-decade-ish AADT panel almost for free by fetching more of what
`road_network` already knows how to fetch, rather than needing a new data
provider (e.g. FDOT's live "Historical TDA" Open Data Hub layer, which only
covers 5 rolling years, or the much heavier `FTI.mdb` historical database) —
those remain options for extending coverage later (see
[Known gaps](#known-gaps-not-blocking)), not something this first pass
needed.

**`traffic/fetch.py` calls straight into
`road_network.fetch.fetch_road_network`** for each requested version rather
than re-implementing the HTTP/zip download — the two sources share one copy
of a release's raw shapefile under `data/florida/road_network/raw/` if it's
already there (e.g. `road_network`'s own default `jul26` snapshot). What
`traffic` adds: reading the shapefile with `ignore_geometry=True` (attributes
only — this source has no use for ~34 MB of centerline geometry per release),
keeping just `ROADWAY, SEGMENTID, BEGIN_POST, END_POST, YEAR_, FUNCLASSCO,
FUNCLASS, LANE_CNT, AADT, FGDLAQDATE`, and — **by default** — deleting the
extracted shapefile again afterwards (`--keep-road-network-raw` to keep it).
Without that cleanup, fetching all 57 releases just for a handful of numeric
columns would leave ~2 GB of geometry on disk that only `road_network` itself
has a use for (and it already keeps its own single default-version copy
separately).

```bash
python -m src.cli florida data traffic list-versions
python -m src.cli florida data traffic fetch                       # every archived release
python -m src.cli florida data traffic fetch --version jul26 --version jan19
python -m src.cli florida data traffic fetch --limit 5             # 5 most recent only (smoke test)
python -m src.cli florida data traffic fetch --force               # re-fetch even if cached
python -m src.cli florida data traffic fetch --keep-road-network-raw
python -m src.cli florida data traffic preprocess                  # -> data/florida/traffic/processed/aadt_panel.parquet (+ traffic.json)
```

`fetch_traffic_version` is idempotent: re-running `fetch` skips a version
whose `data/florida/traffic/raw/aadt_<version>.parquet` already exists unless
`--force`. `fetch_traffic_panel` (the `--limit`/multi-version entry point)
fetches every requested version and returns per-version status
(`fetched`/`cached`).

## Verified against live data: `segmentid` is not stable across releases

The original plan (before checking) was to keep the panel at the same grain
`road_network.parquet` itself uses — `roadway_id × segmentid` — one row per
release a segment appears in. **Checked against two real releases (`jul26`
vs `jan19`) and rejected**: FGDL re-segments each `ROADWAY` differently
release to release. Of `jul26`'s ~40,357 segments, only **5** shared a
`(roadway_id, segmentid)` pair with `jan19`'s ~26,595 — and even
`begin_post`/`end_post` breakpoints for the same physical stretch of road
shift between releases (one sampled `roadway_id` had 2 segments in `jul26`
but 1 in `jan19`, with different boundaries and different `segmentid`
numbers). `roadway_id` itself, by contrast, **is** stable: 15,471 of 18,373
`jul26` roadway ids (84%) also appear in `jan19`.

So `preprocess.py`'s row grain is **`roadway_id × release_year`**, not
`roadway_id × segmentid`: every release's segments within a `roadway_id` are
aggregated into one row, AADT as the **length-weighted mean** (weight =
`end_post - begin_post`, so a roadway carrying 35,000 AADT for 3 miles and
5,000 for 1 mile averages near 35,000, not the plain mean of 20,000) — kept
alongside `aadt_min`/`aadt_max`/`segment_count`/`length_mi` so a consumer can
gauge how much within-roadway heterogeneity the average is smoothing over.
This also matches the grain `schools/assemble.py`'s `road_id` column already
uses (`roadway_id`, algorithm 3 `road_gated`), so no extra aggregation is
needed once an `assemble` stage joins this to schools.

**Confirmed the aggregate still carries real time variation** (the whole
point of building this panel): comparing the two fetched releases' aggregated
AADT for the 15,471 shared roadways, `jul26` (2026) vs `jan19` (2019) shows a
**+10% median change**, roughly **51%/49% up/down** — consistent with
ordinary traffic growth over 7 years, not measurement noise. `release_year`
(parsed from the version tag, e.g. `jul26` → 2026, not the layer's own,
~16%-sentinel `YEAR_` field) is what the panel uses as its observation year.

## Real run (2026-09-14)

**Full archive fetched**: all 57 releases (`fetch`, no `--limit`), no errors.
Then `preprocess`:

- **272,656 rows** (`roadway_id × release_year`), **20,262 distinct roadway
  ids**, `aadt` known for 142,301 (~52%) — the rest are roadways whose every
  contributing segment had a non-positive/missing `AADT` value that year.
  (Corrected 2026-09-14 — see [Fixed](#fixed-2026-09-14-duplicate-rows-for-years-with-several-fgdl-releases)
  below; an earlier run of this same step produced 878,055 rows because of a
  grouping bug, not because the data changed.)
- **18 distinct `release_year`s, not 23** — FGDL's archive has real gaps, not
  just irregular spacing within a year: `2004, 2006–2011, 2016–2026`.
  **2005 and 2012–2015 have no release at all.** That 2012–2015 gap overlaps
  the FCAT 2.0 era of `assessments` — a real coverage hole for the event
  study's earlier years, not a processing bug (confirmed against
  `list-versions`' own 57-item archive listing).
- Per-`release_year` row counts grow steadily (12.4k in 2004 → ~65–72k/year
  2019–2025, dipping to 55k for the not-yet-complete 2026 release) — FGDL's
  own roadway coverage/segmentation has expanded over time, not a fetch
  problem.
- `data/florida/traffic/raw/` (57 attribute-only parquets): **30 MB total** —
  vs. the ~34 MB **per release** the raw geometry would have cost (57 × 34 MB
  ≈ 1.9 GB), confirming the "delete `road_network`'s raw shapefile after
  extracting attributes" design was worth it.

## Fixed 2026-09-14: duplicate rows for years with several FGDL releases

`preprocess.py` originally grouped by `[roadway_id, release_year, version]`
— which, since `version` determines `release_year`, is really grouping by
`version` alone. FGDL releases more than once a year in recent years (2016+
gets 3-4/year, e.g. `jan26`/`apr26`/`jul26` all map to `release_year=2026`),
so this silently produced one row per *release*, not per *year* as
documented: **231,906 of 272,656 `(roadway_id, release_year)` groups (85%)
had 2-4 duplicate rows.** Surfaced while checking whether the panel join
(below) picks a sensible AADT value — `pd.merge_asof` doesn't error on a
duplicate-keyed right side, it just silently resolves ties via its own
internal order, which isn't something to rely on. Checked the magnitude
before fixing: within-year releases are usually close (median max/min ratio
1.03 across ~136.7k roadway-years with >1 release), but a real ~10% tail
differs by >20%, some far more — worth fixing properly rather than
rationalizing away. **Fixed** by grouping directly by `[roadway_id,
release_year]` (dropping `version` from the group key), pooling every
segment from every release sharing that year into one length-weighted mean
in a single pass — cleaner than averaging several already-computed
per-version means. Output row count dropped from 878,055 to the true
272,656; `version` (singular, ambiguous once multiple releases are pooled)
was replaced with `release_count` (how many distinct FGDL versions
contributed to that row). Re-ran the full pipeline: `school_aadt_panel.parquet`
289,967 → 91,431 rows; the panel-join match rate (below) barely moved
(70.8% → 71.3%) since de-duplication doesn't change whether a match exists,
only which AADT value gets picked for years that had multiple releases.

## Known gaps (not blocking)

- **`release_year` gaps: 2005, 2012–2015 (see above).** Not fixable within
  this data source — FGDL simply didn't publish a release those years. A
  consumer joining this panel to `assessments`/`schools` for those years will
  need to interpolate/carry-forward from the nearest available release (or
  flag those years as traffic-uncontrolled) — a decision for whoever builds
  `assemble`, not resolved here.
- **Coverage starts `jun04`.** FCAT-era years before that (the barrier panel
  goes back to the 1990s) have no FGDL `rciroads` release at all. FDOT's
  `FTI.mdb` (Florida Traffic Information database) is the documented fallback
  for that era (`covariates.md` Cluster C) — not attempted here.
- **No Truck AADT / heavy-vehicle share.** Not present in the `rciroads`
  schema; `covariates.md` names a separate FDOT Truck AADT layer / `FTI.mdb`
  for that.
- **FDOT's live "Historical TDA" layer (5 rolling years, Open Data Hub)** was
  considered and deliberately not used as the primary source — `rciroads`'
  57-release archive already covers more history in one consistent schema;
  the live layer would only be worth adding later as a cross-check or to
  extend past whatever the most recent `rciroads` release is.

## `assemble` — implemented and run (2026-09-14)

`traffic/assemble.py` matches every placed school
(`school_cross_section.parquet`, `geom_source != 'none'`) to its nearest
arterial `roadway_id`, reusing `road_network/linear_ref.py`'s
`arterial_subset`/`nearest_road` — the same helpers
`schools/assemble.py`'s `match_barriers_road` already uses for walls,
pointed at school points instead. Two outputs, kept at their natural grain
rather than exploded together:

- **`school_road_match.parquet`** (`data/florida/traffic/assembled/`) — one
  row per placed `msid`: `roadway_id` (`NA` beyond `--max-dist`, default
  1000 m — same default `schools/assemble.py` uses) + `dist_m`.
- **`school_aadt_panel.parquet`** — `msid x release_year`: a left join of
  `school_road_match` onto `aadt_panel.parquet` by `roadway_id`. A school
  with no roadway match, or a roadway with no AADT that release, keeps its
  row with `NA` traffic columns rather than being dropped.

```bash
python -m src.cli florida data traffic assemble               # REQUIRES schools + road-network preprocess, and this source's own fetch+preprocess
python -m src.cli florida data traffic assemble --max-dist 500
```

**Real run**: 5,984 placed schools → **5,366 matched** (89.7%) to an
arterial roadway within 1000 m, 618 unmatched. `school_aadt_panel.parquet`:
**91,431 rows** (corrected — see the duplicate-release fix above), `aadt`
known for 78,455 (~86%).

**Deliberately left at `release_year` grain, not exploded to assessment
years.** Picking, for a given `(msid, assessment_year)`, the nearest
available `release_year`'s AADT is the final event-study panel's job
(`panel/assemble.py`), not this module's — especially since the archive's
2005/2012–2015 gaps (see [Real run](#real-run-2026-09-14) above) mean
"nearest available" isn't always "same year," and how much of a gap to
tolerate before treating a school-year as traffic-uncontrolled is an
analysis-layer judgment call, not a matching one.

## `panel` join — implemented and run (2026-09-14)

`src/regions/florida/sources/panel/assemble.py`'s `attach_traffic` left-joins
`school_aadt_panel.parquet` onto `event_study_panel.parquet` via
`pd.merge_asof(by="msid" (cast to plain `str` for the merge key — a
parquet-read Arrow-string `msid` on one side and a plain-`object` one on the
other otherwise breaks `merge_asof`'s dtype check), direction="nearest",
tolerance=MAX_TRAFFIC_YEAR_GAP=2)`, adding `traffic_roadway_id`,
`traffic_release_year`, `traffic_aadt`, `traffic_match_dist_m` at the
`(msid, grade, subject, year)` grain. A row beyond the 2-year tolerance keeps
`NA` traffic columns rather than a stale match.

**Real run**: 470,763 of 660,681 panel rows (71.3%) got a traffic match
(after the duplicate-release fix above; 70.8% before — the match *rate*
barely moved since de-duplication changes which AADT value gets picked, not
whether a match exists).
**Coverage is markedly lower in 2003–2010 (~46%) than 2014 onward
(~83–88%)**, with 2011–2013 at an intermediate ~57–58%.

**Resolved 2026-09-14 — root cause confirmed empirically, not a matching
bug.** The originally-suspected explanation (older/closed schools
disproportionately unmatched to a roadway) is **wrong**: `school_road_match
.parquet`'s match rate is msid-level, year-invariant, and high (**89.7%**
of placed schools matched to a roadway) — it cannot by itself produce a
year-dependent coverage pattern. The real driver is on the roadway side:
FGDL's `rciroads` `AADT` field itself was sparsely populated in early
releases. Checked directly:

- Across **all** `rciroads` roadways, the share with a real (non-null)
  `AADT` value: **~9–11%** for releases 2004–2010, **21.8%** for 2011, then
  a step up to **~70–74%** for every release 2016 onward.
- Restricted to schools' own matched roadways specifically (`traffic
  /assemble.py` only matches against `arterial_subset` — major/collector
  roads FDOT prioritizes for counting, so coverage is much better than the
  all-roadway figure but shows the identical step pattern):
  `school_aadt_panel.parquet`'s per-release-year AADT-known rate is
  **~63–64%** for 2004–2010, **75.7%** for 2011, then **~98–99.9%** for
  every release 2016 onward.

This release-level step pattern (63% → 76% → 99%) lines up almost exactly
with the panel-level match-rate pattern (46% → 58% → 82%+); the residual
gap is just the ±2-year `merge_asof` tolerance and the 10.3% of schools
with no roadway match at all. **Conclusion: comprehensive AADT counting for
arterial roads wasn't in place until roughly 2016 — a genuine
characteristic of the underlying FDOT/FGDL source, not a pipeline bug.**
Worth keeping in mind as a possible selection concern for the FCAT era
specifically (pre-2016 `traffic_aadt`, where present, may reflect which
roads FDOT happened to count first) — but the match *rate* itself is no
longer unexplained.

## Beyond the nearest arterial: nearby and shielded-road traffic (2026-09-24)

`traffic_aadt` is the AADT of the school's single **nearest arterial**
roadway. For schools an FDOT wall protects, that is the wall's own
reference roadway only 52% of the time: protected schools sit a median
303m from the shielded road, and a nearer arterial is often picked (median
172m). So `assemble` also writes `school_nearby_aadt.parquet`, and `panel
assemble` adds year-varying columns, using the nearest release year within
`MAX_TRAFFIC_YEAR_GAP` as `attach_traffic` does:

| panel column | meaning | schools with a value |
|---|---|---|
| `traffic_max_aadt_250m`, `traffic_max_aadt_500m` | the highest roadway AADT among all RCI roads (any class) within 250m / 500m of the school, for every school, treated or not | 3,464 / 4,358 |
| `traffic_protected_road_aadt` | AADT on the reference roadway of the FDOT wall protecting the school (`protected_road_id`, the nearest protecting wall's, from `barrier_protection`); NA for schools no wall protects | 114 of 116 protected |

- **Magnitude:** for protected schools, median AADT is 67,710 on the
  nearest arterial, 111,882 for the busiest road within 500m, and 121,940
  on the protecting wall's road. The single-nearest-road control
  understates the shielded road's traffic by about 45%.
- **Use:** only `traffic_max_aadt_*` is symmetric between treated and
  control schools, so only it works as a `csdid` covariate.
  `traffic_protected_road_aadt` describes the treated.
- **Caveat:** values are roadway-wide means, like `aadt`, not
  segment-level.

## Local-intensity scaling (`aadt_local`) — implemented (2026-09-14)

`aadt` (the roadway-wide, length-weighted mean) can be a coarse proxy for a
specific school — a `roadway_id` can span a short urban block or a 57 km
stretch, and checked-against-real-data heterogeneity within a roadway is
real: for the 5,366 matched schools, comparing "nearest segment's own AADT"
(from the one snapshot that has geometry, `road_network.parquet`) against
"roadway-wide mean" showed **17.1% of school-roadway pairs diverge >1.5x,
6.3% diverge >2x**.

True segment-level *history* isn't available — the same finding that forced
the roadway-level grain applies here too: FGDL re-segments each `ROADWAY`
differently release to release, so there's no "the segment near this
school" that's stable across all 57 releases, only within one release's own
snapshot. So `traffic/assemble.py`'s `compute_local_intensity` computes,
from that **one** snapshot only (`road_network.parquet`, whichever version
it was last preprocessed from — read from its own provenance sidecar, not
assumed), each matched school's **local-intensity ratio**: its nearest
segment's own AADT ÷ that roadway's `aadt_panel` mean for the *same*
release year. `build_school_aadt_panel` applies that ratio to every release
year's roadway mean, producing `aadt_local` — a school-specific estimate
alongside the unscaled `aadt` (kept, not replaced).

**This is a deliberate approximation, not true history**: it assumes a
school's position *relative to* its roadway's own average is roughly stable
over time (a much weaker assumption than assuming the roadway-wide *level*
is stable, but still an assumption — e.g. it would miss a new interchange
built right at one school's segment after the reference snapshot).

**Real run**: 5,361 of 5,366 matched schools (99.9%) got a ratio (the
handful that didn't have `nearest_segment_aadt` or the reference roadway
mean unavailable). Wired into `panel/assemble.py`'s `attach_traffic` too —
`event_study_panel.parquet` carries `traffic_aadt_local` alongside
`traffic_aadt`, same 470,763-row (71.3%) match coverage since it's a
deterministic function of the already-matched rows. Distribution of
`traffic_aadt_local / traffic_aadt` across the real panel: median 1.01,
IQR [0.91, 1.19], median absolute deviation from 1.0 is 13.3% — a real,
moderate adjustment, not a rounding-error-sized one.

## What's next

- ~~Explain the 2003–2010 vs. 2014+ traffic-match-rate gap~~ **resolved**
  (2026-09-14, above) — FGDL's own AADT-field coverage, not a matching bug.
- **Truck AADT / heavy-vehicle share** and **pre-`jun04` coverage** remain
  open (see [Known gaps](#known-gaps-not-blocking)).
