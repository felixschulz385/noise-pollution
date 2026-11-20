"""The analysis specification, shared by every line of work.

Put here, once: the outcome, the fixed effects, the clusters, the sample, the function that
builds and caches the analysis panel, and the figure style. Lines of work import it instead of
restating the specification (template rule: docs/analysis/code-and-notebooks.md).

So far it holds what every notebook shared: the project root, display options and the colour
palette (formerly ``src/experiments/_setup.py``). The estimation itself (Callaway-Sant'Anna via
Stata ``csdid`` through ``pystata``) still runs in the analysis notebooks,
``notebooks/{sweden,florida}-schools/``; moving their specification here is an open step
(docs/design/2026-11-template-port.md).

Notebooks bootstrap with a few lines of their own (find the root by ``pyproject.toml``, put
``src/`` on ``sys.path`` when the package is not installed), then::

    from noise_pollution.analysis.spec import BLUE, GREY, RED, np, pd, plt
"""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
pd.set_option("display.max_columns", 40)
pd.set_option("display.width", 200)
plt.rcParams["figure.dpi"] = 110

BLUE, RED, GREY, GREEN, ORANGE = "#4C78A8", "#E45756", "#B0B0B0", "#54A24B", "#d9822b"

FIGURES = "output/figures"  # figures go to output/figures/<slug>/<name>.{pdf,png}


def project_root(start: Path | None = None) -> Path:
    """The repository root: the nearest folder upward that holds ``pyproject.toml``."""
    here = (start or Path.cwd()).resolve()
    return next(p for p in [here, *here.parents] if (p / "pyproject.toml").exists())


def style() -> None:
    """The project's one figure style. Today: the dpi and palette above; fill in journal widths
    and fonts once a paper's figures are made."""


__all__ = ["np", "pd", "plt", "BLUE", "RED", "GREY", "GREEN", "ORANGE", "FIGURES", "project_root", "style"]
