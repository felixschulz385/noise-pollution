# Data check run 2026-11-19 for the Trafikverket call (read-only, aggregates only).
# See docs/data/sweden/lastkajen-unused-products.md and scripts/checks/2026-11-lastkajen/README.md.
import pathlib as _pl
ROOT = str(_pl.Path(__file__).resolve().parents[3]) + "/"
import sqlite3, collections, pandas as pd, numpy as np
D = ROOT + "data/sweden/"
P = D + "road_projects/raw/order_121412/Road_Projects_(Rebuild_and_New_Build)_41789.gpkg"
c = sqlite3.connect(f"file:{P}?mode=ro", uri=True)
om = pd.read_sql("select ELEMENT_ID,VALID_FROM,VALID_TO,START_MEASURE,END_MEASURE,EXTENT_LENGTH,Breddning,Ombyggnad_till_motesfri,Ombyggnadsar,Ursprung,Vagkroppsatgard,Vasentlig_ombyggnad,Objekt_nr,Objektnamn,ID_i_fysiskt_arkiv from VIS_DK_O_96_Vagombyggnad", c)
ny = pd.read_sql("select ELEMENT_ID,VALID_FROM,VALID_TO,START_MEASURE,END_MEASURE,EXTENT_LENGTH,Nybyggnadsar,Ursprung,Objekt_nr,Objektnamn,ID_i_fysiskt_arkiv from VIS_DK_O_97_Vagnybyggnad", c)
print("rebuild rows", len(om), "elements", om.ELEMENT_ID.nunique(), "| new-build rows", len(ny), "elements", ny.ELEMENT_ID.nunique())
for nm, d in (("rebuild", om), ("newbuild", ny)):
    print(f"\n-- {nm}: VALID_TO all 9999?", (d.VALID_TO == 99991231).mean().round(3), " VALID_FROM years:", dict(sorted(collections.Counter(str(v)[:4] for v in d.VALID_FROM).items())[:6]), "...")
    print("   total length km:", round(d.EXTENT_LENGTH.sum() / 1000))
    print("   Ursprung:", d.Ursprung.value_counts(dropna=False).head(6).to_dict())
    print("   Objekt_nr filled:", f"{(d.Objekt_nr.fillna('').str.strip()!='').mean():.0%}", " Objektnamn filled:", f"{(d.Objektnamn.fillna('').str.strip()!='').mean():.0%}", " archive id filled:", f"{(d.ID_i_fysiskt_arkiv.fillna('').str.strip()!='').mean():.0%}")
yr = om.Ombyggnadsar; print("\nOmbyggnadsar: null", int(yr.isna().sum()), " range", int(yr.min()), int(yr.max()), " by decade:", dict(sorted(collections.Counter((int(y)//10*10) for y in yr.dropna()).items())))
print("Vasentlig_ombyggnad:", om.Vasentlig_ombyggnad.value_counts(dropna=False).to_dict())
print("Vagkroppsatgard:", om.Vagkroppsatgard.value_counts(dropna=False).head(6).to_dict())
print("Breddning:", om.Breddning.value_counts(dropna=False).to_dict(), "| till mötesfri:", om.Ombyggnad_till_motesfri.value_counts(dropna=False).to_dict())
ny_y = ny.Nybyggnadsar
print("\nNybyggnadsar: 9999 (unknown)", int((ny_y == 9999).sum()), f"({(ny_y==9999).mean():.0%})", " null", int(ny_y.isna().sum()))
k = ny_y[(ny_y != 9999) & ny_y.notna()]
print("  known range", int(k.min()), int(k.max()), " by decade:", dict(sorted(collections.Counter((int(y)//10*10) for y in k).items())))
print("  known share >=1996:", f"{(k>=1996).mean():.0%}", " >=2000:", f"{(k>=2000).mean():.0%}")
print("Objektnamn examples count distinct:", om.Objektnamn.nunique(), ny.Objektnamn.nunique())
om.to_pickle("/tmp/om.pkl"); ny.to_pickle("/tmp/ny.pkl")
