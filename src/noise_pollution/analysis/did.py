"""Difference-in-differences machinery shared by the school-level lines of work.

Used by ``sweden_schools.py`` and ``florida_schools.py`` and their analysis notebooks:

- ``cs_simple_att`` and ``ri_cs``: the unconditional Callaway-Sant'Anna overall ATT in Python, and
  randomization inference on it. A ``csdid`` run takes 90 s (Sweden) to 5 min (Florida), too slow
  for 1,999 shuffles; ``cs_simple_att`` reproduces ``csdid ..., notyet`` + ``estat simple``
  exactly (checked in both notebooks' inference sections).
- ``start_stata`` and ``define_stata_programs``: start Stata through StataCorp's ``pystata`` and
  define the Stata programs both notebooks use (``cs_att``, ``cs_row``, ``twfe_setup``).

The estimation itself runs in Stata (``csdid``, ``drdid``, ``reghdfe``), called from the
notebooks' ``%%stata`` cells.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

RI_SEED = 20261022
"""Seed of every randomization (RI shuffles, ``ritest``, ``boottest``) in the 2026-10-22 runs."""
RI_DRAWS = 1999
"""Shuffles of the treatment year for the CS randomization inference."""

STATA_UTILITIES = "/Applications/Stata/utilities"
"""Where StataCorp's ``pystata`` ships (inside the Stata install, not on PyPI)."""
STATA_EDITION = "mp"
"""The edition of this machine's license (StataMP); ``se``/``be`` elsewhere."""

STATA_PROGRAMS = r"""
* cs_att: one csdid run (not-yet-treated controls unless `never'), reduced
* to its overall ATT (estat simple) in r(att) r(se) r(p) r(N)
capture program drop cs_att
program define cs_att, rclass
    syntax varlist(numeric) [if] [, NEVER]
    local control = cond("`never'" == "", "notyet", "")
    quietly csdid `varlist' `if', ivar(id) time(year) gvar(gvar) `control' method(dripw)
    quietly estat simple
    matrix _t = r(table)
    return scalar att = _t[1,1]
    return scalar se = _t[2,1]
    return scalar p = _t[4,1]
    return scalar N = e(N)
end

* cs_row mat row varlist [if] [, never]: cs_att into columns 1-4 (ATT SE p N) of row `row'
capture program drop cs_row
program define cs_row
    gettoken mat 0 : 0
    gettoken row 0 : 0
    cs_att `0'
    matrix `mat'[`row', 1] = r(att)
    matrix `mat'[`row', 2] = r(se)
    matrix `mat'[`row', 3] = r(p)
    matrix `mat'[`row', 4] = r(N)
end

* twfe_setup: `post' (treated and on/after construction) and `always'
* (treated since the school's first observed year: no pre-period, so CS
* cannot use it either; dropped from every TWFE model)
capture program drop twfe_setup
program define twfe_setup
    capture drop first_obs always post
    bysort id: egen first_obs = min(year)
    generate byte always = gvar > 0 & first_obs >= gvar
    generate byte post = gvar > 0 & year >= gvar
end
"""
"""Stata programs shared by both analysis notebooks. Every model expects the data in memory to
have ``id``, ``year`` and ``gvar`` (the construction year, 0 if never treated)."""


def start_stata(edition: str = STATA_EDITION, utilities: str = STATA_UTILITIES) -> None:
    """Start Stata through ``pystata``, which also registers the ``%%stata`` cell magic."""
    if utilities not in sys.path:
        sys.path.insert(0, utilities)
    from pystata import config

    config.init(edition)


def stata_globals(control_sets: Mapping[str, Sequence[str]]) -> str:
    """Stata ``global`` lines for named control sets: ``{"SES": ["a", "b"]}`` -> ``global SES a b``."""
    return "\n".join(f"global {name} {' '.join(cols)}" for name, cols in control_sets.items())


def define_stata_programs(control_sets: Mapping[str, Sequence[str]] | None = None) -> None:
    """Define ``STATA_PROGRAMS`` (and the control sets as globals) in the running Stata."""
    from pystata import stata

    text = STATA_PROGRAMS + ("\n" + stata_globals(control_sets) if control_sets else "")
    stata.run(text, quietly=True)


def cs_simple_att(df: pd.DataFrame, y: str) -> float:
    """The unconditional Callaway-Sant'Anna overall ATT as `csdid ..., notyet`
    + `estat simple` computes it: for every cohort g and post period t, the
    mean change from g-1 to t of the cohort's schools minus that of schools
    not yet treated at t (never treated, or treated after t), each on the
    schools observed in both years; averaged with weights equal to the
    cohort's schools in each cell."""
    wide = df.pivot_table(index="id", columns="year", values=y)
    g_of = df.groupby("id")["gvar"].first().reindex(wide.index).to_numpy()
    years = wide.columns.to_numpy()
    Y = wide.to_numpy()
    atts, weights = [], []
    for g in np.unique(g_of[g_of > 0]):
        if g - 1 not in years:
            continue
        base = Y[:, np.searchsorted(years, g - 1)]
        for t in years[years >= g]:
            yt = Y[:, np.searchsorted(years, t)]
            both = ~np.isnan(base) & ~np.isnan(yt)
            treated = both & (g_of == g)
            control = both & ((g_of == 0) | (g_of > t))
            if treated.any() and control.any():
                change = yt - base
                atts.append(change[treated].mean() - change[control].mean())
                weights.append(treated.sum())
    return float(np.average(atts, weights=weights))


def ri_cs(df: pd.DataFrame, y: str, draws: int = RI_DRAWS, seed: int = RI_SEED) -> tuple[float, float]:
    """Randomization inference for cs_simple_att: shuffle the treatment year
    across the sample's schools `draws` times. Returns the real ATT and the
    two-sided p-value (share of draws, the real one included, at least as
    large in absolute value)."""
    rng = np.random.default_rng(seed)
    real = cs_simple_att(df, y)
    g = df.groupby("id")["gvar"].first()
    hits = 1
    for _ in range(draws):
        shuffled = pd.Series(rng.permutation(g.to_numpy()), index=g.index)
        hits += abs(cs_simple_att(df.assign(gvar=df["id"].map(shuffled)), y)) >= abs(real)
    return real, hits / (draws + 1)


def identifying_schools(per_school: pd.DataFrame) -> pd.DataFrame:
    """Treated schools observed both before and after construction: rows of ``per_school`` (one
    per school, with ``gvar``, ``first_year``, ``last_year``) with a pre- and a post-period."""
    return per_school[
        (per_school["gvar"] > 0)
        & (per_school["first_year"] < per_school["gvar"])
        & (per_school["last_year"] >= per_school["gvar"])
    ]


__all__ = [
    "RI_DRAWS", "RI_SEED", "STATA_EDITION", "STATA_PROGRAMS", "STATA_UTILITIES",
    "cs_simple_att", "define_stata_programs", "identifying_schools", "ri_cs", "start_stata",
    "stata_globals",
]
