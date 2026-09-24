"""Final assembly for the Sweden barrier-construction event study: joins the
outcome (`assessments`, both vintages) with `schools assemble`'s
road/rail x point/same_route/same_side/protected treatment-timing
definitions into one long analysis panel.

`REQUIRES` `assessments {preprocess-kvalitetssystem,preprocess-siris}` and
`schools {assemble,assemble-rail-network,assemble-road-network,
build-lineage}` to have already run -- this module does no fetching or
cleaning of its own, only joining already-processed local artifacts. Kept
as its own stage (not folded into `schools/assemble.py` or
`assessments/*.py`), same isolation reason Florida's `panel/assemble.py`
is separate: editing an outcome parser or the barrier match should never
have to re-run this join, and vice versa.

**Vanished-school coordinate recovery (2026-09-23, optional)** --
`vanished_recovery.py` recovers real coordinates (via Skolkoll, a
third-party aggregator that retains school units Skolverket's own live
registry purges outright) for 306 of the 803 SIRIS-assessed schools that
have no registry entry at all (see that module's docstring and
`docs/data/sweden/schools/README.md`'s "vanished pre-registry schools"
section). Unlike every other input above, this one is genuinely optional:
`load_treatment_rollup_with_recovery` falls back to the registry-only
rollup, unchanged, if `sweden data panel recover-vanished-schools` hasn't
been run yet -- the panel already produced a complete, working (if
incomplete for this one population) result before this existed, so making
it a hard requirement the way `assessments`/`schools` are would break
every existing full-pipeline run over one additive enhancement. Still only
reaches the 536 *modern* 8-digit vanished codes, not the 267 legacy
9-digit pre-2013 ones -- Skolkoll's ids are themselves modern-format.

**`skolenhetskod` lineage remap (2026-09-22)** -- applied right after
`build_outcomes_long`/`build_treatment_rollup`, before the outcome/
treatment join. `schools/lineage.py`'s high-confidence crosswalk
(`old_code -> new_code` for a retired unit and its reorg successor, see
that module's docstring) is applied by `remap_outcomes_to_lineage` and
`remap_treatment_rollup_to_lineage` -- two different merge policies, not
one, because the two tables need different safety guarantees. The
treatment rollup is purely geometric (barrier distance from a point): a
lineage pair's two rows describe the *same* co-located point, so they're
expected to already agree, and remap-then-aggregate (`ever_treated_*`/
`ever_near_1000m` OR'd, `first_treat_year_*` earliest known,
`nearest_dist_m` min, `n_barriers_1000m` max) is safe and lossless --
confirmed live: every collision checked had identical values on both
sides. Outcome rows are each school's own reported achievement figures,
which CAN legitimately differ for two co-located units that operated in
parallel for a time (confirmed live: 111 `(year, outcome)` keys collide
after a blind remap, e.g. a retiring "B-track" unit and its still-active
sibling both reporting `meritvärde` for the same years) -- there's no
safe way to average two schools' own averages without a student-count
reweight this data doesn't carry for every outcome, so
`remap_outcomes_to_lineage` only remaps a row when the target key is
**not already occupied**, i.e. it fills the successor's real pre-reorg
history gaps and leaves any genuinely overlapping year under its
original code rather than guessing which one is right.

**Cross-era stitching decision (2026-09-17)**: `kvalitetssystem`
(2022/23-2025/26) is kept out of this assembly for now -- its nearest
conceptual analogue to `meritvärde` (`measure_code` `27`, "Delmål 1: ...
lägst betyget E i samtliga ämnen efter årskurs 9") is a binary pass-rate
**share**, not a continuous score (confirmed live by listing all 51
`kvalitetssystem` measures, no `meritvärde`-named measure exists among
them), and the 2020-21 legal-suppression notch means it doesn't even abut
the SIRIS era. `load_kvalitetssystem`/`kvalitetssystem_to_long` are kept
below as-is (still useful for a standalone `kvalitetssystem`-only
analysis) but are no longer called from `run_panel_assemble`.

Within the SIRIS era itself (1998-2019), `stitch_meritvarde` resolves
option (a) from `docs/data/sweden/assessments/README.md` §4: the raw
`genomsnittligt_meritvärde` column is picked per year (`_16` for the old
IG/G/VG/MVG scale, läsår through 2013/14; `_17` for the new A-F scale,
läsår 2014/15 on, including år 2016's one-year doubled-header anomaly via
its `inklusive_okänd_bakgrund`-prefixed `_17` variant -- see the README's
§4 for how both scales were confirmed to share the same 0-320/340 point
range), then z-scored **within each side of the break separately**
(`old_scale` mean/std, `new_scale` mean/std) and stacked into one
continuous `meritvärde_z` outcome -- mirroring how Florida's `z_mss`
differences out its own FCAT/FSA regime breaks by construction. This does
not resolve the harder content-validity question (grading *criteria*
changed at the reform, not just the points scale) -- it's the
literature-backed judgment call the README flagged as undecided, now
picked. `build_outcomes_long` still reshapes SIRIS's raw per-measure
columns into long form too (`(skolenhetskod, year, era, source_dataset,
outcome_name, value)`, one row per real observed value) alongside the
stitched series, so nothing here forces every downstream question to use
`meritvärde_z` specifically.

**Four more stitched series, same "pick the real column, handle the known
seams" recipe (2026-09-22)**: `meritvärde_zw` (`stitch_meritvarde`'s
`antal_elever`-weighted sibling to `meritvärde_z`, mirroring Florida's
`z_mss`/`z_mss_w` pair -- see that function's docstring for why weighting
the standardisation is a different lever from weighting the regression
that consumes it); `andel_uppnått_kunskapskraven_combined` and
`andel_behörig_combined` (`stitch_pass_rate`/`stitch_eligibility` --
extensive-margin pass-rate/eligibility shares, stitched across their own
column-naming seams but left unstandardised, unlike meritvärde, since
neither needs it -- see each function's docstring for the empirical checks
behind that); and `meritvärde_residual_z` (`stitch_salsa_residual` --
SALSA's own composition-adjusted value-added residual, a robustness
outcome with its own bad-control caveat, see that function's docstring).

**Treatment timing is carried as eight parallel definitions**
(`{road,rail}_{point,same_route,same_side,protected}` --
`schools/assemble.py`'s two barrier kinds x four matching-rigour tiers;
`protected` = same side and beside the barrier's own stretch, see
`docs/data/sweden/barrier_matching.md` §7.1) rather than collapsed to one,
mirroring Florida's own three-parallel-definitions convention. A school
with no nearby barrier of a given kind at all gets `ever_treated_*=False`
(a real, informative value), not a missing row or NA -- the outcome-side
join is a LEFT join anchored on the outcomes-long table, so no outcome row
is ever dropped for a missing treatment match (e.g. an ungeocoded school
absent from `schools assemble`'s rollups).

**Traffic (Cluster C) is a genuinely time-varying join, not a
broadcast** -- `attach_traffic` picks, for each outcome row's own `year`,
whichever of the matched school's recovered historical
`[valid_from, valid_to)` windows actually covers that year (a
`merge_asof`-by-vintage interval join, see `attach_traffic`'s own
docstring). This corrects a real, same-session mistake: an earlier version
of this module concluded (from a test that turned out to be biased --
see `docs/data/sweden/traffic/README.md`'s "Correction" section for the
full story) that Lastkajen's `Betraktelsedatum` field couldn't return real
historical ÅDT data, and shipped a flat single-snapshot broadcast instead.
A user-provided example (a real road section's own historical-traffic
lookup on Trafikverket's own web viewer) proved that conclusion wrong --
`Betraktelsedatum` DOES return genuine historical `[valid_from, valid_to)`
windows, `traffic/preprocess.py` now unions every `Trafik` order's full
window history instead of filtering to "current only", and this join
follows suit. A school-year outside every window `preprocess` has managed
to recover (e.g. a läsår before the earliest order's coverage for that
segment) still gets real `NA` traffic columns -- more historical
`Betraktelsedatum` orders (spanning further back, matching the confirmed
4-year/12-year remeasurement cycle) would recover more coverage, this
doesn't need a different product or access method after all.

**Neighbourhood (Cluster F) is joined the same way `traffic` is
attached, but simpler** -- `attach_neighbourhood` (2026-09-17) is a plain
`(skolenhetskod, year)` merge, not an interval-overlap join: DeSO
boundaries don't move year to year the way NVDB's segment-level
`Betraktelsedatum` windows do, so `neighbourhood/assemble.py` already
does the interesting work (point-in-polygon match + outer-merging
income/education/employment on `(desokod, year)`) upstream of this join.
Columns land `neighbourhood_`-prefixed (mean net income, post-secondary
education share, employment rate, plus the raw component counts behind
the derived shares, and `desokod`/`kommunkod`/`lanskod` for a future
DeSO-level cluster-SE choice). A school-year outside every one of the
three source tables' own real coverage (all capped at 2023, see
`docs/data/sweden/neighbourhood/README.md`) gets real `NA`, same
convention as every other covariate here.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.regions.sweden.sources.assessments.shared import assessments_paths
from src.regions.sweden.sources.assessments.siris import IDENTITY_COLUMNS as SIRIS_IDENTITY_COLUMNS
from src.regions.sweden.sources.neighbourhood.shared import assembled_school_neighbourhood_path
from src.regions.sweden.sources.panel.shared import assembled_metadata_path, assembled_panel_path
from src.regions.sweden.sources.schools.lineage import load_lineage_crosswalk
from src.regions.sweden.sources.schools.shared import schools_paths
from src.regions.sweden.sources.traffic.shared import assembled_school_traffic_path

BARRIER_KINDS = ("road", "rail")
TREATMENT_DEFINITIONS = ("point", "same_route", "same_side", "protected")
SIDE_UNKNOWN_FLAGS = ("same_side_unknown", "protected_unknown")

SIRIS_DATASET_KEYS = ("slutbetyg_arskurs9", "salsa")

# `stitch_meritvarde`'s two SIRIS-internal grading-scale sub-eras (see the
# module docstring) -- the last old-scale åk9 slutbetyg was läsår 2013/14
# (år 2014); läsår 2014/15 (år 2015) on is the new A-F scale.
MERITVARDE_OLD_SCALE_LAST_YEAR = 2014
MERITVARDE_OLD_SCALE_COLUMN = "genomsnittligt_meritvärde_16"
MERITVARDE_NEW_SCALE_COLUMN = "genomsnittligt_meritvärde_17"
# år 2016's one-year doubled-header anomaly (module docstring, README §4)
# only carries the new-scale figure under this prefixed name.
MERITVARDE_2016_COLUMN = "inklusive_okänd_bakgrund_genomsnittligt_meritvärde_17"
# The same år-2016 anomaly hits `antal_elever` too (checked empirically --
# it's NaN for every 2016 row; that year's real count only exists under
# this prefixed name), which `stitch_meritvarde`'s weighted `meritvärde_zw`
# needs handled the same way or 2016 silently drops out of the *weighted*
# series (while staying in the unweighted one) with no error or warning.
ANTAL_ELEVER_COLUMN = "antal_elever"
ANTAL_ELEVER_2016_COLUMN = "inklusive_okänd_bakgrund_antal_elever"

# `andel_som_uppnått_kunskapskraven_i_alla_ämnen` (pass rate: met the
# knowledge requirements in every subject) keeps one column name across the
# entire SIRIS window -- checked empirically (yearly coverage table), no
# _16/_17-style rename ever happens for this measure, only år 2016's usual
# doubled-header anomaly needs picking from its `inklusive_okänd_bakgrund`
# variant, same convention as meritvärde's own år-2016 handling.
PASS_RATE_COLUMN = "andel_som_uppnått_kunskapskraven_i_alla_ämnen"
PASS_RATE_2016_COLUMN = "inklusive_okänd_bakgrund_andel_som_uppnått_kunskapskraven_i_alla_ämnen"

# Eligibility-to-upper-secondary column name switches once, år 2010->2011
# (`_till_nationella_program` -> `_yrkesprog`, a Gy2011-reform label change),
# plus the usual år-2016 doubled-header variant. Checked empirically for a
# level/variance discontinuity at the 2010/2011 switch (yearly mean/std) --
# none found (both drift smoothly across the whole window), so unlike
# meritvärde this is treated as one continuous series, not split into
# sub-eras.
ELIGIBILITY_COLUMN_OLD = "andel_behöriga_till_nationella_program"
ELIGIBILITY_COLUMN_NEW = "andel_behörig_yrkesprog"
ELIGIBILITY_2016_COLUMN = "inklusive_okänd_bakgrund_andel_behörig_yrkesprog"

# SALSA's `genomsnittligt_meritvärde_faktiskt_värde_f` (F) keeps one column
# name across the whole window (no _16/_17 split the way slutbetyg has) --
# but its yearly mean still jumps ~10 points at the identical 2014->2015
# grading-scale reform (checked empirically), so the *residual* R = F - B
# needs the same old/new sub-era treatment as meritvärde_z: not because R's
# *mean* shifts (it doesn't -- B moves in lockstep with F, so the level
# shift cancels in F - B), but because R's *std* still drifts from ~11-13
# pre-reform to ~15-17 post-reform (checked empirically), which would still
# miscalibrate a single pooled z-score.
SALSA_RESIDUAL_COLUMN = "genomsnittligt_meritvärde_residual_r_f_b"

TRAFFIC_COLUMNS = [
    "dist_m",
    "element_id",
    "adt_samtliga_fordon",
    "adt_tunga_fordon",
    "adt_axelpar",
    "adt_latta_fordon_06_18",
    "adt_latta_fordon_18_22",
    "adt_latta_fordon_22_06",
    "adt_medeltunga_fordon_06_18",
    "adt_medeltunga_fordon_18_22",
    "adt_medeltunga_fordon_22_06",
    "adt_tunga_fordon_06_18",
    "adt_tunga_fordon_18_22",
    "adt_tunga_fordon_22_06",
    "matarsperiod",
    "matmetod",
]

NEIGHBOURHOOD_COLUMNS = [
    "desokod",
    "kommunkod",
    "lanskod",
    "mean_net_income_tkr",
    "pop_forgymnasial",
    "pop_gymnasial",
    "pop_eftergymnasial_kort",
    "pop_eftergymnasial_lang",
    "pop_uppgift_saknas",
    "total_pop",
    "share_eftergymnasial",
    "antal_sysselsatta",
    "antal_totalt",
    "employment_rate",
]


def load_kvalitetssystem(root: Path | None = None) -> pd.DataFrame:
    path = assessments_paths(root)["processed"] / "kvalitetssystem_grundskola.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data assessments preprocess-kvalitetssystem` first.")
    return pd.read_parquet(path)


def load_siris(dataset_key: str, root: Path | None = None) -> pd.DataFrame:
    path = assessments_paths(root)["processed"] / f"siris_{dataset_key}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing -- run `sweden data assessments preprocess-siris --dataset-key {dataset_key}` first."
        )
    return pd.read_parquet(path)


def load_treatment_rollup(kind: str, root: Path | None = None) -> pd.DataFrame:
    if kind not in BARRIER_KINDS:
        raise ValueError(f"Unknown barrier kind '{kind}'. Use one of: {BARRIER_KINDS}.")
    path = schools_paths(root)["assembled"] / f"schools_{kind}_rollup_network.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing -- run `sweden data schools assemble` then `assemble-{kind}-network` first."
        )
    return pd.read_parquet(path)


def load_treatment_rollup_with_recovery(kind: str, root: Path | None = None) -> pd.DataFrame:
    """`load_treatment_rollup` plus, if present, the vanished-school
    recovery rollup for the same `kind` (see `vanished_recovery.py`'s
    module docstring) -- the two populations are disjoint by construction
    (recovery only ever covers codes absent from the registry, which is
    exactly what `load_treatment_rollup`'s own population excludes), so a
    plain concat is safe: no `skolenhetskod` can appear in both. Imports
    `vanished_recovery` lazily (not at module top) since that module
    imports back from here (`find_vanished_codes` needs `build_outcomes_long`/
    `load_siris`) -- see its docstring for why."""
    from src.regions.sweden.sources.panel.vanished_recovery import load_vanished_recovery_rollup

    base = load_treatment_rollup(kind, root)
    recovered = load_vanished_recovery_rollup(kind, root)
    if recovered is None or recovered.empty:
        return base
    return pd.concat([base, recovered], ignore_index=True)


def load_school_traffic(root: Path | None = None) -> pd.DataFrame:
    path = assembled_school_traffic_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data traffic {{preprocess,assemble}}` first.")
    return pd.read_parquet(path)


def load_school_neighbourhood(root: Path | None = None) -> pd.DataFrame:
    path = assembled_school_neighbourhood_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data neighbourhood assemble` first.")
    return pd.read_parquet(path)


def melt_siris_to_long(df: pd.DataFrame, dataset_key: str) -> pd.DataFrame:
    """One `slutbetyg_arskurs9`/`salsa` frame (wide: one column per measure,
    varying by dataset and even by year -- e.g. the `_16`/`_17` meritvärde
    split at the grading-scale reform, see the module docstring) -> long
    `(skolenhetskod, year, era, source_dataset, outcome_name, value)` rows,
    one per real observed value. `IDENTITY_COLUMNS` (imported from
    `siris.py` rather than re-listed, so the two can't drift apart) are the
    descriptive columns to exclude from `outcome_name`, not measures."""
    id_vars = ["skolenhetskod", "year"]
    value_vars = [c for c in df.columns if c not in SIRIS_IDENTITY_COLUMNS and c not in ("year", "dataset_key")]
    melted = df.melt(id_vars=id_vars, value_vars=value_vars, var_name="outcome_name", value_name="value")
    melted = melted.dropna(subset=["value"])
    melted["era"] = "siris"
    melted["source_dataset"] = dataset_key
    return melted[["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]]


def kvalitetssystem_to_long(df: pd.DataFrame) -> pd.DataFrame:
    """Already long (`measure_code`/`measure_label`/`year_code`/`value`/
    `status`) -- just rename to the shared outcomes-long schema and drop
    rows with no real value (`status in {".","..","...","-"}`, i.e. not
    applicable/suppressed/rounded-to-zero -- confirmed live: `status="None"`
    (a real reported value) is exactly the `value.notna()` subset, see
    `docs/data/sweden/assessments/README.md` §1's real run numbers)."""
    out = df.dropna(subset=["value"]).copy()
    out["year"] = out["year_code"].astype(int)
    out["era"] = "kvalitetssystem"
    out["source_dataset"] = "kvalitetssystem"
    out["outcome_name"] = out["measure_label"]
    return out[["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]]


def _weighted_mean_std(values: pd.Series, weights: pd.Series) -> tuple[float, float]:
    """Population- (student-) weighted mean/std -- Florida's `z_mss_w`
    recipe (`assessments/preprocess.py`'s `_zscores`): `np.average` once
    for the mean, once for the variance around it. NaN weight/value pairs
    are dropped first; an all-missing or zero-total-weight group returns
    `(nan, nan)`, the weighted analogue of an undefined sample std."""
    ok = values.notna() & weights.notna()
    if not ok.any() or weights[ok].sum() <= 0:
        return float("nan"), float("nan")
    mu = float(np.average(values[ok], weights=weights[ok]))
    var = float(np.average((values[ok] - mu) ** 2, weights=weights[ok]))
    return mu, float(np.sqrt(var)) if var > 0 else float("nan")


def _zscore_by_group(df: pd.DataFrame, group_col: str, value_col: str, weight_col: str | None) -> pd.Series:
    """Unweighted (`weight_col=None`, plain `(x - x.mean()) / x.std()`) or
    population-weighted z-score of `value_col`, computed separately within
    each `group_col` level -- the shared "sub-era" recipe `stitch_meritvarde`
    originally used inline, generalised so every stitched outcome below
    (the weighted `meritvärde_zw` sibling, the SALSA residual) can reuse it
    instead of re-deriving the same few lines. A group with an undefined
    (unweighted) or zero/undefined (weighted) std -- e.g. a single-row
    group -- gets `NaN`, dropped by the caller same as today."""
    if weight_col is None:
        return df.groupby(group_col)[value_col].transform(lambda s: (s - s.mean()) / s.std())

    out = pd.Series(np.nan, index=df.index, dtype=float)
    for _, idx in df.groupby(group_col).groups.items():
        mu, sd = _weighted_mean_std(df.loc[idx, value_col], df.loc[idx, weight_col])
        if sd and sd > 0:
            out.loc[idx] = (df.loc[idx, value_col] - mu) / sd
    return out


def stitch_meritvarde(slutbetyg: pd.DataFrame) -> pd.DataFrame:
    """Two continuous z-scored series across the SIRIS-era grading-scale
    reform -- see the module docstring for why z-scoring each side of the
    break separately, then stacking, was picked. Picks whichever real
    column each year actually reports (`_16`/`_17`/år-2016's
    `inklusive_okänd_bakgrund` variant -- confirmed mutually exclusive by
    year, see the module docstring), drops rows with no real value, tags
    `old_scale` (year <= 2014) vs `new_scale` (year >= 2015), then
    z-scores within each side separately.

    Emits **both** `meritvärde_z` (unweighted -- every school-year counts
    equally, matching Florida's `z_mss`) and `meritvärde_zw` (weighted by
    `antal_elever`, matching Florida's `z_mss_w`): the unweighted version
    treats a 13-student and a 700-student school's yearly average as
    equally informative about what "1 SD" is; the weighted version
    standardises against a student-weighted mean/std instead, so a big
    school's typical spread counts more toward the reference distribution
    and a small, noisily-measured school's average gets less influence
    over it. `antal_elever=0` or missing rows drop out of the *weighted*
    series (undefined weight) but stay in the unweighted one."""
    value = slutbetyg.get(MERITVARDE_NEW_SCALE_COLUMN, pd.Series(index=slutbetyg.index, dtype=float))
    value = value.combine_first(slutbetyg.get(MERITVARDE_2016_COLUMN, pd.Series(index=slutbetyg.index, dtype=float)))
    value = value.combine_first(slutbetyg.get(MERITVARDE_OLD_SCALE_COLUMN, pd.Series(index=slutbetyg.index, dtype=float)))
    antal_elever = _combine_year_variant_columns(slutbetyg, [ANTAL_ELEVER_COLUMN, ANTAL_ELEVER_2016_COLUMN])

    base = slutbetyg[["skolenhetskod", "year"]].copy()
    base["value"] = value
    base["antal_elever"] = antal_elever
    base = base.dropna(subset=["value"])
    base["sub_era"] = base["year"].where(base["year"] <= MERITVARDE_OLD_SCALE_LAST_YEAR, "new_scale")
    base["sub_era"] = base["sub_era"].where(base["sub_era"] == "new_scale", "old_scale")

    frames = []
    for outcome_name, weight_col in (("meritvärde_z", None), ("meritvärde_zw", "antal_elever")):
        out = base[["skolenhetskod", "year"]].copy()
        out["value"] = _zscore_by_group(base, "sub_era", "value", weight_col)
        out = out.dropna(subset=["value"])
        out["era"] = "siris"
        out["source_dataset"] = "slutbetyg_arskurs9_stitched"
        out["outcome_name"] = outcome_name
        frames.append(out[["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]])
    return pd.concat(frames, ignore_index=True)


def _combine_year_variant_columns(df: pd.DataFrame, columns_by_priority: list[str]) -> pd.Series:
    """`combine_first` chain over several columns that are mutually
    exclusive by year (a `_16`/`_17`-style rename, or år 2016's doubled-
    header anomaly picking an `inklusive_okänd_bakgrund`-prefixed variant)
    -- the same "pick whichever real column this row's year actually
    reports" logic `stitch_meritvarde` uses, factored out so the pass-rate
    and eligibility stitchers below don't re-derive it."""
    value = pd.Series(index=df.index, dtype=float)
    for col in columns_by_priority:
        value = value.combine_first(df.get(col, pd.Series(index=df.index, dtype=float)))
    return value


def stitch_pass_rate(slutbetyg: pd.DataFrame) -> pd.DataFrame:
    """One continuous `andel_uppnått_kunskapskraven_combined` series (share
    of students meeting the knowledge requirements in every subject) across
    the whole 1998-2019 SIRIS window. Unlike `meritvärde`, this measure's
    column name doesn't change across the grading-scale reform -- only år
    2016's usual doubled-header anomaly needs picking from its
    `inklusive_okänd_bakgrund` variant. Left as a raw 0-100 share, **not**
    z-scored: it's naturally bounded and interpretable as-is (a
    percentage-point ATT), and there's no scale break here to correct for
    the way there is for meritvärde."""
    value = _combine_year_variant_columns(slutbetyg, [PASS_RATE_COLUMN, PASS_RATE_2016_COLUMN])
    out = slutbetyg[["skolenhetskod", "year"]].copy()
    out["value"] = value
    out = out.dropna(subset=["value"])
    out["era"] = "siris"
    out["source_dataset"] = "slutbetyg_arskurs9_stitched"
    out["outcome_name"] = "andel_uppnått_kunskapskraven_combined"
    return out[["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]]


def stitch_eligibility(slutbetyg: pd.DataFrame) -> pd.DataFrame:
    """One continuous `andel_behörig_combined` series (share eligible for
    upper-secondary school) across the whole 1998-2019 SIRIS window. The
    column name switches once, år 2010->2011
    (`andel_behöriga_till_nationella_program` -> `andel_behörig_yrkesprog`,
    a Gy2011-reform label change) plus år 2016's usual doubled-header
    variant -- checked empirically (yearly mean/std around the switch) for
    a level or variance discontinuity the way meritvärde has one at its own
    reform boundary; none found, both drift smoothly across the full
    window, so this is treated as one continuous series with no sub-era
    split. Left as a raw 0-100 share, not z-scored, same reasoning as
    `stitch_pass_rate`."""
    value = _combine_year_variant_columns(
        slutbetyg, [ELIGIBILITY_COLUMN_OLD, ELIGIBILITY_COLUMN_NEW, ELIGIBILITY_2016_COLUMN]
    )
    out = slutbetyg[["skolenhetskod", "year"]].copy()
    out["value"] = value
    out = out.dropna(subset=["value"])
    out["era"] = "siris"
    out["source_dataset"] = "slutbetyg_arskurs9_stitched"
    out["outcome_name"] = "andel_behörig_combined"
    return out[["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]]


def stitch_salsa_residual(salsa: pd.DataFrame) -> pd.DataFrame:
    """One continuous z-scored `meritvärde_residual_z` series: SALSA's own
    composition-adjusted value-added residual (`genomsnittligt_meritvärde_
    residual_r_f_b` = actual meritvärde minus a model-predicted value given
    each school's parental-education/immigrant-share/sex mix), z-scored
    within the same `old_scale`/`new_scale` sub-eras as `meritvärde_z`.
    That split matters here even though R's *mean* doesn't jump at the
    reform (the model-predicted B moves in lockstep with actual F, so the
    ~10-point level shift cancels in F - B) -- R's *std* still drifts from
    ~11-13 pre-reform to ~15-17 post-reform (checked empirically), which
    would miscalibrate a single pooled z-score. Unweighted only: SALSA
    doesn't carry its own `antal_elever` column (unlike `slutbetyg`), and
    joining it in from `slutbetyg` just to weight this one robustness
    outcome wasn't judged worth the extra join for now.

    A genuine caveat, not just a data-availability footnote: this residual
    is *already* adjusted for the school's socioeconomic composition. If
    barrier construction itself shifts who enrols (families sorting toward
    or away from a now-quieter area), SALSA's own adjustment could partial
    out exactly that channel -- useful as a robustness/mechanism check,
    risky as a primary outcome."""
    base = salsa[["skolenhetskod", "year"]].copy()
    base["value"] = salsa.get(SALSA_RESIDUAL_COLUMN, pd.Series(index=salsa.index, dtype=float))
    base = base.dropna(subset=["value"])
    base["sub_era"] = base["year"].where(base["year"] <= MERITVARDE_OLD_SCALE_LAST_YEAR, "new_scale")
    base["sub_era"] = base["sub_era"].where(base["sub_era"] == "new_scale", "old_scale")

    out = base[["skolenhetskod", "year"]].copy()
    out["value"] = _zscore_by_group(base, "sub_era", "value", None)
    out = out.dropna(subset=["value"])
    out["era"] = "siris"
    out["source_dataset"] = "salsa_stitched"
    out["outcome_name"] = "meritvärde_residual_z"
    return out[["skolenhetskod", "year", "era", "source_dataset", "outcome_name", "value"]]


def build_outcomes_long(siris_datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Stack every real observed SIRIS outcome value into one long table --
    see the module docstring for why this is long, not one wide `outcome`
    column: SIRIS's own measures (raw `meritvärde`, SALSA, pass rates, ...)
    don't share a common definition either. `kvalitetssystem` is
    deliberately not included here -- see the module docstring. Includes
    both the raw per-measure melt (every column, every year, including the
    two raw `meritvärde` columns pre/post reform) and four derived stitched
    series -- `stitch_meritvarde`'s `meritvärde_z`/`meritvärde_zw` (needs
    `slutbetyg_arskurs9`), `stitch_pass_rate`/`stitch_eligibility`'s
    `andel_uppnått_kunskapskraven_combined`/`andel_behörig_combined` (same),
    and `stitch_salsa_residual`'s `meritvärde_residual_z` (needs `salsa`) --
    so a raw-value analysis and any of the stitched-series analyses can all
    filter this same table."""
    frames = [melt_siris_to_long(df, key) for key, df in siris_datasets.items()]
    if "slutbetyg_arskurs9" in siris_datasets:
        slutbetyg = siris_datasets["slutbetyg_arskurs9"]
        frames.append(stitch_meritvarde(slutbetyg))
        frames.append(stitch_pass_rate(slutbetyg))
        frames.append(stitch_eligibility(slutbetyg))
    if "salsa" in siris_datasets:
        frames.append(stitch_salsa_residual(siris_datasets["salsa"]))
    return pd.concat(frames, ignore_index=True)


TIER_STAT_RENAME = {
    "point": {"first_treat_year": "first_treat_year_point", "ever_treated": "ever_treated_point",
              "timing_unknown": "timing_unknown_point"},
}


def _rollup_treatment_columns(rollup: pd.DataFrame, kind: str) -> pd.DataFrame:
    """One barrier kind's `schools_{kind}_rollup_network.parquet` -> just
    the columns this panel needs, `{kind}_`-prefixed and with the point
    tier's originally-unsuffixed columns (`first_treat_year`/`ever_treated`/
    `timing_unknown`) renamed to `_point` for a uniform
    `{stat}_{definition}` shape across all four tiers, matching
    `same_route`/`same_side`/`protected`'s own naming. `same_side_unknown` (a school
    with a `same_route` barrier whose side couldn't be determined, see
    `docs/data/sweden/barrier_matching.md`) is carried through so an
    analysis can drop those schools from the `same_side` contrast;
    `protected_unknown` likewise for the `protected` tier."""
    renamed = rollup.rename(columns=TIER_STAT_RENAME["point"])
    columns = ["skolenhetskod", "nearest_dist_m", "n_barriers_1000m", "ever_near_1000m", *SIDE_UNKNOWN_FLAGS] + [
        f"{stat}_{definition}"
        for definition in TREATMENT_DEFINITIONS
        for stat in ("first_treat_year", "ever_treated", "timing_unknown")
    ]
    selected = renamed[columns].rename(columns={c: f"{kind}_{c}" for c in columns if c != "skolenhetskod"})
    return selected


def build_treatment_rollup(rollups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """`{road,rail}_rollup_network.parquet` -> one row per school, all eight
    `{kind}_{stat}_{definition}` treatment columns side by side (outer join
    -- both kinds are built from the same full geocoded-school set in
    `schools/assemble.py`, so this is a no-op in practice, but outer is the
    correct join type regardless of that coincidence)."""
    combined: pd.DataFrame | None = None
    for kind, rollup in rollups.items():
        cols = _rollup_treatment_columns(rollup, kind)
        combined = cols if combined is None else combined.merge(cols, on="skolenhetskod", how="outer")
    return combined


def attach_treatment(outcomes_long: pd.DataFrame, treatment_rollup: pd.DataFrame) -> pd.DataFrame:
    """Left-join the eight treatment-timing definitions onto every outcome
    row by `skolenhetskod` (broadcast across every year/measure that school
    has an observed outcome for) and compute `event_time_{kind}_{definition}
    = year - first_treat_year_{kind}_{definition}` per definition. A school
    absent from `treatment_rollup` (e.g. never geocoded) gets
    `ever_treated_*=False`/`timing_unknown_*=False` -- a real "no barrier
    match" value, matching Florida's own `ever_treated_*` convention, not a
    missing one."""
    out = outcomes_long.merge(treatment_rollup, on="skolenhetskod", how="left")
    for kind in BARRIER_KINDS:
        for definition in TREATMENT_DEFINITIONS:
            ever_col = f"{kind}_ever_treated_{definition}"
            unknown_col = f"{kind}_timing_unknown_{definition}"
            first_year_col = f"{kind}_first_treat_year_{definition}"
            # A left-merge miss leaves these object-dtype (bool mixed with
            # NaN, not a clean bool column) -- casting to pandas' nullable
            # `"boolean"` dtype first avoids `fillna`'s legacy
            # object-downcasting warning that a plain `.fillna(False)` on an
            # object column would otherwise trigger.
            out[ever_col] = out[ever_col].astype("boolean").fillna(False).astype(bool)
            out[unknown_col] = out[unknown_col].astype("boolean").fillna(False).astype(bool)
            out[f"event_time_{kind}_{definition}"] = out["year"] - out[first_year_col]
        for flag in SIDE_UNKNOWN_FLAGS:
            out[f"{kind}_{flag}"] = out[f"{kind}_{flag}"].astype("boolean").fillna(False).astype(bool)
    return out


def attach_traffic(panel: pd.DataFrame, school_traffic: pd.DataFrame) -> pd.DataFrame:
    """Interval-overlap join, not a flat broadcast: for each outcome row's
    own `year`, find the matched school's traffic window whose real
    `[valid_from, valid_to)` actually covers Jan 1 of that year, and use
    THAT window's ÅDT figures -- a school with several recovered
    historical windows (see `traffic/assemble.py`'s module docstring) gets
    genuinely different traffic values for different years, not one
    number copy-pasted everywhere. Implemented as a `merge_asof`
    (`direction="backward"` on `valid_from`, by school) followed by a
    check that the matched window's `valid_to` actually extends past the
    target year -- a year outside every recovered window (e.g. before the
    earliest `Betraktelsedatum` order's coverage for that segment) gets
    real `NA` traffic columns rather than a wrong stale value from an
    unrelated window. `valid_from`/`valid_to` are the raw `YYYYMMDD`
    integers `traffic/preprocess.py` keeps them as (`99991231` is the
    "still open, no end yet" sentinel) -- comparing ints directly avoids
    the `datetime64[ns]` year-9999 overflow that sentinel would cause."""
    traffic = school_traffic.dropna(subset=["element_id"])[["skolenhetskod", "valid_from", "valid_to", *TRAFFIC_COLUMNS]]
    traffic = traffic.sort_values("valid_from").reset_index(drop=True)
    traffic["_key"] = traffic["skolenhetskod"].astype(str)
    # A parquet round-trip through a frame that also had NA `valid_from`
    # rows (unmatched schools) leaves this column float64 even after
    # `dropna` -- `merge_asof` requires the two `on` columns to share an
    # exact dtype, so cast back to the real int64 these are.
    traffic["valid_from"] = traffic["valid_from"].astype("int64")
    traffic["valid_to"] = traffic["valid_to"].astype("int64")

    out = panel.reset_index(drop=True)
    out["_row_order"] = out.index
    out["_key"] = out["skolenhetskod"].astype(str)
    out["_year_as_of"] = out["year"] * 10000 + 101  # Jan 1 of that year, as a YYYYMMDD int
    left_sorted = out.sort_values("_year_as_of").reset_index(drop=True)

    joined = pd.merge_asof(
        left_sorted,
        traffic.drop(columns="skolenhetskod"),
        left_on="_year_as_of",
        right_on="valid_from",
        by="_key",
        direction="backward",
    )
    covers = joined["_year_as_of"] < joined["valid_to"]
    for col in TRAFFIC_COLUMNS:
        joined[f"traffic_{col}"] = joined[col].where(covers)
    joined = joined.drop(columns=[*TRAFFIC_COLUMNS, "valid_from", "valid_to", "_key", "_year_as_of"])
    return joined.sort_values("_row_order").drop(columns="_row_order").reset_index(drop=True)


def attach_neighbourhood(panel: pd.DataFrame, school_neighbourhood: pd.DataFrame) -> pd.DataFrame:
    """Plain `(skolenhetskod, year)` merge -- unlike `attach_traffic`, no
    interval-overlap logic is needed here: `neighbourhood assemble`'s own
    output is already keyed one row per real `(school, year)` covered by
    at least one of its three DeSO-grain tables (or one all-`NA` row for
    a school that never matched a DeSO at all, see
    `docs/data/sweden/neighbourhood/README.md`), not a set of historical
    windows to pick from. A school-year absent from `school_neighbourhood`
    (e.g. a year outside every one of the three tables' own real
    coverage, all capped at 2023 -- see that README) gets real `NA` here
    too, matching every other covariate join in this pipeline."""
    neighbourhood = school_neighbourhood.dropna(subset=["desokod"])[["skolenhetskod", "year", *NEIGHBOURHOOD_COLUMNS]]
    neighbourhood = neighbourhood.astype({"year": "int64"})
    renamed = neighbourhood.rename(columns={col: f"neighbourhood_{col}" for col in NEIGHBOURHOOD_COLUMNS})
    return panel.merge(renamed, on=["skolenhetskod", "year"], how="left")


def remap_treatment_rollup_to_lineage(treatment_rollup: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Remap `old_code -> new_code` (module docstring's lineage crosswalk),
    then collapse any resulting duplicate `skolenhetskod` rows by
    aggregating rather than dropping one side: `ever_treated_*` and
    `ever_near_1000m` OR together (true if either constituent row saw a
    barrier), `first_treat_year_*` takes the earliest known year (`NaN`
    ignored, matching pandas' default `min` behaviour), `nearest_dist_m`
    takes the minimum, `n_barriers_1000m` the maximum. All of this is a
    no-op when the two rows already agree, which a co-located lineage
    pair's *identical* coordinates guarantee for genuinely geometric
    columns -- checked live against every collision this produces
    (`src/experiments/sweden/schools.ipynb` §9): none disagreed."""
    remap = dict(zip(crosswalk["old_code"], crosswalk["new_code"]))
    out = treatment_rollup.copy()
    out["skolenhetskod"] = out["skolenhetskod"].replace(remap)

    agg: dict[str, str] = {}
    for kind in BARRIER_KINDS:
        agg[f"{kind}_nearest_dist_m"] = "min"
        agg[f"{kind}_n_barriers_1000m"] = "max"
        agg[f"{kind}_ever_near_1000m"] = "max"
        for flag in SIDE_UNKNOWN_FLAGS:
            agg[f"{kind}_{flag}"] = "max"
        for definition in TREATMENT_DEFINITIONS:
            agg[f"{kind}_ever_treated_{definition}"] = "max"
            agg[f"{kind}_timing_unknown_{definition}"] = "max"
            agg[f"{kind}_first_treat_year_{definition}"] = "min"
    agg = {col: how for col, how in agg.items() if col in out.columns}
    return out.groupby("skolenhetskod", as_index=False).agg(agg)


def remap_outcomes_to_lineage(outcomes_long: pd.DataFrame, crosswalk: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Remap `old_code -> new_code`, but only where it's safe: unlike the
    treatment rollup (above), two lineage-linked schools' outcome rows are
    NOT guaranteed to agree, or even to avoid the same `(year, outcome)`
    key -- a retiring and successor unit can have genuinely co-existed for
    a transition period with their own separately reported scores (module
    docstring). So a row is only remapped when the target
    `(new_code, year, era, source_dataset, outcome_name)` key is not
    already occupied by a row that keeps its own code -- i.e. this fills
    the successor's real pre-reorg history gaps and leaves any genuinely
    overlapping year under its original code rather than guessing which
    side is right. Returns `(remapped, stats)`; `stats` records how many
    rows moved vs. were left in place by the collision guard, for
    `run_panel_assemble`'s report."""
    remap = dict(zip(crosswalk["old_code"], crosswalk["new_code"]))
    key_cols = ["year", "era", "source_dataset", "outcome_name"]

    out = outcomes_long.copy()
    candidate_code = out["skolenhetskod"].map(remap)
    to_remap = candidate_code.notna()

    existing_keys = pd.MultiIndex.from_frame(out.loc[~to_remap, ["skolenhetskod", *key_cols]])
    candidate_keys = pd.MultiIndex.from_frame(
        pd.concat([candidate_code[to_remap].rename("skolenhetskod"), out.loc[to_remap, key_cols]], axis=1)
    )
    collides = candidate_keys.isin(existing_keys)

    apply_idx = out.index[to_remap][~collides]
    out.loc[apply_idx, "skolenhetskod"] = candidate_code.loc[apply_idx]

    stats = {
        "n_links": int(len(crosswalk)),
        "n_rows_remapped": int(len(apply_idx)),
        "n_rows_blocked_by_collision": int(collides.sum()),
    }
    return out, stats


def build_event_study_panel(
    siris_datasets: dict[str, pd.DataFrame],
    rollups: dict[str, pd.DataFrame],
    school_traffic: pd.DataFrame,
    school_neighbourhood: pd.DataFrame,
    lineage_crosswalk: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    outcomes_long = build_outcomes_long(siris_datasets)
    treatment_rollup = build_treatment_rollup(rollups)

    lineage_report: dict[str, object] = {"n_links": 0, "n_rows_remapped": 0, "n_rows_blocked_by_collision": 0}
    if lineage_crosswalk is not None and len(lineage_crosswalk):
        outcomes_long, lineage_report = remap_outcomes_to_lineage(outcomes_long, lineage_crosswalk)
        treatment_rollup = remap_treatment_rollup_to_lineage(treatment_rollup, lineage_crosswalk)

    panel = attach_treatment(outcomes_long, treatment_rollup)
    panel = attach_traffic(panel, school_traffic)
    panel = attach_neighbourhood(panel, school_neighbourhood)
    return panel, lineage_report


def save_panel(panel: pd.DataFrame, metadata: dict[str, object], root: Path | None = None) -> dict[str, str]:
    panel_path = assembled_panel_path(root)
    meta_path = assembled_metadata_path(root)
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(panel_path, index=False)
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"panel": str(panel_path), "metadata": str(meta_path)}


def _vanished_recovery_counts(root: Path | None = None) -> dict[str, int]:
    """`0` for a `kind` whose recovery rollup hasn't been built yet -- see
    `load_treatment_rollup_with_recovery`."""
    from src.regions.sweden.sources.panel.vanished_recovery import load_vanished_recovery_rollup

    return {
        kind: int(len(rollup)) if (rollup := load_vanished_recovery_rollup(kind, root)) is not None else 0
        for kind in BARRIER_KINDS
    }


def run_panel_assemble(root: Path | None = None) -> dict[str, object]:
    """Load `assessments` (SIRIS only -- `kvalitetssystem` is deliberately
    excluded, see the module docstring) + `schools assemble`'s road/rail
    rollups + `traffic`'s and `neighbourhood`'s own assembled outputs +
    `schools build-lineage`'s `skolenhetskod` crosswalk, join, and persist.
    See the module docstring for the grain, the `meritvärde_z` cross-era
    stitching decision, how the traffic vs. neighbourhood joins differ
    (interval-overlap vs. plain year merge), and the lineage remap's two
    different merge policies. Also picks up `vanished_recovery.py`'s
    Skolkoll-recovered rollups if `sweden data panel
    recover-vanished-schools` has been run -- optional, see
    `load_treatment_rollup_with_recovery`."""
    siris_datasets = {key: load_siris(key, root) for key in SIRIS_DATASET_KEYS}
    rollups = {kind: load_treatment_rollup_with_recovery(kind, root) for kind in BARRIER_KINDS}
    school_traffic = load_school_traffic(root)
    school_neighbourhood = load_school_neighbourhood(root)
    lineage_crosswalk = load_lineage_crosswalk(root)

    panel, lineage_report = build_event_study_panel(
        siris_datasets, rollups, school_traffic, school_neighbourhood, lineage_crosswalk
    )

    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/sweden/sources/panel/assemble.py",
        "grain": "skolenhetskod x year x era x outcome_name (long; era is 'siris' only -- kvalitetssystem excluded, see module docstring)",
        "rows": int(len(panel)),
        "distinct_schools": int(panel["skolenhetskod"].nunique()),
        "year_range": [int(panel["year"].min()), int(panel["year"].max())],
        "rows_by_era": panel["era"].value_counts().to_dict(),
        "distinct_schools_by_era": panel.groupby("era")["skolenhetskod"].nunique().to_dict(),
        "treatment_definitions": {
            f"{kind}_{definition}": {
                "ever_treated_schools": int(
                    panel.loc[panel[f"{kind}_ever_treated_{definition}"], "skolenhetskod"].nunique()
                ),
                "ever_treated_outcome_rows": int(panel[f"{kind}_ever_treated_{definition}"].sum()),
            }
            for kind in BARRIER_KINDS
            for definition in TREATMENT_DEFINITIONS
        },
        **{
            f"{flag}_schools": {
                kind: int(panel.loc[panel[f"{kind}_{flag}"], "skolenhetskod"].nunique()) for kind in BARRIER_KINDS
            }
            for flag in SIDE_UNKNOWN_FLAGS
        },
        "vanished_schools_recovered": _vanished_recovery_counts(root),
        "rows_with_traffic_match": int(panel["traffic_adt_samtliga_fordon"].notna().sum()),
        "schools_with_traffic_match": int(
            panel.loc[panel["traffic_adt_samtliga_fordon"].notna(), "skolenhetskod"].nunique()
        ),
        "rows_with_neighbourhood_match": int(panel["neighbourhood_desokod"].notna().sum()),
        "schools_with_neighbourhood_match": int(
            panel.loc[panel["neighbourhood_desokod"].notna(), "skolenhetskod"].nunique()
        ),
        "lineage_crosswalk": lineage_report,
    }
    saved = save_panel(panel, report, root)
    report["saved"] = saved
    return report
