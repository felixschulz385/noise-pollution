"""Build the tidy, **full-history** `traffic` layer from one or more NVDB
`Trafik` GeoPackages (each a Lastkajen order at a different
`Betraktelsedatum`).

Real schema, checked live 2026-09-16 (not assumed): `ELEMENT_ID` -- the
**exact same id scheme as `road_network`'s own `element_id`** (confirmed
live: 54,444 of 54,454 distinct `Trafik` element_ids, 100.0%, found
verbatim in `road_network.parquet`; the join needs no crosswalk). Plus
`VALID_FROM`/`VALID_TO` -- **kept as real per-segment measurement-validity
windows, not filtered to "current only"**: a correction to this module's
own first version (2026-09-16), which wrongly filtered to `VALID_TO ==
99991231` on the mistaken belief that non-current rows were noise. They
aren't -- `VALID_FROM`/`VALID_TO` mark a genuine historical
`[VALID_FROM, VALID_TO)` validity window for that segment's measured ÅDT,
confirmed by directly matching a real example (Avsnitt `10630008`) against
Trafikverket's own historical-traffic web viewer: our two real orders
(`Betraktelsedatum` 2022-09-14 and 2026-09-16) returned exactly the
2012-2024 window (ÅDT 147, ±44%) and 2024-now window (ÅDT 174, ±18%) the
viewer shows for that section. See `docs/data/sweden/traffic/README.md`'s
"Correction" section for the full story of how the first version of this
module got this wrong and how it was caught.

Also present: `START_MEASURE`/`END_MEASURE`/`EXTENT_LENGTH` (same
linear-reference convention as `road_network`), `DIRECTION` (`Med`/`Mot`),
`ROLE` (`Normal`/`Syskon fram`/`Syskon bak`), the nine CNOSSOS-EU-ready
`Adt_{lätta,medeltunga,tunga}_fordon_{06-18,18-22,22-06}` time-of-day x
vehicle-class fields, `Matarsperiod` (YYYYMM, the actual measurement
vintage for that window), `Matmetod`, `Osakerhet_*`.

**`VALID_FROM`/`VALID_TO` are kept as raw `YYYYMMDD` integers, not parsed
into `datetime64`** -- the "always valid, no end date yet" sentinel
(`99991231`) overflows pandas' `datetime64[ns]` range (max ~2262), same
reason `noise_barriers`/`road_network` keep their own date-like NVDB
fields as plain ints rather than parsed dates.

**Multiple raw `.gpkg` files under `raw/` are unioned, not just the most
recent used.** Each order is a different `Betraktelsedatum` snapshot;
together they cover more of each segment's real history than any one order
alone (confirmed live: combining just the two orders already on disk this
session recovers windows spanning 1994-2026, with roughly half of all
elements already carrying 2+ distinct historical windows). Exact-duplicate
`(element_id, valid_from, valid_to, adt_samtliga_fordon, ...)` rows across
orders are deduplicated."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources.traffic.shared import all_traffic_gpkgs, processed_traffic_path


LAYER_NAME = "TRAFIK_DK_O_105_Trafik"
IS_CURRENT_SENTINEL = 99991231

_RENAME = {
    "ELEMENT_ID": "element_id",
    "VALID_FROM": "valid_from",
    "VALID_TO": "valid_to",
    "START_MEASURE": "start_measure",
    "END_MEASURE": "end_measure",
    "EXTENT_LENGTH": "extent_length_m",
    "DIRECTION": "direction",
    "ROLE": "role",
    "Adt_samtliga_fordon": "adt_samtliga_fordon",
    "Adt_tunga_fordon": "adt_tunga_fordon",
    "Adt_axelpar": "adt_axelpar",
    "Adt_latta_fordon_06_18": "adt_latta_fordon_06_18",
    "Adt_latta_fordon_18_22": "adt_latta_fordon_18_22",
    "Adt_latta_fordon_22_06": "adt_latta_fordon_22_06",
    "Adt_medeltunga_fordon_06_18": "adt_medeltunga_fordon_06_18",
    "Adt_medeltunga_fordon_18_22": "adt_medeltunga_fordon_18_22",
    "Adt_medeltunga_fordon_22_06": "adt_medeltunga_fordon_22_06",
    "Adt_tunga_fordon_06_18": "adt_tunga_fordon_06_18",
    "Adt_tunga_fordon_18_22": "adt_tunga_fordon_18_22",
    "Adt_tunga_fordon_22_06": "adt_tunga_fordon_22_06",
    "Avsnittsidentitet": "avsnittsidentitet",
    "Matarsperiod": "matarsperiod",
    "Matmetod": "matmetod",
    "Mc_floden": "mc_floden",
    "Osakerhet_axelpar": "osakerhet_axelpar",
    "Osakerhet_samtliga_fordon": "osakerhet_samtliga_fordon",
    "Osakerhet_tunga_fordon": "osakerhet_tunga_fordon",
}


def load_traffic(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(path, layer=LAYER_NAME)


def load_all_traffic(root: Path | None = None) -> list[gpd.GeoDataFrame]:
    return [load_traffic(path) for path in all_traffic_gpkgs(root)]


def preprocess_traffic(raw_frames: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    """Union every order's rows (each a real historical `[valid_from,
    valid_to)` window), snake_case-renamed, deduplicated. **Does not
    filter by `VALID_TO`** -- see the module docstring for why an earlier
    version's `VALID_TO == 99991231` filter was a real bug, not a
    simplification."""
    renamed = [df.rename(columns=_RENAME)[[*_RENAME.values(), "geometry"]] for df in raw_frames]
    combined = pd.concat(renamed, ignore_index=True)
    non_geom_cols = [c for c in combined.columns if c != "geometry"]
    combined = combined[~combined[non_geom_cols].duplicated()]
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=raw_frames[0].crs).reset_index(drop=True)


def save_processed_traffic(traffic: gpd.GeoDataFrame, root: Path | None = None) -> str:
    path = processed_traffic_path(root)
    traffic.to_parquet(path, index=False)
    return str(path)


def run_traffic_preprocess(path: Path | None = None, root: Path | None = None) -> dict[str, object]:
    raw_frames = [load_traffic(path)] if path is not None else load_all_traffic(root)
    traffic = preprocess_traffic(raw_frames)
    saved_path = save_processed_traffic(traffic, root)
    return {
        "n_orders": len(raw_frames),
        "rows_read": int(sum(len(df) for df in raw_frames)),
        "rows_after_union_and_dedup": int(len(traffic)),
        "distinct_element_id": int(traffic["element_id"].nunique()),
        "valid_from_year_range": [
            int(traffic["valid_from"].astype(str).str[:4].astype(int).min()),
            int(traffic["valid_from"].astype(str).str[:4].astype(int).max()),
        ],
        "elements_with_multiple_windows": int((traffic.groupby("element_id").size() >= 2).sum()),
        "saved": saved_path,
    }
