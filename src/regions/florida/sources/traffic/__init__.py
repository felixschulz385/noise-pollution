"""Florida `traffic` source: a roadway-segment x release-year AADT panel.

Built entirely from the FGDL `rciroads` releases `road_network` already
fetches -- each release carries an `AADT` field per segment, so pulling many
releases (not just the one `road_network` keeps as its "current" snapshot)
turns that single cross-section into the time-varying traffic covariate the
event study needs (Cluster C, `docs/data/florida/covariates.md`). Full design
brief: `docs/data/florida/traffic/README.md`.

Stages: `fetch` (per-release attribute tables, geometry dropped) ->
`preprocess` (stack into one panel) -> `assemble` (match schools to a
roadway via `road_network/linear_ref.py`'s nearest-road matching, then
attach that roadway's AADT time series, plus a current-snapshot local-
intensity scaling factor -- see `assemble.py`'s module docstring). Joined
into the final event-study panel by `panel/assemble.py`'s `attach_traffic`
(nearest-release-year match, not exact-year -- see that module's docstring).
"""
