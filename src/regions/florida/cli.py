"""Florida's CLI subtree: ``florida data <domain> <verb>``. Handlers live in
``handlers.py``.

Command shape mirrors Sweden's (source-then-verb). Wired up so far:
``noise_barriers`` (`fetch`, `list-versions`, `preprocess` — clean one local
FGDL release to a tidy GeoParquet barrier layer), ``assessments`` (`fetch`,
`list-years` — manual-download orchestrator, www.fldoe.org blocks scripted
clients — and `preprocess`, merging the raw workbooks into one tidy school x
grade x subject x year table), ``schools`` (`fetch` — the school spine:
MSID + NCES EDGE + Urban Institute Education Data API subsources; absorbs the
former ``master_file`` source; `preprocess` — spine + operation panel + Cluster-A
covariates; `assemble` — the school <-> noise-barrier point-only match, REQUIRES
`noise-barriers preprocess`), ``road-network`` (`list-versions`, `fetch`,
`preprocess` — FDOT RCI-derived roadway centerlines from FGDL, same archive
naming/index scheme as `noise-barriers` but a zipped Shapefile, not a
Geodatabase; `preprocess` cleans one release into a tidy GeoParquet layer).
"""
from __future__ import annotations

import argparse

from src.regions.florida import handlers as h


def register(regions: argparse._SubParsersAction) -> None:
    florida = regions.add_parser("florida", help="Florida pipeline (FDOT noise barriers; FLDOE assessments)")
    domains = florida.add_subparsers(dest="domain", required=True)

    data_parser = domains.add_parser("data", help="Data pipeline commands")
    data_domains = data_parser.add_subparsers(dest="data_domain", required=True)

    _register_noise_barriers(data_domains)
    _register_assessments(data_domains)
    _register_schools(data_domains)
    _register_road_network(data_domains)


def _register_noise_barriers(domains: argparse._SubParsersAction) -> None:
    from src.regions.florida.sources.noise_barriers.shared import DEFAULT_VERSION

    noise_barriers = domains.add_parser(
        "noise-barriers", help="FDOT noise-barrier inventory (FGDL) download pipeline"
    )
    cmd = noise_barriers.add_subparsers(dest="stage", required=True)

    nb_versions = cmd.add_parser(
        "list-versions", help="List noise-barrier dataset versions available from the FGDL archive"
    )
    nb_versions.set_defaults(func=h.command_noise_barriers_list_versions)

    nb_fetch = cmd.add_parser(
        "fetch", help="Download one FGDL noise-barrier release and extract its geodatabase into raw/"
    )
    nb_fetch.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"FGDL release tag such as 'apr23' or 'jul26' (default: {DEFAULT_VERSION}).",
    )
    nb_fetch.add_argument(
        "--keep-zip", action="store_true", help="Keep the downloaded .zip after extraction."
    )
    nb_fetch.add_argument(
        "--no-metadata", action="store_true", help="Skip downloading the companion FGDL metadata XML."
    )
    nb_fetch.set_defaults(func=h.command_noise_barriers_fetch)

    nb_pre = cmd.add_parser(
        "preprocess",
        help="Clean one local FGDL release into a tidy GeoParquet barrier layer (EPSG:3087)",
    )
    nb_pre.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"FGDL release tag to read from raw/ (default: {DEFAULT_VERSION}).",
    )
    nb_pre.set_defaults(func=h.command_noise_barriers_preprocess)


def _register_road_network(domains: argparse._SubParsersAction) -> None:
    from src.regions.florida.sources.road_network.shared import DEFAULT_VERSION

    road_network = domains.add_parser(
        "road-network", help="FDOT RCI-derived roadway centerlines (FGDL) download pipeline"
    )
    cmd = road_network.add_subparsers(dest="stage", required=True)

    rn_versions = cmd.add_parser(
        "list-versions", help="List road-network dataset versions available from the FGDL archive"
    )
    rn_versions.set_defaults(func=h.command_road_network_list_versions)

    rn_fetch = cmd.add_parser(
        "fetch", help="Download one FGDL rciroads release and extract its geodatabase into raw/"
    )
    rn_fetch.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"FGDL release tag such as 'jul26' (default: {DEFAULT_VERSION}).",
    )
    rn_fetch.add_argument(
        "--keep-zip", action="store_true", help="Keep the downloaded .zip after extraction."
    )
    rn_fetch.add_argument(
        "--no-metadata", action="store_true", help="Skip downloading the companion FGDL metadata XML."
    )
    rn_fetch.set_defaults(func=h.command_road_network_fetch)

    rn_pre = cmd.add_parser(
        "preprocess",
        help="Clean one local rciroads release into a tidy GeoParquet roadway-segment layer (EPSG:3087)",
    )
    rn_pre.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"FGDL release tag to read from raw/ (default: {DEFAULT_VERSION}).",
    )
    rn_pre.set_defaults(func=h.command_road_network_preprocess)


