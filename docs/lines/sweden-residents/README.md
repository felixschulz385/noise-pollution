---
type: charter
state: active
updated: 2026-11-19
line: sweden-residents
branch: line/sweden-residents
summary: "Does growing up behind a noise barrier change children's school achievement and later outcomes? A cohort-exposure design on the 100 m grid and Swedish registers; design written, no estimate yet"
---

# Sweden: growing up behind a noise barrier

<!-- The charter is the only place that states this line's status. Keep it to one screen.
     Update `state`, `updated` and `summary` above when the line moves; the indexes follow. -->

**Question.** Does living behind a noise barrier as a child, from before birth or from some age
on, change grade-9 achievement and later outcomes?

**Why now.** The school-level design ([`sweden-schools`](../sweden-schools/README.md)) has only
11 identifying schools and measures exposure at school. Swedish registers follow children and
their mothers across moves, so home exposure can be assigned on a 100 m grid before the barrier
and kept as intention to treat.

**Scope.** A cohort-exposure design: each child assigned to the mother's 100 m cell in a
reference year before the barrier, protected cells against comparison cells along the same
road (600–1,500 m behind the barrier), stacked by barrier. This repository builds the grid and
its treatment and exports it; the register linkage and the estimation run with the register
data, outside this repository.

**State.** Active, at the design stage. The protected-tier grid with the control band is built
and exported to the shared folder (2026-10-22, [`grid`](../../data/sweden/grid/README.md),
[`18_grid.ipynb`](../../../notebooks/sweden-residents/18_grid.ipynb)). The design, its decisions
and its rules are one LaTeX document, the line's record:
[`prespec-cohort-exposure.tex`](prespec-cohort-exposure.tex) ([PDF](prespec-cohort-exposure.pdf);
draft, its open decisions wait for Felix). The slides,
[`cohort-exposure-slides.tex`](cohort-exposure-slides.tex), follow it. No estimate exists, so
there is no `results.md`. Group sizes and a back-of-the-envelope MDE from open population data
(2026-11-19, [`population`](../../data/sweden/population/README.md),
[`21_population_power.ipynb`](../../../notebooks/sweden-residents/21_population_power.ipynb);
planning numbers, no outcome; the design as drafted in the pre-spec): few barriers have children
on the opposite side, so the short-run step's MDE with that comparison alone is about 0.25 SD
(rail) and 0.46 SD (road); with the 600–1,500 m band as well and road and rail pooled, about
0.13 SD. The full window works for rail only. With a construction year for every barrier (the
notebook's §6), the short-run MDE with both comparisons would fall to about 0.17 SD (road) and
0.10 SD (rail), and the full window would open to road walls. **Next:** the decisions, among them the two the MDE
raised (the pre-spec's power section, 2026-11-19): pooling the 600–1,500 m band with the
opposite side in the main estimate (decision 9) and rail as the primary estimate (decision 10);
then the stack file the pre-spec specifies; construction years from Trafikverket (call on
2026-11-25; the rail years first); and a source for road-project dates (none found; τ−3 is the
fallback).

**How this line differs.** Estimation runs with a coauthor on the register data (MONA), outside
this repository, and coauthors edit the `.tex` on Overleaf, not Markdown. So the record is the
`.tex` (outcomes go into its §10.3); [`prespec-cohort-exposure.md`](prespec-cohort-exposure.md)
only carries its metadata for the docs index. Keep [`references.bib`](references.bib) in this
folder self-contained, so the folder compiles on Overleaf.

**Branch.** `line/sweden-residents`, from `master` (the work so far is on `master`).

## Documents

<!-- docs:begin docs dir=. recursive -->
| Doc | Type | State | Updated | Summary |
|---|---|---|---|---|
| [prespec-cohort-exposure](prespec-cohort-exposure.md) | prespec | draft | 2026-11-19 | Step 1: the cohort-exposure design (stacked event study, dose, noise vs. project tests), with decisions and rules; the record is the .tex |
<!-- docs:end -->

## Related

- Notebooks: [`notebooks/sweden-residents/`](../../../notebooks/sweden-residents/)
- Data: [`grid`](../../data/sweden/grid/README.md),
  [`barrier_protection`](../../data/sweden/barrier_protection/README.md),
  [`population`](../../data/sweden/population/README.md)
- Literature: method precedents from the lead-exposure literature,
  [`output/research/literature/lead-designs/ranked.md`](../../../output/research/literature/lead-designs/ranked.md)
- Documents: the pre-spec and the slides in this folder (moved 2026-11-18 from
  `output/documents/empirical-strategy/`, which held `empirical_strategy.tex`)
