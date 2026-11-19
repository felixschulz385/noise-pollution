---
type: prespec
state: draft
updated: 2026-11-18
line: florida-schools
step: 1
summary: "Step 1: a per-wall stacked DiD (wall x year FE, clustered by wall) with the DDD against proposed walls as guard, and the dB dose as a robustness check"
---

# Per-wall stack and dB dose (Pre-Specification)

**Status.** Draft 2026-11-18, for Felix. Nothing has run. §0 lists the open choices; nothing
loads an outcome before they are decided.

**Outcome in one line:** (filled in when recorded)

**Why this step.** Step 3 and the open part of step 2 of
[`within_barrier_design.md`](notes/within_barrier_design.md). The exploratory within-wall
comparison (§9 of the notebook, [`results.md`](results.md)) stacks by construction year: a
near school is compared with far schools behind *any* wall built that year. The per-wall stack
compares each wall's protected schools only with schools farther out behind the same wall, as
Moretti & Wheeler (2025) do for house prices.

## 0. Decisions for the author

1. **Event window.** Recommended: ±6 years around the wall's construction year. Alternatives:
   ±4 (more walls with a full window), ±8. **Decided:**
2. **Which controls.** Recommended: each wall's own control-band schools only (33 walls / 46
   protected schools as measured 2026-09-30). Widening with band schools of other walls on the
   same `roadway_id` within about 1 km along the road is a robustness check. **Decided:**
3. **Weights.** Recommended: Wing et al. (2024) corrective weights, so the estimate is an
   average per protected school; unweighted OLS as robustness. **Decided:**
4. **Clusters and the deciding test.** Recommended: standard errors clustered by wall (or by
   group of walls that share a school, if any school enters two stacks); RI decides; the wild
   cluster restricted bootstrap by district (as in the notebook's §16) is reported and labels a
   result "fragile" when above 0.05. **Decided:**
5. **Outcome.** Recommended: `z_mss_w` collapsed to the school-year, as in §4. The grade ×
   subject × year cells are a robustness check. **Decided:**
6. **Event-study base period.** Recommended: TWFE event study with t = −1 as reference; for any
   `csdid` event study, `long2`. **Decided:**

## 1. Questions

| Block | Question |
|---|---|
| G | Can the per-wall stack be built, and how many walls and schools does it hold? (loads no outcome) |
| A | Behind the same wall, do protected schools change relative to schools farther out after construction? |
| B | Does the change scale with the wall's predicted noise reduction (dB)? |

## 2. Data

- **Panel.** `data/florida/panel/assembled/event_study_panel.parquet`, with the pipeline
  changes below. Sample rules as in the exploratory run
  (`src/noise_pollution/analysis/florida_schools.py`, `build_datasets`): regular schools,
  `n_students`-weighted collapse, `protected` tier.
- **Pipeline changes** (from the note):
  - `schools assemble` calls `classify_points(..., control_max_lateral_m=1500)` and writes
    `control_band` and `control_band_gcids` (excluding schools protected by any wall) to the
    rollup.
  - Wall–school pairing widens from 1,000 m to about 1,650 m; the point tier keeps its 1,000 m
    radius.
  - `panel assemble` carries the new columns.
- **Proposed walls.** The 548 FDOT recommended walls never built, with their protected areas
  and control bands ([`barrier_protection.md`](../../data/florida/barrier_protection.md)).
- **Dose.** `noise_reduction_db` per wall. 503 of 1,245 built walls carry exactly 7.0 dB; the
  interquartile range is 7–8 dB.

## 3. Specification

- **Stack.** For each built wall w with construction year τ_w: its protected schools (treated)
  and its control-band schools (controls), school-years τ_w − 6 … τ_w + 6 (§0.1).
- **Block A.** `z = β · treated × post + school × stack FE + stack × year FE`, weights per §0.3,
  clustered per §0.4. Event study: treated × event-time dummies, t = −1 reference.
- **Guard (DDD).** The notebook's §9 DDD on the same windows: built and proposed sites,
  site cohort × year FE and near × year FE (identified by the proposed sites). Proposed walls
  are undated, so they cannot form stacks of their own.
- **Block B.** Block A plus `treated × post × (noise_reduction_db − 7)`.

## 4. ◇ Rules

- **◇ G1, construction (loads no outcome).** After the pipeline change, the protected schools
  equal the notebook's treated schools, and the point-tier counts do not change. If either
  fails, the build is fixed before anything else.
- **◇ G2, construction (loads no outcome).** A stack enters if it has at least one treated and
  one control school observed both before and after τ_w within the window. A school protected
  by several walls belongs to its earliest wall (as `gvar`). A control school is dropped from a
  stack if any wall protects it within the window.
- **◇ G3, construction (loads no outcome).** Before any outcome is loaded, record: stacks,
  treated and control schools per stack, schools in more than one stack, walls per district.
  Fewer than 20 stacks: block A is run but labelled "underpowered; descriptive only".
- **◇ A1.** "A wall changes scores behind it" is claimed only if β's RI p is below 0.05 (999
  permutations of the treated/control label within each stack). WCR by district above 0.05:
  label "fragile".
- **◇ A2.** If A1 holds, it is labelled a wall effect only if the DDD against proposed walls
  has the same sign and p below 0.10. Otherwise: "corridor path, not the wall" (the lesson of
  the notebook's §9).
- **◇ A3.** Event-study leads jointly below 0.10: A1 is labelled "pre-trend; not read as
  causal".
- **◇ A4.** Any split of block A (distance bands, Type I vs. state walls, road type) is
  corrected by Holm across the splits run, and none is claimed without A1.
- **◇ B1.** The dose is a robustness check, not a finding. It is reported as "consistent with
  A1" if its sign matches A1 and p is below 0.10 (WCR by district); otherwise "no dose
  response". It is never claimed on its own.

## 5. Outcomes

Nothing has run.

## Change log

- **2026-11-18, draft.** Written from the exploratory run's Summary (2026-10-22/23) and
  `within_barrier_design.md` steps 2–3. For Felix to decide §0.
