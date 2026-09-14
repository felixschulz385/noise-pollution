"""Florida `shocks` source (covariate Cluster G): county-level disaster/
hurricane declarations that disrupt schooling independent of any noise wall.

v1 scope is the hurricane/disaster-declaration variable only (OpenFEMA
`DisasterDeclarationsSummaries`) -- Class-Size-Reduction compliance, School
Grades archives, and storm-track/wind-swath exposure are documented as
out-of-scope follow-ups, not built here. Full design brief:
`docs/data/florida/shocks/README.md`.

Stages: `fetch` (the entire FL disaster-declaration history in one request,
no pagination) -> `preprocess` (normalize the county name, derive the
assessment year a declaration most likely disrupted) -> `assemble` (county x
assessment-year rollup, joined onto every school via
`school_cross_section.parquet`'s `district_name` -- Florida school districts
are one-per-county, so this is a name join, not a FIPS crosswalk table).
"""
