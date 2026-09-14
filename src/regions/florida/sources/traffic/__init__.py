"""Florida `traffic` source: a roadway-segment x release-year AADT panel.

Built entirely from the FGDL `rciroads` releases `road_network` already
fetches -- each release carries an `AADT` field per segment, so pulling many
releases (not just the one `road_network` keeps as its "current" snapshot)
turns that single cross-section into the time-varying traffic covariate the
event study needs (Cluster C, `docs/data/florida/covariates.md`). Full design
brief: `docs/data/florida/traffic/README.md`.

Stages: `fetch` (per-release attribute tables, geometry dropped) ->
`preprocess` (stack into one panel). No `assemble` yet -- joining the panel
to schools by matched `roadway_id` (from `schools/assemble.py`'s
`match_barriers_road` / `road_network/linear_ref.py`) is future work.
"""
