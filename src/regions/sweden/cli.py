"""Sweden's CLI subtree: ``sweden data <domain> <verb>``. Handlers live in
``handlers.py``.

Command shape today is ``data <domain> <verb>`` (source-then-verb). The
research-project-template's target shape is ``data <verb> --source <name>``,
which depends on the per-region source registry that has not been built yet —
see docs/design/00-overview.md and docs/design/01-multi-region-layout.md.
"""
from __future__ import annotations

import argparse

from src.regions.sweden import handlers as h


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


def register(regions: argparse._SubParsersAction) -> None:
    sweden = regions.add_parser("sweden", help="Swedish rail-traffic pipeline (Trafikverket)")
    domains = sweden.add_subparsers(dest="domain", required=True)

    data_parser = domains.add_parser("data", help="Data pipeline commands")
    data_domains = data_parser.add_subparsers(dest="data_domain", required=True)

    _register_timetable(data_domains)
    _register_stations(data_domains)
    _register_network(data_domains)
    _register_noise_barriers(data_domains)
    _register_schools(data_domains)
    _register_assessments(data_domains)
    _register_road_network(data_domains)
    _register_osm_walls(data_domains)
    _register_barrier_protection(data_domains)
    _register_panel(data_domains)
    _register_traffic(data_domains)
    _register_neighbourhood(data_domains)


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
    from src.regions.sweden.sources.network.shared import network_paths

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

    net_tracks = cmd.add_parser(
        "preprocess-tracks",
        help="Build the fine-grained open-track candidate network (Bandel/km linear reference) for schools' rail matching",
    )
    net_tracks.add_argument("--path", help="Optional explicit path to the grundegenskaper GeoPackage")
    net_tracks.set_defaults(func=h.command_network_preprocess_tracks)


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


def _register_schools(domains: argparse._SubParsersAction) -> None:
    schools = domains.add_parser(
        "schools",
        help="School-unit register (Skolenhetsregistret): identity, geocoding, grade span",
    )
    cmd = schools.add_subparsers(dest="stage", required=True)

    sc_fetch = cmd.add_parser(
        "fetch",
        help="Fetch the school-unit list, then per-school detail records (geocoded)",
    )
    sc_fetch.add_argument("--limit", type=int, help="Fetch detail for at most this many schools (smoke test)")
    sc_fetch.add_argument("--status", choices=["Aktiv", "Vilande", "Planerad"], help="Only fetch this Status")
    sc_fetch.add_argument("--force", action="store_true", help="Refetch detail records already on disk")
    sc_fetch.set_defaults(func=h.command_schools_fetch)

    sc_pre = cmd.add_parser("preprocess", help="Build a tidy, geocoded school-unit table from fetched detail records")
    sc_pre.add_argument("--geojson-filename", default="schools.geojson")
    sc_pre.add_argument("--csv-filename", default="schools.csv")
    sc_pre.set_defaults(func=h.command_schools_preprocess)

    sc_asm = cmd.add_parser("assemble", help="Match geocoded schools to nearby road/rail noise barriers")
    sc_asm.add_argument("--max-dist", type=float, default=1000.0)
    sc_asm.set_defaults(func=h.command_schools_assemble)

    sc_rail_net = cmd.add_parser(
        "assemble-rail-network",
        help="Algorithms 4+5 (same_route/same_side/protected): annotate the rail match with the saved barrier references. Requires assemble + barrier-protection build first",
    )
    sc_rail_net.set_defaults(func=h.command_schools_assemble_rail_network)

    sc_road_net = cmd.add_parser(
        "assemble-road-network",
        help="Algorithms 4+5 (same_route/same_side/protected): annotate the road match with the saved barrier references. Requires assemble + barrier-protection build first",
    )
    sc_road_net.set_defaults(func=h.command_schools_assemble_road_network)

    sc_lineage = cmd.add_parser(
        "build-lineage",
        help="Build the high-confidence skolenhetskod reorg-lineage crosswalk (retired unit -> its successor at the same site). Requires preprocess first",
    )
    sc_lineage.set_defaults(func=h.command_schools_build_lineage)


