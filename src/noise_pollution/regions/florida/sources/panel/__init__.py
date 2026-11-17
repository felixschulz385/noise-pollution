"""Final assembly for the Florida barrier-construction event study.

Joins the outcome (``assessments``), the school spine + Cluster-A covariates
+ barrier-treatment-timing (``schools``), into one analysis-ready panel. Has
no ``fetch``/``preprocess`` of its own — purely a local join of already-
processed artifacts from the other Florida sources.

Stages:

* ``assemble`` (:mod:`.assemble`) — join ``assessments.parquet`` +
  ``school_year_panel.parquet`` + ``school_cross_section.parquet`` +
  ``schools_treatment_rollup.parquet`` into ``event_study_panel.parquet``.
"""
