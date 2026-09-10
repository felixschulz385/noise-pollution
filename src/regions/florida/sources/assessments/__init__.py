"""FLDOE annual school-level assessment results.

Per-school-year workbooks (mean scale score and percent at each achievement
level, by school x grade x subject) published on the FLDOE K-12 Student
Assessment results pages.

Stages:

* ``fetch`` (:mod:`.fetch`) — `www.fldoe.org` blocks automated clients, so this
  is a manual-download orchestrator: it lays out ``raw/<year>/`` folders,
  optionally imports files you downloaded by hand, and reports what is present.
* ``preprocess`` (:mod:`.preprocess`) — merge every raw workbook into one tidy
  table indexed on school x grade x subject x year
  (``processed/assessments.parquet`` + ``assessments.json`` sidecar), carrying
  the within-cell z-score of the school mean scale score as the primary outcome.
  Crystallizes ``src/experiments/florida/assessments.ipynb``.
"""
