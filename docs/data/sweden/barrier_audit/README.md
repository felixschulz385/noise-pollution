# `barrier_audit`: manual side audit of noise barriers

**Status (2026-10-20): `protected` and `national_1`–`_3` answered and
built in; `national_4` and `_5` to do.**
- **Answers** (reviewer `assistant`, 2026-09-30 to 10-18): every task of
  `protected`, `national_1`, `_2` and `_3` (1,394 tasks), imported
  2026-10-20. All panel-school targets (priority tier 1) were in these.
  `national_5` has one stray answer, not imported yet.
- **Result** (after the double coding): 2,827 barriers answered, 2,616
  used by the build (2,468 one side, 148 both sides), 108 not visible, no
  conflicts, 103 decided by Felix's answer. Agreement of the automatic
  methods with the manual side: `osm_offset` 98% (n=165), `parallel_road`
  95% (755), `track_offset` 95.5% (512); answers under 10 s agree as
  often as slower ones.
- **Not visible** (108 barriers: road 44, rail 64) is its own status:
  `audit_decision = "not_visible"` in the barrier references. The side
  stays the automatic one: road 23 `parallel_road`, 18 `unknown`, 3
  `osm_offset`; rail 52 `unknown`, 10 `track_offset`, 1 `osm_offset`, 1
  `bis_sibling`. The status is recorded, not used yet.
- **`outer_track` dropped** (2026-10-20): 99% agreement in band, but 3
  co-located targets were answered Both sides, and the targets now have
  manual sides. See [`../barrier_matching.md`](../barrier_matching.md)
  §7.6.
