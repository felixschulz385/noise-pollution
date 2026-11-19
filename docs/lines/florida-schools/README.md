---
type: charter
state: active
updated: 2026-11-18
line: florida-schools
branch: line/florida-schools
summary: "Do FDOT noise walls raise test scores at the schools they protect? So far a clean null (CS ATT -0.051, RI p=0.456); post-wall cohorts at affluent-intake schools score lower"
---

# Florida: noise walls and school test scores

<!-- The charter is the only place that states this line's status. Keep it to one screen.
     Update `state`, `updated` and `summary` above when the line moves; the indexes follow. -->

**Question.** Does an FDOT noise wall raise standardized test scores at the schools it
protects?

**Why now.** The same design as [`sweden-schools`](../sweden-schools/README.md) in a second
setting with many more walls, proposed walls that were never built (a natural comparison group),
and test scores for every grade from 2003.

**Scope.** School × grade × subject × year panel from FLDOE (assessments, MSID) and NCES, with
FDOT walls, roads, traffic and road projects, and covariates for staff, neighbourhood and
disaster shocks; treatment at the `protected` tier. Estimated with Callaway–Sant'Anna, TWFE and
school × cohort fixed effects in Stata, with comparisons behind built and proposed walls.

**State.** Active. The record is [`results.md`](results.md), written from the last full run
(2026-10-22/23, [`11_analysis.ipynb`](../../../notebooks/florida-schools/11_analysis.ipynb)): a
clean null: CS ATT −0.051 (p=0.460, RI p=0.456), flat event studies, null against proposed-wall schools
and within walls. A near-road drop follows the road corridor, not the wall, and the free-lunch
gradient (+0.130 SD per SD, WCR p=0.044) comes from cohorts arriving after the wall. Every wall
came with a highway project. These steps ran before the project adopted pre-specification
(2026-11-17), so they are exploratory. **Next:** the first pre-spec,
[`prespec-per-wall-stack.md`](prespec-per-wall-stack.md) (draft): the per-wall stack and the dB
dose (steps 2–3 of [`within_barrier_design.md`](notes/within_barrier_design.md)). Its §0 waits
for Felix's decisions.

**Branch.** `line/florida-schools`, from `master` (the work so far is on `master`).

## Documents

<!-- docs:begin docs dir=. recursive -->
| Doc | Type | State | Updated | Summary |
|---|---|---|---|---|
| [results](results.md) | results | current | 2026-11-18 | Exploratory so far: a clean null (CS ATT -0.051, RI p=0.456); the near-road drop follows the road, not the wall (DDD -0.018); the FRPL gradient lives between cohorts |
| [prespec-per-wall-stack](prespec-per-wall-stack.md) | prespec | draft | 2026-11-18 | Step 1: a per-wall stacked DiD (wall x year FE, clustered by wall) with the DDD against proposed walls as guard, and the dB dose as a robustness check |
| [within_barrier_design](notes/within_barrier_design.md) | note | current | 2026-11-03 | Plan for Florida's distance and within-barrier designs (near vs. far behind built and proposed walls, the dB dose) |
<!-- docs:end -->

## Related

- Notebooks: [`notebooks/florida-schools/`](../../../notebooks/florida-schools/) (data
  walkthroughs 03–10, descriptives 07, analysis 11)
- Data: [`docs/data/florida/`](../../data/florida/README.md), especially
  [`barrier_protection.md`](../../data/florida/barrier_protection.md) and
  [`covariates.md`](../../data/florida/covariates.md)
- Code: `src/noise_pollution/regions/florida/`; the specification in
  `src/noise_pollution/analysis/florida_schools.py`, with `did.py` shared with Sweden (both
  imported by the analysis notebook)
- Figures: [`output/figures/florida-schools/`](../../../output/figures/florida-schools/)
