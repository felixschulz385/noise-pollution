"""The specification of the ``sweden-schools`` line: sample, treatment, covariates, baselines,
within-barrier sites and clusters.

Used by ``notebooks/sweden-schools/20_analysis.ipynb``, which estimates in Stata. The record of
the line is ``docs/lines/sweden-schools/results.md``. Moved here from the notebook's §1, §8, §9
and §12 cells on 2026-11-18, unchanged: each builder prints what its cell printed in the
2026-10-22 run.

- **Outcome:** ``meritvärde_z``, grade 9, 1998-2019, z-scored on each side of the 2014/15
  grading reform.
- **Treatment:** a road **or** rail barrier at the ``protected`` tier (the barrier's side,
  within 600 m, beside its stretch; sides from the manual audit). Event time runs from the
  first barrier of either kind.
- **Dropped, not coded as controls:** treated schools whose every barrier lacks a construction
  year, and untreated schools beside a barrier whose side is unknown.
- **Clusters:** school; kommun for §12 (each school's most frequent SIRIS kommun code).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

OUTCOME_NAME = "meritvärde_z"
# road/rail-combined tier: on the barrier's side, within 600m, beside its stretch. Back from the
# 2026-09-28 "same_side" interim on 2026-10-20, once the barrier audit had placed the barriers
# near panel schools (docs/data/sweden/barrier_audit/README.md)
MATCH_TIER = "protected"

OUTCOME_STATA = "meritvarde_z"
COVARIATES = {
    # the busiest counted road within 500m of the school (switched 2026-09-24 from the single
    # nearest segment, which is the protecting barrier's own road for only ~42% of protected
    # schools)
    "traffic_max_adt_500m": "traffic_max_adt",
    "neighbourhood_mean_net_income_tkr": "nbhd_income",
    "neighbourhood_share_eftergymnasial": "nbhd_edu_share",
}
"""Panel column -> Stata name. ``employment_rate`` is left out: its coverage starts in 2020."""

CONTROL_LADDER = {
    "+ Traffic": ("traffic_max_adt",),
    "+ Traffic, income": ("traffic_max_adt", "nbhd_income"),
    "+ Traffic, income, education": ("traffic_max_adt", "nbhd_income", "nbhd_edu_share"),
    "Income only": ("nbhd_income",),
}
"""§5 and §7's increasing controls (Stata names). The notebook's Stata cells spell them out."""

BASELINE_OUTCOMES = {
    "parent_edu": "bakgrundsinformation_föräldrarnas_genomsnittliga_utb_nivå",
    "born_abroad": "bakgrundsinformation_andel_födda_utomlands",
    "foreign_parents": "bakgrundsinformation_andel_med_utländsk_bakgrund",
}
"""SALSA background columns (long-panel ``outcome_name``) behind §9's baselines."""

CLUSTER = "kommun"
"""The second clustering unit (§12), after the school."""


def load_panel() -> pd.DataFrame:
    """The assembled long panel (``noise_pollution sweden data panel assemble``)."""
    from noise_pollution.regions.sweden.sources.panel.shared import assembled_panel_path

    panel = pd.read_parquet(assembled_panel_path())
    print(f"{len(panel):,} panel rows loaded, {panel['skolenhetskod'].nunique():,} distinct schools")
    return panel


