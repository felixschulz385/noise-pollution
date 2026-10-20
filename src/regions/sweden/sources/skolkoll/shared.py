"""Paths and constants for the Sweden `skolkoll` source: a third-party
aggregation of Skolverket's own `api.skolverket.se` school-unit data
(skolkoll.se), fetched to recover coordinates for closed school units
that the register's API v1 left out.

**Not used by the pipeline since 2026-10-20**: `schools fetch` now reads
the register's API v2, which lists closed (`UPPHORT`) units with their
coordinates -- the same points Skolkoll mirrored (all 306 it had
recovered match exactly), so the `panel recover-vanished-schools` stage
that read this source was removed. Kept for its pupil, teacher and
merit-value columns, a possible covariate source.

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
