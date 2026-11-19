---
type: source
state: current
updated: 2026-11-19
summary: "Sweden inspire_noise: Trafikverket's Inspire noise contour maps for 2016 (road, rail, air; Lden and Lnight), downloaded from Lastkajen, raw only"
---

# `inspire_noise`

**What it is.** The "Noise" ready package of Lastkajen's Inspire folder (*Färdiga datapaket* → 4. Inspire →
HH - Human health and safety → Noise, package 10088): dB contour polygons for road, rail and air, as
Lden (day-evening-night) and Lnight, in the Inspire noise data model (inferred: the strategic noise
maps under the EU Environmental Noise Directive; no description page was read). Producer Trafikverket
(`namespace` SE-TRV). **Reference year 2016** (`beginMeasureTime` 2016-01-01, `endMeasureTime`
2016-12-31), `validFrom` 2017-01-01, record version 2024-09-04. Whether earlier or later mapping
rounds exist is not known. Use and limits:
[`../lastkajen-unused-products.md`](../lastkajen-unused-products.md) §3.

**Status.** Raw only: **no `fetch` or `preprocess` module**, no code reads it, no estimate uses it.
Downloaded and inspected 2026-11-19; checks in
[`scripts/checks/2026-11-lastkajen/`](../../../../scripts/checks/2026-11-lastkajen/README.md).
**Requires:** a Lastkajen login; a ready package, so no order.

## Where it lands

- raw: `data/sweden/inspire_noise/raw/<air|rail|road>_<lden|lnight>/` (git-ignored), each with the zip
  and one GeoPackage (0.2 to 187 MB; 645 MB in all), EPSG:3006.
- processed, assembled: none.

## Columns

| Column | Meaning |
|---|---|
| `geom` | contour polygon (mostly MultiPolygon); 12 road and 8 rail Lden polygons are invalid |
| `measure` | the dB level of the contour (Lden: road and rail 50 to 75, air 55 to 75; Lnight: road and rail 45 to 70, air 50 to 70). Whether the bands are nested or exclusive is not stated |
| `type` | `noise` |
| `inspireId`, `localId`, `namespace` | identifiers |
| `location` | a GML point per feature |
| `beginMeasureTime`, `endMeasureTime` | the reference year, 2016 |
| `validFrom`, `validTo`, `beginLifespanVersion`, `endLifespanVersion` | validity and record version |

Polygons per file: road Lden 1,095, road Lnight 1,070, rail Lden 454, rail Lnight 447, air Lden 18, air
Lnight 19.

## Caveats

- **One vintage (2016).** For walls built after 2016 it shows the state before the wall, for earlier
  walls the state after (inferred; whether existing walls are in the model is not stated).
- **Coverage.** 60% of road barriers (1,300 of 2,172) lie inside a road Lden contour of 50 dB or more
  (53% at 65 dB), 54% of rail barriers (985 of 1,829) inside a rail contour (49% at 65 dB); 1,055 of the
  10,531 schools with coordinates lie inside a road or rail Lden contour of 55 dB or more (111 at 65 dB).
  The maps cover the mapped areas only (inferred: agglomerations and the major roads and railways).
- **Not yet checked:** the contour geometry against the wall positions, and the model assumptions.
