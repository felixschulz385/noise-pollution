"""Paths for the Sweden `neighbourhood` source: SCB DeSO-grain small-area
statistics (Covariate Cluster F, `docs/data/sweden/covariates.md`), joined
to schools by point-in-polygon spatial containment rather than
nearest-segment matching -- the DeSO layer tiles the whole country, so
every geocoded school falls inside exactly one DeSO.

DeSO was redrawn in 2025 (`stat:DeSO_2018` and `stat:DeSO_2025` are
separate WFS layers on SCB's geoserver, confirmed live 2026-09-17: 5,984
vs. 6,160 areas). This module uses the **2018** vintage throughout, since
it covers the bulk of the panel's years (income 2011-2024) on stable
boundaries -- the 2024-25 redraw is a known future gap, not handled here,
same shape as the assessments grading-reform stitching decision.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs


DESO_VINTAGE = "2018"


def neighbourhood_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("neighbourhood", root)


def deso_boundaries_raw_dir(root: Path | None = None) -> Path:
    raw_dir = neighbourhood_paths(root)["raw"] / f"deso_{DESO_VINTAGE}_boundaries"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def income_raw_dir(root: Path | None = None) -> Path:
    raw_dir = neighbourhood_paths(root)["raw"] / "income"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def education_raw_dir(root: Path | None = None) -> Path:
    raw_dir = neighbourhood_paths(root)["raw"] / "education"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def employment_raw_dir(root: Path | None = None) -> Path:
    raw_dir = neighbourhood_paths(root)["raw"] / "employment"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def processed_deso_boundaries_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / f"deso_{DESO_VINTAGE}_boundaries.parquet"


def processed_income_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / "income_net_income_structure.parquet"


def processed_education_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / "education_by_level.parquet"


def processed_employment_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["processed"] / "employment_status.parquet"


def assembled_school_neighbourhood_path(root: Path | None = None) -> Path:
    return neighbourhood_paths(root)["assembled"] / "school_neighbourhood.parquet"
