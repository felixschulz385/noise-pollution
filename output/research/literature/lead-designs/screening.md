# Lead-exposure designs as precedents for the noise-barrier cohort design

2026-11-02. Purpose: method precedents for `output/documents/empirical-strategy/` (cohort dose
D_i = years lived with the barrier before the test; assignment by the mother's cell before the
project; protected vs. comparison cells; stacked event study; grade-9 scores). Not a novelty check.

## Search log

- Seeds (OpenAlex, all versions): Grönqvist, Nilsson & Robling 2020 JPE (+ IFAU WP 2017:4);
  Nilsson 2009; Hollingsworth, Huang, Rudik & Sanders (NBER w28250, SSRN, JHR 2022);
  Aizer, Currie, Simon & Vivier 2018; Rau, Urzúa & Reyes (NBER 2013); Persico, Figlio & Roth
  2020; Reyes 2007 (NBER + BEJEAP); Hollingsworth & Rudik 2021; Zahran et al. 2017;
  Klemick, Mason & Sullivan 2020; Billings & Schnepel 2018 (4 versions).
- Forward + backward citations of every seed; 12 boolean OpenAlex sweeps (lead x test scores,
  gasoline phase-out, airports/avgas, smelters/superfund x distance, pipes/Flint, roads/soil,
  causal-design terms, remediation, cumulative/dose, plant openings/closings, wind, Swedish terms).
- Corpus: 2,665 records. Screened by regex filters over the whole corpus (lead terms x design
  terms; econ venues), not only the top of `ranked.md`.
- Web checks: Persico & Venator 2021, Zahran, Keyes & Lanphear 2023, Clay, Severnini & Wang 2025,
  Berkhout et al. 2025 (ADB WP 774, full text read), Grönqvist et al. WP (full text, design
  section read), Hollingsworth et al. w28250 (full text, design section read), Trejo et al. 2024.
- Not done: Semantic Scholar (HTTP 429), Google Scholar (no export). Abstracts not read:
  Klemick et al. 2020, Sorensen et al. 2019, Jacqz 2022, Keyes, Zahran & Mushinski
  ("Long Reach of Lead", SSRN 403), Gamper-Rabindran & Timmins 2013.

## Precedents by design element

### A. Birth cohort x timing of the source change -> exposure dose (our D_i)
- **Grönqvist, Nilsson & Robling 2020 JPE.** Sweden, ~800k children born 1972-84; moss lead
  in the *birth neighbourhood* (parish) at ages 1-3, varying by cohort through the gasoline
  phase-out; outcome grade-9 GPA as a percentile rank (across grading reforms), HS completion,
  crime, earnings; parish + cohort FE, cohort-neighbourhood cells, CZ clustering; sibling FE
  in an appendix; nonlinear, effects above thresholds, boys larger. Closest in data, outcome,
  assignment-at-birth-place (ITT) and robustness set.
- **Nilsson 2009 WP.** Earlier version: nine cohorts, threshold nonlinearity, larger effects
  for low SES.
- **Hollingsworth, Huang, Rudik & Sanders 2022 JHR ("A Thousand Cuts").** Florida schools;
  cumulative inverse-distance-scaled lead from NASCAR races within 50 miles over a cohort's
  life, which stops after the 2007 switch to unleaded; school-grade-subject-year scores,
  school + year FE, clustered by district; separates *duration* (years exposed) from
  *quantity*: duration matters even holding quantity fixed. Treated 3rd-grade cohorts have at
  most 8 cumulative years.
- **Berkhout, Maulana, Molato-Gayares, Park & Suryadarma 2025 (ADB Econ WP 774).** Indonesia,
  lead toxic sites (battery recycling); first exposed in utero/0-6 vs. at 7+ x ln(distance) or
  distance band (<3 km, 3-6 km vs. 6-10 km), site + age-at-test + wave FE, estimated with the
  Gardner (2024) two-stage DiD correction (staggered openings, no never-treated); distance
  fixed at first appearance, movers keep it. Same functional form as ours.
- Background: Reyes 2007; Banzhaf & Banzhaf 2023 (county x month in utero); Keyes, Zahran &
  Mushinski (phase-out x geography -> test scores; abstract unread).

### B. Near ring vs. outer ring, before/after the source changes (protected vs. 600-1,500 m band)
- **Currie, Greenstone & Moretti 2011 AER.** Births <2 km vs. 2-5 km of Superfund sites,
  before/after cleanup (removal of exposure, as with a barrier).
