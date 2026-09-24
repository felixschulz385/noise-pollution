# `traffic`

NVDB's `Trafik` data product -- ÅDT (årsdygnstrafik, annual daily traffic)
and the CNOSSOS-EU-ready time-of-day x vehicle-class flow splits, Covariate
Cluster C (`docs/data/sweden/covariates.md`). The core confounder for the
barrier event study: Trafikverket sites noise barriers by modelled noise
level, which tracks traffic volume, so a traffic trend at a to-be-treated
road can masquerade as a wall effect if left uncontrolled -- same
identification risk `covariates.md` documents for Florida's own AADT.

**Status (2026-09-16): `preprocess` and `assemble` implemented and run
against real data -- now a genuine multi-year historical panel, not a
single snapshot.** No automated `fetch` -- manually downloaded via
Lastkajen (same portal/credentials as `noise_barriers`/`road_network`),
same "place the file, I read it" pattern as those two sources' own manual
downloads, except here **multiple orders are placed on purpose** (see
"How to get it").

## Correction (2026-09-16): an earlier same-session test wrongly concluded historical data isn't available -- it is

Worth recording plainly, not quietly fixing: this module's first version
tested whether ordering an older `Betraktelsedatum` returns real historical
ÅDT values by joining two orders on `(ELEMENT_ID, VALID_FROM)` and finding
99.3% identical values -- and concluded historical reconstruction doesn't
work. **That test was biased and the conclusion was wrong.** Joining on
`VALID_FROM` only compares segments whose measurement window happened to be
*unchanged* between the two orders -- of course those are identical, they're
the same still-open row in both. It silently excluded every segment where a
*new* window had opened between the two `Betraktelsedatum` dates -- checked
directly, that's **~47% of segments** -- which is exactly where the real
historical signal lives.

The user caught this by pointing at Trafikverket's own historical-traffic
web viewer (`vtf.trafikverket.se`), which shows a real multi-decade
breakdown for individual road sections, and pasting one live example
(Avsnitt `10630008`, four distinct `[valid_from, valid_to)` windows from
1994 to today with different ÅDT/uncertainty per window). Checking that
*exact* section in both of our own downloaded orders settled it
immediately:

| Order (`Betraktelsedatum`) | `VALID_FROM` | `VALID_TO` | ÅDT | Uncertainty |
|---|---|---|---|---|
| 2022-09-14 | 2012-01-01 | 2024-01-01 | 147 | ±44% |
| 2026-09-16 | 2024-01-01 | 9999-12-31 (open) | 174 | ±18% |

Both rows match the web viewer's own "2012-2024" and "2024-now" rows
**exactly**, including the uncertainty percentages. `Betraktelsedatum`
genuinely does return the historical `[valid_from, valid_to)` window that
was in effect on that date -- the first test's "no historical data" result
came from how the test was built, not from the product.

**Real consequence**: `preprocess.py` was filtering to `VALID_TO ==
99991231` ("current only"), silently discarding every genuine historical
window as if it were noise. Fixed -- `preprocess` now unions every raw
`.gpkg` order under `raw/` and keeps **every** `[valid_from, valid_to)`
row. Combining just the two orders on disk at the time (no new downloads
needed) recovered a real historical span: 97,795 distinct historical
windows, 55,344 elements, `VALID_FROM` spanning 1994-2026, with 28,690
elements (52%) already carrying 2+ distinct windows -- since extended to
8 orders, see below.

## How to get it

1. Log into <https://lastkajen.trafikverket.se> (credentials in
   `setup/secrets/trafikverket_lastkajen_username`/`_password`).
2. Create a custom order for the **`Trafik`** data product, GeoPackage
   format, `Sverige` (whole-country) area. The order form has a real
   **`Betraktelsedatum`** ("as-of date") field -- **confirmed live
   2026-09-16 this genuinely returns the historical `[valid_from,
   valid_to)` window that was in effect on that date** (see
   "Correction" above).
3. **Place several orders at different historical `Betraktelsedatum`
   values, not just one** -- each captures whichever window(s) were open
   or recently closed as of that date; more orders, spread across the
   analysis period, recover more of each segment's real history. Roughly
   match the confirmed remeasurement cadence (major roads 1-499 every 4
   years, minor roads every 12) rather than ordering densely.