def _register_assessments(domains: argparse._SubParsersAction) -> None:
    from src.regions.sweden.sources.assessments.siris import SIRIS_SCHOOL_GRAIN_DATASETS

    assessments = domains.add_parser(
        "assessments",
        help="School-unit achievement data: live PxWeb kvalitetssystem (2022/23-2025/26) + archived SIRIS (1997/98-2018/19)",
    )
    cmd = assessments.add_subparsers(dest="stage", required=True)

    ks_fetch = cmd.add_parser(
        "fetch-kvalitetssystem",
        help="Fetch school-unit achievement data from the live PxWeb kvalitetssystem API (2022/23-2025/26)",
    )
    ks_fetch.add_argument("--skolform", default="Grundskola")
    ks_fetch.add_argument("--limit-schools", type=int, help="Query at most this many schools (smoke test)")
    ks_fetch.add_argument("--batch-size", type=int, default=200)
    ks_fetch.add_argument("--force", action="store_true", help="Re-fetch metadata/codelist/batches already on disk")
    ks_fetch.set_defaults(func=h.command_assessments_fetch_kvalitetssystem)

    ks_pre = cmd.add_parser("preprocess-kvalitetssystem", help="Flatten fetched kvalitetssystem batches into a tidy table")
    ks_pre.add_argument("--skolform", default="Grundskola")
    ks_pre.set_defaults(func=h.command_assessments_preprocess_kvalitetssystem)

    siris_fetch = cmd.add_parser(
        "fetch-siris",
        help="Fetch one historical school-unit-grain SIRIS series (läsår 1997/98-2018/19) from Skolverket's archived S3 exports",
    )
    siris_fetch.add_argument("--dataset-key", required=True, choices=sorted(SIRIS_SCHOOL_GRAIN_DATASETS))
    siris_fetch.add_argument("--year", action="append", dest="years", help="Restrict to this år (repeatable)")
    siris_fetch.add_argument("--force", action="store_true")
    siris_fetch.set_defaults(func=h.command_assessments_fetch_siris)

    siris_pre = cmd.add_parser("preprocess-siris", help="Parse every fetched year of one SIRIS series into a tidy table")
    siris_pre.add_argument("--dataset-key", required=True, choices=sorted(SIRIS_SCHOOL_GRAIN_DATASETS))
    siris_pre.set_defaults(func=h.command_assessments_preprocess_siris)


def _register_road_network(domains: argparse._SubParsersAction) -> None:
    road_network = domains.add_parser(
        "road-network",
        help="NVDB Vägtrafiknät (road network) -- manually downloaded via Lastkajen, see docs/data/sweden/road_network/README.md",
    )
    cmd = road_network.add_subparsers(dest="stage", required=True)

    rn_pre = cmd.add_parser(
        "preprocess",
        help="Build the candidate car-network (bilnät) layer from the manually-downloaded Vägtrafiknät GeoPackage",
    )
    rn_pre.add_argument("--path", help="Optional explicit path to the GeoPackage")
    rn_pre.add_argument("--network-type", default="bilnät", choices=["bilnät", "cykelnät", "gångnät"])
    rn_pre.set_defaults(func=h.command_road_network_preprocess)


def _register_osm_walls(domains: argparse._SubParsersAction) -> None:
    osm_walls = domains.add_parser(
        "osm-walls",
        help="OpenStreetMap walls -- the one direct source for which side of its road a barrier stands on, "
        "see docs/data/sweden/barrier_matching.md",
    )
    cmd = osm_walls.add_subparsers(dest="stage", required=True)

    ow_fetch = cmd.add_parser("fetch", help="Download Swedish noise-barrier and untyped walls from Overpass")
    ow_fetch.set_defaults(func=h.command_osm_walls_fetch)

    ow_pre = cmd.add_parser("preprocess", help="Parse the fetched Overpass JSON into one GeoParquet")
    ow_pre.set_defaults(func=h.command_osm_walls_preprocess)


def _register_barrier_protection(domains: argparse._SubParsersAction) -> None:
    protection = domains.add_parser(
        "barrier-protection",
        help="Every noise barrier's road stretch, side and protected area -- computed once, used by schools and grid; "
        "see docs/data/sweden/barrier_matching.md",
    )
    cmd = protection.add_subparsers(dest="stage", required=True)

    bp_build = cmd.add_parser(
        "build",
        help="Build and save barrier references + the national protection-zone layer. Requires noise-barriers, "
        "road-network, network preprocess-tracks and osm-walls preprocess first",
    )
    bp_build.add_argument("--kind", choices=["road", "rail"], action="append", help="Default: both")
    bp_build.add_argument("--budget-m", type=float, default=800.0)
    bp_build.add_argument("--buffer-m", type=float, default=600.0)
    bp_build.set_defaults(func=h.command_barrier_protection_build)


def _register_panel(domains: argparse._SubParsersAction) -> None:
    panel = domains.add_parser(
        "panel",
        help="Final event-study panel: joins assessments (both vintages) + schools assemble's treatment timing",
    )
    cmd = panel.add_subparsers(dest="stage", required=True)

    p_recover = cmd.add_parser(
        "recover-vanished-schools",
        help="Recover coordinates (via Skolkoll) for SIRIS-assessed schools absent from the registry entirely, then match them to barriers. Optional -- requires skolkoll preprocess, schools assemble, barrier-protection build first",
    )
    p_recover.add_argument("--max-dist", type=float, default=1000.0)
    p_recover.set_defaults(func=h.command_panel_recover_vanished_schools)

    p_assemble = cmd.add_parser(
        "assemble",
        help="Join assessments + schools assemble's road/rail treatment timing into one long analysis panel",
    )
    p_assemble.set_defaults(func=h.command_panel_assemble)


