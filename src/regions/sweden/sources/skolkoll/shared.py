"""Paths and constants for the Sweden `skolkoll` source: a third-party
aggregation of Skolverket's own `api.skolverket.se` school-unit data
(skolkoll.se), fetched here specifically to recover coordinates for school
units purged from Skolverket's own live `Skolenhetsregistret` snapshot --
see `panel/vanished_recovery.py`'s module docstring for why our own
`schools` domain can't do this on its own (Skolverket's live API has no
history endpoint; a purged code is gone without a trace).

Not a general-purpose school register for this project -- `schools/` (the
`Skolenhetsregistret` fetch) remains the primary, authoritative identity/
geocoding source for every school that's still in the live register.
`skolkoll` is used narrowly, only for the codes that aren't.

Checked live 2026-09-23: a public flat-file CSV download, no
authentication, `;`-delimited, UTF-8 with a BOM, `#`-prefixed metadata/
variable-description header before the real header row. License: per
https://skolkoll.se/en/data-licence/, Skolverket's underlying data is
"free use and reuse in your own services, analyses and statistics"
(no standard licence stated on Skolverket's own page) provided Skolverket
is identified as the data source and Skolkoll's own aggregation/
normalisation is identified as Skolkoll processing, not attributed to
Skolverket -- both are done here (see `preprocess.py`'s module docstring
and this repo's own data documentation).
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs

SCHOOLS_CSV_URL = "https://skolkoll.se/en/download/schools.csv"


def skolkoll_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("skolkoll", root)


def raw_schools_csv_path(root: Path | None = None) -> Path:
    return skolkoll_paths(root)["raw"] / "schools.csv"


def processed_skolkoll_path(root: Path | None = None) -> Path:
    return skolkoll_paths(root)["processed"] / "skolkoll_schools.parquet"
