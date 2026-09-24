"""Recover coordinates for school units that have real SIRIS assessment
history (1998-2019) but no longer exist anywhere in Skolverket's live
`Skolenhetsregistret` snapshot at all -- not even as a retired `Vilande`
unit -- so `schools/lineage.py`'s within-registry crosswalk (a retiring
unit -> its co-located successor) can't reach them, and this panel's own
outcome/treatment join otherwise hard-codes every one of them
`ever_treated_point=False` for lack of any coordinates to match against a
barrier at all. See `docs/data/sweden/schools/README.md`'s "vanished
pre-registry schools" section and `src/experiments/sweden/
schools_lineage.ipynb` §3-4 for the investigation this module implements
the recommended next step of.

**Why a third-party source, not another Skolverket API call**: Skolverket's
live `Skolenhetsregistret` API is a snapshot, not a panel -- a purged code
returns a 404 with no trace it ever existed (confirmed live, see
`schools/lineage.py`'s module docstring). Skolkoll (`skolkoll/`) turns out
to retain exactly this history: its own `status="UPPHORT"` (ceased) value
never appears in our own registry fetch at all. Checked live 2026-09-23
against the real 803 vanished codes: 306 (38%) recover a real WGS84
coordinate via an EXACT `skolenhetskod` match -- no fuzzy name/kommun
matching needed, unlike `schools_lineage.ipynb` §3's heuristic, which
never had coordinates to offer in the first place. This only reaches the
536 *modern* 8-digit vanished codes -- Skolkoll's own ids come from the
same modern `api.skolverket.se`, so it recovers 0 of the 267 legacy
9-digit pre-2013 `Skolkod` codes; those remain genuinely unrecoverable by
this or any exact-id approach.

**Design**: build a small GeoDataFrame (`skolenhetskod` + `geometry`,
EPSG:4326 -- the same shape `schools/assemble.py`'s `match_barriers_point`/`match_barriers_network`
already take)
for just the recovered codes, and run it through those SAME functions
unchanged -- no new matching algorithm, this is purely a second, smaller
population fed through the existing one. Output lands in `schools`' own
`assembled/` dir as `schools_vanished_{kind}_rollup_network.parquet`,
parallel to the registry population's own `schools_{kind}_rollup_network.
parquet`. `panel/assemble.py::load_treatment_rollup_with_recovery`
concatenates the two before the outcome join -- additive and optional
(falls back to the registry-only rollup, unchanged, if this stage hasn't
been run yet), unlike every other panel input, which is a hard
requirement -- the panel already produced a complete, working (if
incomplete for this one population) result before this module existed.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources.barrier_protection.shared import load_barrier_references
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers
from src.regions.sweden.sources.schools.assemble import (
    MAX_DIST_M,
    add_network_treatment_definitions,
    match_barriers_network,
    match_barriers_point,
)
from src.regions.sweden.sources.schools.shared import schools_paths
from src.regions.sweden.sources.skolkoll.preprocess import load_processed_skolkoll

RECOVERED_PROVENANCE_COLUMNS = {"namn": "skolkoll_namn", "kommun_namn": "skolkoll_kommun_namn", "status": "skolkoll_status"}


def load_registry_codes(root: Path | None = None) -> set[str]:
    """Every `skolenhetskod` in the current registry snapshot, geocoded or
    not -- `load_geocoded_schools` (schools/assemble.py) drops ungeocoded
    rows, which would wrongly count a real-but-ungeocoded registry entry as
    "vanished"."""
    path = schools_paths(root)["processed"] / "schools.geojson"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data schools preprocess` first.")
    return set(gpd.read_file(path)["skolenhetskod"])


def find_vanished_codes(root: Path | None = None) -> set[str]:
    """SIRIS-assessed codes absent from the registry entirely -- the same
    population `schools_lineage.ipynb` §3 defines and counts (803 as of
    2026-09-22). Imports `panel.assemble` lazily (not at module top) to
    avoid a circular import: `panel/assemble.py` imports from this module
    too, to load the recovered rollup back in."""
    from src.regions.sweden.sources.panel.assemble import SIRIS_DATASET_KEYS, build_outcomes_long, load_siris

    siris_datasets = {key: load_siris(key, root) for key in SIRIS_DATASET_KEYS}
    outcomes_long = build_outcomes_long(siris_datasets).dropna(subset=["skolenhetskod"])
    return set(outcomes_long["skolenhetskod"]) - load_registry_codes(root)


def recover_vanished_coordinates(vanished_codes: set[str], skolkoll_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Exact-`skolenhetskod` join against Skolkoll's own table, kept to
    just the rows that both are in `vanished_codes` and carry a real
    coordinate (Skolkoll has `UPPHORT` rows with no coordinate too -- see
    `skolkoll/preprocess.py` -- those can't help here). Provenance columns
    are `skolkoll_`-prefixed so a downstream table can't mistake them for
    the registry's own `namn`/`kommun_namn`/`status`."""
    matched = skolkoll_gdf[skolkoll_gdf["skolenhetskod"].isin(vanished_codes) & skolkoll_gdf.geometry.notna()].copy()
    matched = matched.rename(columns=RECOVERED_PROVENANCE_COLUMNS)
    columns = ["skolenhetskod", "geometry", *RECOVERED_PROVENANCE_COLUMNS.values()]
    return matched[columns].reset_index(drop=True)