- **Recheck of co-located walls** (Felix, `serve --tasks`): on the 19
  road tasks the automatic `both_sides` covers, the reviewer had lined up
  one wall in 14; Felix saw both walls in 8 of them, the reviewer's wall
  each time one of the two. On 67 more co-located tasks (mostly rail)
  Felix agreed in 59. His recheck answers now decide
  ([below](#pipeline-integration)).
- **Blind double coding: done** (Felix, 2026-10-20, `serve
  --double-coded`). All 88 double-coding tasks (`protected` 28,
  `national_1`–`_3` 20 each), about 6% of the answered tasks rather than
  the planned 15%. Two in `national_3` (`0ad2367b`, `142acdb8`) Felix had
  first seen as rechecks, so they are not blind and are left out
  (`preprocess.NOT_BLIND`): 86 pairs.
  - same answer 72 of 86 (83.7%), Cohen's κ 0.68 (bootstrap 95%
    0.53–0.82)
  - **where both placed a wall: same side 71 of 73** (Wilson 95%
    0.91–0.99), median |Δ `lateral_m`| 0.76 m
  - the 14 disagreements: 7 whether a wall is visible, 5 one wall vs both
    sides, 2 opposite sides (`national_1` `aefc767a` road, `d2b85ad5`
    rail)
  - by kind: road 40 of 48 identical, rail 32 of 38

  The side is reliable; κ mostly reflects whether a wall is there and how
  many. Felix's answer now decides these disagreements as well
  ([below](#pipeline-integration)). The rebuild changed 11 road and 8 rail
  references. In the panel, `protected` counts are unchanged (road 48, rail 71)
  and one rail school with unknown timing swapped for another. `same_side`:
  road 148 → 147, rail 165 → 167. Grid: road treated 19,196 → 19,148,
  rail 15,338 → 15,341.
- **Still to do:** `national_4` and `_5`.
- **`national_4` and `_5` don't hold up the grid** (counted on the
  2026-10-20 grid). All their barriers are undated, and a cell an undated
  barrier protects has unknown timing, so they can't add a dated treated
  cell. When they come back and the grid is rebuilt:
  - **controls:** 7,077 road and 4,912 rail cells are `side_unknown` only
    because of an undated barrier whose side is unknown. Each becomes a
    clean control or a treated cell with unknown timing.
  - **dated treated cells:** 9 of 10,968 road and 53 of 11,668 rail could
    lose their year, if such a barrier turns out to protect them too.

**Status (2026-09-29): phases 0-2 done; six zips ready, none sent.**
- The device check passed on the reviewer's laptop; the pilot is complete
  (59 answers on 42 barriers, 34 records with a manual side in the build).
- **App 0.7.0** (2026-09-29): Both sides places each wall; walls whose
  records are co-located are one task; a Shift nudge to exactly 2 m no
  longer asks "still on the centre?"; the map start times out with a
  message. See [below](#every-barrier-in-the-country-app-070-2026-09-29).
- **Batch A** (`protected`, 199 tasks, 421 records): the same tasks as
  exported on 2026-09-25, repackaged with app 0.7.0:
  `barrier_audit_protected_20260929.zip` (the 0.6.0 zip was removed unsent).
- **National batches** (2026-09-29): every other barrier in the registers,
  `barrier_audit_national_1_20260929.zip` … `_5_`: 1,989 tasks, 3,608
  records, dated barriers first, by priority, one site after another.
- **Order for the reviewer:** `protected`, then `national_1` … `national_5`.
- Earlier releases: 0.3.0–0.4.0 (infrared, satellite, Street View), 0.5.0
  (one task per wall, type badge), 0.6.0 (whole-wall view), stub records
  hidden; see the sections below.

The app is run by a student assistant (the *reviewer*) on a restricted
university laptop that allows Anaconda but little else. This document is
the design. Where the build refined it, this document has been updated to
match the code.

## Why

Trafikverket draws every barrier on its road or track centreline, and its
`side` attribute carries no signal. The automatic side methods in
`_barrier_reference.py` (see [`../barrier_matching.md`](../barrier_matching.md))
therefore leave many barriers at `side_method = "unknown"`. For the panel
schools (outputs as of 2026-09-24):

| goal | road barriers | rail barriers | schools affected |
|---|---|---|---|
| resolve every `protected_unknown` | 16 | 82 | 16 road / 60 rail |
| resolve every `same_side_unknown` | 210 | 523 | 113 road / 180 rail |

Only a person looking at aerial imagery can settle these. The audit also
gives us something the paper needs anyway: a blind, human-checked accuracy
figure for each automatic method (`parallel_road`, `track_offset`,
`osm_offset`). The pool of already-sided barriers paired with panel schools
has 596 barriers to sample from.

## The task, as the reviewer sees it

```
┌──────────────────────────────────────────────────────────────┐
│ 37 / 230 · rail · concrete · 3.4 m · 562 m · area 4 of 41 ·  │
│ 2 of 5 here · ▬ other barriers                               │
├────┬────────────────────────────────────────────────────┬────┤
│ U  │           aerial imagery (Lantmäteriet)            │ S  │
│ N  │   ────────────────────── other record (orange)     │ U  │
│ S  │   - - - - - - - - - - -  original line (ghost)     │ B  │
│ U  │   ━━━━━━━━━━━━━━━━━━━━━  barrier overlay (moves)   │ M  │
│ R  │                                                    │ I  │
├────┤                                                    │ T  │
│BOTH│                                                    │    │
└────┴────────────────────────────────────────────────────┴────┘
```

- **Start.** The map is centred on the barrier's stretch, and the overlay is
  drawn at the recorded position, which is the road/track centreline. Since
  it sits on the centreline, the overlay says nothing about the side.
- **Aligning.** The reviewer drags the map until the overlay lies on the
  wall in the imagery, then presses **Submit**. With a wall on each side
  they press **Both sides**; if they can't place it, **Unsure**.
- **Result.** The shift they applied is the barrier's real lateral offset
  in metres, and its sign is the side.

### Interaction rules

1. **The barrier runs left to right.** The map is rotated so the barrier's
   local direction points right (east on screen), in its digitised
   direction. "Up" on screen is then always *left of the digitised
   direction*. User rotation is disabled.
2. **Only the sideways part of a drag counts.** For a pan of the map centre
   from `c0` to `c`, the overlay is the barrier line offset by
   `d = (c − c0) · n`, where `n` is the screen-up normal, in metres.
   - The overlay is drawn as a *parallel offset curve*, so curved barriers
     line up along their whole length. A rigid shift would not.
   - Across the road, the overlay stays pinned on screen. Along the road it
     stays fixed in space, so the reviewer can pan along the wall to check
     it without changing `d`.
   - The along-road part of the drag is saved as `along_residual_m`. A large
     value suggests a bad measure range, not a side problem.
3. **Zoom stays centred.** Wheel and pinch zoom work around the map centre,
   so zooming never moves the overlay. Double-click zoom is off.
4. **A ghost of the original line** stays at its recorded position. It
   shows the offset applied so far and gives no side information.
   **Other barrier records** within 300 m (both kinds) are drawn in orange
   at their recorded (centreline) positions, for orientation: a double
   track often has one record per track, each with its own wall. They give
   no side information either.
5. **Keys:**

   | key | action |
   |---|---|
   | ↑ / ↓ | nudge 0.25 m (Shift: 2 m) |
   | Enter | Submit |
   | B | Both sides (walls on both sides of this stretch) |
   | I | switch between the colour and the infrared photo (since 0.4.0) |
   | F | whole wall in view, and back (since 0.6.0) |
   | M | Google satellite in a second tab, north up (since 0.4.0) |
   | G | Street View in the same tab (road tasks only, since 0.3.0) |
   | U | Unsure |
   | 1–3 | pick an Unsure reason |
   | Backspace | back to the previous task |
   | R | reset the offset |
   | Space (hold) | hide the overlay, to see the wall under it |
   | Esc | close a dialog |

6. **Both sides is an answer, not an Unsure reason** (since app 0.2.0).
   It started as Unsure reason 3, but the pilot's first task was a double
   track with a wall on each side, and a confident observation hidden under
   "Unsure" invites lining up one wall instead. It is a separate button
   under Unsure (key B), `status = "both_sides"`.
7. **Unsure needs a reason:**
   - `occluded`: trees, shadow, an image seam
   - `not_visible`: no wall where the stretch is
   - `other`: a note is required

   The reason is one more keypress.
8. **Near-zero offsets.** A submit with `|d| < 2 m` is allowed (a median
   barrier, or a rail wall between tracks), but the app asks for a second
   Enter first, so an accidental Enter can't submit the start position.
   The pipeline treats it as side-unknown (`centre`).
9. **Align the wall's foot or shadow line, not its top.** The imagery is
   not a true orthophoto, so a 3 m wall appears to lean by up to about 1 m
   near image edges. This affects `lateral_m`, not the side.
10. **Long barriers.** The start view is centred on the part of the
   stretch nearest the paired school and fits the whole wall, but no
   coarser than 0.3 m per screen pixel and no finer than a 150 m window
   (since 0.6.0; before, always the 150 m window). A whole 1 km barrier at
   once makes the wall too thin to see, so longer walls start partly in
   view; F shows all of it. See
   [below](#whole-wall-view-app-060-2026-09-25).

### What the reviewer sees in the top bar

The reviewer sees:
- progress and kind (road/rail)
- the area (`area 4 of 41 · 2 of 5 here`, see [Task set](#task-set))
- `material_type` (an earth berm looks nothing like a screen)
- `height_m` and length

They never see:
- the `side` attribute or the automatic `side_method`/sign
- school locations
- whether a task is a validation task

## Imagery

Lantmäteriet's orthophoto WMS, the service behind minkarta.lantmateriet.se.
Tested 2026-09-24:

- **Endpoint:** `https://minkarta.lantmateriet.se/map/ortofoto/`, WMS 1.1.1.
  - GetMap works without login.
  - The capabilities document lists no fees or access limits.
- **Layers:**
  - `Ortofoto_0.16`, `_0.25`, `_0.4`, `_0.5` (colour)
  - `Ortofoto_IR` (infrared, 0.5 m)
  - `*_meta` (flight year) and `*_fs` (image seams)
- **Coverage.** Request `LAYERS=Ortofoto_0.5,Ortofoto_0.4,Ortofoto_0.25,Ortofoto_0.16`
  in one call. WMS draws the layers in order, so the finest available
  resolution ends up on top wherever it exists. This was tested and works.
- **Projections:** EPSG:3006, 3857 and 4326. The map uses 3857 tiles as a
  MapLibre raster source (`BBOX={bbox-epsg-3857}`, 256 px).
- **Flight year: assumed latest, not recorded (decided 2026-09-24).** We
  treat all imagery as the latest available, so answers carry no year.
  GetFeatureInfo is disabled on the service anyway (tested; "WMS request
  not enabled"), and the `_meta` layers exist only as rendered images.
- **Service: the public Min karta WMS (decided 2026-09-24).** This is Min
  karta's own backend, not the official open-data route through Geotorget.
  Our load is small (about 1,000 tasks × about 20 tiles). If it ever
  becomes unavailable, the Geotorget service (account needed) is the
  fallback. Only the tile URL template would change.

## Task set

A **batch** is one exported package. Practice tasks come first. The rest
come **area by area**: tasks whose view centres chain within 2 km form one
area, areas come in random order, and each area is walked nearest-neighbour,
so the reviewer settles one place (e.g. both records of a double track)
before moving on. Groups are mixed within an area, and the reviewer
can't tell the groups apart.

| group | batch A (`protected`) | the national batches (`national_1` … `_5`, 2026-09-29) |
|---|---|---|
| practice (with feedback, excluded from results) | 10 | 4 |
| target: side unknown | 96 records (16 road + 80 rail) in 82 tasks | every other barrier whose side is unknown |
| validation: auto-sided barriers | blind sample, 40 each of `parallel_road`, `track_offset`, `osm_offset` | all of them (a census); 15 per method drawn into `national_1` |
| double-coded by Felix (for agreement) | 15% random overlap | 5% |

The national batches replace the planned batch B; see
[below](#every-barrier-in-the-country-app-070-2026-09-29).

- **Practice tasks** use `osm_offset` barriers whose OSM wall is a tagged
  noise barrier, at least 80 m long, with no second barrier record running
  alongside (within 25 m for half its length), so the green feedback line
  can't be the other record's wall. After each practice task, the app shows
  the OSM wall's position. Practice barriers are excluded from the
  validation sample.
- **Time.** At about 20–30 s per task, batch A (199 tasks) is 1.5–2
  hours of work.
- **Scope.** The exporter builds the set from `schools_{kind}_pairs_network`
  restricted to panel schools. Whether to also include the recovered
  vanished-school pairs is decided at export.

## Deployment on the reviewer's laptop

Constraints: a restricted university device where Anaconda is available.
Conda packages can be installed there too, but the package doesn't need
any: the laptop only serves files and appends answer lines, and every
geometry step runs on our side. Staying on the standard library avoids
creating an environment on the laptop, which could run into the
university proxy.
We should assume none of the following are available: admin rights, git,
Node, the repo, the `data/` folder, the project's full conda environment, or
Stata.

**Design: a self-contained zip that needs only Python's standard library.**
Nothing needs to be installed beyond Anaconda's base Python:

```
barrier_audit_<batch>_<date>.zip
├── README_reviewer.md      short instructions for the reviewer
├── start_audit.bat         Windows: finds Anaconda, runs the app
├── start_audit.command     macOS equivalent
├── barrier_audit/          the app (stdlib only: http.server, json)
│   ├── __main__.py
│   └── static/             index.html, app.js, vendored maplibre-gl.js/.css
├── tasks.json              the blinded tasks (see below)
└── answers/                answers_<reviewer>.jsonl is written here
```

- **Running it.** The reviewer runs `python -m barrier_audit` from the
  unzipped folder, either from Anaconda Prompt or via the launcher.
  - It binds to **127.0.0.1 only**. Localhost-only servers normally don't
    trigger the Windows firewall prompt.
  - It picks a free port if 8765 is taken, then opens the default browser.
- **No geo libraries on the laptop.** The exporter precomputes, for each
  task:
  - the barrier line in lon/lat and in a local metric frame
  - the bearing and the start view
  - the display metadata
  The browser does the offset-curve maths in local metres (a few lines of
  JS). Only numbers come back, and the offset line is rebuilt with shapely
  on our side.
- **Everything is bundled.** MapLibre is copied into `static/`, with no
  CDN. That way a university proxy can't break the page. Only the imagery
  comes from the internet.
- **Answers are append-only.** There is one JSON line per click, flushed
  immediately. Nothing is overwritten, the latest answer per task wins, and
  Backspace plus a re-answer just appends a new line. Closing the app loses
  nothing. On restart it resumes at the first unanswered task.
- **Return path.** The reviewer sends `answers/answers_<reviewer>.jsonl`
  back through a shared OneDrive/SWITCHdrive folder or by email. It is a
  small text file.
- **Startup self-test.** Before the first task, the app shows a green or
  red check for three things:
  - WebGL is available (MapLibre needs it)
  - one imagery tile loads
  - the answers folder is writable
  A red check names the problem, so it can be reported without debugging on
  the device.

### Risks specific to the restricted device

| risk | mitigation |
|---|---|
| no WebGL (old GPU, VDI session, policy) | caught by the self-test. Fallback: Leaflet renders without WebGL but can't rotate, so the app would show the normal as an on-screen arrow and keep the 1-D offset rule |
| university proxy blocks `minkarta.lantmateriet.se` | caught by the self-test. Ask IT to allow the host, or run from another network |
| `.bat` can't find Anaconda | README fallback: open Anaconda Prompt, `cd` to the folder, `python -m barrier_audit` |
| localhost port blocked by policy | unlikely for 127.0.0.1. If it happens, it shows up in phase 0 (below) before any real work |

## Blinding in `tasks.json`

Each task carries only:
- a random `task_id`
- kind, geometry and bearing
- material, height and length
- the other barrier records near the view (`others_lonlat`) and the area
  label (`area`)
- a `practice` flag, plus the practice answer for practice tasks only

The mapping from `task_id` to barrier key, group and automatic answer stays
on our side, in `data/sweden/barrier_audit/packages/<batch>_key.parquet`,
and never goes into the zip.

## Answer record (one JSON line)

| field | meaning |
|---|---|
| `task_id`, `batch`, `reviewer` | identity (one task can cover several records of one wall) |
| `status` | `aligned` / `both_sides` / `unsure` (reasons `occluded`, `not_visible`, `other`, and since 0.5.0 `changes_side`) |
| `reason`, `note` | only for `unsure` (`note` is optional elsewhere) |
| `lateral_m` | signed offset; + = left of the barrier's digitised direction. Both sides (0.7.0): the left wall (> 0), or 0 when the walls weren't placed |
| `lateral_other_m` | Both sides (0.7.0): the right wall (< 0); `null` otherwise, or when the walls weren't placed |
| `along_residual_m` | along-road part of the drag (quality check) |
| `zoom`, `seconds_on_task`, `answered_at` | effort and timing |
| `streetview_opens`, `satellite_opens` | times Street View / Google satellite was opened on the task (0.3.0 / 0.4.0; 0 when absent) |
| `imagery` | the photo shown at submit: `colour` or `infrared` (0.4.0; `colour` when absent) |
| `app_version` | so answers stay interpretable if the app changes |

## Pipeline integration

**Source** at `src/regions/sweden/sources/barrier_audit/`:
- `export.py`: selection, task geometry, key
- `package.py`: zips
- `serve.py`
- `import_answers.py`
- `preprocess.py`
- `shared.py`: paths and `load_manual_sides`
- `app/`: the reviewer app, standard library only (enforced by a test),
  copied into the zip

Commands (`P=python -m src.core.cli.main sweden data barrier-audit`):

```
$P device-check                                 # phase 0 zip
$P export --batch protected                     # tasks + key + zip; --reviewer, --seed, --n-targets, ... override
$P serve --batch pilot                          # the app from the repo, as reviewer "felix"; answers -> raw/<batch>/
$P serve --batch protected --double-coded       # only the batch's 15% double-coding tasks
$P serve --batch national_1 --tasks id1,id2      # only these tasks (a recheck; Felix's answer then wins)
$P import path/to/answers_assistant.jsonl       # checked against the key, copied to raw/<batch>/
$P preprocess                                   # -> processed/manual_sides.parquet + audit_report.json
```

**Batches** (`export.BATCHES`):

| batch | targets | validation per method | practice | double-coded |
|---|---|---|---|---|
| `pilot` | 15 sampled `same_side_unknown` barriers that aren't `protected_unknown` | 5 | 5 | 0 |
| `protected` | all `protected_unknown` (99) | 40 | 10 | 15% |
| `same_side` | all `same_side_unknown` not in an earlier batch (superseded by `national`, never exported) | 0 | 10 | 15% |
| `national` → `national_1` … `national_5` | every register record not in `protected`, without a manual side, not a stub; auto-sided ones as `validation` (a census) | 15 drawn into `national_1` | 4 (in `national_1`) | 5% |

A barrier already in another batch's key is not drawn again for targets
or validation. The seed is fixed (`20260924`), so re-exporting a batch
gives the same task set and task ids.

**Data files** (`data/sweden/barrier_audit/`):
- `packages/<batch>_tasks.json`, `<batch>_key.parquet` and the zips
- `raw/<batch>/answers_<reviewer>.jsonl`
- `serve/<batch>_<reviewer>/`
- `processed/manual_sides.parquet`, `audit_answers.parquet`,
  `audit_report.json`

**Task geometry.** The browser has no projection library, so each task
carries:
- the barrier line in lon/lat and in local EPSG:3006 metres
- the Jacobian of lon/lat with respect to those metres at the view centre
- the tangent `t` and left normal `n` over 150 m around the centre
- the map bearing that puts `t` pointing right

`static/geometry.js` does the offset maths. Both projections are
conformal, so screen-up is `n`.

**`manual_sides.parquet`** has one row per barrier, keyed by `kind`,
`element_id`, `start_measure`, `end_measure`. The key uses the measures, not
`barrier_row`, because `element_id` alone is the road link and
`barrier_row` changes when the barrier layer is rebuilt. Other columns:
- `decision`, `lateral_m`, and the aligned point `aligned_x`/`aligned_y`
- the offset line (EPSG:3006, shapely `offset_curve(lateral_m)`)
- `n_answers`, `n_superseded`, `reviewers`, `categories`, `notes`,
  `stale`, and `manual_sign` (against the saved through-line, for the
  report)

**From answers to one decision per barrier.**
- Each reviewer's last answer per task counts, and practice answers are
  excluded.
- A reviewer who answered the same barrier in several tasks counts once,
  with their latest answer (since 2026-09-25; `n_superseded` counts the
  others). Different reviewers still have to agree.
- Each answer gets a category: `left` / `right` (aligned, `|lateral_m| ≥
  2 m`), `centre` (aligned, smaller offset), `both_sides`, or its Unsure
  reason.
- `occluded` and `other` abstain. The remaining answers decide if they
  all agree. Otherwise the barrier is a `conflict`, which is reported and
  not used.
- **Felix's answer wins** (`preprocess.ADJUDICATOR`, since
  2026-10-20). Where his non-abstaining answer disagrees with the
  reviewer's, his decides alone, and `adjudicated` is set on the row. This
  covers his rechecks (tasks re-served with `serve --tasks` because the
  reviewer's answer looked wrong) and, since the blind double coding the
  same day, the double-coding tasks too. Agreement is measured on the raw
  answers of the double-coding tasks only (not rechecks, not
  `NOT_BLIND`), so the build no longer has to drop a disagreement as a
  `conflict` to keep the measure honest. Conflicts remain possible
  between two reviewers who are not Felix.

**In `build_barrier_references`,** manual answers come first, ahead of
`both_sides`. How each answer is used:

| decision | result |
|---|---|
| `side` (`left`/`right`) | `side_method = "manual"`, sign = `signed_side(through-line, [aligned point])`, the same test `_osm_side` applies to an OSM wall, so no new sign convention. The aligned point is the view centre moved by the mean `lateral_m` along `n`: where the reviewer put the line on the wall. The build used this point instead of the plan's "midpoint of the offset line", which on a long, curved barrier can lie far from the stretch the reviewer looked at. |
| `both_sides` | `side_method = "manual_both_sides"`, sign 0, protected on both sides (`protection.BOTH_SIDES_METHODS`) |
| `centre`, `unsure` (only abstentions), `conflict` | ignored; the automatic method stands |
| `not_visible` | its own status, not acted on: `preprocess` lists these barriers (possible data errors or removed walls), the automatic method stands, and the references carry `audit_decision = "not_visible"` (since 2026-10-20) |

- **Stale answers.** Answers whose key no longer exists in the current
  barrier layer are flagged `stale` and listed by `preprocess`, not
  silently dropped. `build` matches on the key, so they never apply.
- **Re-running.** Adding answers means re-running `barrier-protection build`
  and everything downstream: about 7 minutes.
- **Validation output** (`audit_report.json`):
  - for each automatic method: how its validation barriers were decided,
    and agreement with the manual side (n, share, Wilson 95% interval), plus
    the same for the barriers where Street View or Google satellite was
    opened, or the answer was given on the infrared photo
    (`with_streetview`, `with_satellite`, `with_infrared`)
  - for double-coded tasks: share of identical categories, Cohen's κ on
    the category, and the median |Δ `lateral_m`|
  - practice results per reviewer
  - (until 2026-10-20: `outer_track`, the agreement of rail outer tracks
    with the side away from the other tracks, split by spacing,
    neighbours and recorded distance, with an adoption `verdict`. The
    rule was dropped, and the report no longer scores it:
    [`../barrier_matching.md`](../barrier_matching.md) §7.6.)
- **Later, not in v1.** The manual offset line gives the wall's real
  position, so `protection_zones` could be drawn from it instead of from
  the centreline.

## Phases

0. **Device check (reviewer, about 10 min). Built.** A one-page
   smoke-test zip that runs the self-test only. It confirms Python,
   localhost, WebGL and imagery on the actual laptop before the app is
   built.
   - Build it: `python -m src.core.cli.main sweden data barrier-audit
     device-check`, which writes
     `data/sweden/barrier_audit/packages/barrier_audit_device_check_<date>.zip`
     (about 300 kB).
   - The reviewer runs it and emails back
     `answers/device_check_<timestamp>.json`.
   - Automatic checks: Python version, answers folder writable, not run
     from inside the zip, WebGL 1/2 with the GPU name, one WMS tile
     fetched and decoded (flags a blank image, e.g. a proxy page), the
     rotated MapLibre map drawn with no tile errors, and window size.
   - Manual steps: drag the map, press ↑, confirm the imagery and the red
     line are visible.
   - The sample is a real `osm_offset` road barrier on the E4/E20 south of
     Stockholm.
   - Code: `src/regions/sweden/sources/barrier_audit/`. The shipped app is
     `app/barrier_audit/` (standard library only, enforced by a test), with
     MapLibre 5.24.0 bundled (a single-file classic script that falls back
     to WebGL 1; 6.x is ES-modules-only).
   - Checked here: the unzipped package on macOS's Python 3.9 and in
     headless Chrome, with all ten checks green. The WMS sends CORS
     headers, so MapLibre can fetch its tiles.
   - For phase 1: turn off MapLibre's drag inertia, because a quick drag
     flings the map far away.
   - **Result on the reviewer's laptop (2026-09-24): all ten checks
     passed.**
     - Windows 11, with Anaconda's Python 3.13.9 at
       `C:\ProgramData\anaconda3`.
     - Edge 153 with WebGL 2 on Intel UHD 770 graphics (Direct3D 11).
     - Imagery reachable from the university network: one tile in 0.44 s,
       and the full map drawn in 1.7 s with no tile errors.
     - Window 1912 × 1068 px.
     - Drag, the ↑ key and the visual check all worked.
     - Report: `device_check_2026-09-24T11-37-03-537.json` (in the
       project's Dropbox, `data/barrier_audit/packages/`).
1. **Build. Done (2026-09-24).** The exporter, the app, import and
   preprocess, with tests for:
   - the offset maths: `geometry.js` run in Node against shapely's
     `offset_curve` and `signed_side`
   - the sign convention: a reviewer's offset becomes the right `manual`
     side whichever way the barrier is digitised
   - the append-only resume
   - the decision rules and the report

   Also checked:
   - **In headless Chrome, from the unzipped batch-A package on Python
     3.9:** start checks, left-to-right rotation, ↑/Shift nudges (exact),
     dragging (no fling), practice feedback, the small-offset
     confirmation, the Other note, Backspace, and resuming after a
     reload.
   - **On real data:** for all 50 `osm_offset` barriers in batch A, a
     simulated answer placed on the OSM wall gives the same side as the
     automatic method.
   - **Batch A as exported (2026-09-25, after the §7.6 rebuild):** 229
     tasks (10 practice, 99 targets, 40 per validation method), 33 flagged
     for double-coding. Zip:
     `data/sweden/barrier_audit/packages/barrier_audit_protected_20260925.zip`.
     The 2026-09-24 zip (228 tasks) is superseded and was removed from
     `packages/`. Checked in headless Chrome from the unzipped package on
     Python 3.9: the start checks, the B key and button, the practice
     both-sides feedback, the area label, the orange records, and
     `both_sides` answer lines.
2. **Pilot (Felix, about 30 tasks). Done (2026-09-24).** Tune the window
   size, the nudge step and the Unsure reasons. Check that practice
   feedback is clear. Run `export --batch pilot --no-zip`, then
   `serve --batch pilot`, then `preprocess`.
   - Its findings (wrong OSM matches, twin records, Both sides as an
     answer) led to app 0.2.0 and the §7.6 matching fixes
     ([`../barrier_matching.md`](../barrier_matching.md)).
   - **Never re-export a batch that has answers.** The pilot key was
     re-exported mid-pilot after the rebuild. The new selection drew new
     task ids, and `preprocess` joins answers to the key on `task_id`, so
     the 24 answers already given would have been dropped. They were
     restored into the key from `audit_answers.parquet` (2026-09-25).
     Re-exporting a batch is safe only before any answers come back.
   - **Accidental resubmit (2026-09-25).** `2a7479a1` (rail, 315 m) was
     answered −4.6 m with 0.5.0, then again "aligned" at exactly 0.00 m
     in 6.6 s with 0.6.0, while trying out the whole-wall view. The
     latest answer wins, and 0.00 m counts as side unknown. The −4.6 m
     answer was appended again (same fields, new `answered_at`), so it is
     the latest; the file stays append-only and keeps both.
3. **Batch A.** The reviewer onboards with the practice tasks, then does
   the batch. Import the answers, check agreement, re-run
   `barrier-protection build` and downstream.
4. **Decide on batch B**, based on how much the `protected` results moved
   and on the validation accuracy.

## Beyond the aerial photo (app 0.3.0–0.4.0, 2026-09-25)

**Why.** Aerial imagery hides a wall under trees, a bridge or its own
shadow (`occluded`), and a thin screen or glass panel can be invisible from
above (`not_visible`). The pilot showed the photo is sometimes simply too
coarse to make out the wall. The app therefore offers three more views,
all one key away, in the task view and in the Unsure panel. The Unsure
panel's hint lists the ones that apply to the task.

| key | view | where | tasks |
|---|---|---|---|
| I | **infrared photo** (`Ortofoto_IR`, 0.5 m, same service) | in the app, in place of the colour photo | all |
| M | **Google satellite**, north up, zoom 20 | second browser tab | all |
| G | **Google Street View**, looking along the barrier | the same second tab | road only |

- **Infrared stays in the app,** so the overlay, the offset and the
  answer remain valid on it. Vegetation shows bright red and walls don't,
  so a wall along a hedge or under trees stands out. It is coarser than
  the colour photo (0.5 m vs down to 0.16 m). The top-bar toggle shows
  which photo is on (red when infrared), and the choice carries over to
  the next task.
- **Google views are look-only.** They tell the reviewer which side the
  wall is on, or whether there is one. The line is always placed on
  Lantmäteriet's photo, because Google's terms don't allow deriving
  positions from its imagery. Where the wall shows only in Google's views,
  the reviewer moves the line roughly to it and submits.
  - The links are the public Maps URLs scheme, needing no API key and
    embedding nothing, so the app stays standard-library only.
  - Satellite:
    `https://www.google.com/maps/@?api=1&map_action=map&center=<lat>,<lon>&zoom=20&basemap=satellite`.
  - Street View:
    `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=<lat>,<lon>&heading=<h>`.
- **Viewpoint:** both links use the point of the recorded line nearest the
  current view centre, without the reviewer's sideways shift, so the
  barrier is at the centre of Google's satellite view. Panning along a
  long barrier moves it too.
- **Heading (Street View):** the line's digitised direction there, as a
  true azimuth (converted through the task's Jacobian, since EPSG:3006
  grid north is not true north). Looking that way, the wall is on the
  camera's left exactly when it is up in the app.
- **North arrow.** Google's satellite view is north-up, while the app
  rotates each barrier to run left to right. An arrow in the map's corner
  (rotated by −bearing) shows where north is.
- **One side tab.** `window.open(url, "barrier_lookaround")` reuses the
  same tab for both links on every press, so tabs don't pile up. A
  keypress counts as a user gesture, so popup blockers allow it. If the
  tab is blocked anyway, the app says so.
- **Street View is road only.** Panoramas are taken from roads, so a rail
  wall is rarely in view. Satellite helps rail as much as road.
- **Zoom stays at 19 for the colour photo.** A tile at z19 is ~0.15 m/px at
  59°N, which already matches the finest imagery (0.16 m); z20 would only
  make the server upscale.
- **The reviewer README** says when to use each view and to check Street
  View's capture date before concluding `not_visible`.

**Record.** Every answer carries `streetview_opens`, `satellite_opens` and
`imagery`.
- `server.validate_answer` checks them: whole numbers ≥ 0, `imagery` one of
  `colour`/`infrared`. Defaults when absent: 0, 0, `colour`.
- `preprocess` keeps them in `audit_answers.parquet`, with the same
  defaults for older answers.
- Each method in `audit_report.json` → `validation` gets `with_streetview`,
  `with_satellite` and `with_infrared` counts (`n_sided`, `agree`).
- Decision rules are unchanged.

**Tests.**
- The `geometry.js` viewpoint, heading and both URLs are checked in Node
  against shapely and pyproj on real task geometry near Stockholm. The
  cases are east- and west-digitised lines, one just west of grid north
  (the heading wraps to ~359°), and a curve.
- The server tests cover the new fields, their defaults, and invalid
  values.
- The preprocess test covers the columns and the report split.
- **Headless Chrome, unzipped batch-A package on Python 3.9, with
  `window.open` stubbed (0.4.0):**
  - I shows the infrared layer, and the choice carries over to the next
    task
  - M and G open the expected URLs in the one named tab; on rail, G does
    nothing and M works
  - the Unsure hint adapts to the kind of task
  - the north arrow turns with the bearing
  - the answer lines carry the counts and `imagery`

## One task per wall, and the type badge (app 0.5.0, 2026-09-25)

**Why.** The register splits a wall into pieces wherever an attribute
(height, material) or the road link / track element changes. So a
quarter of all records are under 30 m: 450 of 2,172 road and 496 of 1,829
rail records. In batch A, 54 of 219 tasks were such pieces, 35 of them
under 15 m, hard to make out and each asked separately. Separately, the
pilot showed the reviewer searching for a wall where the record is an
earth berm. Earth berms are 510 road and 219 rail records.

**Chains.** `linear_ref.chain_lines` joins records whose ends meet (within
2 m) and continue in the same direction (turning less than 30°).
- A chain runs the way most of its length is digitised. Each piece
  records its position and whether it is digitised along or against it
  (`chain_orient`).
- Only simple paths are chained. Where a record end meets two others (e.g.
  two records co-located on one stretch) or the pieces close a loop, the
  records stay apart. That is deliberate: co-located records are the
  ambiguous case of the outer-track review
  ([`../barrier_matching.md`](../barrier_matching.md) §7.6).
- **Result:** 896 road records form 305 chains, and 947 rail records form
  295 (up to 23 pieces).
- `barrier-protection build` stores `chain_id` and `chain_orient` in the
  references for later use. Nothing downstream uses them yet.
- **Evidence the pieces share a side:** wherever both pieces at a joint
  have a side from an OSM wall, a manual answer or their own geometry, the
  sides agree, 58/58 road and 35/35 rail joints. That includes 13 joints
  matched to two different OSM walls. Built year agrees at 98% of road and
  92% of rail joints.

**Tasks.** A chosen record's task covers its whole wall, drawn as one line
(`join_chain`).
- The view starts at the point nearest the school of the task's
  highest-ranked record: target, then validation.
- The other pieces aren't drawn in orange, since they are the overlay.
- The key has one row per record. The pieces that weren't chosen join as
  group `chain`, and `task_group` is the task's highest group.
- Each key row carries the point of its own piece nearest the view
  (`center_x/y`) and the task's left normal there (`n_x/y`). The answer's
  offset therefore places every piece's wall.
- `preprocess` draws each piece's offset line on its own left, or on its
  right when it runs against the chain (`chain_orient` −1).
- Practice tasks stay single records.
- **Batch A:** 229 tasks became 195 (185 non-practice), covering 443
  records. The 214 added records are unchosen pieces of the same walls,
  which now get a manual side too. Tasks under 30 m dropped from 54 to 24,
  records with no piece to join. 85 tasks cover several records (up to 23
  pieces, 1.4 km).

**"The wall switches sides."** Adjacent records given sides from the
neighbouring carriageway disagree at 26 of 428 joints, some of which may
be walls that really switch sides. Multi-piece tasks therefore offer Unsure
reason 4, `changes_side`.
- It is its own decision, `changes_side`, not an abstention.
- `preprocess` lists those barriers under `audit_report.json` →
  `changes_side`. They are not used by the build, and go back to one task
  per record in a later batch.

**Validation.** Records answered in one task aren't independent. Each
method in the report therefore also has `n_walls_sided`: the number of
tasks behind its `n_sided` records.

**Type badge.** Each task carries its materials, ordered by length, and a
`type_group`. The app shows the group as a badge at the top left of the
map, with what to look for:

| `type_group` | badge | hint |
|---|---|---|
| `berm` | Earth berm (brown) | Look for a grassy bank, not a wall. Line up the top of the bank. |
| `berm_screen` | Earth berm + screen (brown) | A bank with a screen on top: line up the screen. |
| `glass` | Glass screen (blue) | Hard to see from above: look for its foundation line or shadow. Try I or M. |
| `wall` | Wall: wood / concrete / … (grey) | Line up the foot of the wall or its shadow line. |
| `mixed` | Mixed: … (purple) | The type changes along this barrier. |
| none | Type not recorded | It may be a wall or an earth bank. |

The material moved from the top bar into the badge. The top bar shows the
height (a range for a multi-piece task), the length, and "one barrier in
N register pieces". Tasks exported before 0.5.0 carry only `material`; the
app derives the group from it.

**Tests.**
- `chain_lines`: pieces with a gap and one digitised backwards join in
  order; a 90° turn doesn't join; the chain follows the majority
  direction; co-located records stay apart. `join_chain` gives one
  continuous line.
- Export and preprocess: a wall in three pieces (one backwards) is one
  task with key rows in the right groups, the other record is the only
  orange one, and the type is `mixed` with a height range. One +6 m answer
  puts every piece's aligned point and offset line on the same side.
- The report: `n_walls_sided`.
- **Headless Chrome, unzipped batch-A package on Python 3.9:**
  - the badge and hint for wall, earth berm, glass and mixed
  - a 759 m rail barrier in 18 pieces drawn as one line
  - reason 4 only on multi-piece tasks, and its answer saved

## Whole-wall view (app 0.6.0, 2026-09-25)

**Why.** The 150 m start window showed only part of most walls: in batch
A, 119 of 195 tasks are longer than 150 m (median 221 m, 90th percentile
758 m, longest 1.39 km). The reviewer couldn't see where a wall ends, or
whether it changes sides, without zooming out by hand. The window was also
finer than the photo: 150 m over the ~1,700 px map is 0.09 m/px, while the
imagery tops out at z19, about 0.15 m/px (0.16 m photo).

**What changed.**
- The start zoom fits the whole wall around the start centre
  (`geometry.js` `fitZoom`: the line's extent along t across the screen
  and along n up it, 48 px padding), clamped between the old 150 m window
  and 0.3 m/px. The centre stays on the point nearest the school, since
  moving it would move the offset.
- F (or the "whole wall" button in the top bar) zooms to fit the whole
  wall around the current centre at any scale, and pressed again returns
  to the start zoom. The centre and offset don't change.
- Bent walls look tilted away from the centre: the map is rotated by the
  wall's direction at the centre. The overlay still follows the wall.
- In batch A, 112 of 195 tasks start with the whole wall in view (at that
  map size). The fit is around the start centre, not the wall's middle, so
  an off-centre wall needs a wider view.
- The answer already records `zoom`, so whether zoomed-out answers are
  less reliable can be checked in the validation sample.

**Tests.**
- `fitZoom` (Node): every vertex fits and one axis is tight, for a bent
  wall off-centre, at the start and after a pan.
- **Headless Chrome, unzipped batch-A package, map 1,712 × 972 px:** on
  the first 30 tasks, the 23 walls up to 270 m start fully in view
  (0.09–0.29 m/px); the seven longer ones (490–939 m) start at 0.3 m/px with 35–88%
  in view, F shows 100% (0.44–0.95 m/px), and F again returns to the start
  zoom exactly.

## Stub records (2026-09-25)

**Why.** Pilot task `9376dc21` showed no line at all: its record is 2 cm
long. It is not an export error. The rail register has 63 records whose
geometry is under 1 m (road: none), most spanning a whole micro-link
(measures 0–1). Their kilometre posts often span a real wall: 11+785 to
12+920 for this one, 1.1 km. That wall's geometry sits on four other
records with the same `bis_object_number` (121 + 42 + 621 + 315 m).
40 of the 63 share their object with longer records. The one-task-per-wall
grouping doesn't join them, because a 2 cm line has no direction.

**What changed.**
- The exporter never picks a record under 1 m as a target, validation or
  practice task (`_barrier_reference.is_stub`). It can still ride along as
  a `chain` piece of a longer wall.
- New side method `bis_sibling` (rail, after every other method, before
  `unknown`): a stub takes the side of its BIS object's other records
  within 50 m if they all agree. Each decided record puts a probe 5 m out
  on its protected side, beside the stub, and the probe's side of the
  stub's own through-line is its vote. A record with walls on both sides,
  or any disagreement, leaves the stub unknown.
- **After the rebuild:** 2 stubs got `bis_sibling`, including the pilot's
  (from `2a7479a1`'s manual side). Of the other 30 unknown stubs, 23 have
  same-object records that are themselves still unknown. Most of those
  are audit targets, so the stubs follow once the answers are in. 7 have
  no same-object record within 50 m. Of the 63, 28 are `track_offset`
  and 3 `osm_offset`, both kept.
- **Batch A re-exported** (no answers yet, so safe): 195 → 199 tasks, 443 → 421 records.
  - 3 stub targets and 2 stub validation tasks are gone.
  - A new draw of validation barriers gives 107 validation tasks (was
    100).
  - Rail targets with an `outer_track_sign`: 66 records in 58 tasks (was
    68 in 60).

## Every barrier in the country (app 0.7.0, 2026-09-29)

**Why.** Downstream analyses need the side *and* position of every barrier
in the registers, not only those beside panel schools. The planned batch B
(`same_side`) would also have re-asked 110 records already in batch A and
113 whose barrier side was known (schools past the barrier's end are
`same_side_unknown` whatever the barrier's side).

**Scope.** Every register record (road 2,172, rail 1,829), except batch A's
421, the 16 with a manual side from the pilot, and the 49 rail stubs under
1 m (they take their side from their BIS object). Unknown side → `target`;
an automatic side → `validation`, so every automatic method is checked in
full, and `parallel_road` / `both_sides` barriers get a position for the
first time. Only Trafikverket's registers: OSM maps ≥ 350 noise barriers
(50 km) more than 100 m from any register barrier, e.g. along municipal
streets; they are not in the audit.

**Walls and co-located records.** The export uses the new joining rule
(`../barrier_matching.md` §7.8): road 1,581 → 1,438 walls, rail 1,177 →
902. Walls whose records are co-located (a wall on each side of a road,
both drawn on its centreline) are one task: the longest is drawn, the
others show on the line, and the top bar and type card say "2 barriers
registered on this line: check both sides". 133 national tasks are such
groups. 82 road and 65 rail records share their key with a co-located
partner, so an answer applies to both (`preprocess._record_line` takes
each record's own direction).

**Both sides places each wall (0.7.0).** B → line up one wall, Enter (a
blue line marks it, the view returns to the centre) → line up the wall on
the other side, Enter. A second wall on the same side is refused. B again:
both sides without positions; Esc cancels. The answer has `lateral_m` (> 0,
left) and `lateral_other_m` (< 0); `manual_sides.parquet` gets both, and a
MultiLineString of the two offset lines (curved walls can add parts).

**Priority, timing, sites.** Each task gets a `priority_tier`
(`export.PRIORITY_TIERS`) and `timed` (a record has a build year):

| tier | meaning |
|---|---|
| 1 | side unknown, beside a panel school on its route |
| 2 | side unknown, near another school |
| 3 | side unknown, no school near |
| 4 | side known, no position (`parallel_road`, `both_sides`) |
| 5 | position known from OSM or the rail register (re-measured) |

Dated tasks come first (tiers 1 → 5), then undated ones (1 → 5). Walls
within 30 m of each other for half the shorter one's length (both sides of
a road, both carriageways, neighbouring tracks) form a **site**: its tasks
come one after another, along the site, with the priority of its best
task. 1,689 sites, 247 of more than one task. 15 tasks each of
`parallel_road`, `track_offset` and `osm_offset` are drawn into the first
class, mixed in by area, so `national_1` alone gives a blind accuracy check.

**Five batches** of about 400 tasks, cut between sites:

| batch | tasks | dated | contents |
|---|---|---|---|
| `national_1` | 401 | 381 | 4 practice; dated tiers 1, 2 and part of 3; the validation sample |
| `national_2` | 397 | 393 | dated: rest of tier 3, most of tier 4 |
| `national_3` | 397 | 272 | dated: rest of tiers 4–5; undated tier 1 |
| `national_4` | 397 | 0 | undated tiers 2–3 |
| `national_5` | 397 | 0 | undated: rest of tier 3, tiers 4–5 |

1,042 of 1,989 tasks are dated. 5% of each batch (20 tasks) is flagged for
double-coding. Practice: 4 tasks in `national_1` only.

**Checked (2026-09-29).**
- On the whole register: every record is in batch A or one national task
  (bar stubs and the pilot's), no co-located pair is split across tasks,
  all 247 multi-task sites are served back to back, no site is split
  across batches, and the priority never goes back after `national_1`.
- In headless Chrome from the unzipped `national_1` zip on Python 3.9:
  all 401 tasks with scripted answers (Both sides with both walls, a
  refused same-side second wall, "can't place", Unsure reasons, practice
  feedback "Well done" 4/4, 48 answers at exactly ±2 m without a prompt),
  then `import` and `preprocess` in a scratch data root: 25/25 answers put
  on the OSM wall reproduce `osm_offset`'s side, and all 272 placed Both
  sides rows have a wall on each side of their own line. That run found
  two bugs, fixed before release: a curved wall's offset in several parts,
  and key-sharing records. The repackaged batch A zip ran 40 tasks on
  0.7.0, including Both sides placements.

## Decisions (2026-10-20)

1. **`not_visible`:** its own status (`audit_decision` in the references),
   still never demotes a barrier. This updates decision 2 below.
2. **`outer_track`:** dropped, not a side method.
3. **Next:** `national_4` and `_5`. The grid doesn't wait for them (see
   the status above). The blind double coding is done (κ 0.68; the same
   side 71 of 73 times).
5. **Double-coding disagreements:** Felix's answer decides, as on his
   rechecks (decided after the double coding, the same day).
4. **Construction years:** a separate source is being looked for. OSM walls
   outside Trafikverket's registers are ignored for now
   ([`../barrier_protection/README.md`](../barrier_protection/README.md),
   "Known gaps").

## Decisions (2026-09-24)

1. **Imagery service:** start with the public Min karta WMS.
2. **`not_visible`:** reported only, never demotes a barrier.
3. **Double-coding share:** 15%.
4. **Flight year:** all imagery is assumed to be the latest available; no
   year is recorded per answer, and the reviewer gets no year overlay.
