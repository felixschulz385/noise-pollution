"""Florida school spine — identity, geometry, crosswalk, panel, treatment.

`schools` is the per-school backbone of the barrier-construction event study. It
keys on the FLDOE ``msid`` (2-digit district + 4-digit school = the key the
assessment workbooks use) and attaches:

* the NCES ``NCESSCH`` crosswalk (embedded in MSID as
  ``FEDERAL_DIST_NO`` + ``FEDERAL_SCHL_NO`` — no external match needed for the
  primary path),
* coordinates (MSID lat/lon primary, NCES EDGE fill, geocode fallback),
* an open/close operation panel and school-type flags,
* time-varying school covariates (covariates.md Cluster A) from CCD / CRDC /
  EDFacts via the Urban Institute Education Data API, and
* (stage 2) the school ↔ barrier ↔ road-network match that produces per-school
  treatment timing.

This source **absorbs the former ``master_file`` source**: its MSID download is
the ``msid`` subsource here. See ``docs/data/florida/schools/README.md`` for the
full design and findings.

Only ``fetch`` is implemented so far (``preprocess`` is prototyped in
``src/experiments/florida/schools.ipynb`` first).
"""
