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


def command_master_file_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.master_file.fetch import fetch_master_file

    result = fetch_master_file(
        datasets=args.dataset,
        from_files=args.from_file,
        file_url=args.file_url,
    )
    print_json({"domain": "master_file", "stage": "fetch", **result})
    return 0
