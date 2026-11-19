# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, collections, re
base = ROOT + "data/sweden/noise_barriers/raw/"
def load(p):
    c = sqlite3.connect(f"file:{base}{p}?mode=ro", uri=True)
    l = c.execute("select table_name from gpkg_contents where data_type='features'").fetchone()[0]
    cur = c.execute(f'select * from "{l}"')
    cols = [d[0] for d in cur.description]
    return l, [dict(zip(cols, r)) for r in cur.fetchall()]
lr, road = load("railway_noise_barriers.gpkg")    # names swapped: this is ROAD
lt, rail = load("highway_noise_barriers.gpkg")    # this is RAIL
print("road layer", lr, len(road), "| rail layer", lt, len(rail))
C = collections.Counter
pct = lambda a, n: f"{a} ({a/n:.1%})"
n_r, n_t = len(road), len(rail)

print("\n-- claim 5: Byggar unknown (road 1900, rail 0?)")
print("road Byggar==1900", pct(sum(r["Byggar"] == 1900 for r in road), n_r), "null", sum(r["Byggar"] is None for r in road))
bt = C(r["Byggar"] for r in rail)
print("rail Byggar top", bt.most_common(3), "==0", pct(bt.get(0, 0), n_t), "null", bt.get(None, 0))
print("rail min/max non-zero", min(k for k in bt if k), max(k for k in bt if k))

print("\n-- claim 7: Hojd")
print("road Hojd==0 or null", pct(sum(not r["Hojd"] for r in road), n_r))
print("rail Hojd_over_rok_m == 999", pct(sum(r["Hojd_over_rok_m"] == 999 for r in rail), n_t), " ==0", pct(sum(r["Hojd_over_rok_m"] == 0 for r in rail), n_t))

print("\n-- claim 8: buckets (road / rail)")
def bucket(y, sent):
    if y is None or y == sent: return "unknown"
    if y < 1996: return "<1996"
    if y <= 2005: return "1996-2005"
    if y <= 2014: return "2006-2014"
    if y <= 2022: return "2015-2022"
    return "2023+"
br = C(bucket(r["Byggar"], 1900) for r in road); bt2 = C(bucket(r["Byggar"], 0) for r in rail)
for k in ("unknown", "<1996", "1996-2005", "2006-2014", "2015-2022", "2023+"):
    print(f"  {k:10s} road {br[k]:5d}  rail {bt2[k]:5d}")
print("  sums", sum(br.values()), sum(bt2.values()))

print("\n-- claim 9 / chart split of unknowns")
ur = [r for r in road if r["Byggar"] in (1900, None)]
print("road unknown", len(ur), "with VALID_FROM 20060101:", sum(r["VALID_FROM"] == 20060101 for r in ur), " share", f'{sum(r["VALID_FROM"]==20060101 for r in ur)/len(ur):.1%}')
print("road all VALID_FROM 20060101:", sum(r["VALID_FROM"] == 20060101 for r in road))
ut = [r for r in rail if r["Byggar"] in (0, None)]
ink = lambda r: str(r["Inkopplingsdatum"]) if r["Inkopplingsdatum"] is not None else ""
print("rail unknown", len(ut), "Inkopplingsdatum starting '<':", sum(ink(r).startswith("<") for r in ut), " distinct '<' values", C(ink(r) for r in rail if ink(r).startswith("<")).most_common(3))
print("rail all '<' :", sum(ink(r).startswith("<") for r in rail), " real dates:", sum(bool(re.match(r"^\d{8}$", ink(r))) for r in rail), " blank:", sum(ink(r) == "" for r in rail))
print("rail unknown Byggar with real date:", sum(bool(re.match(r"^\d{8}$", ink(r))) for r in ut))
yrs = [int(ink(r)[:4]) for r in rail if re.match(r"^\d{8}$", ink(r))]
print("rail real-date years:", sorted(C(yrs).items()))

print("\n-- claim 10: VALID_TO")
print("road VALID_TO", C(r["VALID_TO"] for r in road).most_common(2), "rail", C(r["VALID_TO"] for r in rail).most_common(2))

print("\n-- claim 6: side / distance")
print("road SIDE", C(r["SIDE"] for r in road).most_common())
print("rail SIDE", C(r["SIDE"] for r in rail).most_common())
print("rail Sida_h_v_b", C(r["Sida_h_v_b"] for r in rail).most_common())
dist = [r["Avstand_fr_sparmitt_m"] for r in rail]
print("rail Avstand: ==999", pct(sum(d == 999 for d in dist), n_t), " null", sum(d is None for d in dist), " real", pct(sum(d is not None and d != 999 for d in dist), n_t), " ==0", sum(d == 0 for d in dist))
real = sorted(d for d in dist if d is not None and d != 999)
print("rail Avstand real: min", real[0], "median", real[len(real)//2], "max", real[-1])

print("\n-- road Materialtyp / Pa_bro / others")
print("Materialtyp", C(r["Materialtyp"] for r in road).most_common())
print("Pa_bro", C(r["Pa_bro"] for r in road).most_common())
print("Absorbent", C(r["Absorbent"] for r in road).most_common(4), "Grundlaggning", C(r["Grundlaggningstyp"] for r in road).most_common(4))
print("Agare", C(r["Agare"] for r in road).most_common(4))
print("\n-- rail Typ / Besiktningsklass / ...")
print("Typ", C(r["Typ"] for r in rail).most_common())
print("Besiktningsklass", C(r["Besiktningsklass"] for r in rail).most_common())
print("Bisobjekttypnr", C(r["Bisobjekttypnr"] for r in rail).most_common(5))
print("Bisobjektnr distinct", len({r["Bisobjektnr"] for r in rail}), "null", sum(r["Bisobjektnr"] is None for r in rail))
tz = [r["Typritningsnr"] for r in rail]
print("Typritningsnr non-empty", pct(sum(bool(t) and t != "-" for t in tz), n_t), "distinct", len(set(tz)), "top", C(tz).most_common(5))
print("Kmtal sample types", C(type(r["Kmtal"]).__name__ for r in rail), [r["Kmtal"] for r in rail[:3]])
