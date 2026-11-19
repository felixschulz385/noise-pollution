# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, sys, collections

def load(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    l = con.execute("select table_name from gpkg_contents where data_type='features'").fetchone()[0]
    cur = con.execute(f'select * from "{l}"')
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return l, rows

ln, new = load(sys.argv[1])
lo, old = load(sys.argv[2])
print("NEW", ln, len(new)); print("OLD", lo, len(old))

def cnt(rows, k): return collections.Counter(r[k] for r in rows)

for k in ("VALID_FROM", "VALID_TO"):
    for tag, rows in (("NEW", new), ("OLD", old)):
        c = cnt(rows, k)
        print(k, tag, "distinct", len(c), "min", min(c), "max", max(c), "top", c.most_common(4))

for tag, rows in (("NEW", new), ("OLD", old)):
    by = cnt(rows, "Byggar"); h = cnt(rows, "Hojd")
    n = len(rows)
    print(tag, "Byggar==1900:", by.get(1900, 0), f"({by.get(1900,0)/n:.0%})", "Byggar null:", by.get(None, 0),
          "| Hojd 0/null:", h.get(0, 0) + h.get(None, 0), f"({(h.get(0,0)+h.get(None,0))/n:.0%})",
          "| Byggar year range of known:", min(k for k in by if k and k != 1900), max(k for k in by if k and k != 1900))

# key: ELEMENT_ID + START/END
def key(r): return (r["ELEMENT_ID"], r["START_MEASURE"], r["END_MEASURE"], r["SIDE"])
kn = {key(r): r for r in new}; ko = {key(r): r for r in old}
print("keys new/old", len(kn), len(ko), "both", len(set(kn) & set(ko)), "only new", len(set(kn) - set(ko)), "only old", len(set(ko) - set(kn)))
en = {r["ELEMENT_ID"] for r in new}; eo = {r["ELEMENT_ID"] for r in old}
print("ELEMENT_ID new/old", len(en), len(eo), "both", len(en & eo), "only new", len(en - eo), "only old", len(eo - en))

closed = [r for r in new if r["VALID_TO"] != 99991231]
print("closed in NEW:", len(closed))
print("  VALID_TO years:", sorted(collections.Counter(str(r["VALID_TO"])[:4] for r in closed).items()))
print("  closed rows whose ELEMENT_ID is gone from July file:", sum(1 for r in closed if r["ELEMENT_ID"] not in eo))
print("  closed rows whose key still in July file:", sum(1 for r in closed if key(r) in ko))
print("  closed total length m:", sum((r["EXTENT_LENGTH"] or 0) for r in closed), "of", sum((r["EXTENT_LENGTH"] or 0) for r in new))

# first-appearance dates: OLD records with VALID_FROM <= 2014 and in OLD
old_pre = [r for r in old if r["VALID_FROM"] <= 20141231]
print("OLD records with VALID_FROM <= 2014-12-31:", len(old_pre))
print("OLD VALID_FROM year dist:", sorted(collections.Counter(str(r["VALID_FROM"])[:4] for r in old).items()))
print("NEW VALID_FROM year dist:", sorted(collections.Counter(str(r["VALID_FROM"])[:4] for r in new).items()))
print("OLD Byggar year dist (known):", sorted((k, v) for k, v in cnt(old, "Byggar").items() if k)[:12], "...")
print("Sample closed:", [(r["ELEMENT_ID"], r["VALID_FROM"], r["VALID_TO"], r["Byggar"], r["Hojd"], r["SIDE"]) for r in closed[:6]])
