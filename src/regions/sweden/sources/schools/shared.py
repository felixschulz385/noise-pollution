"""Paths and constants for the Sweden `schools` source.

The `Skolenhetsregistret` (school unit register) directory -- identity,
geocoding, grade span, operator, start and closing dates. See
`docs/data/sweden/schools/README.md`.

API v2 since 2026-10-20. v1 (used until then) is marked "Retired" in
Skolverket's own spec, and leaves closed (`UPPHORT`) units out of its list
and answers HTTP 410 for them; v2 lists them, with an `endDate`.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs


SKOLENHETSREGISTRET_BASE = "https://api.skolverket.se/skolenhetsregistret/v2"

# v2's `CodeSchoolUnitStatus` enum.
SCHOOL_UNIT_STATUSES = ("AKTIV", "VILANDE", "UPPHORT", "PLANERAD")

# Grundskola grades 1-9 (`schoolTypeProperties.gr.grades`), kept as one
# boolean column each.
GRUNDSKOLA_GRADES = [str(n) for n in range(1, 10)]


def schools_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("schools", root)


def skolenhet_list_url() -> str:
    return f"{SKOLENHETSREGISTRET_BASE}/school-units"


def skolenhet_detail_url(skolenhetskod: str) -> str:
    return f"{SKOLENHETSREGISTRET_BASE}/school-units/{skolenhetskod}"