def _register_traffic(domains: argparse._SubParsersAction) -> None:
    traffic = domains.add_parser(
        "traffic",
        help="NVDB Trafik (ÅDT / traffic flow) -- manually downloaded via Lastkajen, see docs/data/sweden/traffic/README.md",
    )
    cmd = traffic.add_subparsers(dest="stage", required=True)

    t_pre = cmd.add_parser("preprocess", help="Build the tidy traffic layer from the manually-downloaded Trafik GeoPackage")
    t_pre.add_argument("--path", help="Optional explicit path to the GeoPackage")
    t_pre.set_defaults(func=h.command_traffic_preprocess)

    t_assemble = cmd.add_parser("assemble", help="Match schools to their nearest Trafik segment")
    t_assemble.add_argument("--max-dist", type=float, default=1000.0)
    t_assemble.set_defaults(func=h.command_traffic_assemble)


def _register_neighbourhood(domains: argparse._SubParsersAction) -> None:
    neighbourhood = domains.add_parser(
        "neighbourhood",
        help="SCB DeSO-grain neighbourhood income (Covariate Cluster F), see docs/data/sweden/covariates.md",
    )
    cmd = neighbourhood.add_subparsers(dest="stage", required=True)

    n_fetch_boundaries = cmd.add_parser("fetch-boundaries", help="Fetch DeSO 2018 boundary polygons (SCB WFS)")
    n_fetch_boundaries.add_argument("--page-size", type=int, default=1000)
    n_fetch_boundaries.add_argument("--force", action="store_true")
    n_fetch_boundaries.set_defaults(func=h.command_neighbourhood_fetch_boundaries)

    n_pre_boundaries = cmd.add_parser("preprocess-boundaries", help="Build the tidy DeSO 2018 boundary layer")
    n_pre_boundaries.set_defaults(func=h.command_neighbourhood_preprocess_boundaries)

    n_fetch_income = cmd.add_parser(
        "fetch-income", help="Fetch mean net income by DeSO2018 area and year (SCB PxWeb Tab2InkDesoRegso)"
    )
    n_fetch_income.add_argument("--batch-size", type=int, default=500)
    n_fetch_income.add_argument("--limit", type=int, help="Cap the number of DeSO codes queried (smoke test)")
    n_fetch_income.add_argument("--force", action="store_true")
    n_fetch_income.set_defaults(func=h.command_neighbourhood_fetch_income)

    n_pre_income = cmd.add_parser("preprocess-income", help="Build the tidy DeSO2018 mean-net-income table")
    n_pre_income.set_defaults(func=h.command_neighbourhood_preprocess_income)

    n_fetch_education = cmd.add_parser(
        "fetch-education", help="Fetch population by education level by DeSO2018 area and year (SCB PxWeb UtbSUNBefDesoRegso)"
    )
    n_fetch_education.add_argument("--batch-size", type=int, default=500)
    n_fetch_education.add_argument("--limit", type=int, help="Cap the number of DeSO codes queried (smoke test)")
    n_fetch_education.add_argument("--force", action="store_true")
    n_fetch_education.set_defaults(func=h.command_neighbourhood_fetch_education)

    n_pre_education = cmd.add_parser("preprocess-education", help="Build the tidy DeSO2018 education-by-level table")
    n_pre_education.set_defaults(func=h.command_neighbourhood_preprocess_education)

    n_fetch_employment = cmd.add_parser(
        "fetch-employment", help="Fetch employment status by DeSO2018 area and year (SCB PxWeb ArRegDesoStatusN)"
    )
    n_fetch_employment.add_argument("--batch-size", type=int, default=500)
    n_fetch_employment.add_argument("--limit", type=int, help="Cap the number of DeSO codes queried (smoke test)")
    n_fetch_employment.add_argument("--force", action="store_true")
    n_fetch_employment.set_defaults(func=h.command_neighbourhood_fetch_employment)

    n_pre_employment = cmd.add_parser("preprocess-employment", help="Build the tidy DeSO2018 employment-status table")
    n_pre_employment.set_defaults(func=h.command_neighbourhood_preprocess_employment)

    n_assemble = cmd.add_parser(
        "assemble", help="Match schools to their containing DeSO and attach income/education/employment"
    )
    n_assemble.set_defaults(func=h.command_neighbourhood_assemble)
