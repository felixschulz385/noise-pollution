# Sweden — data sources

Index of every data domain in the Sweden pipeline. Each gets its own page at
`docs/data/sweden/<source>/README.md` once the per-region source registry
(template `docs/02`, see also [`../../design/01-multi-region-layout.md`](../../design/01-multi-region-layout.md))
is in place; until then this table is maintained by hand from
`src/regions/sweden/cli.py` and the modules under `src/regions/sweden/sources/`.

| Domain | Steps implemented | Prerequisites | Module |
|---|---|---|---|
| `timetable` | `fetch`, `preprocess` (`assemble` stubbed) | — | `src/regions/sweden/sources/timetable/` |
| `stations` | `fetch`, `preprocess` (`assemble` stubbed) | — | `src/regions/sweden/sources/stations/` |
| `network` | `preprocess`, `assemble` (`fetch` is a manual-download warning) | `stations.preprocess` for the overlay plot | `src/regions/sweden/sources/network/` |
| `noise_barriers` | `list-files`, `fetch`, `preprocess` | — | `src/regions/sweden/sources/noise_barriers/` |

On-disk output lands under `data/sweden/<domain>/{raw,processed,assembled}/`.

**TODO (needs live data):** row/feature counts, date coverage, and on-disk
sizes once a full run completes.
