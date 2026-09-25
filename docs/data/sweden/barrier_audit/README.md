# `barrier_audit`: manual side audit of noise barriers

**Status (2026-09-25): phases 0-2 done.**
- The device check passed on the reviewer's laptop.
- The app (0.3.0), exporter, `import`, `preprocess` and the `manual` side
  method are built and tested. Since 0.3.0, road tasks can open Google
  Street View (key G, see [below](#street-view-for-road-barriers-app-030-built-2026-09-25)).
- The pilot is complete: 35 answers, 16 manual sides, in the build.
- The batch-A zip (`protected`, 229 tasks) was re-exported after the §7.6
  rebuild, then rebuilt with app 0.3.0 from the same tasks:
  `barrier_audit_protected_20260925.zip`. It has not been sent yet.
- Next: phase 3, batch A.

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
   | G | Street View in a second tab (road tasks only, since 0.3.0) |
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
10. **Long barriers.** The start view is a window of about 150 m, at full
   resolution, around the part of the stretch nearest the paired school.
   A whole 1 km barrier at once makes the wall too thin to see. The
   reviewer can zoom out for context.

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

| group | batch A (`protected`) | later batch B (`same_side`) |
|---|---|---|
| practice (with feedback, excluded from results) | 10 | — |
| target: side unknown | 99 (16 road + 83 rail) | the remaining ~635 |
| validation: blind sample of auto-sided barriers | 40 each of `parallel_road`, `track_offset`, `osm_offset` | top-up if needed |
| double-coded by Felix (for agreement) | 15% random overlap | 15% |

- **Practice tasks** use `osm_offset` barriers whose OSM wall is a tagged
  noise barrier, at least 80 m long, with no second barrier record running
  alongside (within 25 m for half its length), so the green feedback line
  can't be the other record's wall. After each practice task, the app shows
  the OSM wall's position. Practice barriers are excluded from the
  validation sample.
- **Time.** At about 20–30 s per task, batch A (about 230 tasks) is 1.5–2
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
| `task_id`, `batch`, `reviewer` | identity |
| `status` | `aligned` / `both_sides` / `unsure` |
| `reason`, `note` | only for `unsure` (`note` is optional elsewhere) |
| `lateral_m` | signed offset; + = left of the barrier's digitised direction |
| `along_residual_m` | along-road part of the drag (quality check) |
| `zoom`, `seconds_on_task`, `answered_at` | effort and timing |
| `streetview_opens` | times Street View was opened on the task (0.3.0; 0 when absent) |
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
$P import path/to/answers_assistant.jsonl       # checked against the key, copied to raw/<batch>/
$P preprocess                                   # -> processed/manual_sides.parquet + audit_report.json
```

**Batches** (`export.BATCHES`):

| batch | targets | validation per method | practice | double-coded |
|---|---|---|---|---|
| `pilot` | 15 sampled `same_side_unknown` barriers that aren't `protected_unknown` | 5 | 5 | 0 |
| `protected` | all `protected_unknown` (99) | 40 | 10 | 15% |
| `same_side` | all `same_side_unknown` not in an earlier batch | 0 | 10 | 15% |

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
- `n_answers`, `reviewers`, `categories`, `notes`, `stale`, and
  `manual_sign` (against the saved through-line, for the report)

**From answers to one decision per barrier.**
- Each reviewer's last answer per task counts, and practice answers are
  excluded.
- Each answer gets a category: `left` / `right` (aligned, `|lateral_m| ≥
  2 m`), `centre` (aligned, smaller offset), `both_sides`, or its Unsure
  reason.
- `occluded` and `other` abstain. The remaining answers decide if they
  all agree. Otherwise the barrier is a `conflict`, which is reported and
  not used.

**In `build_barrier_references`,** manual answers come first, ahead of
`both_sides`. How each answer is used:

| decision | result |
|---|---|
| `side` (`left`/`right`) | `side_method = "manual"`, sign = `signed_side(through-line, [aligned point])`, the same test `_osm_side` applies to an OSM wall, so no new sign convention. The aligned point is the view centre moved by the mean `lateral_m` along `n`: where the reviewer put the line on the wall. The build used this point instead of the plan's "midpoint of the offset line", which on a long, curved barrier can lie far from the stretch the reviewer looked at. |
| `both_sides` | `side_method = "manual_both_sides"`, sign 0, protected on both sides (`protection.BOTH_SIDES_METHODS`) |
| `centre`, `unsure` (only abstentions), `conflict` | ignored; the automatic method stands |
| `not_visible` | reported, not acted on: `preprocess` lists these barriers (possible data errors or removed walls), and the automatic method stands |

- **Stale answers.** Answers whose key no longer exists in the current
  barrier layer are flagged `stale` and listed by `preprocess`, not
  silently dropped. `build` matches on the key, so they never apply.
- **Re-running.** Adding answers means re-running `barrier-protection build`
  and everything downstream: about 7 minutes.
- **Validation output** (`audit_report.json`):
  - for each automatic method: how its validation barriers were decided,
    and agreement with the manual side (n, share, Wilson 95% interval), plus
    the same for the barriers where Street View was opened
    (`with_streetview`)
  - for double-coded tasks: share of identical categories, Cohen's κ on
    the category, and the median |Δ `lateral_m`|
  - practice results per reviewer
  - `outer_track`: for rail barriers on an outer track (`outer_track_sign`
    in the key), how often the manual side is the one away from the other
    tracks, for targets and validation separately. This decides whether
    `outer_track` becomes a side method
    ([`../barrier_matching.md`](../barrier_matching.md) §7.6).

  To be written up in `barrier_matching.md` once batch A is in.
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
3. **Batch A.** The reviewer onboards with the practice tasks, then does
   the batch. Import the answers, check agreement, re-run
   `barrier-protection build` and downstream.
4. **Decide on batch B**, based on how much the `protected` results moved
   and on the validation accuracy.

## Street View for road barriers (app 0.3.0, built 2026-09-25)

**Why.** Aerial imagery hides a wall under trees, a bridge or its own
shadow (`occluded`), and a thin screen or glass panel can be invisible from
above (`not_visible`). From the road, the same wall is usually obvious.

**What the reviewer gets.** On **road** tasks only there is a **Street
View** button under Both sides (key **G**). It works in the task view and
in the Unsure panel, where a hint suggests it. It opens Google Maps in a
second tab:
`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=<lat>,<lon>&heading=<h>`.
- **No API key, nothing embedded.** This is the public Maps URLs scheme,
  so the app stays standard-library only. Google shows the panorama
  nearest the viewpoint, which for a road barrier is on the road itself.
- **Viewpoint:** the point of the recorded line nearest the current view
  centre, without the reviewer's sideways shift. Panning along a long
  barrier moves it too.
- **Heading:** the line's digitised direction there, as a true azimuth
  (converted through the task's Jacobian, since EPSG:3006 grid north is
  not true north). Looking that way, the wall is on the camera's left
  exactly when it is up in the app.
- **One tab.** `window.open(url, "barrier_streetview")` reuses the same
  tab on every press. A keypress counts as a user gesture, so popup
  blockers allow it. If the tab is blocked anyway, the app says so.

**Rail is left out.** Panoramas are taken from roads, so a rail wall is
rarely in view, or only at an angle from a crossing road.

**How answers use it.** Street View never answers the task by itself. It
tells the reviewer which side the wall is on, and they still line the
overlay up on the aerial photo, or press Both sides. If the wall shows
only in Street View, they move the line to roughly where it stands and
submit. The reviewer README tells them to check the capture date before
concluding that a wall is `not_visible`.

**Record.** Every answer carries `streetview_opens`, how many times G was
pressed on that task.
- `server.validate_answer` checks it: a whole number ≥ 0, and 0 when
  absent, as in 0.2.0 answers.
- `preprocess` keeps it in `audit_answers.parquet`, with 0 for older
  answers.
- Each method in `audit_report.json` → `validation` gets a
  `with_streetview` count (`n_sided`, `agree`).
- Decision rules are unchanged.

**Tests.**
- The `geometry.js` viewpoint and heading are checked in Node against
  shapely and pyproj on real task geometry near Stockholm. The cases are
  east- and west-digitised lines, one just west of grid north (the
  heading wraps to ~359°), and a curve.
- The server tests cover the new field, its default, and invalid values.
- The preprocess test covers the count and the report split.
- **Headless Chrome, unzipped batch-A package on Python 3.9, with
  `window.open` stubbed:**
  - on road tasks, G and the button open the expected URL in the named
    tab, and the heading matches the map bearing + 90° (40.0° vs 40.2°)
  - G works from the Unsure panel, where the hint shows
  - on rail tasks, the button and hint are hidden and G does nothing
  - the count reaches the answer line

## Decisions (2026-09-24)

1. **Imagery service:** start with the public Min karta WMS.
2. **`not_visible`:** reported only, never demotes a barrier.
3. **Double-coding share:** 15%.
4. **Flight year:** all imagery is assumed to be the latest available; no
   year is recorded per answer, and the reviewer gets no year overlay.
