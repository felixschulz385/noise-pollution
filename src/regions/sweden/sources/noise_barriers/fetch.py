from __future__ import annotations

from src.regions.sweden.sources.noise_barriers.shared import (
    build_download_path,
    extract_noise_barrier_zip,
    normalize_dataset_name,
    validate_noise_barrier_source,
)
from src.regions.sweden.sources._trafikverket import (
    lastkajen_authenticated_get,
    lastkajen_download_file,
    lastkajen_login,
)


def list_user_files() -> list[dict]:
    access_token = lastkajen_login()["access_token"]
    files = lastkajen_authenticated_get("file/GetUserFiles", access_token)
    if not isinstance(files, list):
        raise RuntimeError("Expected a list of user files from Lastkajen.")
    return files


def get_user_file_download_token(file_name: str) -> str:
    access_token = lastkajen_login()["access_token"]
    token = lastkajen_authenticated_get(
        "file/GetUserFileDownloadToken",
        access_token,
        params={"fileName": file_name},
    )
    if not isinstance(token, str) or not token:
        raise RuntimeError("Expected a non-empty Lastkajen download token.")
    return token


def resolve_dataset_file(file_entries: list[dict], dataset_name: str) -> dict:
    normalized_dataset = normalize_dataset_name(dataset_name)
    matches = []
    for entry in file_entries:
        name = str(entry.get("name") or "")
        path_name = name.strip()
        if not path_name.casefold().endswith(".zip"):
            continue
        if Path(path_name).stem == normalized_dataset:
            matches.append(entry)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        available = ", ".join(
            sorted(
                Path(str(entry.get("name"))).stem
                for entry in file_entries
                if str(entry.get("name") or "").casefold().endswith(".zip")
            )
        )
        raise RuntimeError(
            f"Dataset '{normalized_dataset}' was not found in your Lastkajen account. "
            f"Available datasets: {available or 'none'}."
        )

    matched_names = ", ".join(str(entry.get("name")) for entry in matches)
    raise RuntimeError(f"Dataset '{normalized_dataset}' matched multiple files: {matched_names}.")


def download_user_file(
    *,
    source: str,
    dataset_name: str,
    output_name: str | None = None,
) -> dict[str, object]:
    normalized_source = validate_noise_barrier_source(source)
    file_entries = list_user_files()
    selected_entry = resolve_dataset_file(file_entries, dataset_name)
    file_name = str(selected_entry.get("name"))

    token = get_user_file_download_token(file_name)
    archive_path = build_download_path(normalized_source, output_name=output_name)
    lastkajen_download_file(token, archive_path, path_or_url="file/GetFileStream")
    extracted_paths = extract_noise_barrier_zip(archive_path, normalized_source, output_name=output_name)

    return {
        "source": normalized_source,
        "dataset_name": normalize_dataset_name(dataset_name),
        "file_name": file_name,
        "date_time": selected_entry.get("dateTime"),
        "reported_size": selected_entry.get("size"),
        "archive_removed": True,
        "extracted_paths": extracted_paths,
    }
