"""Dispatch logic for Sweden's `data` subcommands. The argparse wiring that
calls these lives in `src/regions/sweden/cli.py`."""
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

    from src.regions.sweden.sources.timetable.fetch import fetch_train_announcements, save_raw_payloads

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

    from src.regions.sweden.sources.timetable.fetch import load_raw_payloads
    from src.regions.sweden.sources.timetable.preprocess import (
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
    from src.regions.sweden.sources.timetable.assemble import run_timetable_assembly

    run_timetable_assembly()
    return 0


def command_stations_fetch(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.stations.fetch import fetch_stations, save_raw_stations
    from src.regions.sweden.sources.stations.preprocess import extract_train_stations

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
    from src.regions.sweden.sources.stations.fetch import load_raw_stations
    from src.regions.sweden.sources.stations.preprocess import (
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
    from src.regions.sweden.sources.stations.assemble import run_station_assembly

    run_station_assembly()
    return 0


def command_network_fetch(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.network.fetch import fetch_network_data
    from src.regions.sweden.sources.network.shared import MANUAL_DOWNLOAD_WARNING

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fetch_network_data()
    warning_message = str(caught[-1].message) if caught else MANUAL_DOWNLOAD_WARNING
    print_json({"domain": "network", "stage": "fetch", "warning": warning_message})
    return 0


def command_network_preprocess(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.network.assemble import summarize_and_save_network

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

    from src.regions.sweden.sources.network.assemble import save_network_plot_with_stations, summarize_and_save_network

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
    from src.regions.sweden.sources.noise_barriers.fetch import list_user_files

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
    from src.regions.sweden.sources.noise_barriers.fetch import download_user_file

    result = download_user_file(
        source=args.dataset_source,
        dataset_name=args.dataset_name,
        output_name=args.output_name,
    )
    print_json({"domain": "noise_barriers", "stage": "fetch", **result})
    return 0


def command_noise_barriers_preprocess(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.noise_barriers.preprocess import run_noise_barrier_preprocess

    result = run_noise_barrier_preprocess(
        dataset_name=args.dataset_name,
        output_stem=args.output_stem,
    )
    print_json({"domain": "noise_barriers", "stage": "preprocess", **result})
    return 0


def command_assessments_fetch_kvalitetssystem(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.assessments.kvalitetssystem import fetch_kvalitetssystem

    result = fetch_kvalitetssystem(
        skolform=args.skolform,
        limit_schools=args.limit_schools,
        batch_size=args.batch_size,
        force=args.force,
    )
    print_json({"domain": "assessments", "stage": "fetch-kvalitetssystem", **result})
    return 0


def command_assessments_preprocess_kvalitetssystem(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.assessments.kvalitetssystem import (
        load_measure_batches,
        preprocess_kvalitetssystem,
        save_processed_kvalitetssystem,
    )

    batches = load_measure_batches(skolform=args.skolform)
    df = preprocess_kvalitetssystem(batches)
    saved_path = save_processed_kvalitetssystem(df, parquet_name=f"kvalitetssystem_{args.skolform.lower()}.parquet")
    print_json(
        {
            "domain": "assessments",
            "stage": "preprocess-kvalitetssystem",
            "skolform": args.skolform,
            "rows": int(len(df)),
            "saved": saved_path,
        }
    )
    return 0


def command_assessments_fetch_siris(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.assessments.siris import fetch_siris_dataset

    result = fetch_siris_dataset(args.dataset_key, years=args.years, force=args.force)
    print_json({"domain": "assessments", "stage": "fetch-siris", **result})
    return 0


def command_assessments_preprocess_siris(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.assessments.siris import preprocess_siris_dataset, save_processed_siris

    df = preprocess_siris_dataset(args.dataset_key)
    saved_path = save_processed_siris(df, args.dataset_key)
    print_json(
        {
            "domain": "assessments",
            "stage": "preprocess-siris",
            "dataset_key": args.dataset_key,
            "rows": int(len(df)),
            "saved": saved_path,
        }
    )
    return 0


def command_traffic_preprocess(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.traffic.preprocess import run_traffic_preprocess

    result = run_traffic_preprocess(path=args.path)
    print_json({"domain": "traffic", "stage": "preprocess", **result})
    return 0


def command_traffic_assemble(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.traffic.assemble import run_traffic_assemble

    result = run_traffic_assemble(max_dist=args.max_dist)
    print_json({"domain": "traffic", "stage": "assemble", **result})
    return 0


def command_neighbourhood_fetch_boundaries(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.fetch import fetch_all_deso_boundaries

    result = fetch_all_deso_boundaries(page_size=args.page_size, force=args.force)
    print_json({"domain": "neighbourhood", "stage": "fetch-boundaries", **result})
    return 0


def command_neighbourhood_preprocess_boundaries(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.preprocess import run_deso_boundaries_preprocess

    result = run_deso_boundaries_preprocess()
    print_json({"domain": "neighbourhood", "stage": "preprocess-boundaries", **result})
    return 0


def _neighbourhood_deso2018_region_codes(limit: int | None) -> list:
    from src.regions.sweden.sources.neighbourhood.preprocess import run_deso_boundaries_preprocess
    from src.regions.sweden.sources.neighbourhood.shared import processed_deso_boundaries_path
    import geopandas as gpd

    boundaries_path = processed_deso_boundaries_path()
    if not boundaries_path.exists():
        run_deso_boundaries_preprocess()
    region_codes = gpd.read_parquet(boundaries_path)["desokod"].tolist()
    return region_codes[:limit] if limit is not None else region_codes


def command_neighbourhood_fetch_income(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.fetch import fetch_income_values

    region_codes = _neighbourhood_deso2018_region_codes(args.limit)
    result = fetch_income_values(region_codes, batch_size=args.batch_size, force=args.force)
    print_json({"domain": "neighbourhood", "stage": "fetch-income", "n_regions_queried": len(region_codes), **result})
    return 0


def command_neighbourhood_preprocess_income(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.preprocess import run_income_preprocess

    result = run_income_preprocess()
    print_json({"domain": "neighbourhood", "stage": "preprocess-income", **result})
    return 0


def command_neighbourhood_fetch_education(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.fetch import fetch_education_values

    region_codes = _neighbourhood_deso2018_region_codes(args.limit)
    result = fetch_education_values(region_codes, batch_size=args.batch_size, force=args.force)
    print_json({"domain": "neighbourhood", "stage": "fetch-education", "n_regions_queried": len(region_codes), **result})
    return 0


def command_neighbourhood_preprocess_education(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.preprocess import run_education_preprocess

    result = run_education_preprocess()
    print_json({"domain": "neighbourhood", "stage": "preprocess-education", **result})
    return 0


def command_neighbourhood_fetch_employment(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.fetch import fetch_employment_values

    region_codes = _neighbourhood_deso2018_region_codes(args.limit)
    result = fetch_employment_values(region_codes, batch_size=args.batch_size, force=args.force)
    print_json({"domain": "neighbourhood", "stage": "fetch-employment", "n_regions_queried": len(region_codes), **result})
    return 0


def command_neighbourhood_preprocess_employment(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.preprocess import run_employment_preprocess

    result = run_employment_preprocess()
    print_json({"domain": "neighbourhood", "stage": "preprocess-employment", **result})
    return 0


def command_neighbourhood_assemble(args: argparse.Namespace) -> int:
    from src.regions.sweden.sources.neighbourhood.assemble import run_neighbourhood_assemble

    result = run_neighbourhood_assemble()
    print_json({"domain": "neighbourhood", "stage": "assemble", **result})
    return 0
