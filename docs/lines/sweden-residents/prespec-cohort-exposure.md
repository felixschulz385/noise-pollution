---
type: prespec
state: draft
updated: 2026-11-18
line: sweden-residents
step: 1
summary: "Step 1: the cohort-exposure design (stacked event study, dose, noise vs. project tests), with decisions and rules; the record is the .tex"
---

# Cohort-exposure design (Pre-Specification)

**This page only carries the metadata for the docs index.** The pre-specification itself is
[`prespec-cohort-exposure.tex`](prespec-cohort-exposure.tex)
([PDF](prespec-cohort-exposure.pdf)): the design, the open decisions, the ◇ rules, the outcomes
and the change log. Coauthors edit the `.tex` (on Overleaf, with
[`references.bib`](references.bib)); the slides,
[`cohort-exposure-slides.tex`](cohort-exposure-slides.tex), follow it.

## Open questions

Kept in the `.tex`, where coauthors see them: §9 (questions for the register data, including
whether the grade-3 and grade-6 results are tests or grades, and for our own data build) and
§10.1 (open decisions 1–8). Questions for Trafikverket, shared with `sweden-schools`:
[`noise_barriers`](../../data/sweden/noise_barriers/README.md#open-questions).

## Maintenance

When the `.tex` changes state (draft → confirmed → run → recorded) or changes in substance,
update `state`, `updated` and `summary` above and run `python scripts/docs.py index`.
