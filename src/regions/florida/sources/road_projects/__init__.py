"""Florida `road_projects` source (covariate Cluster D): FDOT road-works and
construction projects co-timed with noise-barrier construction.

A wall is frequently one line item inside a widening, resurfacing, or PD&E
project; the widening adds capacity (more traffic) and the construction
itself is disruptive, both coinciding with the wall's own completion date.
This source exists to control for that co-timed confounder and to split
"wall built as part of a widening" from standalone barrier retrofits.

Full design brief, live-verified ArcGIS REST schema, and the join strategy:
``docs/data/florida/road_projects/README.md``. In short: two FDOT ArcGIS
REST FeatureServer extracts (``Work_Program_Current`` layers 2/13,
``Active_Construction_Projects``), both keyed by the same ``ROADWAY`` id
format ``road_network.roadway_id`` already uses, so the join to
``road_network``/``schools``/``traffic`` is a direct ``roadway_id`` +
milepost-overlap join -- no spatial nearest-line matching needed, unlike
``noise_barriers``.
"""
