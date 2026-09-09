"""argparse wiring for the `data` domain. Handlers live in `handlers.py`.

Command shape today is ``data <domain> <verb>`` (source-then-verb). The
research-project-template's target shape is ``data <verb> --source <name>``,
which depends on the source registry that has not been built yet — see
docs/design/00-overview.md.
"""
from __future__ import annotations

import argparse

from src.cli.data import handlers as h


def _add_timetable_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--location-signature")
    parser.add_argument("--advertised-train-ident")
    parser.add_argument("--activity-type", choices=["Ankomst", "Avgang"])
    parser.add_argument("--operator")
    parser.add_argument("--canceled", choices=["true", "false"])


def _add_station_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country-code", default="SE")
    parser.add_argument("--location-signature")
    parser.add_argument("--advertised", choices=["true", "false"])
    parser.add_argument("--prognosticated", choices=["true", "false"])


def register(subparsers: argparse._SubParsersAction) -> None:
    data_parser = subparsers.add_parser("data", help="Data pipeline commands")
    domains = data_parser.add_subparsers(dest="data_domain", required=True)

    _register_timetable(domains)
    _register_stations(domains)
    _register_network(domains)
    _register_noise_barriers(domains)


def _register_timetable(domains: argparse._SubParsersAction) -> None:
    timetable = domains.add_parser("timetable", help="Timetable pipeline")
    cmd = timetable.add_subparsers(dest="stage", required=True)

    tt_fetch = cmd.add_parser("fetch", help="Fetch timetable raw payloads")
    tt_fetch.add_argument("--start", required=True, help="Start timestamp")
    tt_fetch.add_argument("--end", required=True, help="End timestamp")
    tt_fetch.add_argument("--chunk-size", default="2h")
    tt_fetch.add_argument("--limit", type=int, default=50000)
    tt_fetch.add_argument("--raw-filename", default="train_announcements_sample.json")
    _add_timetable_filter_arguments(tt_fetch)
    tt_fetch.set_defaults(func=h.command_timetable_fetch)

    tt_pre = cmd.add_parser("preprocess", help="Preprocess raw timetable payloads into a clean table")
    tt_pre.add_argument("--raw-filename", default="train_announcements_sample.json")
    tt_pre.add_argument("--csv-filename", default="train_announcements_sample.csv")
    tt_pre.add_argument("--parquet-filename", default="train_announcements_sample.parquet")
    _add_timetable_filter_arguments(tt_pre)
    tt_pre.set_defaults(func=h.command_timetable_preprocess)

    tt_asm = cmd.add_parser("assemble", help="Not implemented yet for timetable")
    tt_asm.set_defaults(func=h.command_timetable_assemble)


def _register_stations(domains: argparse._SubParsersAction) -> None:
    stations = domains.add_parser("stations", help="Stations pipeline")
    cmd = stations.add_subparsers(dest="stage", required=True)

    st_fetch = cmd.add_parser("fetch", help="Fetch raw station payloads")
    st_fetch.add_argument("--raw-filename", default="train_stations_sweden.json")
    _add_station_filter_arguments(st_fetch)
    st_fetch.set_defaults(func=h.command_stations_fetch)

    st_pre = cmd.add_parser("preprocess", help="Preprocess raw station payload into clean outputs")
    st_pre.add_argument("--raw-filename", default="train_stations_sweden.json")
    st_pre.add_argument("--geojson-filename", default="train_stations_sweden.geojson")
    st_pre.add_argument("--csv-filename", default="train_stations_sweden.csv")
    _add_station_filter_arguments(st_pre)
    st_pre.set_defaults(func=h.command_stations_preprocess)

    st_asm = cmd.add_parser("assemble", help="Not implemented yet for stations")
    st_asm.set_defaults(func=h.command_stations_assemble)


def _register_network(domains: argparse._SubParsersAction) -> None:
    from src.data.network.shared import network_paths

    network = domains.add_parser("network", help="Network pipeline")
    cmd = network.add_subparsers(dest="stage", required=True)

    net_fetch = cmd.add_parser("fetch", help="Warn that network data requires manual download")
    net_fetch.set_defaults(func=h.command_network_fetch)

    net_pre = cmd.add_parser("preprocess", help="Load local network GeoPackage and save a summary")
    net_pre.add_argument("--path", help="Optional explicit path to the GeoPackage")
    net_pre.set_defaults(func=h.command_network_preprocess)

    default_plot = network_paths()["assembled"] / "network_with_stations.png"
    net_asm = cmd.add_parser("assemble", help="Summarize network and optionally render stations overlay")
    net_asm.add_argument("--path", help="Optional explicit path to the GeoPackage")
    net_asm.add_argument("--stations-geojson", help="Processed stations GeoJSON to overlay")
    net_asm.add_argument("--plot-path", default=str(default_plot))
    net_asm.set_defaults(func=h.command_network_assemble)


def _register_noise_barriers(domains: argparse._SubParsersAction) -> None:
    noise_barriers = domains.add_parser("noise-barriers", help="Noise barrier download pipeline")
    cmd = noise_barriers.add_subparsers(dest="stage", required=True)

    nb_files = cmd.add_parser("list-files", help="List files in your Lastkajen account")
    nb_files.set_defaults(func=h.command_noise_barriers_list_files)

    nb_fetch = cmd.add_parser("fetch", help="Download one noise-barrier dataset from your Lastkajen account")
    nb_fetch.add_argument(
        "--dataset-source",
        "--source",
        dest="dataset_source",
        required=True,
        choices=["railway", "highway"],
        help="Which Lastkajen catalogue to pull from.",
    )
    nb_fetch.add_argument("--dataset-name", required=True, help='Dataset stem such as "Sound_Barriers_-_Road"')
    nb_fetch.add_argument("--output-name")
    nb_fetch.set_defaults(func=h.command_noise_barriers_fetch)

    nb_pre = cmd.add_parser(
        "preprocess",
        help="Translate and clean one local noise-barrier dataset into GeoParquet",
    )
    nb_pre.add_argument("--dataset-name", required=True, help='Dataset stem such as "Sound_Barriers_-_Road"')
    nb_pre.add_argument("--output-stem", help="Optional processed output stem")
    nb_pre.set_defaults(func=h.command_noise_barriers_preprocess)
