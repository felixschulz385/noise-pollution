"""Download GHS-POP tiles (per epoch) and SCB's open 1 km population grid (per year).

GHS-POP comes as one zip per 1,000 km tile, holding the GeoTIFF, the input metadata and a
data-package PDF; only the GeoTIFF is kept. SCB's grid comes from its geoserver's WFS as one
geopackage per year (~35 MB). Both are open, no key needed. Existing files are skipped unless
`overwrite`.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from noise_pollution.regions.sweden.sources.population.shared import (
    DEFAULT_GHS_EPOCHS,
    GHS_TILE_URL,
    SCB_LAYER,
    SCB_WFS_URL,
    SCB_YEARS,
    ghs_raw_dir,
    ghs_tiles,
    scb_raw_path,
)

TIMEOUT_S = 300


def _download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    with urlopen(url, timeout=TIMEOUT_S) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    partial.replace(path)


def ghs_tile_url(epoch: int, tile: str) -> str:
    return GHS_TILE_URL.format(epoch=epoch, tile=tile)


def ghs_tile_path(epoch: int, tile: str, root: Path | None = None) -> Path:
    return ghs_raw_dir(epoch, root) / f"GHS_POP_E{epoch}_GLOBE_R2023A_54009_100_V1_0_{tile}.tif"


def extract_tif(zip_path: Path, out_path: Path) -> None:
    """Write the archive's one GeoTIFF to `out_path`, by its member name alone (no paths from
    the archive are used)."""
    with zipfile.ZipFile(zip_path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".tif")]
        if len(members) != 1:
            raise ValueError(f"{zip_path} holds {len(members)} GeoTIFFs, expected one")
        with archive.open(members[0]) as src, out_path.open("wb") as out:
            shutil.copyfileobj(src, out, length=1 << 20)


def fetch_ghs(epochs=DEFAULT_GHS_EPOCHS, *, root: Path | None = None, overwrite: bool = False) -> list[Path]:
    paths = []
    for epoch in epochs:
        for tile in ghs_tiles():
            tif = ghs_tile_path(epoch, tile, root)
            if tif.exists() and not overwrite:
                paths.append(tif)
                continue
            zip_path = tif.with_suffix(".zip")
            _download(ghs_tile_url(epoch, tile), zip_path)
            extract_tif(zip_path, tif)
            zip_path.unlink()
            paths.append(tif)
    return paths


def scb_url(year: int) -> str:
    query = {
        "service": "WFS",
        "REQUEST": "GetFeature",
        "version": "1.1.0",
        "TYPENAMES": SCB_LAYER.format(year=year),
        "outputFormat": "geopackage",
    }
    return f"{SCB_WFS_URL}?{urlencode(query)}"


def fetch_scb(years=SCB_YEARS, *, root: Path | None = None, overwrite: bool = False) -> list[Path]:
    paths = []
    for year in years:
        path = scb_raw_path(year, root)
        if overwrite or not path.exists():
            _download(scb_url(year), path)
        paths.append(path)
    return paths


def run_population_fetch(
    epochs=DEFAULT_GHS_EPOCHS, years=SCB_YEARS, *, root: Path | None = None, overwrite: bool = False
) -> dict:
    ghs = fetch_ghs(epochs, root=root, overwrite=overwrite)
    scb = fetch_scb(years, root=root, overwrite=overwrite)
    return {"ghs_tiles": len(ghs), "ghs_epochs": list(epochs), "scb_years": list(years), "scb_files": len(scb)}
