# `road_network`

NVDB's (Nationell Vägdatabas) national road-traffic network (`Vägtrafiknät`)
-- the base geometric road network Sweden lacked entirely before 2026-09-15,
needed for `schools`' matching algorithms 4/5 (`same_route`/`same_side`).
See [`schools/README.md`](../schools/README.md)'s "Algorithms 4+5" section
for how it's actually used and the real run's findings.

**Status (2026-09-15): `preprocess` implemented and run against real data.**
No automated `fetch` -- manually downloaded via Lastkajen (same portal/
credentials as `noise_barriers`), same "place the file, I read it" pattern
as the rail `network` source's own manual download.

## How to get it

1. Log into <https://lastkajen.trafikverket.se> (credentials in
   `setup/secrets/trafikverket_lastkajen_username`/`_password`).
2. Order/download the **NVDB Vägtrafiknät** Sverigefiler package, GeoPackage
   format. Confirmed live 2026-09-15 that a whole-of-Sweden order exists as
   one of six "Sverigefiler utvalda NVDB-data" packages (the other five --
   `funkvägklass`, `hastighetsgräns`, `slitlager`, `vägbredd`,
   `väghållare` -- are thematic attribute layers that join to this same
   network by linear reference; **not downloaded**, not needed for the
   current matching algorithms).
3. Unzip and place under `data/sweden/road_network/raw/` (any nested
   folder structure is fine -- `road_network/shared.py::default_road_network_gpkg`
   finds the `.gpkg` by glob, not a fixed filename, since Lastkajen bakes a
   per-order id into the name).

The real file: **1.4 GB, single layer `NVDB_DK_O_88_Vagtrafiknat`,
2,497,041 rows, EPSG:3006**.

## Real schema, checked live (not assumed)

`ELEMENT_ID, VALID_FROM, VALID_TO, START_MEASURE, END_MEASURE,
EXTENT_LENGTH, Nattyp` + geometry (`LineString`, sampled 5,000 rows, no
`Multi`-geometry seen). **No route/road-number field** -- unlike rail's
`Bandel`, this product is NVDB's bare geometric network; a road-number
attribute would live in a separate NVDB product not downloaded this
session. This does not block `same_route`/`same_side` (see
`schools/README.md`) -- those are purely geometric (corridor containment +
signed offset) decisions; a route label was only ever informational, never
load-bearing, even for rail.

- **`Nattyp`** (network type): `bilnät` 2,080,277 (83%, car/vehicle
  network) / `cykelnät` 214,150 (9%, bicycle) / `gångnät` 202,614 (8%,
  pedestrian). `preprocess` defaults to `bilnät` only -- noise barriers sit
  along vehicle roads, not bike/foot paths. This is the road analogue of
  rail's `Status == "Öppen"` filter.
- **`VALID_TO`**: 2,496,848 of 2,497,041 (99.99%) are the "always valid"
  sentinel `99991231` -- almost the entire layer is current; `preprocess`
  filters on it anyway for correctness/consistency with the rest of the
  pipeline, though it barely changes row counts (~193 dropped).
