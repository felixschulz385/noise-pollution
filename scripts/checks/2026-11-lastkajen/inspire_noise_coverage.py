# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import geopandas as gpd, pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
D = ROOT + "data/sweden/"
road = gpd.read_file(D + "inspire_noise/raw/road_lden/HH_NOISE_ROAD_LDEN.gpkg")
rail = gpd.read_file(D + "inspire_noise/raw/rail_lden/HH_NOISE_RAIL_LDEN.gpkg")
for nm, g in (("road Lden", road), ("rail Lden", rail)):
    print(nm, "n", len(g), "geom types", g.geom_type.value_counts().to_dict(), "valid", int(g.is_valid.sum()), "crs", g.crs.to_epsg())
    a = g.assign(area_km2=g.area / 1e6).groupby("measure").area_km2.sum().round(0)
    print("  total area km2 by dB band:", a.to_dict())

# barriers (processed, WGS84) -> 3006
bar = {k: gpd.read_parquet(D + f"noise_barriers/processed/{k}_noise_barriers.parquet").to_crs(3006) for k in ("road", "rail")}
sch = gpd.read_file(D + "schools/processed/schools.geojson").to_crs(3006)
sch = sch[sch.geometry.notna() & ~sch.geometry.is_empty]
print("barriers", {k: len(v) for k, v in bar.items()}, "| schools with geometry", len(sch))

def share_in(points_gdf, contours, band):
    cont = contours[contours.measure >= band]
    u = cont.geometry.union_all() if hasattr(cont.geometry, "union_all") else cont.unary_union
    pts = points_gdf.copy()
    pts["geometry"] = points_gdf.geometry.representative_point() if not points_gdf.geom_type.isin(["Point"]).all() else points_gdf.geometry
    hit = pts.within(u)
    return int(hit.sum()), len(pts)

print("\nroad barriers inside road Lden contour >= band, and rail barriers inside rail Lden:")
for band in (50, 55, 60, 65):
    r = share_in(bar["road"], road, band); t = share_in(bar["rail"], rail, band)
    print(f"  >= {band} dB: road barriers {r[0]}/{r[1]} ({r[0]/r[1]:.0%}) | rail barriers {t[0]}/{t[1]} ({t[0]/t[1]:.0%})")
print("\nschools inside road Lden >= band / rail Lden >= band / either:")
for band in (55, 65):
    cr = road[road.measure >= band]; ct = rail[rail.measure >= band]
    ur = cr.geometry.union_all(); ut = ct.geometry.union_all()
    inr = sch.within(ur); intl = sch.within(ut)
    print(f"  >= {band} dB: road {int(inr.sum())}, rail {int(intl.sum())}, either {int((inr | intl).sum())} of {len(sch)}")
