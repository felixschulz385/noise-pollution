"""Paths and constants for the Sweden `grid` source: a self-built 100m x
100m analysis grid ("statistikrutor") covering the area around Sweden's
road/rail noise barriers, matched to schools' `noise_barriers` layer to
assign treated/untreated distance-band flags per cell -- a second output
spec alongside `schools assemble` (which matches barriers to *schools*
instead of grid cells), see docs/data/sweden/grid/README.md.

**This is NOT SCB's real 100m register grid.** SCB's genuine
individual-geocoded 100m population grid is restricted MONA microdata (a
formal researcher application + remote-access session, confirmed live
2026-09-22 -- SCB's only *open* grid geodata product, "Statistik på
rutor", is 1km resolution, see
https://www.scb.se/en/services/open-data-api/open-geodata/grid-statistics/).
Since this output only needs cell *geometry* (to place treated/untreated
distance bands), not real population counts, `preprocess.py` generates the
100m tiling itself -- deterministically aligned to the same convention
SCB's/INSPIRE's real grids use (cell id keyed on the SWEREF99TM coordinates
of the cell's lower-left corner, snapped to multiples of `RESOLUTION_M`),
so cells would line up with the real grid if MONA access is ever obtained
later.
"""
from __future__ import annotations

from pathlib import Path

from src.regions.sweden.sources._layout import domain_dirs
from src.regions.sweden.sources._linear_ref import METRIC_CRS  # noqa: F401  (re-exported for grid modules)
RESOLUTION_M = 100
# 100m increments out to 500m (mirrors Moretti & Wheeler's distance-bin
# structure, Table 2/Figure 4), plus a single 500-1000m control band.
BAND_RADII_M = (100, 200, 300, 400, 500, 1000)
# The fishnet only needs to extend as far as the widest band -- a cell
# further than this from every barrier can never be `ever_near_*` under any
# configured band, so there's no reason to generate it.
BUFFER_M = max(BAND_RADII_M)

# Distance-decay index (`assemble.py::relative_loudness_reduction_pct`):
# reproduces Moretti & Wheeler's Appendix Table A3 physics -- inverse-square-
# law decibel decay (-6 dB per doubling of distance) from a reference noise
# level, then a barrier's assumed attenuation, converted to a 0-100 perceived
# loudness scale (a 10 dB drop halves perceived loudness). Neither Florida's
# public FGDL barrier layer nor Sweden's Trafikverket layer records a real
# per-barrier engineering dB reduction (the paper's FDOT-internal field), so
# `ASSUMED_BARRIER_REDUCTION_DB` is a documented ASSUMPTION applied uniformly
# to every barrier, not a measured value -- it is close to both the paper's
# own Florida sample average (7.15 dB) and the national average it cites
# (7.0 dB, Rochat 2016). The resulting index is a distance-only exposure
# proxy for dose-response analysis, not a claim about any specific barrier's
# real acoustic performance.
ASSUMED_BARRIER_REDUCTION_DB = 7.0
REFERENCE_DIST_M = 25.0
REFERENCE_DB = 76.0


def grid_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("grid", root)


def cell_id(easting: int, northing: int, resolution_m: int = RESOLUTION_M) -> str:
    """`SE{res}mN{northing}E{easting}` -- `northing`/`easting` are the
    cell's lower-left (SW) corner in `METRIC_CRS`, integers, always a
    multiple of `resolution_m`. Mirrors the SW-corner-keyed convention
    SCB/INSPIRE grid ids use, `SE`-prefixed to mark this as a
    SWEREF99TM-native id, not the official INSPIRE CRS3035/LAEA one."""
    return f"SE{resolution_m}mN{northing}E{easting}"


def processed_grid_cells_path(root: Path | None = None) -> Path:
    return grid_paths(root)["processed"] / "grid_cells.parquet"


def assembled_dir(root: Path | None = None) -> Path:
    return grid_paths(root)["assembled"]
