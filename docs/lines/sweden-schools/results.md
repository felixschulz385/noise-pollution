---
type: results
state: current
updated: 2026-11-18
line: sweden-schools
summary: "Exploratory so far: CS ATT +0.285 rests on two 2001-cohort schools and fails RI (p=0.186); a parental-education gradient (+0.309 per SD) survives RI and WCR"
---

# Sweden: noise barriers and school achievement: Results

**This page is the record.** It summarises the outcomes recorded in the pre-specs and adds no
estimate of its own. Anything downstream (the outline) is updated in the same commit as this
page.

**No step here was pre-specified.** Every result below comes from the run of
[`20_analysis.ipynb`](../../../notebooks/sweden-schools/20_analysis.ipynb) on 2026-10-22,
before the project adopted pre-specification (2026-11-17). They are **exploratory**: rules,
thresholds and corrections were not fixed before the outcomes were seen. Section 2 therefore
has one section per notebook Part, not one per pre-spec. The numbers are copied from the
notebook's Summary and section results; none is re-derived here.

## Summary

1. **No overall effect that stands out from chance.** CS ATT +0.285 SD (SE 0.130,
   school-clustered p=0.028), but randomization inference gives p=0.186. Only 11 treated
   schools are observed before and after construction.
2. **The headline rests on two schools.** The 2001 cohort (one road wall, one rail wall, 3 pre-
   and 19 post-years) carries about half the weight. Its own ATT is +0.481; without it
   +0.066 (p=0.543).
3. **The effect is zero on the income-complete sample, because of the sample.** Without controls
   on the same rows the ATT is already 0.004–0.066.
4. **TWFE gives a similar size but rises before construction.** `post` +0.216 (p=0.044; RI
   p=0.174); far leads around −0.2.
5. **A gradient by parental education survives.** The effect rises by +0.309 SD per SD of
   baseline parental education (RI p=0.010, wild cluster bootstrap p=0.017). Exploratory, and
   one of several cuts.
6. **Other outcomes and composition do not move.** SALSA residual, pass rate and eligibility
   are positive and insignificant; parental education and share of boys do not shift at
   construction.

## 1. Question and design

- **Question.** Does a noise barrier along a Swedish road or railway raise grade-9 achievement
  at the schools on its protected side?
- **Outcome.** `meritvärde_z`, grade 9, 1998–2019, z-scored on each side of the 2014/15 grading
  reform.
- **Treatment.** Road **or** rail barrier construction at the `protected` tier: on the
  barrier's side, within 600 m, beside its stretch. Sides from the manual barrier audit. A
  school's event time runs from the first barrier.
- **Sample.** 29,687 school-years, 2,550 schools. 55 treated schools have a construction year.
  Dropped: 58 treated schools with no construction year on any barrier, and 7 untreated schools
  beside a barrier of unknown side.
- **Estimators.** Callaway–Sant'Anna (`csdid`, not-yet-treated controls, `dripw`) and TWFE
  (`reghdfe`), in Stata through `pystata`. Standard errors clustered by school unless stated.

## 2. Results, step by step

All sections below are exploratory (run 2026-10-22, before pre-specification). Section numbers
(§) are the notebook's.

### 2.1 Part I. Data (§1–§3), exploratory

- 55 treated schools: 5 built before 1998, 27 after 2019, 23 inside the window (13
  construction years, at most 3 schools each).
- **11** of the 23 are observed both before and after construction. Every estimate rests on
  them.
- Covariate coverage: traffic 44.9%, neighbourhood income 41.2%, neighbourhood education 24.5%.
- Treated schools sit by busier roads (11,590 vs. 7,839 vehicles/day) in slightly poorer and
  less-educated neighbourhoods.

### 2.2 Part II. The main estimate (§4–§7), exploratory

- **CS ATT +0.285 SD** (SE 0.130, p=0.028, 95% CI 0.03 to 0.54). `Pre_avg` −0.018 (p=0.443),
  single pre-periods swing ±0.18. `Post_avg` +0.179 (p=0.037).
- **Controls (§5).**

  | controls | ATT | p | N | no controls, same sample |
  |---|---|---|---|---|
  | + traffic | 0.352 | 0.007 | 13,117 | 0.381 |
  | + traffic, income | 0.024 | 0.883 | 5,454 | 0.004 |
  | + traffic, income, education | 0.037 | 0.794 | 3,170 | 0.021 |
  | income only | 0.080 | 0.449 | 11,991 | 0.066 |

  The controls do not remove the effect; the sample does.
- **The 2001 cohort (§6).** Two schools (kommun 1880 Örebro, road; 1293 Hässleholm, rail),
  1998–2000 before and 19 years after. Their ATT +0.481 (p=0.006). Without them +0.066
  (SE 0.109, p=0.543). Cohort average (`GAverage`) +0.101 (p=0.038). No neighbourhood data in
  their base year 2000, so every income spec loses them.
- **TWFE (§7).** `post` +0.216 (SE 0.107), +0.212 without the 2001 cohort. Far leads `F5`–`F8`
  −0.18 to −0.27 (jointly p=0.138): treated schools were improving before their wall. Gone on
  the income-complete sample, as in CS.

### 2.3 Part III. Behind the same barriers (§8), exploratory

Schools in a barrier's protected area against schools 600–1,500 m out behind barriers.

