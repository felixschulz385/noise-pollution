"""Florida's CLI subtree: ``florida data <domain> <verb>``. Handlers live in
``handlers.py``.

Command shape mirrors Sweden's (source-then-verb). Wired up so far:
``noise_barriers`` (`fetch`, `list-versions`), ``master_file`` (`fetch` —
real download from the FLDOE EDS app), ``assessments`` (`fetch`, `list-years` —
manual-download orchestrator; www.fldoe.org blocks scripted clients). No
``preprocess`` anywhere yet; the FLDOE parsing steps are being worked out in
`src/experiments/florida/`.
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
    _register_master_file(data_domains)


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


def _register_master_file(domains: argparse._SubParsersAction) -> None:
    from src.regions.florida.sources.master_file.shared import DATASETS, DEFAULT_DATASET

    master_file = domains.add_parser(
        "master-file",
        help="FLDOE Master School ID (MSID) file",
    )
    cmd = master_file.add_subparsers(dest="stage", required=True)

    m_fetch = cmd.add_parser(
        "fetch", help="Download an MSID export from the FLDOE EDS app into raw/"
    )
    m_fetch.add_argument(
        "--dataset", action="append", choices=sorted(DATASETS),
        help=f"MSID export to download (repeatable). Default: {DEFAULT_DATASET}.",
    )
    m_fetch.add_argument(
        "--from-file", action="append",
        help="Path to an MSID export you downloaded by hand; copied into raw/ instead of downloading.",
    )
    m_fetch.add_argument(
        "--file-url", help="Arbitrary URL to GET instead of the EDS endpoints (best effort)."
    )
    m_fetch.set_defaults(func=h.command_master_file_fetch)
