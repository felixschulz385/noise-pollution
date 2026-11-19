---
type: charter
state: active
updated: 2026-11-18
line: sweden-schools
branch: line/sweden-schools
summary: "Do Swedish road and rail noise barriers raise grade-9 achievement at the schools they protect? So far no effect beyond chance (RI p=0.186); a parental-education gradient survives"
---

# Sweden: noise barriers and school achievement

<!-- The charter is the only place that states this line's status. Keep it to one screen.
     Update `state`, `updated` and `summary` above when the line moves; the indexes follow. -->

**Question.** Does a noise barrier built along a Swedish road or railway raise grade-9
achievement (`meritvärde`, 1998–2019) at the schools on its protected side?

**Why now.** The project's first question: Trafikverket's barrier registers date construction,
and SIRIS has school results for two decades, so barrier construction can be studied as a
staggered event study.

**Scope.** School-level panel from Skolverket (SIRIS, Skolenhetsregistret) and Trafikverket
(barrier registers, NVDB roads and traffic), with SCB neighbourhood controls; treatment at the
`protected` tier (the barrier's side, beside its stretch, within 600 m; sides from the manual
audit), road and rail combined. Estimated with Callaway–Sant'Anna and TWFE in Stata. Outcomes of
individual children are the [`sweden-residents`](../sweden-residents/README.md) line.

**State.** Active. The record is [`results.md`](results.md), written from the last full run
(2026-10-22, [`20_analysis.ipynb`](../../../notebooks/sweden-schools/20_analysis.ipynb)). It gives a CS
ATT of +0.285 SD (p=0.028) that rests on two schools of the 2001 cohort (without them +0.066,
p=0.543) and does not survive randomization inference (p=0.186) with 11 identifying schools; the
gradient in baseline parental education survives (RI p=0.010). These steps ran before the
project adopted pre-specification (2026-11-17), so they are exploratory. **Next:** the first
pre-spec, [`prespec-construction-years.md`](prespec-construction-years.md) (draft): check the
walls of the two 2001 schools and recover construction years (58 treated schools are dropped
for lack of one), then re-estimate. Its §0 waits for Felix's decisions.

**Branch.** `line/sweden-schools`, from `master` (the work so far is on `master`).

## Documents

<!-- docs:begin docs dir=. recursive -->
| Doc | Type | State | Updated | Summary |
|---|---|---|---|---|
| [results](results.md) | results | current | 2026-11-18 | Exploratory so far: CS ATT +0.285 rests on two 2001-cohort schools and fails RI (p=0.186); a parental-education gradient (+0.309 per SD) survives RI and WCR |
| [prespec-construction-years](prespec-construction-years.md) | prespec | draft | 2026-11-18 | Step 1: check the 2001 walls and recover construction years, then re-estimate the headline (RI decides) and re-test the parental-education gradient on new schools |
<!-- docs:end -->

## Related

- Notebooks: [`notebooks/sweden-schools/`](../../../notebooks/sweden-schools/) (data walkthroughs
  01–17, descriptives 19, analysis 20)
- Data: [`docs/data/sweden/`](../../data/sweden/README.md), especially
  [`barrier_matching.md`](../../data/sweden/barrier_matching.md),
  [`barrier_audit`](../../data/sweden/barrier_audit/README.md) and
  [`covariates.md`](../../data/sweden/covariates.md)
- Code: `src/noise_pollution/regions/sweden/` (`panel assemble` builds the analysis panel);
  the specification in `src/noise_pollution/analysis/sweden_schools.py`, with `did.py` shared
  with Florida (both imported by the analysis notebook)
- Literature: [`output/documents/literature-review/`](../../../output/documents/literature-review/)
