---
type: results
state: current
updated: 2026-11-18
line: florida-schools
summary: "Exploratory so far: a clean null (CS ATT -0.051, RI p=0.456); the near-road drop follows the road, not the wall (DDD -0.018); the FRPL gradient lives between cohorts"
---

# Florida: noise walls and school test scores: Results

**This page is the record.** It summarises the outcomes recorded in the pre-specs and adds no
estimate of its own. Anything downstream (the outline) is updated in the same commit as this
page.

**No step here was pre-specified.** Every result below comes from the run of
[`11_analysis.ipynb`](../../../notebooks/florida-schools/11_analysis.ipynb) on 2026-10-22/23,
before the project adopted pre-specification (2026-11-17). They are **exploratory**: rules,
thresholds and corrections were not fixed before the outcomes were seen. Section 2 therefore
has one section per notebook Part, not one per pre-spec. The numbers are copied from the
notebook's Summary and section results; none is re-derived here.

## Summary

1. **A clean null.** CS ATT −0.051 SD (SE 0.068, p=0.460; RI p=0.456), flat leads and lags.
   TWFE −0.026 / −0.030; school × cohort FE −0.085 (p=0.176).
2. **Null against comparison groups sited like the treated.** Proposed-wall schools as the only
   controls: CS −0.029, TWFE +0.036. Within walls, net of proposed walls (DDD): −0.018
   (SE 0.080).
3. **A near-road drop that follows the road, not the wall.** Schools ≤300 m from the road: CS
   −0.171 (p=0.044; RI 0.064). It is fragile, comes with falling enrollment, is zero against
   near-road proposed-wall schools (+0.000), and the DDD finds the same decline behind walls
   never built.
4. **A free-lunch gradient that lives between cohorts.** +0.130 SD per SD of baseline FRPL share
   (WCR p=0.044), but +0.031 with school × cohort FE: post-wall cohorts at affluent-intake
   schools score lower. Points to who enrols, not to learning.
5. **Every FDOT wall came with a highway project.** The wall and its road works cannot be
   separated in this data.

## 1. Question and design

- **Question.** Does an FDOT noise wall raise standardized test scores at the schools it
  protects?
- **Outcome.** `z_mss_w`, the school mean scale score standardised within
  grade/subject/year/regime, collapsed to one `n_students`-weighted value per school-year,
  regular schools only. TWFE models also use the grade × subject × year cells.
- **Treatment.** The school lies in an FDOT wall's protected area: the wall's side, beside its
  stretch, within 600 m. Walls with unknown timing are dropped from the treated group.
- **Sample.** 72,570 school-years, 4,066 schools; 102 treated schools have a construction year
  (31 built before 2003). 58 are observed before and after construction, in 10 of 77 districts.
- **Estimators.** Callaway–Sant'Anna (`csdid`, not-yet-treated controls, `dripw`), TWFE
  (`reghdfe`) and school × cohort FE, in Stata through `pystata`. Standard errors clustered by
  school unless stated.

## 2. Results, step by step

All sections below are exploratory (run 2026-10-22/23, before pre-specification). Section
numbers (§) are the notebook's.

### 2.1 Part I. Data (§1–§3), exploratory

- Treated schools sit by roads with about 4.4× the traffic (122,580 vs. 27,969 vehicles/day),
  in somewhat poorer tracts, with higher baseline FRPL (55.4% vs. 48.6%) and Black share
  (41.6% vs. 23.5%).

### 2.2 Part II. The main estimate (§4–§7), exploratory

- **CS ATT −0.051** (SE 0.068, p=0.460, 95% CI −0.18 to 0.08). `Pre_avg` −0.008 (p=0.453),
  `Post_avg` −0.026 (p=0.626). No single period significant at 10%.
- **Controls (§5).**

  | controls | ATT | SE | p | N | no controls, same sample |
  |---|---|---|---|---|---|
  | none | −0.051 | 0.068 | 0.460 | 71,574 | −0.051 |
  | + traffic | −0.135 | 0.076 | 0.077 | 50,706 | −0.095 |
  | + road projects, shocks | −0.112 | 0.075 | 0.138 | 50,706 | −0.095 |
  | + census-tract SES | −0.113 | 0.079 | 0.152 | 50,345 | −0.095 |
  | census-tract SES only | −0.058 | 0.070 | 0.410 | 70,814 | −0.051 |

  Traffic moves the estimate mostly through the sample; SES changes nothing.
