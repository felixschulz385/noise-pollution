---
type: source
state: current
updated: 2026-11-19
summary: "Sweden population: open 100 m residents per grid cell, GHS-POP 1975-2025 (modelled) and SCB's 1 km register counts with ages (2015-2025)"
---

# `population`

Residents per cell of the [`grid`](../grid/README.md) source's 100 m grid, from open data, to
size the treatment and comparison groups of the
[`sweden-residents`](../../../lines/sweden-residents/README.md) design before the register is
counted on MONA. SCB's own 100 m grid is restricted microdata (see the `grid` README); these
are its open stand-ins.

| Product | Resolution | Years | What it is |
|---|---|---|---|
| [GHS-POP R2023A](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php) (JRC) | 100 m, Mollweide | 1975–2025, every 5 years | **Modelled.** For Sweden: SCB's 2010 register counts per parish (församling, 1,460 units) spread over built-up volume; other epochs from 2005–2010 kommun growth rates and each epoch's built-up area (`GHS_POP_GLOBE_R2023A_input_metadata.xlsx`). CC BY 4.0. |
| [SCB Statistik på rutor](https://www.scb.se/en/services/open-data-api/open-geodata/grid-statistics/) | 1 km, SWEREF99 TM | 2015–2025, annual | **Register counts**, with sex and 5-year age groups, as of 31 December. Only populated cells are listed. |

So within a km, where people live comes from GHS-POP's built-up layers; how many live in the
km, and their ages, comes from SCB (from 2015). Before 2015 there are only GHS-POP's
parish-based estimates: good on where buildings stood, not on how many people lived in them.

## Commands

```bash
noise_pollution sweden data population fetch        # --epochs 1975 ... 2025, --years 2015 ... 2025, --overwrite
noise_pollution sweden data population preprocess
noise_pollution sweden data population assemble     # REQUIRES grid preprocess
```

**`fetch`** downloads, per epoch, the GHSL tiles that Sweden's bounds touch (`R2_C19`,
`R2_C20`, `R3_C19`, `R3_C20`; 1,000 km tiles of the Mollweide grid, `shared.ghs_tiles`) and
keeps the GeoTIFF of each zip (`raw/ghs_pop/E<epoch>/`), and SCB's yearly geopackage from its
geoserver's WFS (`raw/scb_1km/befolkning_1km_<year>.gpkg`, ~35 MB, 2–3 minutes each). The GHS
input metadata and data-package PDF are in `raw/ghs_pop/`. 2030 (a projection) is not fetched
by default.

**`preprocess`** warps each epoch onto one national SWEREF99 TM raster
(`processed/ghs_pop_e<epoch>_sweref99tm_100m.tif`; E 260–930 km, N 6,120–7,670 km, aligned to
whole km so 10 × 10 blocks are SCB's km cells). GDAL's `sum` resampling carries residents over
by overlap share; each tile is warped alone and the results added, so cells on a tile seam
keep both shares. SCB's years go into one long table (`processed/scb_1km.parquet`: `year`,
`km_e`/`km_n` from `rutid_scb`, `pop`, `men`, `women`, `age_0_4` … `age_100_plus`).

**`assemble`** writes, for every grid cell:

- `assembled/grid_population_ghs.parquet`: `cell_id`, `pop_<epoch>` (GHS-POP residents).
- `assembled/grid_population_scb.parquet`: `cell_id`, `year` and SCB's columns, the km's counts
  times the cell's share of the km's GHS-POP residents in the nearest epoch (2015–17 → 2015,
  2018–22 → 2020, 2023–25 → 2025). Cells without residents are left out. A km where GHS-POP
  has nobody but SCB has residents is spread evenly over its 100 cells. A km's age structure
  is assumed the same in all its cells.

Analyses use GHS-POP for levels in any year (interpolated between epochs) and SCB for the age
structure: `noise_pollution.analysis.sweden_residents.children_per_cohort`.

## Real run (2026-11-19)

- **`fetch`**: 44 GHS-POP tiles (11 epochs × 4), 975 MB; 11 SCB geopackages, 385 MB. GHSL's
  server is fast, SCB's WFS takes 2–3 minutes a year.
- **`preprocess`**: 11 rasters of 6,700 × 15,500 cells, 25–27 MB each (deflate), about 4.5
  minutes per epoch (49 minutes in all). The time goes into the `sum` resampling; warping each
  tile only into the window it covers is no faster. SCB's grid lists 9.83 million residents in
  2015 and 10.36 million in 2020 (10.38 million registered; the rest have no coordinates), in
  1.26 million km-cell rows over the 11 years.
- **`assemble`** (37 s), on the `grid`'s 832,221 cells (within 1.6 km of a barrier):

  | | 1975 | 1995 | 2010 | 2015 | 2020 | 2025 |
  |---|---|---|---|---|---|---|
  | GHS-POP | 3.00 M | 3.17 M | 3.46 M | 3.65 M | 3.85 M | 3.98 M |
  | SCB, spread by GHS-POP | | | | 3.65 M | 3.88 M | 4.01 M |

  The two agree within 1% where both exist.

## Open questions

Not blocking.

1. GHS-POP before 2015 rests on SCB's 2010 parish counts and growth rates. SCB's open 1 km
   grid starts in 2015, and SCB's own 100 m grid is MONA-only. Is there an open source of
   earlier small-area counts (e.g. older SCB grid products, or DeSO back to 2010) to check the
   1995–2010 epochs?