def build_analysis(panel: pd.DataFrame) -> pd.DataFrame:
    """§1: the CS-ready school-year dataset: ``id``, ``year``, ``gvar`` (first construction year,
    0 if never treated), ``meritvarde_z`` and the covariates under their Stata names."""
    outcome = panel.loc[panel["outcome_name"] == OUTCOME_NAME].copy()
    print(f"{len(outcome):,} rows for outcome_name == {OUTCOME_NAME!r}, "
          f"{outcome['skolenhetskod'].nunique():,} schools, "
          f"years {outcome['year'].min()}-{outcome['year'].max()}")

    road_ever = outcome[f"road_ever_treated_{MATCH_TIER}"]
    road_unknown = outcome[f"road_timing_unknown_{MATCH_TIER}"]
    rail_ever = outcome[f"rail_ever_treated_{MATCH_TIER}"]
    rail_unknown = outcome[f"rail_timing_unknown_{MATCH_TIER}"]

    combined_ever = road_ever | rail_ever
    combined_usable = (road_ever & ~road_unknown) | (rail_ever & ~rail_unknown)

    both_kinds = (road_ever & ~road_unknown) & (rail_ever & ~rail_unknown)
    print(f"\n{combined_ever.sum():,} rows ever-treated by road or rail ({MATCH_TIER}); "
          f"{both_kinds.sum():,} of those rows are near BOTH a road and a rail barrier with known timing "
          "-- combined event time uses whichever came first for these.")

    # A school ever-treated only by kind(s) whose construction year is itself unknown can't be
    # placed in event time at all -- drop it rather than silently mis-code it as a control.
    drop_mask = combined_ever & ~combined_usable
    print(f"dropping {drop_mask.sum():,} rows ({outcome.loc[drop_mask, 'skolenhetskod'].nunique():,} schools): "
          "ever-treated but every matching barrier's construction year is unknown")
    # Likewise a never-treated school beside a barrier whose side is unknown: it may be
    # protected, so it is not a clean control either -- drop it too.
    side_unknown = outcome[f"road_{MATCH_TIER}_unknown"] | outcome[f"rail_{MATCH_TIER}_unknown"]
    unknown_mask = side_unknown & ~combined_ever
    print(f"dropping {unknown_mask.sum():,} rows ({outcome.loc[unknown_mask, 'skolenhetskod'].nunique():,} schools): "
          "not treated, but beside a barrier whose side is unknown")
    outcome = outcome.loc[~(drop_mask | unknown_mask)].copy()

    # per-kind usability recomputed on the filtered frame
    road_year = outcome[f"road_first_treat_year_{MATCH_TIER}"].where(
        outcome[f"road_ever_treated_{MATCH_TIER}"] & ~outcome[f"road_timing_unknown_{MATCH_TIER}"]
    )
    rail_year = outcome[f"rail_first_treat_year_{MATCH_TIER}"].where(
        outcome[f"rail_ever_treated_{MATCH_TIER}"] & ~outcome[f"rail_timing_unknown_{MATCH_TIER}"]
    )
    # combined first-treatment year: the earlier of the two kinds' usable years (0 = never
    # treated, csdid's own sentinel)
    combined_year = pd.concat([road_year, rail_year], axis=1).min(axis=1, skipna=True)

    outcome["id"] = outcome["skolenhetskod"].astype("int64")
    outcome["gvar"] = combined_year.fillna(0.0)

    analysis = outcome[["id", "year", "gvar", "value", *COVARIATES]].rename(
        columns={"value": OUTCOME_STATA, **COVARIATES}
    )

    n_treated_schools = analysis.loc[analysis["gvar"] > 0, "id"].nunique()
    print(f"\nfinal analysis dataset: {len(analysis):,} rows, {analysis['id'].nunique():,} schools, "
          f"{n_treated_schools:,} with a usable combined treatment year")
    print("\ncovariate coverage (share non-missing):")
    print(analysis[list(COVARIATES.values())].notna().mean())
    return analysis


def pull_outcome(panel: pd.DataFrame, name: str, colname: str) -> pd.DataFrame:
    """One ``outcome_name`` of the long panel as an (``id``, ``year``, ``colname``) frame."""
    out = panel.loc[panel["outcome_name"] == name, ["skolenhetskod", "year", "value"]].rename(
        columns={"skolenhetskod": "id", "value": colname}
    )
    out["id"] = out["id"].astype("int64")
    return out


