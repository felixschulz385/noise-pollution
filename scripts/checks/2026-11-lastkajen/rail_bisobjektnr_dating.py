# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, numpy as np, pandas as pd
base = ROOT + "data/sweden/noise_barriers/raw/"
c = sqlite3.connect(f"file:{base}highway_noise_barriers.gpkg?mode=ro", uri=True)   # RAIL (names swapped)
df = pd.read_sql('select ELEMENT_ID, Byggar, Bisobjektnr, Inkopplingsdatum, EXTENT_LENGTH from BIS_DK_O_10006_Bullerskydd', c)
df["dated"] = df.Byggar != 0
d = df[df.dated]
print("dated", len(d), "undated", (~df.dated).sum())
print("Spearman (tie-averaged):", round(d.Bisobjektnr.rank().corr(d.Byggar.rank()), 3))
print("Bisobjektnr range dated:", d.Bisobjektnr.min(), d.Bisobjektnr.max(), "| undated:", df[~df.dated].Bisobjektnr.min(), df[~df.dated].Bisobjektnr.max())
# per-object table: one row per Bisobjektnr (dated objects), year = mode
obj = d.groupby("Bisobjektnr").Byggar.agg(lambda s: s.mode().iloc[0]).sort_index()
print("dated objects", len(obj), " distinct Bisobjektnr overall", df.Bisobjektnr.nunique())
# leave-one-object-out: predict year by the mean of nearest dated neighbours below and above in Bisobjektnr
ids = obj.index.values; ys = obj.values
errs = []
for i in range(1, len(ids) - 1):
    lo, hi = ys[i - 1], ys[i + 1]
    errs.append((lo, hi, ys[i]))
errs = np.array(errs)
inside = ((errs[:, 2] >= np.minimum(errs[:, 0], errs[:, 1])) & (errs[:, 2] <= np.maximum(errs[:, 0], errs[:, 1]))).mean()
width = np.abs(errs[:, 1] - errs[:, 0])
mid = (errs[:, 0] + errs[:, 1]) / 2
print(f"leave-one-out: true year inside [lower neighbour, upper neighbour]: {inside:.0%}; median bracket width {np.median(width):.0f} yrs; share of brackets <=2 yrs: {(width<=2).mean():.0%}")
print(f"  |midpoint - true| <=1: {(np.abs(mid-errs[:,2])<=1).mean():.0%}, <=2: {(np.abs(mid-errs[:,2])<=2).mean():.0%}")
# undated objects: bracket
und = df[~df.dated]
res = []
for oid in und.Bisobjektnr.unique():
    below = obj[obj.index < oid]; above = obj[obj.index > oid]
    lo = below.iloc[-1] if len(below) else np.nan; hi = above.iloc[0] if len(above) else np.nan
    res.append((oid, lo, hi))
r = pd.DataFrame(res, columns=["oid", "lo", "hi"])
r["width"] = (r.hi - r.lo).abs()
cnt = und.groupby("Bisobjektnr").size().rename("n")
r = r.join(cnt, on="oid")
print("undated objects", len(r), "records", int(r.n.sum()))
print(" records whose neighbours bracket within <=2 years:", int(r[r.width <= 2].n.sum()), " <=5:", int(r[r.width <= 5].n.sum()), " no upper or lower neighbour:", int(r[r.lo.isna() | r.hi.isna()].n.sum()))
print(" lower-neighbour year distribution for undated (records):", r.groupby("lo").n.sum().to_dict())
# among the undated with '<20190405'
u2 = und[und.Inkopplingsdatum.astype(str).str.startswith("<")]
print(" undated with '<20190405':", len(u2), " Bisobjektnr median undated vs dated:", int(und.Bisobjektnr.median()), int(d.Bisobjektnr.median()))
print(" year by Bisobjektnr decile (dated):")
d2 = d.assign(q=pd.qcut(d.Bisobjektnr, 10, labels=False))
print(d2.groupby("q").Byggar.agg(["min", "median", "max"]).astype(int).T.to_string())
