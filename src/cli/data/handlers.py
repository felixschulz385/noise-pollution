"""Dispatch logic for the `data` domain's subcommands. The argparse wiring that
calls these lives in `commands.py`."""
from __future__ import annotations

import argparse
import json
import warnings


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def timetable_filter_args(args: argparse.Namespace) -> dict:
    return {
        "location_signature": args.location_signature,
        "advertised_train_ident": args.advertised_train_ident,
        "activity_type": args.activity_type,
        "operator": args.operator,
        "canceled": args.canceled,
    }


def station_filter_args(args: argparse.Namespace) -> dict:
    return {
        "country_code": args.country_code,
        "location_signature": args.location_signature,
        "advertised": args.advertised,
        "prognosticated": args.prognosticated,
    }


def command_timetable_fetch(args: argparse.Namespace) -> int:
    import pandas as pd

    from src.data.timetable.fetch import fetch_train_announcements, save_raw_payloads

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    payloads, chunk_log = fetch_train_announcements(
        start,
        end,
        chunk_size=args.chunk_size,
        limit=args.limit,
        filters=timetable_filter_args(args),
    )
    raw_path = save_raw_payloads(payloads, filename=args.raw_filename)
    print_json(
        {
            "domain": "timetable",
            "stage": "fetch",
            "raw_path": raw_path,
            "num_payloads": len(payloads),
            "filters": timetable_filter_args(args),
            "chunk_log": chunk_log.to_dict(orient="records"),
        }
    )
    return 0


def command_timetable_preprocess(args: argparse.Namespace) -> int:
    import pandas as pd

    from src.data.timetable.fetch import load_raw_payloads
    from src.data.timetable.preprocess import (
        extract_train_announcements,
        preprocess_train_announcements,
        save_processed_train_announcements,
    )

    payloads = load_raw_payloads(filename=args.raw_filename)
    raw_df = pd.DataFrame.from_records(extract_train_announcements(payloads))
    df = preprocess_train_announcements(raw_df, filters=timetable_filter_args(args))
    saved = save_processed_train_announcements(
        df,
        csv_name=args.csv_filename,
        parquet_name=args.parquet_filename,
    )
    print_json(
        {
            "domain": "timetable",
            "stage": "preprocess",
            "rows": int(len(df)),
            "columns": list(df.columns),
            "filters": timetable_filter_args(args),
            "saved": saved,
        }
    )
    return 0


def command_timetable_assemble(args: argparse.Namespace) -> int:
    from src.data.timetable.assemble import run_timetable_assembly

    run_timetable_assembly()
    return 0


def command_stations_fetch(args: argparse.Namespace) -> int:
    from src.data.stations.fetch import fetch_stations, save_raw_stations
    from src.data.stations.preprocess import extract_train_stations

    payload = fetch_stations(filters=station_filter_args(args))
    raw_path = save_raw_stations(payload, filename=args.raw_filename)
    print_json(
        {
            "domain": "stations",
            "stage": "fetch",
            "raw_path": raw_path,
            "filters": station_filter_args(args),
            "rows": len(extract_train_stations(payload)),
        }
    )
    return 0


def command_stations_preprocess(args: argparse.Namespace) -> int:
    from src.data.stations.fetch import load_raw_stations
    from src.data.stations.preprocess import (
        extract_train_stations,
        preprocess_train_stations,
        save_processed_stations,
    )

    payload = load_raw_stations(filename=args.raw_filename)
    records = extract_train_stations(payload)
    stations_gdf = preprocess_train_stations(records, filters=station_filter_args(args))
    saved = save_processed_stations(
        stations_gdf,
        geojson_name=args.geojson_filename,
        csv_name=args.csv_filename,
    )
    print_json(
        {
            "domain": "stations",
            "stage": "preprocess",
            "rows": int(len(stations_gdf)),
            "filters": station_filter_args(args),
            "saved": saved,
        }
    )
    return 0


def command_stations_assemble(args: argparse.Namespace) -> int:
    from src.data.stations.assemble import run_station_assembly

    run_station_assembly()
    return 0


def command_network_fetch(args: argparse.Namespace) -> int:
    from src.data.network.fetch import fetch_network_data
    from src.data.network.shared import MANUAL_DOWNLOAD_WARNING

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fetch_network_data()
    warning_message = str(caught[-1].message) if caught else MANUAL_DOWNLOAD_WARNING
    print_json({"domain": "network", "stage": "fetch", "warning": warning_message})
    return 0


def command_network_preprocess(args: argparse.Namespace) -> int:
    from src.data.network.assemble import summarize_and_save_network

    bundle = summarize_and_save_network(path=args.path)
    print_json(
        {
            "domain": "network",
            "stage": "preprocess",
            "summary": bundle["summary"].to_dict(),
            "summary_path": bundle["summary_path"],
        }
    )
    return 0


def command_network_assemble(args: argparse.Namespace) -> int:
    import geopandas as gpd

    from src.data.network.assemble import save_network_plot_with_stations, summarize_and_save_network

    bundle = summarize_and_save_network(path=args.path)
    output = {
        "domain": "network",
        "stage": "assemble",
        "summary": bundle["summary"].to_dict(),
        "summary_path": bundle["summary_path"],
    }
    if args.stations_geojson:
        stations_gdf = gpd.read_file(args.stations_geojson)
        plot_path = save_network_plot_with_stations(bundle["network"], stations_gdf, args.plot_path)
        output["plot_path"] = plot_path
    print_json(output)
    return 0


def command_noise_barriers_list_files(args: argparse.Namespace) -> int:
    from src.data.noise_barriers.fetch import list_user_files

    files = list_user_files()
    print_json(
        {
            "domain": "noise_barriers",
            "stage": "list-files",
            "count": len(files),
            "files": files,
        }
    )
    return 0


def command_noise_barriers_fetch(args: argparse.Namespace) -> int:
    from src.data.noise_barriers.fetch import download_user_file

    result = download_user_file(
        source=args.dataset_source,
        dataset_name=args.dataset_name,
        output_name=args.output_name,
    )
    print_json({"domain": "noise_barriers", "stage": "fetch", **result})
    return 0


def command_noise_barriers_preprocess(args: argparse.Namespace) -> int:
    from src.data.noise_barriers.preprocess import run_noise_barrier_preprocess

    result = run_noise_barrier_preprocess(
        dataset_name=args.dataset_name,
        output_stem=args.output_stem,
    )
    print_json({"domain": "noise_barriers", "stage": "preprocess", **result})
    return 0