| model | near × post | SE | p |
|---|---|---|---|
| CS, far schools as controls | +0.269 | 0.138 | 0.052 |
| CS, without the 2001 cohort | +0.066 | 0.116 | 0.568 |
| TWFE, site cohort × year FE (5 near schools) | +0.144 | 0.160 | |

The statewide control group does not create the effect; the 2001 cohort does. Sweden has no
proposed barriers, so no triple difference.

### 2.4 Part IV. For whom (§9), exploratory

- `post` × baseline parental education: **+0.309 SD per SD** (SE 0.076). Effect at −1 / 0 / +1
  SD: +0.045 / +0.354 / +0.662.
- CS median split agrees: high +0.483 (p=0.004), low +0.117 (p=0.105).
- Leave-one-out over the 11 schools: +0.215 to +0.337. Without the 2001 cohort: +0.320.
- Foreign background adds nothing (+0.049, SE 0.067).
- Opposite sign to Florida's free-lunch gradient.

### 2.5 Part V. Other outcomes and who attends (§10–§11), exploratory

- SALSA composition-adjusted residual +0.317 (SE 0.334, p=0.344). Pass rate +4.7 points
  (p=0.196), eligibility +2.1 points (p=0.356). No multiple-testing correction.
- Composition: parental education `Post_avg` 0.018 (p=0.693), share of boys 0.12 (p=0.957). No
  shift at construction.

### 2.6 Part VI. Inference (§12), exploratory

| estimate | value | p, school | p, kommun | p, WCR (kommun) | p, RI |
|---|---|---|---|---|---|
| CS ATT, all (§4) | +0.285 | 0.028 | 0.031 | | **0.186** |
| CS ATT, without the 2001 cohort (§6) | +0.066 | 0.543 | | | 0.736 |
| CS ATT, near vs. far (§8) | +0.269 | 0.052 | | | 0.176 |
| TWFE `post` (§7) | +0.216 | 0.044 | 0.036 | 0.086 | **0.174** |
| TWFE `post` × parental education (§9) | +0.309 | <0.001 | <0.001 | **0.017** | **0.010** |

RI: 1,999 shuffles of the treatment year (CS, seed 20261022), 999 for TWFE (`ritest`). WCR:
`boottest`, Webb weights, 9,999 draws. The 11 identifying schools sit in 10 kommuner, so kommun
clustering changes little.

### 2.7 Appendix A. Weighting, exploratory

Weighting the score (`meritvärde_zw`): +0.323 (SE 0.146, p=0.027). The regression-weighted rows
were not run.

## 3. What the results support

All of this is exploratory; none of it was pre-specified.

- **Supported:** nothing yet as a pre-specified claim.
- **Recorded, but not a finding to build on:**
  - The parental-education gradient (+0.309 per SD). It survives RI and WCR, and no single
    school carries it, but it is 11 schools and one of several heterogeneity cuts, chosen
    after seeing the data.
  - The positive TWFE estimate: it partly reflects a pre-existing upward trend.
- **Not supported:**
  - An overall effect of barriers on `meritvärde_z`. The headline fails RI (p=0.186) and is
    +0.066 without the two 2001 schools.
  - A change in who enrols at construction.

## 4. Limitations

- **Few identifying schools.** 11 treated schools with a pre- and a post-period;
  school-clustered p-values over-reject.
- **Missing construction years.** 58 treated schools are dropped, more than the 55 kept.
- **The 2001 cohort** has three pre-years and has not been checked against the barrier
  records.
- **Covariates** cover 24–45% of school-years; the controlled samples are different samples.
- **Exploratory.** Several tiers, samples and heterogeneity cuts were tried over the
  revisions; no correction for that search.
- **`csdid` pre-periods** use the short-gap convention; `long2` is not decided.

## 5. Next steps (not scheduled)

- Check the two 2001 walls (barrier rows road 1166, rail 551) and recover construction years
  for the 58 dropped schools: [`prespec-construction-years.md`](prespec-construction-years.md)
  (draft).
- A pre-trend check of the gradient by baseline-education half, and the gradient in the SALSA
  residual.
- `same_side` minus `protected` schools, to see whether the wider tier dilutes the effect.
- The regression-weighted Appendix A rows (`RUN_WEIGHTED_REGRESSION = True`).
- Cluster B (staff) from `kvalitetssystem` (2022/23 on), for the 27 schools treated after 2019.

## 6. Reproduction

- **Data.** `data/sweden/panel/assembled/event_study_panel.parquet`, built by
  `noise_pollution sweden data panel assemble` (panel of 2026-10-20, rebuilt after the blind
  double coding: 29,687 analysis rows). Upstream pages: [`docs/data/sweden/`](../../data/sweden/README.md).
- **Code.** The specification (sample, treatment, covariates, baselines, sites, clusters, RI):
  `src/noise_pollution/analysis/sweden_schools.py`, with the shared pieces in
  `src/noise_pollution/analysis/did.py`.
- **Notebook.** [`20_analysis.ipynb`](../../../notebooks/sweden-schools/20_analysis.ipynb), run
  top to bottom 2026-10-22. Needs Stata 18 MP with `csdid`, `drdid`, `reghdfe`, `ritest`,
  `boottest`. One `csdid` call takes about 90 s. The cells with timing metadata (21, from
  the 2026-10-21 run) sum to about 30 minutes; the slowest are the §5 ladder, §6, §10 and
  Appendix A (4–6 minutes each). The §12 RI loops come on top.
- **Earlier runs.** The notebook's Revision history (tiers `same_route`, `same_side`,
  `protected`, 2026-09-22 to 2026-10-22).
