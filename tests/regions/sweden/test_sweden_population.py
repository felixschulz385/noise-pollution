"""The `population` source on small synthetic rasters and grids (no downloads)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import box

from noise_pollution.regions.sweden.sources.population import assemble, preprocess, shared

# 10 x 10 km near Stockholm, whole km
BOUNDS = (670_000, 6_570_000, 680_000, 6_580_000)


def test_ghs_tiles_cover_sweden_with_the_known_tiles():
    tiles = shared.ghs_tiles()
    assert {"R2_C20", "R3_C19", "R3_C20"} <= set(tiles)
    assert all(t.startswith("R") and "_C" in t for t in tiles)
    assert shared.ghs_tiles(BOUNDS) == ["R3_C20"]


@pytest.mark.parametrize(
    ("year", "epochs", "expected"),
    [(2017, shared.GHS_EPOCHS, 2015), (2018, shared.GHS_EPOCHS, 2020), (1990, shared.GHS_EPOCHS, 1990), (2020, (2015, 2025), 2015)],
)
def test_nearest_epoch(year, epochs, expected):
    assert shared.nearest_epoch(year, epochs) == expected


def _mollweide_tiles(tmp_path, bounds, value=1.0, margin_m=2_000):
    """Two adjacent 100 m Mollweide GeoTIFFs (left and right half) covering `bounds` plus a
    margin, every pixel `value` residents."""
    tf = Transformer.from_crs(shared.METRIC_CRS, shared.GHS_CRS, always_xy=True)
    xmin, ymin, xmax, ymax = bounds
    mx, my = tf.transform([xmin, xmax, xmin, xmax], [ymin, ymin, ymax, ymax])
    x0 = np.floor((min(mx) - margin_m) / 100) * 100
    x1 = np.ceil((max(mx) + margin_m) / 100) * 100
    y0 = np.floor((min(my) - margin_m) / 100) * 100
    y1 = np.ceil((max(my) + margin_m) / 100) * 100
    mid = x0 + np.floor((x1 - x0) / 200) * 100
    paths = []
    for i, (a, b) in enumerate([(x0, mid), (mid, x1)]):
        w, h = int((b - a) / 100), int((y1 - y0) / 100)
        path = tmp_path / f"tile_{i}.tif"
        with rasterio.open(
            path, "w", driver="GTiff", dtype="float32", count=1, width=w, height=h,
            crs=shared.GHS_CRS, transform=from_origin(a, y1, 100, 100), nodata=-200,
        ) as dst:
            dst.write(np.full((h, w), value, dtype=np.float32), 1)
        paths.append(path)
    return paths


def test_warp_keeps_residents_across_a_tile_seam(tmp_path):
    out = preprocess.warp_to_sweref(_mollweide_tiles(tmp_path, BOUNDS), bounds=BOUNDS)
    assert out.shape == (100, 100)
    # one resident per 100 m Mollweide pixel; both CRSs are close to true area here
    assert out.sum() == pytest.approx(10_000, rel=0.01)
    # no seam: every target cell gets about one resident
    assert out.min() > 0.95 and out.max() < 1.05


def test_raster_grid_rejects_bounds_not_on_whole_km():
    with pytest.raises(ValueError):
        preprocess.raster_grid((670_050, 6_570_000, 680_000, 6_580_000))


def test_read_scb_year_parses_the_cell_code_and_ages(tmp_path):
    gdf = gpd.GeoDataFrame(
        {
            "rutid_scb": [4230006223000, 6740006571000],
            "beftotalt": [12, 3],
            "man": [6, 1],
            "kvinna": [6, 2],
            "ald0_4": [2, 0],
            "ald100w": [0, 1],
        },
        geometry=[box(423000, 6223000, 424000, 6224000), box(674000, 6571000, 675000, 6572000)],
        crs=shared.METRIC_CRS,
    )
    path = tmp_path / "befolkning_1km_2020.gpkg"
    gdf.to_file(path, driver="GPKG")
    out = preprocess.read_scb_year(path, 2020)
    assert out[["km_e", "km_n"]].values.tolist() == [[423000, 6223000], [674000, 6571000]]
    assert out["pop"].tolist() == [12, 3]
    assert {"age_0_4", "age_100_plus", "men", "women"} <= set(out.columns)
    assert (out["year"] == 2020).all()


def _cells(bounds=BOUNDS):
    xmin, ymin, xmax, ymax = bounds
    e, n = np.meshgrid(np.arange(xmin, xmax, 100), np.arange(ymin, ymax, 100))
    e, n = e.ravel(), n.ravel()
    return pd.DataFrame({"cell_id": [f"{a}{b}" for a, b in zip(e, n)], "easting": e, "northing": n})


def test_cell_index_maps_lower_left_corners_to_raster_cells():
    rows, cols = assemble.cell_index([670_000, 679_900], [6_579_900, 6_570_000], BOUNDS)
    assert rows.tolist() == [0, 99] and cols.tolist() == [0, 99]


def test_km_shares_and_distribution_keep_scb_totals():
    array = np.zeros((100, 100), dtype=np.float32)
    array[95, 0] = 3.0  # km (670000, 6570000): one populated cell
    array[95, 5] = 1.0  # same km
    # km (671000, 6570000): no GHS residents
    cells = _cells()
    rows, cols = assemble.cell_index(cells["easting"], cells["northing"], BOUNDS)
    share = assemble.km_shares(array, rows, cols)
    scb = pd.DataFrame(
        {"year": [2020, 2020], "km_e": [670_000, 671_000], "km_n": [6_570_000, 6_570_000], "pop": [40, 50], "age_0_4": [8, 10]}
    )
    out = assemble.distribute_scb(cells, scb, share)
    first = out[out["cell_id"].isin(cells.loc[(cells.easting < 671_000) & (cells.northing < 6_571_000), "cell_id"])]
    assert first["pop"].sum() == pytest.approx(40)
    assert sorted(first["pop"].tolist()) == pytest.approx([10.0, 30.0])
    assert first["age_0_4"].sum() == pytest.approx(8)
    second = out[out["cell_id"].isin(cells.loc[(cells.easting.between(671_000, 671_900)) & (cells.northing < 6_571_000), "cell_id"])]
    assert len(second) == 100 and second["pop"].sum() == pytest.approx(50)
    assert out["pop"].sum() == pytest.approx(90)