4. Unzip and place each under `data/sweden/traffic/raw/` (any nested
   folder structure is fine -- `traffic/shared.py::all_traffic_gpkgs`
   finds every `.gpkg` by glob and `preprocess` unions all of them, not
   just the most recent).

**Eight real orders exist as of 2026-09-16**, spread across the analysis
period at roughly the confirmed 4-year major-road cadence:
`Betraktelsedatum` = 1999-01-01, 2003-01-01, 2007-01-01, 2011-01-01,
2015-01-01, 2019-01-01, 2022-09-14, 2026-09-16 -- all single layer
`TRAFIK_DK_O_105_Trafik`, EPSG:3006, ~120-140 MB each.

## Real schema, checked live 2026-09-16 (not assumed)

`ELEMENT_ID, VALID_FROM, VALID_TO, START_MEASURE, END_MEASURE,
EXTENT_LENGTH, DIRECTION, ROLE, ISHOST, SEQ_NO` (linear-reference/lineage
fields, same convention as `road_network`) plus the actual traffic
attributes: `Adt_samtliga_fordon` / `Adt_tunga_fordon` / `Adt_axelpar` (all
vehicles / heavy vehicles / axle-pairs ÅDT) and the nine CNOSSOS-EU-ready
time-of-day x vehicle-class fields (`Adt_{lätta,medeltunga,tunga}_fordon_
{06-18,18-22,22-06}`) the spec PDF promised -- confirmed present with real,
sensible values (median 950 vehicles/day, max 72,240, across the whole
current-snapshot layer). Plus `Avsnittsidentitet`, `Matarsperiod` (YYYYMM
measurement vintage), `Matmetod` (measurement method), `Mc_floden`, and
three `Osakerhet_*` (uncertainty) fields.

- **`VALID_FROM`/`VALID_TO` are a genuine historical validity window, not
  noise to filter out** -- see "Correction" above. `preprocess.py` keeps
  them as raw `YYYYMMDD` integers (not parsed to `datetime64`, since the
  "still open" sentinel `99991231` overflows pandas' datetime range) and
  no longer filters by them at all.
- **`ELEMENT_ID` joins directly to `road_network`'s own `element_id`, no
  crosswalk needed** -- checked live, **100.0% (54,444 of 54,454) of
  `Trafik`'s distinct `ELEMENT_ID` values (2026-09-16 order) are found
  verbatim in `road_network.parquet`'s `element_id`** (same
  `"10015:147598"`-style compound id format on both layers). `traffic/
  assemble.py` doesn't use this join (it matches schools directly to the
  nearest `Trafik` segment) but it's confirmed available.
