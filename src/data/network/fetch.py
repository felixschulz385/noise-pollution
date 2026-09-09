from __future__ import annotations

import warnings

from src.data.network.shared import MANUAL_DOWNLOAD_WARNING


def fetch_network_data() -> None:
    warnings.warn(MANUAL_DOWNLOAD_WARNING, stacklevel=2)
