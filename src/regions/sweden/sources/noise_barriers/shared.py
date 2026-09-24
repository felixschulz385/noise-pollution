from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd

from src.regions.sweden.sources._layout import domain_dirs


NOISE_BARRIER_SOURCES = ("railway", "highway")
BARRIER_KINDS = ("road", "rail")


def noise_barrier_paths(root: Path | None = None) -> dict[str, Path]:
    return domain_dirs("noise_barriers", root)


def load_noise_barriers(kind: str, root: Path | None = None) -> gpd.GeoDataFrame:
    if kind not in BARRIER_KINDS:
        raise ValueError(f"Unknown barrier kind '{kind}'. Use one of: {BARRIER_KINDS}.")
    path = noise_barrier_paths(root)["processed"] / f"{kind}_noise_barriers.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing -- run "
            f"`sweden data noise-barriers preprocess --dataset-name <...> --output-stem {kind}_noise_barriers` first."
        )
    return gpd.read_parquet(path)


def validate_noise_barrier_source(source: str) -> str:
    normalized = source.strip().lower()
    if normalized not in NOISE_BARRIER_SOURCES:
        supported = ", ".join(NOISE_BARRIER_SOURCES)
        raise ValueError(f"Unsupported noise barrier source '{source}'. Use one of: {supported}.")
    return normalized


def sanitize_download_name(file_name: str) -> str:
    cleaned = file_name.strip().replace("/", "_").replace("\\", "_")
    return cleaned or "download.bin"


def normalize_dataset_name(dataset_name: str) -> str:
    normalized = dataset_name.strip()
    if not normalized:
        raise ValueError("Dataset name must be non-empty.")
    return Path(normalized).stem


def infer_dataset_kind(dataset_name: str) -> str:
    normalized = normalize_dataset_name(dataset_name).casefold()
    if "road" in normalized:
        return "road"
    if "rail" in normalized:
        return "rail"
    return normalized.replace(" ", "_")


def processed_dataset_stem(dataset_name: str, output_stem: str | None = None) -> str:
    if output_stem:
        return Path(sanitize_download_name(output_stem)).stem
    return f"{infer_dataset_kind(dataset_name)}_noise_barriers"


def noise_barrier_dataset_stem(source: str, output_name: str | None = None) -> str:
    normalized_source = validate_noise_barrier_source(source)
    if output_name:
        return Path(sanitize_download_name(output_name)).stem
    return f"{normalized_source}_noise_barriers"


def default_raw_filename(source: str, output_name: str | None = None) -> str:
    return f"{noise_barrier_dataset_stem(source, output_name)}.zip"


def build_download_path(source: str, output_name: str | None = None) -> Path:
    paths = noise_barrier_paths()
    return paths["raw"] / default_raw_filename(source, output_name)


def extracted_member_path(source: str, member_name: str, output_name: str | None = None) -> Path:
    paths = noise_barrier_paths()
    member = Path(member_name)
    stem = noise_barrier_dataset_stem(source, output_name)
    suffix = member.suffix.lower()

    if suffix == ".gpkg":
        target_name = f"{stem}.gpkg"
    elif "leveransinformation" in member.stem.casefold():
        target_name = f"{stem}_delivery_info.txt"
    elif "licensinformation" in member.stem.casefold():
        target_name = f"{stem}_license.txt"
    else:
        target_name = f"{stem}_{sanitize_download_name(member.name)}"
    return paths["raw"] / target_name


def extract_noise_barrier_zip(archive_path: str | Path, source: str, output_name: str | None = None) -> list[str]:
    archive = Path(archive_path)
    extracted_paths: list[str] = []

    with ZipFile(archive) as zip_file:
        for member_name in zip_file.namelist():
            member = Path(member_name)
            if member_name.endswith("/") or not member.name:
                continue
            target_path = extracted_member_path(source, member.name, output_name=output_name)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(member_name) as source_handle, target_path.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
            extracted_paths.append(str(target_path))

    archive.unlink()
    return extracted_paths


def find_local_noise_barrier_bundle(dataset_name: str) -> dict[str, Path]:
    normalized_dataset = normalize_dataset_name(dataset_name)
    paths = noise_barrier_paths()

    for delivery_path in sorted(paths["raw"].glob("*_delivery_info.txt")):
        content = delivery_path.read_text(encoding="utf-8-sig")
        if normalized_dataset not in content:
            continue
        bundle_stem = delivery_path.name.removesuffix("_delivery_info.txt")
        gpkg_path = paths["raw"] / f"{bundle_stem}.gpkg"
        license_path = paths["raw"] / f"{bundle_stem}_license.txt"
        if not gpkg_path.exists():
            raise FileNotFoundError(f"Missing GeoPackage for dataset '{normalized_dataset}': {gpkg_path}")
        return {
            "dataset_name": Path(normalized_dataset).stem,
            "gpkg": gpkg_path,
            "delivery_info": delivery_path,
            "license": license_path,
        }

    available = []
    for delivery_path in sorted(paths["raw"].glob("*_delivery_info.txt")):
        content = delivery_path.read_text(encoding="utf-8-sig")
        for line in content.splitlines():
            if line.startswith("Namn på beställning:"):
                available.append(Path(line.split(":", 1)[1].strip()).stem)
                break
    available_text = ", ".join(available) or "none"
    raise FileNotFoundError(
        f"Could not find local raw files for dataset '{normalized_dataset}'. Available local datasets: {available_text}."
    )


def parse_delivery_info(path: str | Path) -> dict[str, str]:
    content = Path(path).read_text(encoding="utf-8-sig")
    metadata: dict[str, str] = {}
    current_section: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or set(line) == {"-"}:
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
            continue
        if line in {"Område", "Dataprodukter", "Övrig information"}:
            current_section = line
            continue
        if current_section:
            metadata[current_section] = line
            current_section = None
    return metadata