- **`ELEMENT_ID`** is not a unique row key (211,598 of 2,497,041 rows,
  8.5%, are duplicated -- lower than rail's 83.5%, but still not 1:1).
  Matches the same caution already documented for rail and for
  `noise_barriers`' own `element_id`.
- **`EXTENT_LENGTH`**: median ~46m, max ~130 km -- an even more extreme
  long-segment case than rail's 13 km max, so the corridor flood-fill's
  seed-segment trimming (`_linear_ref.py::corridor_geometry`) matters even
  more here.
- **No absolute route-km reference** (no `Bandel`-style field). `km_from_m`/
  `km_to_m` in the processed output are **local to each row's own
  geometry** (`0` to `extent_length_m`), not a nationwide position -- fine
  for matching (which only needs `line.project()` + local begin/end to
  rescale a 0-1 fraction), just not comparable the informational way rail's
  real km position is.

## `preprocess` -- real run 2026-09-15

```bash
python -m src.cli sweden data road-network preprocess   # defaults to --network-type bilnät
```

Reads only the requested `Nattyp` via GDAL's own SQL `where` filter
(reading all 2.5M rows attribute-only takes ~15s; the filter avoids paying
that cost for the ~420k bike/pedestrian rows this source doesn't need),
drops non-current rows, renames columns to the same convention rail's
`network_tracks.parquet` uses. **Real run**: 2,080,277 rows read -> 2,080,116
current -> `data/sweden/road_network/processed/road_network.parquet`
(689 MB, 1,934,567 distinct `element_id`).

## Real finding while using this for algorithm 5: road barrier geometry is centerline-coincident, not offset

Found while matching schools -- see [`schools/README.md`](../schools/README.md)'s
"Road `same_side`" section for the full writeup. Short version:
`noise_barriers`' road barrier `LineString`s share exact vertices with
this network's own geometry (confirmed by direct coordinate comparison),
meaning the barrier's geometry is not an independently surveyed wall
position -- it reads as a copy of a stretch of a specific carriageway's
own reference line. This makes the naive *signed-offset* side derivation
(rail's own method) unusable for road (measures `0.0` offset for 99.8% of
matched pairs) even though `same_route` (corridor containment) works fine.
Rail does not have this problem (checked directly, not assumed) -- rail
barrier geometry is genuinely offset from the track.

**Fixed 2026-09-23, not via the offset method.** NVDB's own spec for this
product states the reference line "follows the outer lane on a divided
road" -- each carriageway of a divided road gets its own separate line.
That reframes the centerline-coincidence finding above: it isn't that
road barriers carry no side information, it's that they're snapped onto
one *specific* carriageway's line, and a divided road's other carriageway
is right there as a second, independently-digitized line 100% of the time
NVDB actually splits the road (confirmed geographically: reverse-geocoded
sibling-pair locations landed on real motorways, e.g. E18). `schools/
assemble.py`'s `carriageway_sibling`/`reciprocal_carriageway_sibling`
(`_linear_ref.py`, re-exported here) detect that second line, and
`match_barriers_network` compares which specific carriageway a school is
nearer to instead of a sign. Real result: `ever_treated_same_side` for
road rose from 4 (broken) to 869 schools. Full method + numbers in
`schools/README.md`.

## Open questions (not blocking)

1. ~~Fix `same_side` for road using the barrier's own recorded `side`/
   `side_code` attribute~~ **refuted 2026-09-18** (no usable correlation
   with true geometric side, validated via rail as an independent check --
   see `schools/README.md`) **and superseded 2026-09-23** by the
   carriageway-identity fix above, which needed no attribute at all.
2. **Carriageway-sibling detection is imperfect, not exhaustive.** Only
   ~54% of one-directional nearest-parallel-similar-length matches among
   barrier-touched network rows are reciprocal (checked live); the
   `reciprocal_carriageway_sibling` gate keeps only those, so ~46% of
   candidate pairings are discarded as noise rather than risked. A tighter
   or differently-tuned heuristic (narrower search distance, a length-ratio
   or angle threshold refit against more real examples) could plausibly
   recover some of that -- not attempted, current thresholds were only
   validated against the sample checked this session.
3. No main-line/highway-class filter applied (Florida's `arterial_subset`
   equivalent) -- every current `bilnät` segment is a candidate, including
   minor local roads. The five undownloaded thematic layers (`funkvägklass`
   especially, or `väghållare` for a state-road-only filter) would enable
   this if matching performance or false-positive corridors become a
   concern.
4. Whether NVDB has a genuine route/road-number product (a `Bandel`
   equivalent) was not investigated -- the six-package Sverigefiler list
   checked this session didn't include one, but a different NVDB export
   might.
