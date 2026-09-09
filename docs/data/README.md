# Data sources

Index of every data domain in the pipeline. Each gets its own page at
`docs/data/<source>/README.md` once the source registry (template `docs/02`) is
in place; until then this table is maintained by hand from the CLI in
`src/cli/data/commands.py` and the modules under `src/data/`.

| Domain | Steps implemented | Prerequisites | Module |
|---|---|---|---|
| `timetable` | `fetch`, `preprocess` (`assemble` stubbed) | — | `src/data/timetable/` |
| `stations` | `fetch`, `preprocess` (`assemble` stubbed) | — | `src/data/stations/` |
| `network` | `preprocess`, `assemble` (`fetch` is a manual-download warning) | `stations.preprocess` for the overlay plot | `src/data/network/` |
| `noise_barriers` | `list-files`, `fetch`, `preprocess` | — | `src/data/noise_barriers/` |

**TODO (needs live data):** row/feature counts, date coverage, and on-disk
sizes once a full run completes.