- **TWFE (§6).** −0.026 (SE 0.060) with school + year FE, −0.030 (SE 0.061) with grade ×
  subject × year FE. Event study flat: leads jointly p=0.339, lags −0.041 to +0.059.
- **School × cohort FE (§7).** −0.085 (SE 0.063); event study flat (joint p=0.62).

### 2.3 Part III. Comparison groups sited like the treated (§8–§9), exploratory

- **Proposed-wall schools as the only controls (§8)**, 26 schools: CS −0.017 (not yet
  treated), −0.029 (never treated); TWFE +0.036.
- **Within walls (§9)**, stacked by construction year:

  | model | near × post | SE |
  |---|---|---|
  | CS, far built schools as controls (not yet / never) | −0.132 / −0.142 | 0.072 / 0.073 |
  | DD, site cohort × year FE | −0.173 | 0.081 |
  | DDD, + proposed walls, near × year FE | **−0.018** | 0.080 |

  The DD is a pre-trend: leads positive and shrinking toward t = −1 (`F8` +0.359, jointly
  p=0.044), lags flat. The DDD removes it (leads jointly p=0.207).

### 2.4 Part IV. Distance from the road (§10–§11), exploratory

- **Split at 300 m (§10).** Near −0.171 (SE 0.085, p=0.044), far +0.082 (p=0.408). All of the
  near effect sits at 150–300 m; 0–150 m is +0.166 on 5 schools.
- **Robustness (§11).**
  - Cutoff: CS negative from 200 to 400 m (−0.21 to −0.13), significant only at 250–300 m.
  - Permutation of near/far labels: gap p=0.049.
  - Leave one district or road out: sign never changes; 12 of 27 drops lose 5% significance.
  - Holm over §10's six splits: CS near 0.222, TWFE 150–300 m 0.013.
  - Near schools' log enrollment −0.102 (p=0.029), falling from the construction year on
    (`Post_avg` −0.127, no pre-trend).
  - Nearby traffic was already rising before the wall (`Pre_avg` p=0.002).
  - Against the 13 near-road proposed-wall schools: +0.000 (SE 0.099).
  - Larger behind federal Type I walls (−0.211, p=0.049) than state ones (−0.113); not
    significantly different (TWFE p=0.42–0.46).

### 2.5 Part V. For whom (§12–§13), exploratory

- **FRPL gradient (§12).** `post` × baseline FRPL share +0.130 SD per SD (SE 0.049). Effect at
  −1 SD (affluent intake) −0.180 (p=0.009), average −0.050, +1 SD +0.081.
- **Between cohorts (§7).** On graded cells: +0.144 with school FE, +0.031 (SE 0.049) with
  school × cohort FE.
- Black share adds nothing once FRPL is in (+0.015).
- **Subjects and grade bands (§13).** ELA −0.040, math −0.102, science −0.000; elementary
  −0.027, middle −0.062, high −0.287 (SE 0.217, 22 schools). All null.

### 2.6 Part VI. Other outcomes and who attends (§14–§15), exploratory

- Pass rate −1.37 points (p=0.226); `pct_l1` +1.66 (p=0.091). Both lean against a benefit.
- Composition: `pct_black` flat; `frpl_share` clean before, drifts up after (`Post_avg` +0.022,
  p=0.232).

### 2.7 Part VII. Inference (§16), exploratory

