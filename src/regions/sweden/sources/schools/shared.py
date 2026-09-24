"""Paths and constants for the Sweden `schools` source.

Phase 1 only: the `Skolenhetsregistret` (school unit register) directory --
identity, geocoding, grade span, operator. See
`docs/data/sweden/schools/README.md` for the full multi-phase design (the
register here, plus the historical SIRIS archive and the live PxWeb
`kvalitetssystem` API for achievement data, not yet built).

API v1 is used deliberately (confirmed live 2026-09-15); v2 exists but its
field differences from v1 were not checked -- see the README's open
questions before migrating.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs


SKOLENHETSREGISTRET_BASE = "https://api.skolverket.se/skolenhetsregistret/v1"

# `Ak1`..`Ak9` are the grade-span booleans Skolverket returns on a Grundskola
# `Skolformer` entry (confirmed live: a school serving grades 4-9 returns
# `Ak4`..`Ak9=true`, `Ak1`..`Ak3=false`).
GRUNDSKOLA_GRADE_FIELDS = [f"Ak{n}" for n in range(1, 10)]


def schools_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("schools", root)


def skolenhet_list_url() -> str:
    return f"{SKOLENHETSREGISTRET_BASE}/skolenhet"


def skolenhet_detail_url(skolenhetskod: str) -> str:
    return f"{SKOLENHETSREGISTRET_BASE}/skolenhet/{skolenhetskod}"
