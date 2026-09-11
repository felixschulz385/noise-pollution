"""Dispatch logic for Florida's `data` subcommands. The argparse wiring that
calls these lives in `src/regions/florida/cli.py`."""
from __future__ import annotations

import argparse
import json


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def command_noise_barriers_list_versions(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.noise_barriers.fetch import list_versions

    print_json({"domain": "noise_barriers", "stage": "list-versions", **list_versions()})
    return 0


def command_noise_barriers_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.noise_barriers.fetch import fetch_noise_barriers

    result = fetch_noise_barriers(
        version=args.version,
        keep_zip=args.keep_zip,
        with_metadata=not args.no_metadata,
    )
    print_json({"domain": "noise_barriers", "stage": "fetch", **result})
    return 0


def command_noise_barriers_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.noise_barriers.preprocess import run_barrier_preprocess

    result = run_barrier_preprocess(version=args.version)
    print_json({"domain": "noise_barriers", "stage": "preprocess", **result})
    return 0


def command_road_network_list_versions(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.road_network.fetch import list_versions

    print_json({"domain": "road_network", "stage": "list-versions", **list_versions()})
    return 0


def command_road_network_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.road_network.fetch import fetch_road_network

    result = fetch_road_network(
        version=args.version,
        keep_zip=args.keep_zip,
        with_metadata=not args.no_metadata,
    )
    print_json({"domain": "road_network", "stage": "fetch", **result})
    return 0


def command_road_network_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.road_network.preprocess import run_road_network_preprocess

    result = run_road_network_preprocess(version=args.version)
    print_json({"domain": "road_network", "stage": "preprocess", **result})
    return 0


def command_assessments_list_years(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.assessments.fetch import list_years

    print_json({"domain": "assessments", "stage": "list-years", **list_years()})
    return 0


def command_assessments_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.assessments.fetch import fetch_assessments

    result = fetch_assessments(
        years=args.year,
        from_files=args.from_file,
        file_url=args.file_url,
    )
    print_json({"domain": "assessments", "stage": "fetch", **result})
    return 0


def command_assessments_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.assessments.preprocess import run_assessment_preprocess

    result = run_assessment_preprocess(years=args.year)
    print_json({"domain": "assessments", "stage": "preprocess", **result})
    return 0


def command_schools_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.schools.fetch import fetch_schools

    result = fetch_schools(
        subsources=args.subsource,
        years=args.years,
        via=args.via,
        msid_datasets=args.msid_dataset,
        edge_vintage=args.edge_vintage,
        from_files=args.from_file,
        refresh=args.refresh,
    )
    print_json({"domain": "schools", "stage": "fetch", **result})
    return 0


def command_schools_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.schools.preprocess import run_schools_preprocess
    from src.regions.florida.sources.schools.shared import parse_year_range

    result = run_schools_preprocess(
        panel_years=parse_year_range(args.panel_years),
        edge_vintage=args.edge_vintage,
    )
    print_json({"domain": "schools", "stage": "preprocess", **result})
    return 0


def command_schools_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.schools.assemble import run_schools_assemble

    result = run_schools_assemble(max_dist=args.max_dist)
    print_json({"domain": "schools", "stage": "assemble", **result})
    return 0
