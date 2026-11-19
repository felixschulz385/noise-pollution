# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, glob, collections, struct
root = ROOT + "data/sweden/inspire_noise/raw/"
C = collections.Counter
for p in sorted(glob.glob(root + "*/*.gpkg")):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    t = c.execute("select table_name from gpkg_contents").fetchone()[0]
    gt = c.execute("select geometry_type_name from gpkg_geometry_columns where table_name=?", (t,)).fetchone()
    print("\n=====", t, "geometry:", gt[0])
    q = lambda col: C(r[0] for r in c.execute(f'select {col} from "{t}"'))
    for col in ("namespace", "type", "measure", "beginMeasureTime", "endMeasureTime", "validFrom", "validTo", "beginLifespanVersion", "endLifespanVersion"):
        v = q(col)
        print(f"  {col}: distinct {len(v)}", dict(sorted(v.items(), key=lambda kv: str(kv[0]))[:14]))
    loc = q("location")
    print("  location: distinct", len(loc), "| top:", [(k[:40], n) for k, n in loc.most_common(4)])
    # extent from gpkg_contents
    print("  extent:", c.execute("select min_x,min_y,max_x,max_y from gpkg_contents").fetchone())
