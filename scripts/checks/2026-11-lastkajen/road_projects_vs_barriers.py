# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, pandas as pd, numpy as np
D = ROOT + "data/sweden/"
om = pd.read_pickle("/tmp/om.pkl"); ny = pd.read_pickle("/tmp/ny.pkl")
c = sqlite3.connect(f"file:{D}noise_barriers/raw/railway_noise_barriers.gpkg?mode=ro", uri=True)   # ROAD (names swapped)
b = pd.read_sql("select rowid as rid, ELEMENT_ID,VALID_FROM,START_MEASURE,END_MEASURE,EXTENT_LENGTH,Byggar,Hojd from VIS_DK_O_63_Bullerskydd_vag", c)
print("barriers", len(b), "| measure range barrier:", b.START_MEASURE.min(), b.END_MEASURE.max(), "| projects:", om.START_MEASURE.min(), om.END_MEASURE.max())
b["known"] = b.Byggar != 1900
b["batch06"] = b.VALID_FROM.astype(str).str[:4].eq("2006")

def overlap_join(b, p, ycol, unknown):
    m = b.merge(p[["ELEMENT_ID", "START_MEASURE", "END_MEASURE", ycol]], on="ELEMENT_ID", suffixes=("", "_p"))
    ov = np.minimum(m.END_MEASURE, m.END_MEASURE_p) - np.maximum(m.START_MEASURE, m.START_MEASURE_p)
    m = m[ov > 0].copy()
    m["year"] = m[ycol].where(m[ycol] != unknown)
    return m

for nm, p, ycol, unk in (("Vägombyggnad (rebuild)", om, "Ombyggnadsar", 9999), ("Vägnybyggnad (new build)", ny, "Nybyggnadsar", 9999)):
    m = overlap_join(b, p, ycol, unk)
    hit = m.rid.nunique()
    print(f"\n=== {nm}: barriers with an overlapping record: {hit} of {len(b)} ({hit/len(b):.0%}); overlapping record pairs {len(m)}")
    mk = m[m.year.notna()]
    print("  barriers with an overlapping record that has a known year:", mk.rid.nunique(), f"({mk.rid.nunique()/len(b):.0%})")
    # barrier-level: take the latest year <= ... just the min and max years per barrier
    g = mk.groupby("rid").agg(ymin=("year", "min"), ymax=("year", "max"), byg=("Byggar", "first"), known=("known", "first"), b06=("batch06", "first"))
    kn = g[g.known]
    if len(kn):
        d = kn.byg - kn.ymax    # wall year minus latest project year
        d2 = kn.byg - kn.ymin
        print(f"  DATED barriers with a project year: {len(kn)}")
        print("   |Byggar - closest project year| <=1:", f"{(np.minimum(abs(kn.byg-kn.ymin),abs(kn.byg-kn.ymax))<=1).mean():.0%}", " <=2:", f"{(np.minimum(abs(kn.byg-kn.ymin),abs(kn.byg-kn.ymax))<=2).mean():.0%}", " <=5:", f"{(np.minimum(abs(kn.byg-kn.ymin),abs(kn.byg-kn.ymax))<=5).mean():.0%}")
        print("   Byggar - project year (single-year barriers), counts clipped -3..6:", dict(sorted(pd.Series(np.clip((kn.byg - kn.ymin)[kn.ymin == kn.ymax], -3, 6)).value_counts().items())))
    un = g[~g.known]
    print(f"  UNDATED barriers with a project year: {len(un)} (of {int((~b.known).sum())} undated; {int(un.b06.sum())} in the 2006 batch)")
    if len(un):
        # lower bound on wall year = latest project year of an overlapping road record; compare to the 2006 'built by' bound
        lb = un.ymax
        print("   project year (max) distribution:", dict(sorted(pd.Series((lb // 10 * 10)).value_counts().items())))
        w = un[un.b06]
        if len(w):
            wd = 2006 - w.ymax
            print(f"   2006-batch undated with a project year: {len(w)}; project year <= 2006 gives a bracket [year, 2006]:")
            print("     bracket width <=3 yrs:", int((wd.between(0, 3)).sum()), " <=6:", int((wd.between(0, 6)).sum()), " project year after 2006 (inconsistent with 'built by 2006'):", int((wd < 0).sum()), " project year 1990s or earlier:", int((w.ymax < 2000).sum()))
    # barriers where the project says "built the same year" -> new info for the non-batch undated
print("\nundated barriers not in the 2006 batch:", int(((~b.known) & (~b.batch06)).sum()))
# Vasentlig_ombyggnad overlap
mv = overlap_join(b, om[om.Vasentlig_ombyggnad == "Ja"], "Ombyggnadsar", 9999)
print("barriers overlapping a 'Väsentlig ombyggnad = Ja' stretch:", mv.rid.nunique())
# project identity
mo = overlap_join(b, om[om.Objekt_nr.fillna("").str.strip() != ""], "Ombyggnadsar", 9999)
mn = overlap_join(b, ny[ny.Objekt_nr.fillna("").str.strip() != ""], "Nybyggnadsar", 9999)
print("barriers overlapping a record with an Objekt_nr: rebuild", mo.rid.nunique(), " new build", mn.rid.nunique(), " either", len(set(mo.rid) | set(mn.rid)))
