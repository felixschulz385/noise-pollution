# Lastkajen data checks, 2026-11-19

Read-only checks run for the call with Trafikverket (25 November 2026). They read the raw
GeoPackages under `data/sweden/` (git-ignored) and print aggregates; none writes to the data root.
Paths resolve from the repository root. No script loads an outcome, so none is a pre-specified step;
a result that enters the analysis needs a pre-spec entry first (see `AGENTS.md`).

Run with `python -I <script>` (standard library only) or, where marked, with the `noise_pollution`
conda environment (`pandas`, `geopandas`).

| Script | Env | What it checks | Where the result is written |
|---|---|---|---|
| `raw_barrier_claims.py` | stdlib | Counts, `Byggår` and `Höjd` sentinels, the bar-chart buckets, `VALID_TO`, side and distance fields, material and bridge fields, drawing numbers | `prep/02-local-data-check-report.md` §1, §2.4 |
| `rail_dates_and_siblings.py` | stdlib | Rail `Inkopplingsdatum` against `Byggar`; `Sida_h_v_b` against `SIDE`; sibling fill by `Bisobjektnr` and `ELEMENT_ID` | report 02 §1 (claim 6), §2.4 |
| `rail_bisobjektnr_dating.py` | conda | Rank correlation of `Bisobjektnr` with `Byggar`; leave-one-out bracket accuracy; brackets for the undated rail records | `docs/data/sweden/noise_barriers/README.md` (dating leads), report 02 §2.1 |
| `compare_road_snapshots.py <new.gpkg> <old.gpkg>` | conda | Two road snapshots: counts, `VALID_FROM`/`VALID_TO`, closed records, shared and dropped elements | `prep/01-lastkajen-catalogue-report.md` §6 |
| `compare_four_snapshots.py` | stdlib | The 2015, 2019, 2022 and July 2026 road files: growth, removals, attribute stability | `prep/01-lastkajen-catalogue-report.md` §6 |
| `inspect_new_gpkgs.py` | stdlib | Layers, columns and row counts of the road projects and Inspire files | `docs/data/sweden/lastkajen-unused-products.md` |
| `inspire_noise_attributes.py` | stdlib | Inspire attributes: reference year, dB levels, validity | same |
| `inspire_noise_coverage.py` | conda | Contour area per band, share of barriers and schools inside the contours (about 2 minutes) | same |
| `road_projects_profile.py` | conda | Vägombyggnad and Vägnybyggnad: years, fill rates, flags. **Run first**: writes `/tmp/om.pkl` and `/tmp/ny.pkl` | same |
| `road_projects_vs_barriers.py` | conda | Joins the projects to the road barriers on `ELEMENT_ID` and measure overlap | same |

**Raw file names.** In `data/sweden/noise_barriers/raw/` the road layer is in
`railway_noise_barriers.gpkg` and the rail layer in `highway_noise_barriers.gpkg` (the names are
swapped; see the `noise_barriers` README). The scripts use the file that holds the layer they
mean, so they would need the paths changed if the files are renamed. The three snapshot folders
`raw/road_ref_<date>/` hold the earlier-date road orders.
