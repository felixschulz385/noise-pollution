# `noise_barriers`

Trafikverket's register of noise barriers along state roads and railways,
ordered from Lastkajen: `Bullerskydd - väg` (road, ordered 2026-07-06) and
`Bullerskydd` (rail, ordered 2026-07-07), both GeoPackage in EPSG:3006. The
order receipts are next to the raw files in `data/sweden/noise_barriers/raw/`.

`preprocess` writes `data/sweden/noise_barriers/processed/{road,rail}_noise_barriers.parquet`
(`src/regions/sweden/sources/noise_barriers/`). Side matching and protected
areas are built from these files in [`../barrier_protection/README.md`](../barrier_protection/README.md);
the method is in [`../barrier_matching.md`](../barrier_matching.md).

## What the register is

- **One record per stretch of uniform wall**, not per wall. The register
  splits a wall wherever the road link, track element, height or material
  changes; `barrier_protection` joins the pieces into walls (`chain_id`).
- **Current walls only.** Every record has `is_current = True` and no
  `valid_to`. Walls that were demolished or replaced are not in it, and
  there is no history of earlier versions in our extract.
- **Geometry sits on the road or track centreline** (road 99.8%, rail
  99.7% of records), so it says where along the road a wall stands, not how
  far from the road. The `side` attribute carries no signal. See
  [`../barrier_matching.md`](../barrier_matching.md) §3.

## Sentinels

| column | sentinel | cleaned in `preprocess`? |
|---|---|---|
| `built_year` (road) | `1900` | yes, to NA (2026-09-15) |
| `built_year` (rail) | `0` | yes, to NA (2026-09-15) |
| `distance_from_track_center_m` (rail) | `999` | yes, to NA (2026-09-23) |
| `height_m` (road) | `0` (62% of records) | **no**: treat `0` as missing |
| `height_above_rail_top_m` (rail) | `999` (16% of records); also `0` (5%) | **no**: treat both as missing |

One road record has `height_m = 102.9` (an earth berm built 2020), an entry
error; the next highest is 11.6 m.

## Coverage of the attributes the design needs (checked 2026-11-02)

Records, not walls. The empirical strategy
(`output/documents/empirical-strategy/empirical_strategy.tex`) needs, per
wall, a construction year (for the event time) and, for its intensity
tests, the wall's height and its distance from the road.

| | road | rail |
|---|---|---|
| records | 2,172 | 1,829 |
| total length | 251 km | 275 km |
| `built_year` present | 49% (52% of length) | 73% (68% of length) |
| height present (neither `0` nor `999`) | 38% | 79% |
| distance from road / track present | none (geometry on the centreline) | 44% |
| dated records built 2015 or later | 71% | 54% |
| records built 2007 or earlier | 140 | 414 |
| ... of those with a height | **2** | 323 |

**The 2006 batch.** 1,092 road records have `valid_from` 2006-01-01, the
date the register started. 978 of them have neither a construction year
nor a height, and no record in the batch has a height. Records added
later usually have `valid_from` within a year of `built_year` (median
difference 0, upper quartile 1 year). So the road walls without a year or height are mostly those already
standing when the register started: built in 2006 or earlier, but we do
not know when.

**Why this matters for the design.** A wall contributes a full event window
(placebo cohorts, the ramp and the plateau) only if it was built at least
17 years before the last year of grade data, which means 2007 or earlier
for grades through 2024. Those are exactly the walls where the road
register is thinnest:
- the event study on full windows rests mostly on rail walls and on the
  few old road walls with a year;
- a dB intensity measure is feasible for rail (heights for 323 of 414 old
  records), but not for old road walls (2 of 140).

Rail heights are measured above the top of the rail; road heights are
presumably above the ground or the carriageway (not documented).

## Open questions for Trafikverket

1. Do older registers or project archives hold heights and construction
   years for the road walls loaded in 2006?
2. Is `built_year` the year a wall was completed, and does rebuilding a
   wall overwrite it with the new year?
3. Can we get historical versions of the register, including removed walls?
4. Are there records of the façade insulation programme, by dwelling and
   year?
5. Is there any source of start or announcement dates for the road projects
   that came with the walls? The traffic-information API keeps finished
   roadworks for only about a year ([`../covariates.md`](../covariates.md),
   Cluster D).