- **`Matarsperiod` is a genuine per-segment, per-window measurement
  vintage** -- combined across both real orders it spans **200001 to
  202601** (parsed from `VALID_FROM`, matches each window's own start).
- **`Matmetod`** (measurement method, 2026-09-16 order): `Stickprovsmätning`
  (sample measurement) 66% / `Bedömt flöde utan stödmätning` (estimated, no
  support measurement) 33% / `Bedömt flöde med stödmätning` 1% /
  `Helårsmätning` (whole-year measurement) a tiny 4 rows. `Osakerhet_*`
  (uncertainty) populated for exactly the sampled/estimated share.
- **`ELEMENT_ID` is NOT a unique row key** -- now doubly true, since the
  same element also has multiple historical-window rows. Traced to three
  real, legitimate causes (not a data error): `DIRECTION` (`Med`/`Mot`)
  splits a two-way road into separate rows per direction, `ROLE`
  (`Normal`/`Syskon fram`/`Syskon bak`) further splits some segments into
  direction-specific "sibling" rows, and now genuinely different
  historical `[valid_from, valid_to)` windows for the same element.
  `assemble.py` handles this by using only each element's *current* row
  for the spatial match (`most_current_rows`), then broadcasting the
  FULL window history onto whichever school matched.

## `preprocess` -- real run 2026-09-16 (unions all 8 real orders)

```bash
python -m src.cli sweden data traffic preprocess
```

Unions every `.gpkg` order found under `raw/`, snake_case-renames columns,
deduplicates exact-duplicate rows across orders. **Does not filter by
`VALID_TO`** -- keeps every historical window. **Real run**: 8 orders,
488,143 rows read -> **295,696 rows after union + dedup**, 77,485 distinct
`element_id`, `VALID_FROM` spanning **1984-2026**, 58,566 elements (76%)
with 2+ recovered windows -> `data/sweden/traffic/processed/traffic.parquet`.

## `assemble` -- real run 2026-09-16 (interval history, not a snapshot)

```bash
python -m src.cli sweden data traffic assemble   # defaults to --max-dist 1000
```

Two-step design: (1) `match_schools_to_element` -- a spatial nearest-segment
match (`_linear_ref.py::nearest_segment`) against each element's *current*
row only, giving one static `(skolenhetskod, element_id, dist_m)` row per
school; (2) `build_school_traffic_history` -- broadcasts the matched
element's FULL historical window table onto that school, so a school whose
segment has 3 recovered windows gets 3 rows, not 1. `panel/assemble.py`'s
`attach_traffic` then does an interval-overlap join, picking whichever
window actually covers each outcome row's own year.

**Real run**: of 9,520 geocoded schools, **8,629 (90.6%) matched within
1000m** (median match distance 230m), **45,628 total history rows**
(median 3.0 windows per matched school). Output:
`data/sweden/traffic/assembled/school_traffic.parquet`.

**Real coverage in the joined panel** (`panel/assemble.py`, see its own
README row): with 8 `Betraktelsedatum` orders spread across 1999-2026, the
traffic match rate is now a roughly **uniform ~30-40% across läsår
1998-2019**, rising to **~50% for 2022-2025** -- a real, substantial
flattening from the earlier ~0%-pre-2011-to-70% shape recorded with only 2
orders. More orders, especially filling remaining gaps (e.g. between 2019
and 2022, or before 1999), would push the rate higher still -- confirmed
working, not a dead end.

## `TrafficFlow` (the real-time API, not NVDB) checked and ruled out -- confirmed live 2026-09-16

Separately from the `Betraktelsedatum` correction above: also checked
whether **`TrafficFlow`** (namespace `road.trafficinfo`, the real-time
`api.trafikinfo.trafikverket.se` API this repo already has working
infrastructure for -- a different object type/access method than NVDB's
`Trafik` Lastkajen product) could be a historical-panel substitute, prompted
by the same `vtf.trafikverket.se` viewer. It can't, for an unrelated reason:
**retention is only about a week**. Real per-minute point-sensor readings
(`SiteId`, `MeasurementTime`, `VehicleFlowRate`, `AverageVehicleSpeed`,
Stockholm-area coordinates -- confirmed a sparse *urban point-sensor* feed,
structurally unlike NVDB's nationwide periodic ÅDT survey) -- whole-day
queries found real data 6-7 days back, zero 8+ days back and at every
longer horizon tested. `vtf.trafikverket.se`'s own historical-traffic
lookup (the one that led to the correction above) must be reading from the
NVDB `Trafik`/`TRAFIK_DK_O` product's versioned history, not this API.

## Open questions (not blocking)

1. **Coverage is now roughly uniform (~30-40%) across 1998-2019 but still
   caps around 50%** even for the best-covered recent years -- 8 orders
   recovers real history for most but not all elements (23.6% of schools
   never match a segment within 1000m at all, a spatial-match limit
   separate from the `Betraktelsedatum` question). More orders would raise
   the ceiling further but each additional order has diminishing returns
   now that most 4-year gaps are filled.
2. Whether the `Osakerhet_*` (uncertainty) values should gate a
   confidence-weighted regression, or just flag `Stickprovsmätning`/
   `Bedömt flöde` rows for a robustness check, not decided.
3. NVDB retains windows back to at least **1984** now (recovered from the
   8-order union, up from 1994 with 2 orders) -- whether it goes back
   further wasn't tested; an order at an even earlier `Betraktelsedatum`
   (pre-1999) would test this directly, but returns are likely small given
   how little changed between the 1984 floor and the 1999 order.
