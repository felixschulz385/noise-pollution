"""The specification of the ``florida-schools`` line: sample, treatment, collapse, baselines,
grade x subject x year cells, within-wall sites and clusters.

Used by ``notebooks/florida-schools/11_analysis.ipynb``, which estimates in Stata. The record of
the line is ``docs/lines/florida-schools/results.md``. Moved here from the notebook's §1, §2, §9
and §16 cells on 2026-11-18, unchanged: each builder prints what its cell printed in the
2026-10-22/23 run.

- **Outcome:** ``z_mss_w`` (mean scale score standardised within grade/subject/year/regime),
  collapsed to one ``n_students``-weighted value per school-year, regular schools only. TWFE
  models also use the uncollapsed grade x subject x year cells (``build_cells``).
- **Treatment:** the school lies in an FDOT wall's protected area (``protected`` tier: the
  wall's side, beside its stretch, within 600 m).
- **Dropped, not coded as controls:** treated schools whose wall has no construction year, and
  untreated schools beside a wall whose side is unknown.
- **Baselines** (held fixed per school): census-tract SES from each school's earliest ACS
  vintage; free/reduced-lunch and Black share in the first observed year, standardised.
- **Clusters:** school; the school district for §16.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# switched 2026-09-24: the school lies in a wall's protected area -- same side AND beside the
# wall's own stretch (docs/data/florida/barrier_protection.md)
MATCH_TIER = "protected"

COVARIATES = {
    # the busiest RCI road within 500m of the school (switched 2026-09-24 from the single
    # nearest arterial, which is the protecting wall's own road for only ~52% of protected
    # schools)
    "traffic_max_aadt_500m": "traffic_max_aadt_500m",
    "n_road_projects_active": "n_road_projects",
    "shock_any_major_disaster": "shock_major",
}
"""Time-varying covariates: panel column -> Stata name."""

SES_COLS = {
    "nbhd_median_household_income": "ses_log_income",
    "nbhd_poverty_rate": "ses_poverty",
    "nbhd_pct_bachelors_plus": "ses_bachelors",
    "nbhd_pct_owner_occupied": "ses_owner",
}
"""Census-tract SES (ACS 5-year), each school's earliest vintage: panel column -> Stata name."""

CONTROL_SETS = {
    "TRAFFIC": ("traffic_max_aadt_500m",),
    "ROADSHOCK": ("n_road_projects", "shock_major"),
    "SES": tuple(SES_COLS.values()),
}
"""The covariate sets every CS and TWFE model uses, as Stata globals ($TRAFFIC, $ROADSHOCK, $SES)."""

NEAR_M = 300
"""§10: a treated school is near if its wall is within this distance of the road."""
LAT_BIN_M = 150
"""§10: width of the distance bins (1-4, up to 600 m)."""

WALL_CATEGORIES = ["fdot_barrier", "proposed_barrier"]
"""§9: built walls and walls a noise study recommended but that were never built."""

CLUSTER = "district"
"""The second clustering unit (§16), after the school."""


def load_panel() -> pd.DataFrame:
    """The assembled panel (``noise_pollution florida data panel assemble``)."""
    from noise_pollution.regions.florida.sources.panel.shared import assembled_panel_path

    panel = pd.read_parquet(assembled_panel_path())
    print(f"{len(panel):,} panel rows loaded, {panel['msid'].nunique():,} distinct schools, "
          f"grain msid x grade x subject x year")
    return panel


def wavg_z(g: pd.DataFrame) -> float:
    """``z_mss_w`` averaged over a group's rows, weighted by test-takers (``n_students``)."""
    return float(np.average(g["z_mss_w"], weights=g["n_students"]))


