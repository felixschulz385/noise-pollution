# Florida: distance and within-barrier designs (plan, 2026-09-30)

The Florida analysis (`output/notebooks/florida/analysis.ipynb`) finds no
effect of wall construction on test scores. This plan takes three steps
toward the design of Moretti & Wheeler (2025, NBER w34298), who find a
clear house-price effect of the same FDOT walls. It uses what
`barrier_protection` added on 2026-09-30:
- `lateral_m` (already in the pair table)
- the control band (`control_band_zones`)
- `noise_reduction_db`

See [`barrier_protection.md`](barrier_protection.md) and
[`shared_methodology.ipynb`](../../../src/experiments/shared_methodology.ipynb) §2.

## Why

Moretti & Wheeler's effect is 6.8% within 100m of the wall and fades to
zero by 300-400m. The design compares homes 0-500m behind a wall with
homes 500-1500m behind the same wall, and scales the effect by each wall's
decibel reduction. Our protected tier differs in three ways:
- **One flag for 0-600m.** Most treated schools sit where they find
  nothing (table below), so a real effect near the road could be diluted.
- **Statewide controls.** The CS/TWFE controls are never- or
  not-yet-treated schools anywhere in Florida. Treated schools sit by roads
  with about 4× the traffic (`analysis.ipynb` §3).
- **No dose.** The wall's dB reduction isn't used.

## What the data supports (measured 2026-09-30)

| | schools |
|---|---|
| protected by a built wall | 128 (125 dated) |
| … 0-150m from the road (`protected_lateral_m`) | 17 |
| … 150-300m | 47 |
| … 300-450m | 28 |
| … 450-600m | 36 |
| in the event-study panel | 116 (57 within 300m, 59 beyond) |
| in a built wall's control band, protected by no wall | 237 |
| walls with both a protected and a band school | 33 walls (46 protected, 59 band schools) |
| proposed walls with both | 8 walls |

`protected_lateral_m` is the distance from its road of the wall that dates
the school's treatment: the earliest-built protecting wall, the nearest
among equals. For 2 of the 27 schools with several protecting walls this
is not the nearest one. `schools assemble` writes it to the rollup (since
2026-09-30), and `panel assemble` carries it.

## The three steps, in order

### 1. Distance split (implemented 2026-09-30, `analysis.ipynb` §12)

Split the treated schools at 300m from the road. Estimate each half against
the same controls as §4-§6:
- **CS:** `csdid` on `gvar == 0 | near` and on `gvar == 0 | far`.
- **TWFE:** `post_near` and `post_far` in one model (Panel B: school and
  grade × subject × year FE), with a test of equality. A second model uses
  four 150m bins, the analogue of Moretti & Wheeler's distance profile.
- **Reading:** a real effect diluted by distant schools shows up near and
  fades far. Nulls in both halves mean dilution isn't the explanation.

No pipeline change beyond `protected_lateral_m`.

**Result (run 2026-09-30).** Not a diluted benefit: the near half moves
*down*.

| treated schools | CS ATT | SE | p | TWFE, + controls |
|---|---|---|---|---|
| all | -0.051 | 0.068 | 0.460 | |
| near, 0-300m | -0.171 | 0.085 | 0.044 | -0.160 (0.076) |
| far, 300-600m | +0.082 | 0.099 | 0.408 | +0.015 (0.098) |
| … 0-150m | | | | +0.160 (0.237) |
| … 150-300m | | | | -0.218 (0.071) |

- The near group's event study has flat leads (`Pre_avg` -0.014, p=0.315)
  and a gradual decline after construction (`Tp4` -0.176, `Tp8` -0.313).
- There is no distance gradient. The effect sits entirely at 150-300m,
  and 0-150m has only 5 schools with a pre-period.
- About 30 schools carry it (31 near schools with a pre-period, on 19
  roads in 8 districts).
- **Robustness (`analysis.ipynb` §13, run 2026-09-30): real but fragile.**
  - Cutoff: CS is negative from 200m to 400m (-0.21 to -0.13; p<0.05 at
    250-300m only). TWFE's near/far contrast holds only at 250-300m.
  - Permutation (999 random near/far splits of the treated schools): the
    near-far gap has p=0.049.
  - Leave one district or road out: the sign never changes, but 12 of 27
    drops take p above 0.05 (at most 0.139).
  - Holm over §12's six splits: CS near 0.222, TWFE 150-300m 0.013.
  - Intake: the near schools' enrollment falls by about 10% (p=0.029), and
    their free/reduced-lunch share rises 4.5 points (p=0.19).
  - Traffic: the busiest road within 500m of a near school is +7.5% after
    construction (p<0.001; pre-trend not checked). The protecting road's
    own AADT has no break at construction.
  - So the drop comes with fewer students and more traffic around the
    road, which fits a lasting change near the road (traffic, right-of-way
    takings, families leaving) better than a construction disturbance.
    Part of it may be who attends.
- **Wall or road works (`analysis.ipynb` §13 (g)-(i), run 2026-09-30).**
  - The near schools' enrollment has no pre-trend and falls from the
    construction year on (`Post_avg` -0.127, p=0.001).
  - Their nearby traffic was already rising before the wall (`Pre_avg`
    p=0.002), so the traffic rise isn't tied to it.
  - Against the 13 schools within 300m of a proposed, never-built wall's
    road, the near drop is zero (CS +0.000, SE 0.099; TWFE +0.028).
  - It is larger behind federal Type I walls (new road or added lanes:
    CS -0.211, p=0.049) than behind state ones (-0.113), not
    significantly (TWFE p=0.42).
  - Every FDOT wall came with a highway project: 780 of 1,245 built walls
    are Type I, the rest state or other, none a Type II retrofit. The
    wall and its road project can't be separated in this data. Linking
    `fm_id` to the Work Program only works for recent walls (the fetched
    program covers fiscal years 2023-2030).
- **What it changes for step 2.** The evidence leans toward the road
  project, not the wall, without settling it. The within-wall design
  absorbs road-wide changes but not a disturbance that fades within 600m,
  so it would not separate them either. It still answers a different
  question: is there any wall effect at all, against schools behind the
  same wall but farther out?

### 2. Within-wall stacked design (not started)

The analogue of Moretti & Wheeler's Eq. 1:
- **Units:** per wall, its protected schools are treated and its
  control-band schools are controls. Stack one dataset per wall on the
  wall's own event time (window about ±6 years).
- **Model:** school FE + wall × year FE, clustered by wall (Cengiz et al.
  2019 stacked DiD).
- **Size:** 33 walls / 46 treated schools. To widen it, let band schools of
  other walls on the same `roadway_id`, or within about 1km along the same
  road, serve as controls.

Pipeline changes it needs:
- `schools assemble` calls `classify_points(..., control_max_lateral_m=1500)`
  and writes `control_band` and `control_band_gcids` (excluding schools
  protected by any wall) to the rollup.
- Wall-school pairing widens from 1,000m to about 1,650m (1,500m from the
  road plus the wall's offset). The point tier keeps its own 1,000m radius,
  so its counts don't change.
- `panel assemble` carries the new columns.

Caveat: a school's catchment reaches well beyond 600m, so band schools can
share families with treated schools. That spillover pushes the estimate
toward zero.

### 3. Dose (not started)

Interact `post` with `noise_reduction_db − 7` among treated schools. 503 of
1,245 built walls carry exactly 7.0 dB and the interquartile range is
7-8 dB, so this is a robustness check, not a finding.

**Not feasible:** a matched design on proposed walls (their DDD). Only 8
proposed walls have schools on both sides of the 600m line.