def _register_assessments(domains: argparse._SubParsersAction) -> None:
    assessments = domains.add_parser(
        "assessments",
        help="FLDOE annual school-level assessment results (manual-download orchestrator)",
    )
    cmd = assessments.add_subparsers(dest="stage", required=True)

    a_list = cmd.add_parser(
        "list-years", help="Show the FLDOE results-page registry and what is already in raw/"
    )
    a_list.set_defaults(func=h.command_assessments_list_years)

    a_fetch = cmd.add_parser(
        "fetch",
        help="Lay out raw/<year>/ folders, import downloaded workbooks, and report status",
    )
    a_fetch.add_argument(
        "--year", type=int, action="append",
        help="Spring administration year (repeatable). Default: all registered years.",
    )
    a_fetch.add_argument(
        "--from-file", action="append",
        help="Path to a workbook you downloaded; copied into raw/<year>/. Needs exactly one --year.",
    )
    a_fetch.add_argument(
        "--file-url",
        help="Direct file URL to try (best effort; www.fldoe.org normally 403s). Needs exactly one --year.",
    )
    a_fetch.set_defaults(func=h.command_assessments_fetch)

    a_pre = cmd.add_parser(
        "preprocess",
        help="Merge raw/<year>/ workbooks into one tidy school x grade x subject x year table",
    )
    a_pre.add_argument(
        "--year", type=int, action="append",
        help="Spring administration year to include (repeatable). Default: every year in raw/.",
    )
    a_pre.set_defaults(func=h.command_assessments_preprocess)


def _register_schools(domains: argparse._SubParsersAction) -> None:
    from src.regions.florida.sources.schools.shared import (
        API_YEARS_DEFAULT,
        DEFAULT_SUBSOURCES,
        EDGE_DEFAULT_VINTAGE,
        MSID_DATASETS,
        MSID_DEFAULT_DATASET,
        SUBSOURCES,
    )

    schools = domains.add_parser(
        "schools",
        help="School spine: MSID + NCES EDGE + Urban Institute Education Data API",
    )
    cmd = schools.add_subparsers(dest="stage", required=True)

    default_years = f"{API_YEARS_DEFAULT[0]}:{API_YEARS_DEFAULT[1]}"
    s_fetch = cmd.add_parser(
        "fetch", help="Download the school-spine subsources into raw/"
    )
    s_fetch.add_argument(
        "--subsource", action="append", choices=[*SUBSOURCES, "all"],
        help=f"Subsource to fetch (repeatable; 'all' selects every one). "
             f"Default: {', '.join(DEFAULT_SUBSOURCES)}.",
    )
    s_fetch.add_argument(
        "--years", default=default_years,
        help=f"Year range LO:HI for the Urban API subsources (default: {default_years}).",
    )
    s_fetch.add_argument(
        "--via", choices=["auto", "api", "csv"], default="auto",
        help="Route for the CCD/CRDC/EDFacts subsources: 'csv' = static flat files "
             "(survive API outages), 'api' = paginated REST, 'auto' = csv then REST "
             "for the gaps (default: auto).",
    )
    s_fetch.add_argument(
        "--msid-dataset", action="append", choices=sorted(MSID_DATASETS),
        help=f"MSID export(s) for the 'msid' subsource (repeatable). Default: {MSID_DEFAULT_DATASET}.",
    )
    s_fetch.add_argument(
        "--edge-vintage", default=EDGE_DEFAULT_VINTAGE,
        help=f"NCES EDGE geocode vintage, e.g. 2425 for SY2024-25 (default: {EDGE_DEFAULT_VINTAGE}).",
    )
    s_fetch.add_argument(
        "--from-file", action="append",
        help="Path to a file you downloaded by hand (MSID .tsv or EDGE .zip); copied into raw/.",
    )
    s_fetch.add_argument(
        "--refresh", action="store_true",
        help="Re-download Urban API years / the EDGE zip already cached in raw/.",
    )
    s_fetch.set_defaults(func=h.command_schools_fetch)

    from src.regions.florida.sources.schools.shared import PANEL_YEARS_DEFAULT

    default_panel = f"{PANEL_YEARS_DEFAULT[0]}:{PANEL_YEARS_DEFAULT[1]}"
    s_pre = cmd.add_parser(
        "preprocess",
        help="Build the school spine + operation panel (stages 1a/1b) into processed/",
    )
    s_pre.add_argument(
        "--panel-years", default=default_panel,
        help=f"Panel year range LO:HI, spring years (default: {default_panel}).",
    )
    s_pre.add_argument(
        "--edge-vintage", default=EDGE_DEFAULT_VINTAGE,
        help=f"NCES EDGE geocode vintage to read from raw/ (default: {EDGE_DEFAULT_VINTAGE}).",
    )
    s_pre.set_defaults(func=h.command_schools_preprocess)

    s_asm = cmd.add_parser(
        "assemble",
        help="School <-> barrier point-only match (stage 2, REQUIRES noise-barriers preprocess) into assembled/",
    )
    s_asm.add_argument(
        "--max-dist", type=float, default=1000.0,
        help="Candidate (msid, gcid) pair cutoff in metres (default: 1000).",
    )
    s_asm.set_defaults(func=h.command_schools_assemble)
