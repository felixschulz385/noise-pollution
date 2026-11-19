"""Group sizes and a back-of-the-envelope minimum detectable effect (MDE) for the
``sweden-residents`` cohort-exposure design
(``docs/lines/sweden-residents/prespec-cohort-exposure.tex``).

No outcome is loaded here: sizes come from the open population grid (the `population` source),
not from the register, which only the coauthors with MONA access can count.

- **Groups, per barrier b** (one stack each, dated barriers only):
  - *protected*: cells b protects whose first protecting barrier is b's year (``treat_year``),
    timing known;
  - *opposite side* (comparison 1, main): the protected-area rule with b moved across its
    road (`opposite_side_references`), one-sided barriers only;
  - *600-1500 m band* (comparison 2): b's control band, same side, farther behind.
  A comparison cell is clean unless it is of unknown side or undated, or protected (by a
  barrier of the same kind) before the window ends, ``treat_year <= tau_b + e_max`` (the
  pre-spec's "no already-treated cell is a control").
- **Children per birth cohort** in a cell at the reference year ``rho_b = tau_b - 3``: GHS-POP
  residents interpolated between epochs, times the cell's share aged 0-19 in SCB's 1 km grid
  (nearest SCB year, 2015-2025), divided by 20. Assigned through the mother's cell at
  ``rho_b``, a stack holds roughly this many children per cohort on each side.
- **MDE**: the per-stack estimate is a contrast of protected and comparison means across event
  times, with the pre-spec's regressors on that contrast; its variance is
  ``sigma^2 * [(X'X)^-1]_kk * sum_g (icc + (1 - icc) / n_g)`` over the two sides g. Stacks are
  pooled with the pre-spec's treated-share weights (Wing et al.), ``Var = sum_b w_b^2 Var_b``.
  MDE = (z_0.975 + z_0.8) x SE, in SD units of the outcome (a percentile rank has SD 28.9).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from noise_pollution.core.barrier_geometry.protection import (
    CONTROL_MAX_LATERAL_M,
    PROTECTED_MAX_LATERAL_M,
    PROTECTED_SPAN_MARGIN_M,
    BarrierReferences,
    classify_points,
    opposite_side_references,
)

# --- the pre-spec's design constants -------------------------------------------------------
A = 16  # age at the grade-9 test, on time
K = 4  # cohorts tested before the barrier, e = -K ... -2 (reference e = -2)
L = 1  # cohorts beyond A in the full window
RHO_LAG = 3  # reference year rho_b = tau_b - 3
GRADE_YEARS = (1996, 2022)
SHORT_E_MAX = 3
FULL_E_MAX = A + L
WINDOWS = {
    # every cohort e = -K ... e_max has a grade year
    "short": (GRADE_YEARS[0] + K, GRADE_YEARS[1] - SHORT_E_MAX),  # 2000-2019
    "full": (GRADE_YEARS[0] + K, GRADE_YEARS[1] - FULL_E_MAX),  # 2000-2005
}
E_MAX = {"short": SHORT_E_MAX, "full": FULL_E_MAX}
DISTANCE_BANDS = (0, 100, 250, 600, 1500)  # pre-spec r: 0-100, 100-250, 250-600; band 600-1500
CHILD_AGE_COLUMNS = ("age_0_4", "age_5_9", "age_10_14", "age_15_19")
CHILD_YEARS = 20
PERCENTILE_SD = 100 / np.sqrt(12)
Z_ALPHA, Z_POWER = 1.959964, 0.841621
MIN_PER_COHORT = 1.0
GROUPS = ("protected", "opposite", "band")


# --- pairs of cells and barriers -------------------------------------------------------------
def barrier_cell_pairs(points: np.ndarray, barriers_m, refs: BarrierReferences) -> pd.DataFrame:
    """Every (cell, barrier) pair where the barrier protects the cell, holds it in its control
    band, or would protect it from across the road: `cell` (position in `points`),
    `barrier_row`, `group` ("protected" / "band" / "opposite") and `lateral_m` (distance from
    the barrier's road). `points` and `barriers_m` in `refs.crs`."""
    frames = []
    cell, row = barriers_m.sindex.query(points, predicate="dwithin", distance=CONTROL_MAX_LATERAL_M + 100)
    own = classify_points(points[cell], row, refs, control_max_lateral_m=CONTROL_MAX_LATERAL_M)
    for group, column in (("protected", "protected"), ("band", "control_band")):
        hit = own[column].to_numpy()
        frames.append(pd.DataFrame({"cell": cell[hit], "barrier_row": row[hit], "group": group, "lateral_m": own["lateral_m"].to_numpy()[hit]}))
    mirror, one_sided = opposite_side_references(refs)
    cell, row = barriers_m.sindex.query(points, predicate="dwithin", distance=PROTECTED_MAX_LATERAL_M + PROTECTED_SPAN_MARGIN_M + 100)
    keep = one_sided[row]
    cell, row = cell[keep], row[keep]
    opp = classify_points(points[cell], row, mirror)
    hit = opp["protected"].to_numpy()
    frames.append(pd.DataFrame({"cell": cell[hit], "barrier_row": row[hit], "group": "opposite", "lateral_m": opp["lateral_m"].to_numpy()[hit]}))
    return pd.concat(frames, ignore_index=True)


# --- children per cohort ---------------------------------------------------------------------
def interpolate_ghs(ghs: pd.DataFrame, year: float) -> np.ndarray:
    """GHS-POP residents per row of `ghs` (columns `pop_<epoch>`) in `year`, linear between
    epochs, flat beyond the first and last."""
    epochs = sorted(int(c.split("_")[1]) for c in ghs.columns if c.startswith("pop_"))
    year = min(max(year, epochs[0]), epochs[-1])
    lo = max(e for e in epochs if e <= year)
    hi = min(e for e in epochs if e >= year)
    if lo == hi:
        return ghs[f"pop_{lo}"].to_numpy(dtype=float)
    w = (year - lo) / (hi - lo)
    return (1 - w) * ghs[f"pop_{lo}"].to_numpy(dtype=float) + w * ghs[f"pop_{hi}"].to_numpy(dtype=float)


def child_share(scb: pd.DataFrame, cell_ids: pd.Series, year: int) -> np.ndarray:
    """Share aged 0-19 per cell in SCB's grid, nearest SCB year; the national share where the
    cell has no SCB residents."""
    years = scb["year"].unique()
    y = int(min(max(year, years.min()), years.max()))
    s = scb[scb["year"] == y]
    kids = s[list(CHILD_AGE_COLUMNS)].sum(axis=1)
    national = kids.sum() / s["pop"].sum()
    share = pd.Series((kids / s["pop"]).to_numpy(), index=s["cell_id"].to_numpy())
    return share.reindex(cell_ids.to_numpy()).fillna(national).to_numpy()


def children_per_cohort(ghs: pd.DataFrame, scb: pd.DataFrame, years) -> pd.DataFrame:
    """Rows of `ghs` (with `cell_id`) x one column per year: GHS residents x share 0-19 / 20."""
    return pd.DataFrame(
        {int(y): interpolate_ghs(ghs, y) * child_share(scb, ghs["cell_id"], int(y)) / CHILD_YEARS for y in years},
        index=ghs.index,
    )


# --- stacks ----------------------------------------------------------------------------------
def stack_cells(pairs: pd.DataFrame, status: pd.DataFrame, built_year: np.ndarray, window: str) -> pd.DataFrame:
    """The cells of every stack: `pairs` of barriers dated inside `window`, kept by the rules in
    the module docstring, with `tau` and `rho`. `status` is indexed like `pairs.cell` with
    `treated`, `treat_year`, `timing_unknown`, `side_unknown` for this barrier kind."""
    lo, hi = WINDOWS[window]
    tau = built_year[pairs["barrier_row"].to_numpy()]
    out = pairs.assign(tau=tau)
    out = out[np.isfinite(out["tau"]) & out["tau"].between(lo, hi)].copy()
    st = status.iloc[out["cell"].to_numpy()].reset_index(drop=True)
    out = out.reset_index(drop=True)
    treat_year = st["treat_year"].astype("Float64").to_numpy(dtype=float, na_value=np.nan)
    treated = st["treated"].to_numpy(bool)
    undated = st["timing_unknown"].to_numpy(bool)
    unknown = st["side_unknown"].to_numpy(bool)
    is_p = out["group"].eq("protected").to_numpy()
    keep_p = is_p & treated & ~undated & (treat_year == out["tau"].to_numpy())
    clean = ~unknown & ~undated & (~treated | (treat_year > out["tau"].to_numpy() + E_MAX[window]))
    out = out[keep_p | (~is_p & clean)].copy()
    out["tau"] = out["tau"].astype(int)
    out["rho"] = out["tau"] - RHO_LAG
    return out


def stack_sizes(cells: pd.DataFrame, children: pd.DataFrame) -> pd.DataFrame:
    """Children per cohort at `rho` per barrier and group (columns of the result), from
    `children` (rows = cells, columns = years)."""
    rows = cells["cell"].to_numpy()
    values = children.to_numpy()
    col = {y: i for i, y in enumerate(children.columns)}
    n = values[rows, [col[r] for r in cells["rho"]]]
    sizes = cells.assign(n=n).pivot_table(index="barrier_row", columns="group", values="n", aggfunc="sum", fill_value=0.0)
    for g in GROUPS:
        if g not in sizes:
            sizes[g] = 0.0
    sizes["tau"] = cells.groupby("barrier_row")["tau"].first()
    return sizes[[*GROUPS, "tau"]]


# --- MDE -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Design:
    """The regressors on the protected-minus-comparison contrast, over event times `e`."""

    name: str
    e: np.ndarray
    columns: dict


def _short() -> Design:
    e = np.arange(-K, SHORT_E_MAX + 1)
    return Design(
        "short",
        e,
        {
            "const": np.ones(len(e)),
            "delta_SR": ((e >= 1) & (e <= SHORT_E_MAX)).astype(float),
            "d_-1": (e == -1).astype(float),
            "d_0": (e == 0).astype(float),
            "pre": np.where(e <= -2, e + 2, 0).astype(float),
        },
    )


def _full() -> Design:
    e = np.arange(-K, FULL_E_MAX + 1)
    return Design(
        "full",
        e,
        {
            "const": np.ones(len(e)),
            "delta": (e >= 1).astype(float),
            "beta_per_year": np.clip(e, 0, A).astype(float),
            "d_-1": (e == -1).astype(float),
            "d_0": (e == 0).astype(float),
            "beta_utero": (e > A).astype(float),
            "pre": np.where(e <= -2, e + 2, 0).astype(float),
        },
    )


DESIGNS = {"short": _short(), "full": _full()}


def variance_factor(design: Design, coef: str) -> float:
    """[(X'X)^-1]_kk for `coef`: its variance per unit variance of one cohort's contrast."""
    X = np.column_stack(list(design.columns.values()))
    k = list(design.columns).index(coef)
    return float(np.linalg.inv(X.T @ X)[k, k])


def mde(
    sizes: pd.DataFrame,
    comparison: str,
    design: Design,
    coef: str,
    *,
    icc: float = 0.0,
    sigma: float = 1.0,
    min_per_cohort: float = MIN_PER_COHORT,
) -> dict:
    """MDE of `coef` pooling the stacks of `sizes` with at least `min_per_cohort` expected
    children per cohort on both sides (`comparison`: "opposite", "band", or "both" for their
    sum), treated-share weighted; also the inverse-variance pooled MDE (the most a reweighting
    could gain). Below one expected child per cohort a side is empty in most cohorts and the
    stack drops out of the regression; `protected_lost_share` reports what that costs."""
    n_c = sizes[["opposite", "band"]].sum(axis=1) if comparison == "both" else sizes[comparison]
    n_p = sizes["protected"]
    use = (n_p >= min_per_cohort) & (n_c >= min_per_cohort)
    if not use.any():
        return {"stacks": 0, "protected_per_cohort": 0.0, "comparison_per_cohort": 0.0, "protected_lost_share": 1.0,
                "mde_sd": np.nan, "mde_sd_inverse_variance": np.nan, "mde_percentile_points": np.nan}
    cell = lambda n: icc + (1 - icc) / n  # noqa: E731
    var_b = sigma**2 * variance_factor(design, coef) * (cell(n_p[use]) + cell(n_c[use]))
    w = n_p[use] / n_p[use].sum()
    se = float(np.sqrt((w**2 * var_b).sum()))
    se_iv = float(np.sqrt(1 / (1 / var_b).sum()))
    z = Z_ALPHA + Z_POWER
    return {
        "stacks": int(use.sum()),
        "protected_per_cohort": float(n_p[use].sum()),
        "comparison_per_cohort": float(n_c[use].sum()),
        "protected_lost_share": float(1 - n_p[use].sum() / n_p.sum()) if n_p.sum() else np.nan,
        "mde_sd": z * se,
        "mde_sd_inverse_variance": z * se_iv,
        "mde_percentile_points": z * se * PERCENTILE_SD,
    }
