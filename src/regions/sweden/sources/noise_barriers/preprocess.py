from __future__ import annotations

import geopandas as gpd
import pandas as pd

from src.regions.sweden.sources.noise_barriers.shared import (
    find_local_noise_barrier_bundle,
    infer_dataset_kind,
    parse_delivery_info,
    processed_dataset_stem,
)


COMMON_COLUMN_TRANSLATIONS = {
    "ELEMENT_ID": "element_id",
    "VALID_FROM": "valid_from",
    "VALID_TO": "valid_to",
    "START_MEASURE": "start_measure",
    "END_MEASURE": "end_measure",
    "EXTENT_LENGTH": "extent_length_m",
    "SIDE": "side",
}

ROAD_COLUMN_TRANSLATIONS = {
    "Absorbent": "absorbent",
    "Agare": "owner",
    "Byggar": "built_year",
    "Grundlaggningstyp": "foundation_type",
    "Hojd": "height_m",
    "Materialtyp": "material_type",
    "Pa_bro": "on_bridge",
    "Skotselansvarig": "maintenance_responsible",
    "Skotselanvisning": "maintenance_instruction_status",
}

RAIL_COLUMN_TRANSLATIONS = {
    "Absorbent": "absorbent",
    "Agare": "owner",
    "Avstand_fr_sparmitt_m": "distance_from_track_center_m",
    "Besiktningsklass": "inspection_class",
    "Bisobjektnr": "bis_object_number",
    "Bisobjekttypnr": "bis_object_type_number",
    "Byggar": "built_year",
    "Grundlaggningstyp": "foundation_type",
    "Hojd_over_rok_m": "height_above_rail_top_m",
    "Inkopplingsdatum": "connection_date_text",
    "Kmtal": "kilometer_from",
    "Kmtalti": "kilometer_to",
    "Not_om_grundlaggning": "foundation_note",
    "Sida_h_v_b": "side_code",
    "Typ": "barrier_type",
    "Typritningsnr": "drawing_number",
    "Underhallsansvarig": "maintenance_responsible",
    "Underhallsinstruktion": "maintenance_instruction_available",
}

VALUE_TRANSLATIONS = {
    "side": {
        "Höger": "right",
        "Vänster": "left",
        "Vänster och höger": "both_sides",
        "Mitt": "center",
    },
    "side_code": {"h": "right", "v": "left", "b": "both_sides"},
    "absorbent": {"Ja": True, "Nej": False, "j": True, "n": False, "Okänt": None, "?": None},
    "on_bridge": {"Ja": True, "Nej": False, "Okänt": None},
    "maintenance_instruction_available": {"j": True, "n": False, "?": None},
    "maintenance_instruction_status": {"Finns": True, "Finns ej": False, "Okänt": None},
    "owner": {
        "Trafikverket": "Swedish Transport Administration",
        "Kommun": "municipality",
        "Kommunen": "municipality",
        "Markägare, övriga": "other landowners",
        "Övriga markägare": "other landowners",
        "Annan": "other",
        "Okänt": None,
        "Okänd": None,
        "?": None,
    },
    "foundation_type": {
        "Betongfundament": "concrete foundation",
        "Betongmur": "concrete wall",
        "Jordankare": "ground anchor",
        "Inget fundament": "no foundation",
        "Ingen": "no foundation",
        "Annat": "other",
        "Annan": "other",
        "Okänt": None,
        "?": None,
    },
    "material_type": {
        "Trä": "wood",
        "Jordvall": "earth berm",
        "Glas/plexiglas": "glass_or_plexiglass",
        "Plast": "plastic",
        "Annan": "other",
        "Sten/tegel": "stone_or_brick",
        "Betong": "concrete",
        "Metall": "metal",
        "Gabion": "gabion",
        "Okänt": None,
    },
    "barrier_type": {
        "Trä": "wood",
        "Jordvall": "earth berm",
        "Metall": "metal",
        "Betong": "concrete",
        "Glas/Plexiglas": "glass_or_plexiglass",
        "Plast": "plastic",
        "Jordvall/Trä": "earth_berm_and_wood",
        "Annan": "other",
        "Gabion": "gabion",
        "?": None,
    },
    "maintenance_responsible": {
        "Trafikverket": "Swedish Transport Administration",
        "Kommun": "municipality",
        "Kommunen": "municipality",
        "Markägare, övriga": "other landowners",
        "Övriga markägare": "other landowners",
        "Annan": "other",
        "Okänd": None,
        "Okänt": None,
        "?": None,
    },
}

DELIVERY_INFO_TRANSLATIONS = {
    "Namn på beställning": "order_name",
    "Beställningsdatum": "order_datetime",
    "Betraktelsedatum": "reference_date",
    "Format": "format",
    "Koordinatsystem": "coordinate_system",
    "Område": "coverage_area",
    "Dataprodukter": "data_products",
    "Övrig information": "other_information",
}


def load_raw_noise_barriers(dataset_name: str) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    bundle = find_local_noise_barrier_bundle(dataset_name)
    layer_name = gpd.list_layers(bundle["gpkg"]).iloc[0]["name"]
    gdf = gpd.read_file(bundle["gpkg"], layer=layer_name)
    delivery_info_sv = parse_delivery_info(bundle["delivery_info"])
    metadata = {
        "dataset_name": bundle["dataset_name"],
        "dataset_kind": infer_dataset_kind(dataset_name),
        "raw_gpkg_path": str(bundle["gpkg"]),
        "raw_delivery_info_path": str(bundle["delivery_info"]),
        "raw_license_path": str(bundle["license"]) if bundle["license"].exists() else None,
        "raw_layer_name": layer_name,
        "raw_crs": str(gdf.crs),
        "delivery_info_sv": delivery_info_sv,
        "delivery_info_en": {DELIVERY_INFO_TRANSLATIONS.get(k, k): v for k, v in delivery_info_sv.items()},
    }
    return gdf, metadata


