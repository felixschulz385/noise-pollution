from __future__ import annotations

import warnings

from noise_pollution.regions.sweden.sources.network.shared import MANUAL_DOWNLOAD_WARNING


def fetch_network_data() -> None:
    warnings.warn(MANUAL_DOWNLOAD_WARNING, stacklevel=2)
