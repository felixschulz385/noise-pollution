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


def command_traffic_list_versions(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.traffic.fetch import list_versions

    print_json({"domain": "traffic", "stage": "list-versions", **list_versions()})
    return 0


def command_traffic_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.traffic.fetch import fetch_traffic_panel

    result = fetch_traffic_panel(
        versions=args.versions,
        limit=args.limit,
        force=args.force,
        keep_road_network_raw=args.keep_road_network_raw,
    )
    print_json({"domain": "traffic", "stage": "fetch", **result})
    return 0


def command_traffic_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.traffic.preprocess import run_traffic_preprocess

    result = run_traffic_preprocess()
    print_json({"domain": "traffic", "stage": "preprocess", **result})
    return 0


def command_traffic_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.traffic.assemble import MAX_MATCH_DIST_M, run_traffic_assemble

    result = run_traffic_assemble(max_dist=args.max_dist if args.max_dist is not None else MAX_MATCH_DIST_M)
    print_json({"domain": "traffic", "stage": "assemble", **result})
    return 0


def command_road_projects_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.road_projects.fetch import fetch_road_projects

    result = fetch_road_projects(force=args.force)
    print_json({"domain": "road_projects", "stage": "fetch", **result})
    return 0


def command_road_projects_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.road_projects.preprocess import run_road_projects_preprocess

    result = run_road_projects_preprocess()
    print_json({"domain": "road_projects", "stage": "preprocess", **result})
    return 0


def command_road_projects_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.road_projects.assemble import (
        MAX_MATCH_DIST_M,
        MILEPOST_TOLERANCE_MI,
        run_road_projects_assemble,
    )

    result = run_road_projects_assemble(
        max_dist=args.max_dist if args.max_dist is not None else MAX_MATCH_DIST_M,
        tolerance_mi=args.tolerance_mi if args.tolerance_mi is not None else MILEPOST_TOLERANCE_MI,
    )
    print_json({"domain": "road_projects", "stage": "assemble", **result})
    return 0


def command_shocks_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.shocks.fetch import fetch_disaster_declarations

    result = fetch_disaster_declarations(force=args.force)
    print_json({"domain": "shocks", "stage": "fetch", **result})
    return 0


def command_shocks_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.shocks.preprocess import run_shocks_preprocess

    result = run_shocks_preprocess()
    print_json({"domain": "shocks", "stage": "preprocess", **result})
    return 0


def command_shocks_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.shocks.assemble import run_shocks_assemble

    result = run_shocks_assemble()
    print_json({"domain": "shocks", "stage": "assemble", **result})
    return 0


def command_staff_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.staff.fetch import fetch_district_finance, fetch_out_of_field, fetch_teacher_salary

    result: dict[str, object] = {}
    if args.subsource in (None, "teacher-salary"):
        result["teacher_salary"] = fetch_teacher_salary(
            years=args.year, from_file=args.from_file, file_url=args.file_url
        )
    if args.subsource in (None, "out-of-field"):
        result["out_of_field"] = fetch_out_of_field(
            years=args.year, from_file=args.from_file, file_url=args.file_url
        )
    if args.subsource in (None, "district-finance"):
        result["district_finance"] = fetch_district_finance(years=args.year)
    print_json({"domain": "staff", "stage": "fetch", **result})
    return 0


def command_staff_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.staff.preprocess import run_staff_preprocess

    result = run_staff_preprocess()
    print_json({"domain": "staff", "stage": "preprocess", **result})
    return 0


def command_staff_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.staff.assemble import run_staff_assemble

    result = run_staff_assemble()
    print_json({"domain": "staff", "stage": "assemble", **result})
    return 0


def command_neighbourhood_fetch(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.neighbourhood.fetch import (
        fetch_acs,
        fetch_tract_boundaries,
        fetch_zcta_boundaries,
        fetch_zhvi,
    )
    from src.regions.florida.sources.neighbourhood.shared import TRACT_BOUNDARY_URLS

    result: dict[str, object] = {}
    if args.subsource in (None, "tract-boundaries"):
        result["tract_boundaries"] = {v: fetch_tract_boundaries(v) for v in TRACT_BOUNDARY_URLS}
    if args.subsource in (None, "zcta-boundaries"):
        result["zcta_boundaries"] = fetch_zcta_boundaries()
    if args.subsource in (None, "zhvi"):
        result["zhvi"] = fetch_zhvi()
    if args.subsource in (None, "acs"):
        result["acs"] = fetch_acs(years=args.year)
    print_json({"domain": "neighbourhood", "stage": "fetch", **result})
    return 0


def command_neighbourhood_preprocess(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.neighbourhood.preprocess import run_neighbourhood_preprocess

    result = run_neighbourhood_preprocess()
    print_json({"domain": "neighbourhood", "stage": "preprocess", **result})
    return 0


def command_neighbourhood_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.neighbourhood.assemble import run_neighbourhood_assemble

    result = run_neighbourhood_assemble()
    print_json({"domain": "neighbourhood", "stage": "assemble", **result})
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


def command_barrier_protection_build(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.barrier_protection.build import run_barrier_protection_build

    result = run_barrier_protection_build(budget_m=args.budget_m, buffer_m=args.buffer_m)
    print_json({"domain": "barrier_protection", "stage": "build", **result})
    return 0


def command_schools_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.schools.assemble import run_schools_assemble

    result = run_schools_assemble(max_dist=args.max_dist)
    print_json({"domain": "schools", "stage": "assemble", **result})
    return 0


def command_panel_assemble(args: argparse.Namespace) -> int:
    from src.regions.florida.sources.panel.assemble import run_panel_assemble

    result = run_panel_assemble()
    print_json({"domain": "panel", "stage": "assemble", **result})
    return 0
