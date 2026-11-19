---
type: prespec
state: draft
updated: 2026-11-18
line: sweden-schools
step: 1
summary: "Step 1: check the 2001 walls and recover construction years, then re-estimate the headline (RI decides) and re-test the parental-education gradient on new schools"
---

# The 2001 cohort and recovered construction years (Pre-Specification)

**Status.** Draft 2026-11-18, for Felix. Nothing has run. §0 lists the open choices; nothing
loads an outcome before they are decided.

**Outcome in one line:** (filled in when recorded)

**Why this step.** The exploratory run ([`results.md`](results.md)) rests on 11 identifying
schools. Two of them, the 2001 cohort, carry the headline (+0.285 with them, +0.066 without).
58 more treated schools are dropped because no matching barrier has a construction year. This
step checks the dates first, without looking at scores, and only then re-estimates.

## 0. Decisions for the author

1. **Which schools get the date check.** Recommended: the barriers of **all 23 in-window
   treated schools** (and the 58 undated ones, block G2), with the same protocol, not only the
   two 2001 schools. Checking only the schools that carry the result is a selective audit: it
   can only remove an effect, never add one. **Decided:**
2. **Which evidence counts for a construction year** (rule ◇ G1). Recommended order: (a) a
   Trafikverket project record or archive; (b) the register's `built_year`; (c) a bracket from
   dated aerial imagery (Lantmäteriet historical orthophotos; Street View for roads), the
   first year the wall is visible, if the bracket is at most 2 years wide. `valid_from` alone
   never counts (the 2006 batch only says "built by 2006"). **Decided:**
3. **Bracket width for imagery dates.** Recommended: at most 2 years (the year assigned is the
   first year the wall is visible). Alternative: 3 years, which recovers more schools with a
   noisier event time. **Decided:**
4. **The parental-education gradient.** Recommended: re-test it **only on newly identifying
   schools** (schools that gain a pre- and post-period through this step). They did not
   produce the gradient, so this is a confirmatory test. The full-sample estimate is reported
   but decides nothing. Alternative: re-test on the full corrected sample (more power, but it
   contains the 11 schools that produced the gradient). **Decided:**
5. **Event-study base period.** Recommended: adopt `long2` for `estat event` (every pre-period
   relative to g−1, as a textbook event study), in this line and in Florida's. It changes only
   the pre-period plot; `estat simple` and the post-period ATTs do not change. **Decided:**
6. **Outcome.** Recommended: `meritvärde_z` stays the outcome. SALSA's residual, pass rate and
   eligibility are secondary and decide nothing. **Decided:**
7. **Multiple testing across the two deciding tests** (◇ A1, ◇ B1). Recommended: Holm over
   the two. **Decided:**

## 1. Questions

| Block | Question |
|---|---|
| G | Are the construction years of the identifying schools' barriers right, and how many of the 58 undated treated schools can be dated? (loads no outcome) |
| A | On the corrected sample, do barriers raise `meritvärde_z`, judged by randomization inference? |
| B | Does the parental-education gradient hold on schools that did not produce it? |

## 2. Data

- **Panel.** `data/sweden/panel/assembled/event_study_panel.parquet`, rebuilt after block G.
  Sample rules as in the exploratory run
  (`src/noise_pollution/analysis/sweden_schools.py`, `build_analysis`): `meritvärde_z`,
  1998–2019, `protected` tier, road or rail, first barrier dates the school.
- **The 2001 walls.** Barrier rows road 1166 (kommun 1880, Örebro) and rail 551 (kommun 1293,
  Hässleholm). Check: the construction year, the audit's side, the school's distance and
  whether it lies beside the stretch.
- **The 58 undated treated schools** and their barriers (`road/rail_timing_unknown_protected`).
  Most undated road records come from the batch loaded when the register started in 2006
  ([`noise_barriers`](../../data/sweden/noise_barriers/README.md)).
- **Date sources.** Trafikverket (questions 1–2 of the noise-barriers page), dated aerial
  imagery, Street View (roads). The reviewer records the source and the bracket per barrier.

## 3. Specification

- **Block G.** No model. A table per barrier: register year, recovered year, source, bracket,
  side and distance confirmed (yes / no / changed).
- **Block A.** As §4 of the exploratory run: `csdid meritvarde_z, ivar(id) time(year)
  gvar(gvar) notyet method(dripw)`, `estat simple`. No controls. Standard errors clustered by
  school (reported). Randomization inference: the Python CS ATT (`cs_simple_att`), 1,999
  shuffles of the treatment year across schools, seed 20261022.
- **Block B.** As §9: `reghdfe meritvarde_z post post_edu i.year#c.parent_edu_base_z if
  !always, absorb(id year)`, on newly identifying treated schools plus all controls. Baseline
  parental education in each school's first observed year, standardised across all schools.

## 4. ◇ Rules

- **◇ G1, construction (loads no outcome).** A construction year counts if it comes from the
  evidence accepted in §0.2 within the bracket of §0.3. Where two sources disagree by more
  than one year, the higher-ranked source wins and the case is listed.
- **◇ G2, construction (loads no outcome).** A checked school is **kept** if its year is
  confirmed (±1 year) and its side and distance hold; **re-dated** if accepted evidence gives
  a year more than one year off; **dropped** as timing-unknown if the evidence contradicts the
  register year but gives no year of its own; **moved to control or dropped** if the side or
  stretch does not hold (as the panel's own rules then say). The same rules apply to the 2001
  schools as to every other school.
- **◇ G3, construction (loads no outcome).** Before any outcome is loaded, record: treated
  schools, identifying schools (observed before and after), newly identifying schools, and
  schools per cohort. The reviewer does not see scores.
- **◇ A1.** "Barriers raise grade-9 achievement" is claimed only if the CS ATT on the corrected
  sample is positive and its RI p is below 0.05 (after §0.7's correction). School-clustered p
  is reported but does not decide. Otherwise: "no effect distinguishable from chance".
- **◇ A2.** If A1 holds, it is labelled "rests on one cohort" when dropping the cohort with the
  largest weight in `estat simple` takes RI p to 0.10 or above.
- **◇ A3.** If the CS event study (base period per §0.5) has `Pre_avg` with p below 0.10, or
  TWFE leads jointly below 0.10 (RI), A1 is labelled "pre-trend; not read as causal".
- **◇ B1.** "The gradient replicates" is claimed only if, on newly identifying schools, `post`
  × parental education is positive and its RI p (999 shuffles of the baseline across
  schools, one-sided, as the sign is predicted) is below 0.05 (after §0.7's correction).
  Fewer than 6 newly identifying schools: "not testable", and the test is not run.
  Otherwise: "not replicated".

## 5. Outcomes

Nothing has run.

## Change log

- **2026-11-18, draft.** Written from the exploratory run's Summary (2026-10-22) and the
  charter's next step. For Felix to decide §0.
