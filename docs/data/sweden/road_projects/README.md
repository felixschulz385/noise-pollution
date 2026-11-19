---
type: source
state: current
updated: 2026-11-19
summary: "Sweden road_projects: NVDB Vägombyggnad and Vägnybyggnad (completion years and project numbers of road rebuilds and new roads), downloaded from Lastkajen, raw only"
---

# `road_projects`

**What it is.** Two NVDB data products from Trafikverket's Lastkajen: **Vägombyggnad** (ID 96, the year
a road stretch was rebuilt, with the kind of rebuild and a "substantial rebuild" noise flag) and
**Vägnybyggnad** (ID 97, the year a road in its present alignment was completed). Both carry a project
object number and name and have history (Historik = Ja). Sweden, EPSG:3006, on the same NVDB road
elements as `noise_barriers`' road layer. Why they matter and what they could date:
[`../lastkajen-unused-products.md`](../lastkajen-unused-products.md) §1 and §2.

**Status.** Raw only: **no `fetch` or `preprocess` module yet**, no code reads it, and no estimate uses
it. Downloaded and inspected 2026-11-19; the checks are in
[`scripts/checks/2026-11-lastkajen/`](../../../../scripts/checks/2026-11-lastkajen/README.md).
**Requires:** a Lastkajen login (manual order, as for `traffic` and `road_network`).

## Where it lands

- raw: `data/sweden/road_projects/raw/order_121412/` (git-ignored): the zip, the receipt
  `Leveransinformation_41789.txt` and `Road_Projects_(Rebuild_and_New_Build)_41789.gpkg` (181 MB, two
  layers). Order "Road Projects (Rebuild and New Build)", 121412, both products, Sweden, GeoPackage,
  EPSG:3006, reference date empty (order day 2026-11-19).
- processed, assembled: none.

## Columns

| Layer (rows) | Column | Meaning |
|---|---|---|
| both | `ELEMENT_ID`, `START_MEASURE`, `END_MEASURE`, `EXTENT_LENGTH` | the NVDB road element and the stretch on it (measure 0 to 1), as in the barrier file; join key to a barrier |
| both | `VALID_FROM`, `VALID_TO` | version dates; `VALID_FROM` is 2023 for most records (bulk load), `VALID_TO` 9999-12-31 |
| both | `Ursprung` | type of source of the year ("taken from an existing road database 2022", "relation or construction document", unknown, "local knowledge") |
| both | `Objekt_nr`, `Objektnamn`, `ID_i_fysiskt_arkiv` | project number, name and archive reference |
| `VIS_DK_O_96_Vagombyggnad` (7,457) | `Ombyggnadsar` | year the rebuild was completed (9999 = unknown) |
| | `Vagkroppsatgard`, `Breddning`, `Ombyggnad_till_motesfri` | kind of rebuild (road body, widening, to 1+1 or 2+1) |
| | `Vasentlig_ombyggnad` | a stretch where physical changes since 1997 substantially raise noise or vibration |
| `VIS_DK_O_97_Vagnybyggnad` (83,475) | `Nybyggnadsar` | year the road structure in its present alignment was completed (9999 = unknown) |

## Caveats

- **Thin where it matters for noise.** `Vasentlig_ombyggnad` is `Okänt` for 95% of rebuilds (Ja 21,
  Nej 335); `Objekt_nr` is filled for 19% of rebuilds and 22% of new builds, `Objektnamn` for 12% and
  4%, the archive reference for none. `Nybyggnadsar` is 9999 for 46%.
- **No start or announcement dates**, only completion years.
- **The year is not the wall's year.** Of 307 dated road barriers on a rebuilt stretch, `Byggår` equals
  the rebuild year in 217 of the single-year cases; on new roads it equals the road's year in 493 of 902
  and is six or more years later in 289.
- **History is shallow** (`VALID_FROM` 2021 to 2026); an earlier reference date was not ordered
  (inferred: it returns little before 2021).
- **Overlap with barriers:** 501 of 2,172 road barriers (23%) lie on a rebuild record, 2,152 (99%) on
  a new-build record.