def within_sites(analysis: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """§8: each school's place relative to the barriers. Returns ``sites`` (one row per near or
    dated far school: ``near``, ``site_g``, ``in_window``) and ``analysis_within`` (``analysis``
    restricted to those schools, with ``site_g`` and ``near``).

    - near: in a barrier's protected area; these are exactly the treated schools of ``analysis``.
    - far: in a barrier's control band (same side and stretch, 600-1,500 m) and in no
      protected area, dated by its band barrier's construction year (the earliest); undated far
      schools are dropped.
    """
    import geopandas as gpd

    from noise_pollution.regions.sweden.sources.barrier_protection.shared import (
        load_control_band_zones,
        load_protection_zones,
    )
    from noise_pollution.regions.sweden.sources.schools.assemble import load_geocoded_schools

    zones = load_protection_zones()
    points = load_geocoded_schools().to_crs(zones.crs)[["skolenhetskod", "geometry"]]
    points["id"] = points["skolenhetskod"].astype("int64")
    points = points.loc[points["id"].isin(analysis["id"])]
    in_zone = gpd.sjoin(points, zones, predicate="within")
    in_band = gpd.sjoin(points, load_control_band_zones(), predicate="within")

    near = set(in_zone.loc[in_zone["zone_status"] == "protected", "id"])
    any_zone = set(in_zone["id"])  # also side-unknown protected areas: such a school may be behind the barrier
    band = in_band.loc[(in_band["zone_status"] == "control_band") & ~in_band["id"].isin(any_zone)]
    band_year = band.groupby("id")["built_year"].min().astype("float64")

    sites = analysis.groupby("id").agg(gvar=("gvar", "first"), first_year=("year", "min"), last_year=("year", "max"))
    print(f"{len(sites):,} schools in §1's sample, {sites.index.isin(points['id']).sum():,} geocoded")
    # near = §1's treated schools (same layers as schools assemble)
    assert (sites.index.isin(near) == (sites["gvar"] > 0)).all()
    sites["near"] = sites.index.isin(near).astype("int8")
    sites["site_g"] = np.where(sites["near"] == 1, sites["gvar"], sites.index.map(band_year))
    far_all = sites.index.isin(band["id"]) & (sites["near"] == 0)
    print(f"far schools: {far_all.sum()}, of them undated (dropped): {(far_all & sites['site_g'].isna()).sum()}")
    sites = sites.loc[(sites["near"] == 1) | (far_all & sites["site_g"].notna())]
    # observed both before and after its (band) barrier was built
    sites["in_window"] = (sites["first_year"] < sites["site_g"]) & (sites["last_year"] >= sites["site_g"])
    print(pd.crosstab(sites["near"].map({1: "near", 0: "far"}),
                      sites["in_window"].map({True: "observed before and after", False: "other"})).to_string())
    both = sites.loc[sites["in_window"]].groupby("site_g")["near"].agg(["sum", "count"])
    both = both[(both["sum"] > 0) & (both["sum"] < both["count"])]
    print(f"\nsite cohorts with near and far schools observed before and after: {len(both)}, "
          f"{int(both['sum'].sum())} near and {int((both['count'] - both['sum']).sum())} far schools")
    analysis_within = analysis.merge(sites[["site_g", "near"]], left_on="id", right_index=True, how="inner")
    print(f"{analysis_within['id'].nunique():,} schools, {len(analysis_within):,} school-years")
    return sites, analysis_within


@dataclass
class Baselines:
    """§9's baselines. ``heterogeneity`` is ``analysis`` with the standardised baselines and the
    median-split flags (``edu_high``, ``foreign_high``); the rest are the intermediate frames."""

    background: pd.DataFrame
    base: pd.DataFrame
    per_school: pd.DataFrame
    identifying: pd.DataFrame
    medians: pd.Series
    heterogeneity: pd.DataFrame


def baselines(panel: pd.DataFrame, analysis: pd.DataFrame) -> Baselines:
    """§9: SALSA background in each school's first observed year, standardised across schools
    (parental education; foreign background = born abroad + foreign-born parents), and the
    median split among the identifying treated schools for the CS check."""
    background = analysis[["id", "year", "gvar"]]
    for col, name in BASELINE_OUTCOMES.items():
        background = background.merge(pull_outcome(panel, name, col), on=["id", "year"], how="left")
    background["foreign"] = background["born_abroad"] + background["foreign_parents"]
    print("share of school-years where the foreign-background share is below the born-abroad share: "
          f"{(background['foreign_parents'] < background['born_abroad']).mean():.1%}")

    base = {}
    for col in ("parent_edu", "foreign"):
        first = background.dropna(subset=[col]).sort_values("year").drop_duplicates("id").set_index("id")
        base[f"{col}_base"] = first[col]
        base[f"{col}_base_year"] = first["year"]
    base = pd.DataFrame(base)
    for col in ("parent_edu", "foreign"):
        base[f"{col}_base_z"] = (base[f"{col}_base"] - base[f"{col}_base"].mean()) / base[f"{col}_base"].std()

    per_school = analysis.groupby("id").agg(
        gvar=("gvar", "first"), first_year=("year", "min"), last_year=("year", "max")
    ).join(base)
    # observed both before and after construction (§6's list)
    identifying = per_school[(per_school["gvar"] > 0) & (per_school["first_year"] < per_school["gvar"])
                             & (per_school["last_year"] >= per_school["gvar"])]
    print(f"\n{len(identifying)} treated schools observed before and after their wall:")
    for col in ("parent_edu", "foreign"):
        has = identifying[f"{col}_base"].notna()
        before = (identifying[f"{col}_base_year"] < identifying["gvar"]).sum()
        print(f"  {col}: baseline for {has.sum()}, measured before construction for {before}; "
              f"mean {identifying[f'{col}_base_z'].mean():+.2f} SD (all schools 0)")
    print(f"\ncorrelation of the two baselines across schools: {base['parent_edu_base'].corr(base['foreign_base']):.2f}")

    # median split among the treated schools, for the CS check
    medians = identifying[["parent_edu_base_z", "foreign_base_z"]].median()
    heterogeneity = analysis.merge(base[["parent_edu_base_z", "foreign_base_z"]], left_on="id", right_index=True, how="left")
    for col, name in (("parent_edu_base_z", "edu_high"), ("foreign_base_z", "foreign_high")):
        heterogeneity[name] = np.where(heterogeneity[col].isna(), np.nan, (heterogeneity[col] > medians[col]).astype(float))
    print(identifying.assign(edu_high=identifying["parent_edu_base_z"] > medians["parent_edu_base_z"],
                             foreign_high=identifying["foreign_base_z"] > medians["foreign_base_z"])
          [["gvar", "parent_edu_base", "foreign_base", "edu_high", "foreign_high"]].round(2).to_string())
    return Baselines(background, base, per_school, identifying, medians, heterogeneity)


def kommun_by_school() -> pd.Series:
    """§12's cluster: each school's most frequent kommun code in SIRIS, indexed by ``id``."""
    from noise_pollution.regions.sweden.sources.assessments.shared import assessments_paths

    siris = pd.read_parquet(assessments_paths()["processed"] / "siris_slutbetyg_arskurs9.parquet",
                            columns=["skolenhetskod", "kommunkod"]).dropna()
    kommun_of = siris.groupby("skolenhetskod")["kommunkod"].agg(lambda s: s.mode().iat[0]).pipe(pd.to_numeric)
    kommun_of.index = kommun_of.index.astype("int64")
    return kommun_of


__all__ = [
    "BASELINE_OUTCOMES", "CLUSTER", "CONTROL_LADDER", "COVARIATES", "MATCH_TIER", "OUTCOME_NAME",
    "OUTCOME_STATA", "Baselines", "baselines", "build_analysis", "kommun_by_school", "load_panel",
    "pull_outcome", "within_sites",
]