def _run_one_kind(kind: str, recovered_gdf: gpd.GeoDataFrame, *, max_dist: float, root: Path | None) -> dict:
    barriers_gdf = load_noise_barriers(kind, root)
    pair, rollup = match_barriers_point(recovered_gdf, barriers_gdf, max_dist=max_dist)

    refs = load_barrier_references(kind, root, barriers_gdf=barriers_gdf)
    annotated_pair = match_barriers_network(pair, recovered_gdf, refs, kind=kind)
    annotated_rollup = add_network_treatment_definitions(annotated_pair, rollup)

    # Uses this module's own `schools_paths` reference (imported above), not
    # `schools/assemble.py::assembled_dir` -- that helper closes over
    # *that* module's own bound `schools_paths` name, which a test (or a
    # future caller) patching only this module's reference wouldn't reach.
    assembled = schools_paths(root)["assembled"]
    pair_path = assembled / f"schools_vanished_{kind}_pairs_network.parquet"
    rollup_path = assembled / f"schools_vanished_{kind}_rollup_network.parquet"
    annotated_pair.to_parquet(pair_path, index=False)
    annotated_rollup.to_parquet(rollup_path, index=False)

    return {
        "n_recovered_schools": int(len(recovered_gdf)),
        "n_ever_treated_point": int(annotated_rollup["ever_treated"].sum()),
        "n_ever_treated_same_route": int(annotated_rollup["ever_treated_same_route"].sum()),
        "n_ever_treated_same_side": int(annotated_rollup["ever_treated_same_side"].sum()),
        "n_ever_treated_protected": int(annotated_rollup["ever_treated_protected"].sum()),
        "saved": {"pairs": str(pair_path), "rollup": str(rollup_path)},
    }


def run_recover_vanished_schools(
    *,
    max_dist: float = MAX_DIST_M,
    root: Path | None = None,
) -> dict:
    vanished_codes = find_vanished_codes(root)
    skolkoll_gdf = load_processed_skolkoll(root)
    recovered_gdf = recover_vanished_coordinates(vanished_codes, skolkoll_gdf)

    by_kind = {
        kind: _run_one_kind(kind, recovered_gdf, max_dist=max_dist, root=root)
        for kind in BARRIER_KINDS
    }
    return {
        "n_vanished_codes": len(vanished_codes),
        "n_recovered_with_coordinates": int(len(recovered_gdf)),
        "by_kind": by_kind,
    }


def load_vanished_recovery_rollup(kind: str, root: Path | None = None) -> pd.DataFrame | None:
    """`None` (not an exception) when `run_recover_vanished_schools` hasn't
    been run for this `kind` yet -- this population is an additive,
    optional enhancement over an already-complete panel, not a hard
    prerequisite the way every other panel input is (see module
    docstring)."""
    if kind not in BARRIER_KINDS:
        raise ValueError(f"Unknown barrier kind '{kind}'. Use one of: {BARRIER_KINDS}.")
    path = schools_paths(root)["assembled"] / f"schools_vanished_{kind}_rollup_network.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)
