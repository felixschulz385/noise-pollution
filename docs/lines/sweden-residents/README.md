---
type: charter
state: active
updated: 2026-11-17
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
[`18_grid.ipynb`](../../../notebooks/sweden-residents/18_grid.ipynb)); the empirical strategy is
written ([`empirical_strategy.pdf`](../../../output/documents/empirical-strategy/empirical_strategy.pdf),
slides alongside). No estimate exists. **Next:** a pre-spec from the empirical strategy
(reference dates, distance bands, the age profile), and a source for road-project dates (none
found; τ−3 is the fallback).

**Branch.** `line/sweden-residents`, from `master` (the work so far is on `master`).

## Documents

<!-- docs:begin docs dir=. recursive -->
| Doc | Type | State | Updated | Summary |
|---|---|---|---|---|
<!-- docs:end -->

## Related

- Notebooks: [`notebooks/sweden-residents/`](../../../notebooks/sweden-residents/)
- Data: [`grid`](../../data/sweden/grid/README.md),
  [`barrier_protection`](../../data/sweden/barrier_protection/README.md)
- Literature: method precedents from the lead-exposure literature,
  [`output/research/literature/lead-designs/ranked.md`](../../../output/research/literature/lead-designs/ranked.md)
- Documents: [`output/documents/empirical-strategy/`](../../../output/documents/empirical-strategy/)
