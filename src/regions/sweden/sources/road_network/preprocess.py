"""Build the candidate road network for `schools`' algorithms 4/5 from
NVDB's `Vägtrafiknät` GeoPackage (2,497,041 raw rows nationwide).

Real schema, checked live 2026-09-15 (not assumed): `ELEMENT_ID`,
`VALID_FROM`/`VALID_TO`, `START_MEASURE`/`END_MEASURE` (0-1 fractional
position within `ELEMENT_ID`, same convention as the rail network's
`grundegenskaper` file), `EXTENT_LENGTH` (metres), `Nattyp` (network type:
`bilnät`/`cykelnät`/`gångnät` -- car/bike/pedestrian), geometry. **No
route/road-number field on this layer** -- `Vägtrafiknät` is NVDB's base
geometric network only; a road number lives in a separate NVDB product
(not downloaded this session). This doesn't block algorithms 4/5: `bandel`
served only as an informational label for rail, not an input to the
`same_route` decision itself (that's corridor containment, purely
geometric) -- see `_barrier_reference.py`.
"""
from __future__ import annotations

import geopandas as gpd

from src.regions.sweden.sources.road_network.shared import default_road_network_gpkg, processed_road_network_path


LAYER_NAME = "NVDB_DK_O_88_Vagtrafiknat"
IS_CURRENT_SENTINEL = 99991231


def load_road_network(path=None, *, network_type: str = "bilnät") -> gpd.GeoDataFrame:
    """Read only the requested `Nattyp` via GDAL's own SQL `where` filter
    (checked live: reading all 2.5M rows attribute-only takes ~15s; the SQL
    filter avoids paying that cost for the ~420k bike/pedestrian rows this
    source doesn't need -- noise barriers sit along vehicle roads, not
    bike/foot paths)."""
    gpkg_path = path or default_road_network_gpkg()
    return gpd.read_file(gpkg_path, layer=LAYER_NAME, where=f"Nattyp = '{network_type}'")


def preprocess_road_network(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clean to the candidate network `_barrier_reference.py` matches
    against: current rows only (`VALID_TO == 99991231`, drops ~193 of
    2.08M `bilnät` rows -- checked live, this layer is almost entirely
    "always valid", unlike some Trafikverket layers). No absolute route-km
    reference exists in this product (see module docstring), so
    `km_from_m`/`km_to_m` are **local to each row's own geometry** (`0` to
    `extent_length_m`), not a nationwide position -- fine for the
    matching algorithms (which only need `line.project()` + local
    begin/end to rescale a 0-1 fraction), just not comparable in the
    informational way rail's real `Bandel` km position is."""
    tracks = raw[raw["VALID_TO"].eq(IS_CURRENT_SENTINEL)].copy()
    tracks = tracks.rename(
        columns={
            "ELEMENT_ID": "element_id",
            "VALID_FROM": "valid_from",
            "VALID_TO": "valid_to",
            "START_MEASURE": "start_measure",
            "END_MEASURE": "end_measure",
            "EXTENT_LENGTH": "extent_length_m",
            "Nattyp": "network_type",
        }
    )
    tracks["km_from_m"] = 0.0
    tracks["km_to_m"] = tracks["extent_length_m"]
    columns = [
        "element_id",
        "network_type",
        "km_from_m",
        "km_to_m",
        "start_measure",
        "end_measure",
        "extent_length_m",
        "valid_from",
        "geometry",
    ]
    return tracks[columns].reset_index(drop=True)


def save_processed_road_network(road_network: gpd.GeoDataFrame) -> str:
    path = processed_road_network_path()
    road_network.to_parquet(path, index=False)
    return str(path)


def run_road_network_preprocess(path=None, *, network_type: str = "bilnät") -> dict[str, object]:
    raw = load_road_network(path, network_type=network_type)
    road_network = preprocess_road_network(raw)
    saved_path = save_processed_road_network(road_network)
    return {
        "rows_read": int(len(raw)),
        "rows_current": int(len(road_network)),
        "distinct_element_id": int(road_network["element_id"].nunique()),
        "saved": saved_path,
    }
