# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, glob, collections
root = ROOT + "data/sweden/"
files = sorted(glob.glob(root + "road_projects/raw/*/*.gpkg") + glob.glob(root + "inspire_noise/raw/*/*.gpkg"))
for p in files:
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    print("\n=====", p.replace(root, ""))
    for (t, dt, srs) in c.execute("select table_name, data_type, srs_id from gpkg_contents"):
        cols = [(r[1], r[2]) for r in c.execute(f'pragma table_info("{t}")')]
        n = c.execute(f'select count(*) from "{t}"').fetchone()[0]
        print(f"  layer {t} [{dt}, EPSG:{srs}] rows={n}")
        print("   cols:", ", ".join(f"{a}:{b}" for a, b in cols))