| estimate | value | p, school | p, district | p, WCR (district) | p, RI |
|---|---|---|---|---|---|
| CS ATT, all (§4) | −0.051 | 0.460 | 0.481 | | 0.456 |
| CS ATT, near ≤300 m (§10) | −0.171 | 0.044 | 0.063 | | **0.064** |
| TWFE `post` (§6, Panel B) | −0.030 | 0.618 | 0.608 | 0.621 | |
| TWFE `post`, school × cohort FE (§7) | −0.085 | 0.176 | 0.285 | 0.430 | |
| TWFE `post`, near ≤300 m (§10) | −0.144 | 0.065 | 0.093 | **0.167** | |
| TWFE `post` × FRPL share (§12) | +0.130 | 0.008 | 0.002 | **0.044** | |
| within-wall DD (§9) | −0.173 | 0.034 | 0.048 | **0.110** | |
| within-wall DDD (§9) | −0.018 | 0.820 | 0.809 | 0.850 | |

RI: 1,999 shuffles of the treatment year (seed 20261022). WCR: `boottest`, Webb weights, by
district.

### 2.8 Appendix A. Weighting (recorded 2026-09-24, not re-run)

`z_mss_w` −0.051 (p=0.460), `z_mss` −0.046 (p=0.454). The regression-weighted rows were never
run on the `protected` tier.

## 3. What the results support

All of this is exploratory; none of it was pre-specified.

- **Supported:** nothing yet as a pre-specified claim. The null is consistent across every
  estimator, comparison group and inference method tried.
- **Recorded, but not a finding to build on:**
  - The near-road drop (−0.171): fragile, not significant at 5% under RI, district clustering
    or WCR, and zero against near-road proposed-wall schools.
  - The FRPL gradient (+0.130, WCR p=0.044): one of several cuts, TWFE only, and it sits
    between cohorts, so it reads as a change in who enrols.
- **Not supported:**
  - An effect of walls on test scores.
  - A diluted benefit near the road.
  - A wall effect within the same corridors (DDD −0.018).

## 4. Limitations

- **Wall and road project together.** Every FDOT wall came with a highway project; the
  fetched Work Program covers fiscal years 2023–2030 only, so older projects cannot be typed.
- **No composition-adjusted outcome.** Florida has no counterpart to SALSA's residual, so a
  change in who attends and a change in learning look the same.
- **The within-wall design** is stacked by construction year, not by wall; far schools within
  1,500 m can share catchments with near ones (bias toward zero).
- **Exploratory.** Several distance cuts, heterogeneity cuts and comparison groups were tried;
  Holm was applied only within §10's splits.
- **`csdid` pre-periods** use the short-gap convention; `long2` is not decided.

## 5. Next steps (not scheduled)

- The per-wall stack (wall × year FE, clustered by wall) and the dB dose:
  [`prespec-per-wall-stack.md`](prespec-per-wall-stack.md) (draft).
- The FRPL gradient in CS (split by baseline FRPL share), and whether `frpl_share`'s drift
  accounts for it.
- A historical Work Program, to tell widenings from other projects for older walls.
- The regression-weighted Appendix A rows (about 1 hour).
- Subgroup achievement (race/ethnicity, economic disadvantage, ELL, SWD), not in the fetched
  FLDOE workbooks.

## 6. Reproduction

- **Data.** `data/florida/panel/assembled/event_study_panel.parquet`, built by
  `noise_pollution florida data panel assemble`. Upstream pages:
  [`docs/data/florida/`](../../data/florida/README.md).
- **Code.** The specification (sample, treatment, collapse, baselines, cells, sites, clusters,
  RI): `src/noise_pollution/analysis/florida_schools.py`, with the shared pieces in
  `src/noise_pollution/analysis/did.py`.
- **Notebook.** [`11_analysis.ipynb`](../../../notebooks/florida-schools/11_analysis.ipynb), run
  top to bottom 2026-10-22/23. Needs Stata 18 MP with `csdid`, `drdid`, `reghdfe`, `ritest`,
  `boottest`. One `csdid` call takes about 5 minutes; the full notebook takes several hours
  (the §5 ladder alone about 40 minutes in the 2026-09-30 timing), plus the §16 RI loops.
- **Figures.** [`output/figures/florida-schools/`](../../../output/figures/florida-schools/)
  (descriptive; the analysis notebook writes none).
- **Earlier runs.** The notebook's Revision history.
- **Plan for the within-wall designs.**
  [`notes/within_barrier_design.md`](notes/within_barrier_design.md).