- **Persico, Figlio & Roth 2020 JOLE.** Florida; siblings gestated before vs. after a nearby
  Superfund cleanup (or a family move); test scores and behaviour. Template for timing-of-removal
  x siblings.
- **Persico & Venator 2021 JHR (TRI, not lead-specific).** Florida schools <1 mile of a TRI
  plant opening/closing vs. 1-2 miles; event study; test scores.
- **Currie, Davis, Greenstone & Walker 2015 AER.** 1,600 plant openings/closings; emissions move
  air quality only within 1 mile, infant-health effects within 1 mile; how to choose the ring.
- **Rau, Urzúa & Reyes 2015 JAERE.** Arica, Chile: residential/school distance to a toxic-waste
  dump x cohort, DiD; scores rise 0.07-0.09 SD per km.
- **Bui, Shadbegian, Marquez & Klemick 2022 Env Int.** NASCAR deleading 2007: births <4 km vs.
  >10 km of the speedway, DiD.
- **Klemick, Mason & Sullivan 2020 JEEM.** Superfund cleanups -> child BLL (abstract unread).

### C. Same distance, different exposure (our opposite-side contrast)
- **Heissel, Persico & Simon 2022 JHR (air pollution, not lead).** Schools at the same distance
  from a highway, downwind vs. upwind; students switching schools. Closest analog to
  "opposite side, same distance", and also the threat to it: near-road air pollution is
  wind-asymmetric too.
- **Zahran, Iverson, McElmurry & Weiler 2017 JAERE.** Michigan airports: BLL dose-response in
  distance, piston traffic, share of days downwind; drop after 9/11 grounding.
- **Zahran, Keyes & Lanphear 2023 PNAS Nexus.** Reid-Hillview airport: <0.5 mi vs. 0.5-1.5 mi,
  downwind vs. upwind.
- **Clay, Severnini & Wang 2025 (NBER w33447).** Fugitive lead emissions x wind speed as IV.

### D. Road proximity x timing, and per-unit (2SLS) scaling
- **Aizer & Currie 2019 REStat.** Rhode Island; instruments BLL with within-neighbourhood
  variation from road proximity x the deleading of gasoline (a near-road x cohort timing
  design), plus multiple noisy measures; OLS understates. Precedent for our 2SLS per realised
  year.
- **Aizer, Currie, Simon & Vivier 2018 AEJ Applied.** BLL -> 3rd-grade reading, IV from
  multiple measures and housing-remediation timing.
- **Clay, Portnykh & Severnini 2019 EHB.** Topsoil lead, IV from the 1944 Interstate plan.

### E. Assignment at a pre-period place; movers
- Grönqvist et al. (birth neighbourhood); Berkhout et al. (migration histories);
  **Fletcher & Noghanibehambari 2023/2025** (birth-city lead, not later residence, drives
  old-age mortality: analog of our ITT vs. residents-at-test gap); **Ferrie, Rolf & Troesken
  2012 EHB** (1930 residence -> WWII test scores; longer exposure, larger effect).

### Background (one line)
Billings & Schnepel 2018; Sorensen et al. 2019; Gazzè, Persico & Spirovska 2024 JOLE (peer
spillovers); Reyes 2015; Sauve-Syed 2023 and Trejo, Yeomans-Maldonado & Jacob 2024 (Flint;
the latter contested); Dave & Yang 2022; Troesken 2008; Feigenbaum & Muller 2016; Erixson et
al. 2024 JUE (Swedish SES vs. toxic-metal exposure: little sorting); Clay, Hollingsworth &
Severnini 2023 (review of quasi-experimental lead studies).

## What to take for the design
1. Cite Grönqvist et al. as the Swedish register precedent for birth-place assignment, cohort x
   place FE, sibling FE as robustness, and percentile-ranked grade-9 GPA.
2. Hollingsworth et al. separate duration from intensity; with per-barrier dB attenuation we
   could do the same (D_i x dB as a secondary dose).
3. Ring cut-offs in the literature come from a shown gradient (CDGW 2015, CGM 2011, Zahran
   2023); a distance-band gradient plot would justify the 600-1,500 m band.
4. Heissel et al. is the precedent *and* the threat for the opposite-side contrast; it argues
   for testing wind asymmetry rather than using wind only as heterogeneity.
5. Berkhout et al. use our functional form and already correct TWFE (Gardner two-stage);
   they cite the same heterogeneity problem we do, so this is a shared choice, not an advantage.