def _translate_values(series: pd.Series, mapping: dict) -> pd.Series:
    return series.map(lambda value: mapping.get(value, value))


def _parse_valid_to(value: object):
    text = str(value) if value is not None else ""
    if text == "99991231":
        return pd.NaT
    return pd.to_datetime(text, format="%Y%m%d", errors="coerce")


def preprocess_noise_barriers(gdf: gpd.GeoDataFrame, dataset_kind: str) -> gpd.GeoDataFrame:
    translated = gdf.copy()
    translated = translated.to_crs(4326) if translated.crs else translated

    column_map = dict(COMMON_COLUMN_TRANSLATIONS)
    if dataset_kind == "road":
        column_map.update(ROAD_COLUMN_TRANSLATIONS)
    elif dataset_kind == "rail":
        column_map.update(RAIL_COLUMN_TRANSLATIONS)
    else:
        raise ValueError(f"Unsupported dataset kind '{dataset_kind}'.")

    translated = translated.rename(columns=column_map)
    translated["dataset_kind"] = dataset_kind
    translated["valid_from"] = pd.to_datetime(translated.get("valid_from"), format="%Y%m%d", errors="coerce")
    translated["valid_to"] = translated.get("valid_to", pd.Series(dtype=object)).apply(_parse_valid_to)
    translated["is_current"] = gdf.get("VALID_TO", pd.Series(dtype=object)).astype(str).eq("99991231")

    if "built_year" in translated.columns:
        translated["built_year"] = pd.to_numeric(translated["built_year"], errors="coerce").astype("Int64")

    for numeric_column in [
        "start_measure",
        "end_measure",
        "extent_length_m",
        "distance_from_track_center_m",
        "height_m",
        "height_above_rail_top_m",
    ]:
        if numeric_column in translated.columns:
            translated[numeric_column] = pd.to_numeric(translated[numeric_column], errors="coerce")

    if "connection_date_text" in translated.columns:
        translated["connection_date_is_before_flag"] = translated["connection_date_text"].astype(str).str.startswith("<")
        translated["connection_date"] = pd.to_datetime(
            translated["connection_date_text"].astype(str).str.lstrip("<"),
            format="%Y%m%d",
            errors="coerce",
        )

    for column, mapping in VALUE_TRANSLATIONS.items():
        if column in translated.columns:
            translated[column] = _translate_values(translated[column], mapping)

    if "inspection_class" in translated.columns:
        translated["inspection_class"] = translated["inspection_class"].astype(str).str.lower().replace({"nan": None})

    column_order = [
        "element_id",
        "dataset_kind",
        "valid_from",
        "valid_to",
        "is_current",
        "start_measure",
        "end_measure",
        "extent_length_m",
        "side",
        "side_code",
        "absorbent",
        "owner",
        "material_type",
        "barrier_type",
        "foundation_type",
        "height_m",
        "height_above_rail_top_m",
        "distance_from_track_center_m",
        "on_bridge",
        "built_year",
        "inspection_class",
        "maintenance_responsible",
        "maintenance_instruction_status",
        "maintenance_instruction_available",
        "connection_date",
        "connection_date_is_before_flag",
        "connection_date_text",
        "kilometer_from",
        "kilometer_to",
        "bis_object_number",
        "bis_object_type_number",
        "drawing_number",
        "foundation_note",
        "geometry",
    ]
    existing = [column for column in column_order if column in translated.columns]
    remaining = [column for column in translated.columns if column not in existing]
    return translated[existing + remaining].sort_values("element_id").reset_index(drop=True)


def save_processed_noise_barriers(
    gdf: gpd.GeoDataFrame,
    *,
    dataset_name: str,
    output_stem: str | None = None,
) -> dict[str, str]:
    from data.noise_barriers.shared import noise_barrier_paths

    paths = noise_barrier_paths()
    stem = processed_dataset_stem(dataset_name, output_stem)
    parquet_path = paths["processed"] / f"{stem}.parquet"

    # Write a single GeoParquet artifact that preserves schema and geometry.
    gdf.to_parquet(parquet_path, index=False)

    return {
        "parquet": str(parquet_path),
    }


def run_noise_barrier_preprocess(dataset_name: str, output_stem: str | None = None) -> dict[str, object]:
    raw_gdf, metadata = load_raw_noise_barriers(dataset_name)
    processed_gdf = preprocess_noise_barriers(raw_gdf, metadata["dataset_kind"])
    metadata["rows"] = int(len(processed_gdf))
    metadata["columns"] = list(processed_gdf.columns)
    metadata["processed_crs"] = str(processed_gdf.crs)
    saved = save_processed_noise_barriers(processed_gdf, dataset_name=dataset_name, output_stem=output_stem)
    return {
        "dataset_name": metadata["dataset_name"],
        "dataset_kind": metadata["dataset_kind"],
        "rows": int(len(processed_gdf)),
        "columns": list(processed_gdf.columns),
        "saved": saved,
    }
