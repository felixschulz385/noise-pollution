# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, collections, glob

base = ROOT + "data/sweden/noise_barriers/raw/"
files = {
    "2015": glob.glob(base + "road_ref_2015-01-01/*.gpkg")[0],
    "2019": glob.glob(base + "road_ref_2019-01-01/*.gpkg")[0],
    "2022": glob.glob(base + "road_ref_2022-01-01/*.gpkg")[0],
    "2026": base + "railway_noise_barriers.gpkg",  # holds the ROAD layer (names swapped)
}

def load(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    l = con.execute("select table_name from gpkg_contents where data_type='features'").fetchone()[0]
    cur = con.execute(f'select * from "{l}"')
    cols = [d[0] for d in cur.description]
    return l, [dict(zip(cols, r)) for r in cur.fetchall()]

D = {}
for k, p in files.items():
    l, rows = load(p)
    assert l == "VIS_DK_O_63_Bullerskydd_vag", (k, l)
    D[k] = rows

def key(r): return (r["ELEMENT_ID"], r["START_MEASURE"], r["END_MEASURE"], r["SIDE"])
def length(rows): return sum((r["EXTENT_LENGTH"] or 0) for r in rows) / 1000

print("snapshot  records  elements  km    closed(VALID_TO<9999)  Byggar=1900  Hojd=0  VALID_FROM_max")
for k, rows in D.items():
    n = len(rows)
    closed = sum(1 for r in rows if r["VALID_TO"] != 99991231)
    b = sum(1 for r in rows if r["Byggar"] == 1900)
    h = sum(1 for r in rows if not r["Hojd"])
    print(f"{k}      {n:5d}   {len({r['ELEMENT_ID'] for r in rows}):5d}   {length(rows):6.1f}   {closed:4d}   {b:5d} ({b/n:.0%})  {h:5d} ({h/n:.0%})  {max(r['VALID_FROM'] for r in rows)}")

order = ["2015", "2019", "2022", "2026"]
print("\nElement-level transitions (ELEMENT_ID present in snapshot A, absent in B):")
for a, b in zip(order, order[1:]):
    ea = {r["ELEMENT_ID"] for r in D[a]}; eb = {r["ELEMENT_ID"] for r in D[b]}
    print(f"  {a}->{b}: dropped {len(ea-eb)}, added {len(eb-ea)}, kept {len(ea&eb)}")
e15 = {r["ELEMENT_ID"] for r in D["2015"]}; e26 = {r["ELEMENT_ID"] for r in D["2026"]}
print(f"  2015->2026 directly: dropped {len(e15-e26)}, added {len(e26-e15)}")
allsnap = set().union(*({r['ELEMENT_ID'] for r in D[k]} for k in D))
print("  ELEMENT_IDs seen in any snapshot:", len(allsnap), " absent from the 2026 file:", len(allsnap - e26))

print("\nSegment-key (element, start, end, side) dropped/added:")
for a, b in zip(order, order[1:]):
    ka = {key(r) for r in D[a]}; kb = {key(r) for r in D[b]}
    print(f"  {a}->{b}: dropped {len(ka-kb)}, added {len(kb-ka)}")

print("\nClosed records (VALID_TO<9999) by VALID_TO year, per snapshot:")
for k in order:
    c = collections.Counter(str(r['VALID_TO'])[:4] for r in D[k] if r['VALID_TO'] != 99991231)
    print(f"  {k}: {dict(sorted(c.items()))}")

print("\nVALID_FROM year distribution in the 2026 file for records NOT in 2022 snapshot (new since 2022-01-01):")
k22 = {key(r) for r in D["2022"]}
new22 = [r for r in D["2026"] if key(r) not in k22]
print("  ", len(new22), dict(sorted(collections.Counter(str(r['VALID_FROM'])[:4] for r in new22).items())))

print("\nByggar of known year (not 1900) by snapshot: count, min, max")
for k in order:
    ys = [r["Byggar"] for r in D[k] if r["Byggar"] and r["Byggar"] != 1900]
    print(f"  {k}: n={len(ys)}, {min(ys)}-{max(ys)}")

# Does a closed record in a snapshot carry a different Byggar/Hojd than its successor? (edit vs removal)
print("\nElements closed in 2022 snapshot (VALID_TO<9999, ends 2022+): successor present in 2026 file?")
c22 = [r for r in D["2022"] if r["VALID_TO"] != 99991231]
print("  closed records:", len(c22), " element still in 2026:", sum(1 for r in c22 if r["ELEMENT_ID"] in e26))

# Heights: share with Hojd known in 2022 vs 2026 among shared segment keys
shared = [k for k in {key(r) for r in D["2022"]} & {key(r) for r in D["2026"]}]
m22 = {key(r): r for r in D["2022"]}; m26 = {key(r): r for r in D["2026"]}
ch_h = sum(1 for k in shared if (m22[k]["Hojd"] or 0) != (m26[k]["Hojd"] or 0))
ch_b = sum(1 for k in shared if m22[k]["Byggar"] != m26[k]["Byggar"])
print(f"  shared segments 2022 vs 2026: {len(shared)}; Hojd changed {ch_h}; Byggar changed {ch_b}")
m15 = {key(r): r for r in D["2015"]}
sh = [k for k in set(m15) & set(m26)]
print(f"  shared segments 2015 vs 2026: {len(sh)}; Hojd changed {sum(1 for k in sh if (m15[k]['Hojd'] or 0)!=(m26[k]['Hojd'] or 0))}; Byggar changed {sum(1 for k in sh if m15[k]['Byggar']!=m26[k]['Byggar'])}")
