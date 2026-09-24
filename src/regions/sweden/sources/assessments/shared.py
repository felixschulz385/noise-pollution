"""Paths for the Sweden `assessments` source: school-level achievement data,
two vintages (`kvalitetssystem.py` for the live 2022/23-2025/26 PxWeb API,
`siris.py` for the archived 1998-2019 S3 exports). See
`docs/data/sweden/assessments/README.md` for the full design.

Kept as its own domain, separate from `schools` (identity, geocoding,
grade span, barrier-treatment timing) -- mirrors Florida's `assessments`
vs. `schools` split (`docs/data/florida/README.md`): outcome data and
school-directory/treatment data are independently-changing concerns, joined
later by a `panel`-equivalent step, not built yet.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs


def assessments_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("assessments", root)
