# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, collections, re, statistics
base = ROOT + "data/sweden/noise_barriers/raw/"
def load(p):
    c = sqlite3.connect(f"file:{base}{p}?mode=ro", uri=True)
    l = c.execute("select table_name from gpkg_contents where data_type='features'").fetchone()[0]
    cur = c.execute(f'select * from "{l}"')
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
road = load("railway_noise_barriers.gpkg"); rail = load("highway_noise_barriers.gpkg")
C = collections.Counter
ur = [r for r in road if r["Byggar"] == 1900]
print("road unknown:", len(ur))
print(" VALID_FROM year 2006:", sum(str(r["VALID_FROM"])[:4] == "2006" for r in ur), "| ==20060101:", sum(r["VALID_FROM"] == 20060101 for r in ur), "| <=2006:", sum(r["VALID_FROM"] <= 20061231 for r in ur))
print(" road all with VALID_FROM year 2006:", sum(str(r["VALID_FROM"])[:4] == "2006" for r in road))
print(" unknown AND Hojd 0 AND year 2006:", sum(str(r["VALID_FROM"])[:4] == "2006" and not r["Hojd"] for r in ur))
print(" 2006 batch records (VALID_FROM year 2006):", sum(str(r["VALID_FROM"])[:4] == "2006" for r in road), " with Byggar known:", sum(str(r["VALID_FROM"])[:4] == "2006" and r["Byggar"] != 1900 for r in road), " with Hojd:", sum(str(r["VALID_FROM"])[:4] == "2006" and bool(r["Hojd"]) for r in road))

print("\nrail: SIDE vs Sida_h_v_b")
m = {"h": "Höger", "v": "Vänster", "b": "Vänster och höger"}
both = [r for r in rail if r["Sida_h_v_b"] in m]
agree = sum(m[r["Sida_h_v_b"]] == r["SIDE"] for r in both)
print(" records with Sida_h_v_b:", len(both), "of", len(rail), "| equal to SIDE:", agree, f"({agree/len(both):.1%})")
print(" cross-tab:", C((r["Sida_h_v_b"], r["SIDE"]) for r in rail).most_common(8))

print("\nrail Inkopplingsdatum vs Byggar (records with both a real date and a known year)")
real = [r for r in rail if re.match(r"^\d{8}$", str(r["Inkopplingsdatum"]))]
both = [r for r in real if r["Byggar"] != 0]
diff = [int(str(r["Inkopplingsdatum"])[:4]) - r["Byggar"] for r in both]
print(" real-date records:", len(real), "| with Byggar known:", len(both))
print(" date year - Byggar:", sorted(C(max(min(d, 5), -5) for d in diff).items()), "(clipped +-5)")
print(" same year:", sum(d == 0 for d in diff), " date later by 1:", sum(d == 1 for d in diff), " later by >=2:", sum(d >= 2 for d in diff), " earlier:", sum(d < 0 for d in diff))
lt = [r for r in rail if str(r["Inkopplingsdatum"]).startswith("<")]
print(" '<20190405' records:", len(lt), " with Byggar known:", sum(r["Byggar"] != 0 for r in lt), " Byggar range of those:", min(r["Byggar"] for r in lt if r["Byggar"]), max(r["Byggar"] for r in lt if r["Byggar"]))
print(" Byggar >=2019 among '<' records (should be impossible if the date means connection):", sum(r["Byggar"] >= 2019 for r in lt))
print(" Byggar<2019 among real-date records:", sum(0 < r["Byggar"] < 2019 for r in real))
print(" VALID_FROM of the rail file:", sorted(C(str(r["VALID_FROM"])[:4] for r in rail).items()))

print("\n-- could anything date undated walls? sibling fill")
# rail: same Bisobjektnr with a dated sibling
by = collections.defaultdict(list)
for r in rail: by[r["Bisobjektnr"]].append(r)
und = [r for r in rail if r["Byggar"] == 0]
fill = [r for r in und if any(s["Byggar"] != 0 for s in by[r["Bisobjektnr"]])]
print(" rail undated:", len(und), " with a dated record sharing Bisobjektnr:", len(fill))
yrs_consistent = 0; multi = 0
for k, g in by.items():
    ys = {r["Byggar"] for r in g if r["Byggar"] != 0}
    if len(ys) >= 1 and len(g) > 1:
        multi += 1; yrs_consistent += (len(ys) == 1)
print(" Bisobjektnr groups with >1 record and >=1 dated:", multi, " of which all dated records share one year:", yrs_consistent)
# road: same ELEMENT_ID siblings
byr = collections.defaultdict(list)
for r in road: byr[r["ELEMENT_ID"]].append(r)
undr = [r for r in road if r["Byggar"] == 1900]
print(" road undated:", len(undr), " with a dated record on the same ELEMENT_ID:", sum(any(s["Byggar"] != 1900 for s in byr[r["ELEMENT_ID"]]) for r in undr))
# rail Typ / drawing: does Typritningsnr or Besiktningsklass relate to year?
print(" rail undated by Besiktningsklass:", C((r["Besiktningsklass"] or "").lower() for r in und).most_common(5))
print(" rail dated by Besiktningsklass:", C((r["Besiktningsklass"] or "").lower() for r in rail if r["Byggar"] != 0).most_common(5))
# Bisobjektnr vs year correlation among dated
pairs = [(r["Bisobjektnr"], r["Byggar"]) for r in rail if r["Byggar"] != 0]
def rank(v):
    s = sorted(range(len(v)), key=lambda i: v[i]); rk = [0]*len(v)
    for i, j in enumerate(s): rk[j] = i
    return rk
a = rank([p[0] for p in pairs]); b = rank([p[1] for p in pairs]); n = len(a)
ma, mb = statistics.mean(a), statistics.mean(b)
rho = sum((x-ma)*(y-mb) for x, y in zip(a, b)) / (sum((x-ma)**2 for x in a) * sum((y-mb)**2 for y in b)) ** 0.5
print(" Spearman(Bisobjektnr, Byggar) among dated rail (ties not averaged):", round(rho, 2), "n", n)
# Typritningsnr: contains a 4-digit year?
tz = [r["Typritningsnr"] for r in rail if r["Typritningsnr"] and r["Typritningsnr"] != "-"]
print(" Typritningsnr non-empty:", len(tz), " sample patterns:", C(re.sub(r"\d", "9", t)[:14] for t in tz).most_common(5))
print(" undated rail with a Typritningsnr:", sum(bool(r["Typritningsnr"]) and r["Typritningsnr"] != "-" for r in und))
print(" Typ=? or Okänt material:", sum(r["Typ"] == "?" for r in rail), sum(r["Materialtyp"] in ("Okänt", None) for r in road))
print(" road Pa_bro Okänt among undated:", sum(r["Pa_bro"] == "Okänt" for r in ur), "of", len(ur), "| among dated:", sum(r["Pa_bro"] == "Okänt" for r in road if r["Byggar"] != 1900), "of", len(road) - len(ur))
print(" road Agare Okänt undated/dated:", sum(r["Agare"] == "Okänt" for r in ur), sum(r["Agare"] == "Okänt" for r in road if r["Byggar"] != 1900))
print(" road Materialtyp known undated/dated:", sum(r["Materialtyp"] not in ("Okänt", None) for r in ur), sum(r["Materialtyp"] not in ("Okänt", None) for r in road if r["Byggar"] != 1900))
