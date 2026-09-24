"""Shared notebook boilerplate for `src/experiments/{florida,sweden}/*.ipynb`
and `output/notebooks/{florida,sweden}/*.ipynb` -- the display/plot options
and repo-root resolution every notebook in both regions used to copy-paste
verbatim. Import after the notebook's own tiny path bootstrap (this module
itself needs `src` importable to be reached at all, so it can't resolve the
path for you):

    import sys
    from pathlib import Path

    def _find_repo_root(start=None):
        p = (start or Path.cwd()).resolve()
        for c in [p, *p.parents]:
            if (c / "src").is_dir() and (c / "data").is_dir():
                return c
        raise FileNotFoundError(f"repo root not found from {Path.cwd()}")

    ROOT = _find_repo_root()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from src.experiments._setup import np, pd, plt, BLUE, RED, GREY, GREEN
"""
from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
pd.set_option("display.max_columns", 40)
pd.set_option("display.width", 200)
plt.rcParams["figure.dpi"] = 110

BLUE, RED, GREY, GREEN, ORANGE = "#4C78A8", "#E45756", "#B0B0B0", "#54A24B", "#d9822b"

__all__ = ["np", "pd", "plt", "BLUE", "RED", "GREY", "GREEN", "ORANGE"]