def build_school_year(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """§1, first step. Returns ``rows`` (regular schools with a real weighted score), its first
    row per school-year (``school_year``, for the school-level columns), and ``merged``: one
    collapsed ``z_mss_w_school`` per school-year with treatment and covariates, after the drops."""
    # Restrict to regular schools with a real weighted score, per docs/data/florida/covariates.md's
    # "weight by test-takers; restrict to regular schools with stable grade spans" guidance.
    rows = panel.loc[(panel["is_regular"] == True) & panel["z_mss_w"].notna() & panel["n_students"].notna()].copy()  # noqa: E712
    print(f"{len(rows):,} of {len(panel):,} panel rows kept (is_regular & real z_mss_w & n_students)")

    # Collapse grade/subject cells to one z_mss_w per (msid, year), weighted by test-takers; the
    # panel's other columns (treatment, covariates) are already constant within (msid, year).
    outcome_vals = (
        rows.groupby(["msid", "year"])
        .apply(wavg_z, include_groups=False)
        .rename("z_mss_w_school")
        .reset_index()
    )

    ever_col, first_col, unknown_col = (
        f"ever_treated_{MATCH_TIER}", f"first_treat_year_{MATCH_TIER}", f"timing_unknown_{MATCH_TIER}",
    )
    side_unknown_col = f"{MATCH_TIER}_unknown"
    school_year = rows.drop_duplicates(["msid", "year"])
    other_cols = school_year[
        ["msid", "year", ever_col, first_col, unknown_col, side_unknown_col, "proposed_protected", "protected_lateral_m",
         *COVARIATES]
    ]

    merged = outcome_vals.merge(other_cols, on=["msid", "year"], how="left")
    print(f"{len(merged):,} school-year rows after collapsing grade/subject")

    # A school ever-treated whose matched barrier's construction year is itself unknown can't be
    # placed in event time -- drop it rather than silently mis-code it as a control.
    drop_mask = merged[ever_col] & merged[unknown_col]
    print(f"dropping {drop_mask.sum():,} rows ({merged.loc[drop_mask, 'msid'].nunique():,} schools): "
          "ever-treated but construction year unknown")
    # Likewise a never-treated school beside a wall whose side is unknown may be protected, so it
    # is not a clean control either -- drop it too.
    unknown_mask = merged[side_unknown_col] & ~merged[ever_col]
    print(f"dropping {unknown_mask.sum():,} rows ({merged.loc[unknown_mask, 'msid'].nunique():,} schools): "
          "not treated, but beside a wall whose side is unknown")
    merged = merged.loc[~(drop_mask | unknown_mask)].copy()
    return rows, school_year, merged


def add_school_baselines(
    merged: pd.DataFrame, school_year: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """§1, second step. Adds the school-level baselines, ``gvar``, the proposed-wall flag and
    §10's distance groups to ``merged``. Returns ``merged``, ``comp`` (composition per school-year,
    with ``frpl_share``) and ``analysis`` (the CS-ready dataset, Stata names)."""
    ever_col, first_col = f"ever_treated_{MATCH_TIER}", f"first_treat_year_{MATCH_TIER}"

    # Census-tract SES: each school's earliest ACS vintage
    first_acs = school_year.dropna(subset=list(SES_COLS)).sort_values("year").drop_duplicates("msid").set_index("msid")
    ses = first_acs[list(SES_COLS)].rename(columns=SES_COLS)
    ses["ses_log_income"] = np.log(ses["ses_log_income"])
    print("baseline ACS vintage per school:")
    print(first_acs["year"].value_counts().sort_index().to_string())

    # Composition in the school's first observed year
    comp = school_year[["msid", "year", "frpl_n", "enrollment", "pct_black"]].copy()
    comp["frpl_share"] = comp["frpl_n"] / comp["enrollment"]
    # a handful of rows have enrollment <= 0 or a share > 1 (data artifacts)
    comp.loc[(comp["enrollment"] <= 0) | (comp["frpl_share"] > 1.5), "frpl_share"] = np.nan
    baseline = pd.DataFrame({
        f"{name}_base": comp.dropna(subset=[col]).sort_values("year").drop_duplicates("msid").set_index("msid")[col]
        for name, col in (("frpl", "frpl_share"), ("black", "pct_black"))
    })

    merged = (
        merged.merge(ses, left_on="msid", right_index=True, how="left")
        .merge(baseline, left_on="msid", right_index=True, how="left")
    )
    # standardise across schools (one value per school), for §12's interactions
    per_school = merged.drop_duplicates("msid")
    for name in ("frpl", "black"):
        col = f"{name}_base"
        merged[f"{name}_base_z"] = (merged[col] - per_school[col].mean()) / per_school[col].std()

    merged["id"] = merged["msid"].astype("int64")
    merged["gvar"] = np.where(merged[ever_col], merged[first_col], 0.0)
    merged["proposed_ctrl"] = (merged["proposed_protected"] & ~merged[ever_col]).astype("int8")
    # §10: the treating wall's distance from its road, for treated schools
    # (docs/lines/florida-schools/notes/within_barrier_design.md): near = within NEAR_M,
    # lat_bin = 150m bins 1-4 (0 = not treated)
    treated = merged[ever_col].to_numpy()
    lateral = merged["protected_lateral_m"].to_numpy()
    merged["lat_near"] = (treated & (lateral <= NEAR_M)).astype("int8")
    merged["lat_far"] = (treated & (lateral > NEAR_M)).astype("int8")
    merged["lat_bin"] = np.where(treated, np.clip(np.ceil(lateral / LAT_BIN_M), 1, 4), 0).astype("int8")

    analysis = merged[[
        "id", "year", "gvar", "z_mss_w_school", *COVARIATES, *SES_COLS.values(),
        "frpl_base", "black_base", "frpl_base_z", "black_base_z", "proposed_ctrl",
        "protected_lateral_m", "lat_near", "lat_far", "lat_bin",
    ]].rename(columns={"z_mss_w_school": "z_mss_w", **COVARIATES})
    analysis["shock_major"] = analysis["shock_major"].astype("float64")  # Stata-friendly (avoid a bool dtype round-trip)

    n_treated_schools = analysis.loc[analysis["gvar"] > 0, "id"].nunique()
    print(f"\nfinal analysis dataset: {len(analysis):,} rows, {analysis['id'].nunique():,} schools, "
          f"{n_treated_schools:,} with a usable treatment year")
    print("\ncoverage (share of school-years non-missing):")
    print(analysis.drop(columns=["id", "year", "gvar", "z_mss_w", "proposed_ctrl", "protected_lateral_m", "lat_near", "lat_far", "lat_bin"])
          .notna().mean().round(3).to_string())
    return merged, comp, analysis


def build_cells(rows: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """§1, third step: one row per msid x grade x subject x year, same schools and years as
    ``analysis``. Each cell is weighted by its share of the school-year's test-takers
    (``cell_w``), so every school-year carries total weight 1 and, with only school and year FE,
    the cells reproduce the school-year regression exactly (checked in §6). Adds ``gsy`` (grade x
    subject x year group; EOC subjects carry grade "EOC") and ``cohort`` (year - grade; none for
    EOC)."""
    cells = rows[["msid", "grade", "subject", "year", "z_mss_w", "n_students"]].copy()
    cells["id"] = cells["msid"].astype("int64")
    cells = (
        cells.drop(columns="msid")
        .merge(analysis.drop(columns="z_mss_w"), on=["id", "year"], how="inner")
        .astype({"z_mss_w": "float64", "n_students": "float64"})
    )
    cells["cell_w"] = cells["n_students"] / cells.groupby(["id", "year"])["n_students"].transform("sum")
    cells["gsy"] = pd.factorize(cells["grade"] + "_" + cells["subject"] + "_" + cells["year"].astype(str))[0]
    cells["cohort"] = cells["year"] - pd.to_numeric(cells["grade"], errors="coerce")
    cells = cells.drop(columns=["grade", "subject"])
    print(f"{len(cells):,} grade x subject x year cells, {cells['id'].nunique():,} schools, "
          f"{cells['gsy'].nunique():,} grade x subject x year groups")
    return cells


@dataclass
class Datasets:
    """§1's frames, as the notebook's later sections use them."""

    rows: pd.DataFrame
    school_year: pd.DataFrame
    comp: pd.DataFrame
    merged: pd.DataFrame
    analysis: pd.DataFrame
    cells: pd.DataFrame


def build_datasets(panel: pd.DataFrame) -> Datasets:
    """All of §1 at once: ``build_school_year``, ``add_school_baselines``, ``build_cells``."""
    rows, school_year, merged = build_school_year(panel)
    merged, comp, analysis = add_school_baselines(merged, school_year)
    cells = build_cells(rows, analysis)
    return Datasets(rows, school_year, comp, merged, analysis, cells)


def within_sites(
    merged: pd.DataFrame, analysis: pd.DataFrame, cells: pd.DataFrame, school_year: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """§9: each school's place relative to built and proposed walls. Returns ``sites`` (one row
    per placed school: ``group``, ``site_g``, ``near``, ``built``, ``has_pre``) and
    ``analysis_within`` / ``cells_within`` (restricted to those schools, with ``site_g``,
    ``near``, ``built`` and ``district``).

    - near, built: in a built wall's protected area; exactly the treated schools of ``analysis``.
    - far, built: in a built wall's control band (600-1,500 m) and in no built wall's protected
      area, dated by its band wall's construction year (the earliest); undated ones are dropped.
    - near / far, proposed: the same areas around walls never built, for schools in no built
      wall's area or band (undated: ``site_g`` 0).
    """
    import geopandas as gpd

    from noise_pollution.regions.florida.sources.barrier_protection.shared import (
        load_control_band_zones,
        load_protection_zones,
    )
    from noise_pollution.regions.florida.sources.panel.shared import assembled_panel_path

    points = gpd.read_parquet(assembled_panel_path(), columns=["msid", "geometry"]).drop_duplicates("msid")
    points = points.loc[points["msid"].isin(merged["msid"])]
    in_zone = gpd.sjoin(points, load_protection_zones().query("category in @WALL_CATEGORIES"), predicate="within")
    in_band = gpd.sjoin(points, load_control_band_zones().query("category in @WALL_CATEGORIES"), predicate="within")

    def _schools(frame, category, status):
        return set(frame.loc[(frame["category"] == category) & (frame["zone_status"] == status), "msid"])

    near_built = _schools(in_zone, "fdot_barrier", "protected")
    far_built = _schools(in_band, "fdot_barrier", "control_band") - near_built
    near_prop = _schools(in_zone, "proposed_barrier", "protected") - near_built - far_built
    far_prop = _schools(in_band, "proposed_barrier", "control_band") - near_built - far_built - near_prop
    band_year = (
        in_band.loc[(in_band["category"] == "fdot_barrier") & (in_band["zone_status"] == "control_band")]
        .groupby("msid")["built_year"].min().astype("float64")
    )

    sites = merged.groupby("msid").agg(id=("id", "first"), gvar=("gvar", "first"), first_year=("year", "min"))
    sites["group"] = np.select(
        [sites.index.isin(near_built), sites.index.isin(far_built), sites.index.isin(near_prop), sites.index.isin(far_prop)],
        ["near, built", "far, built", "near, proposed", "far, proposed"], "",
    )
    # near built = §1's treated schools (same layers as schools assemble)
    assert ((sites["group"] == "near, built") == (sites["gvar"] > 0)).all()
    sites["site_g"] = np.select(
        [sites["group"] == "near, built", sites["group"] == "far, built"],
        [sites["gvar"], sites.index.map(band_year)], 0.0,
    )
    sites = sites.loc[(sites["group"] != "") & sites["site_g"].notna()]
    sites["near"] = sites["group"].str.startswith("near").astype("int8")
    sites["built"] = sites["group"].str.endswith("built").astype("int8")
    sites["has_pre"] = (sites["built"] == 0) | (sites["first_year"] < sites["site_g"])
    print(f"undated far built schools dropped: {len(far_built - set(band_year.dropna().index))}")
    print(pd.crosstab(sites["group"], sites["has_pre"].map({True: "with a pre-period", False: "without"})).to_string())

    # site cohorts with both near and far built schools that have a pre-period
    pre_built = sites.loc[(sites["built"] == 1) & sites["has_pre"]]
    cohorts = pre_built.groupby("site_g")["near"].agg(["sum", "count"])
    both = cohorts[(cohorts["sum"] > 0) & (cohorts["sum"] < cohorts["count"])]
    print(f"\nsite cohorts with near and far built schools (pre-period): {len(both)}, "
          f"{int(both['sum'].sum())} near and {int((both['count'] - both['sum']).sum())} far schools")

    district = school_year.groupby("msid")["district_number"].first().pipe(pd.to_numeric)
    site_cols = sites.assign(district=sites.index.map(district))[["id", "site_g", "near", "built", "district"]]
    analysis_within = analysis.merge(site_cols, on="id", how="inner")
    cells_within = cells.merge(site_cols, on="id", how="inner")
    print(f"\n{analysis_within['id'].nunique():,} schools, {len(analysis_within):,} school-years, {len(cells_within):,} cells")
    return sites, analysis_within, cells_within


def district_by_school(school_year: pd.DataFrame) -> pd.Series:
    """§16's cluster: each school's district number, indexed by ``id``."""
    district_of = school_year.groupby("msid")["district_number"].first().pipe(pd.to_numeric)
    district_of.index = district_of.index.astype("int64")
    return district_of


__all__ = [
    "CLUSTER", "CONTROL_SETS", "COVARIATES", "LAT_BIN_M", "MATCH_TIER", "NEAR_M", "SES_COLS",
    "WALL_CATEGORIES", "Datasets", "add_school_baselines", "build_cells", "build_datasets",
    "build_school_year", "district_by_school", "load_panel", "wavg_z", "within_sites",
]
