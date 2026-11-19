# Prompt 1: what Lastkajen offers (Claude in Chrome)

Paste everything below the line into Claude in Chrome. Save its reply as
`prep/01-lastkajen-catalogue-report.md` next to this file; prompt 2 reads it.

---

## Context

I am preparing a call with Trafikverket (noise and vibration coordination) on 25 November 2026.
Before asking them for data, I want to be sure we are not asking for something Lastkajen
already offers. Lastkajen is Trafikverket's download portal: https://lastkajen.trafikverket.se.
I am logged in with my own account in this browser.

What we already have, ordered from Lastkajen as GeoPackage, whole of Sweden, EPSG:3006:

| Order | Ordered | Data product | Layer in the file |
|---|---|---|---|
| Sound_Barriers_-_Road_GeoPackage_447607 | 2026-07-06 | Bullerskydd - väg | `VIS_DK_O_63_Bullerskydd_vag` (2,172 records) |
| Sound_Barriers_-_Rail_GeoPackage_451138 | 2026-07-07 | Bullerskydd | `BIS_DK_O_10006_Bullerskydd` (1,829 records) |

We also hold several NVDB orders: the road network and Trafik (ÅDT). For Trafik we placed
orders with different reference dates (*Betraktelsedatum*) to rebuild history back to about 1998.

Fields in our barrier files:
- Road: `ELEMENT_ID, VALID_FROM, VALID_TO, START_MEASURE, END_MEASURE, EXTENT_LENGTH, SIDE,
  Absorbent, Agare, Byggar, Grundlaggningstyp, Hojd, Materialtyp, Pa_bro, Skotselansvarig,
  Skotselanvisning`
- Rail: `ELEMENT_ID, VALID_FROM, VALID_TO, START_MEASURE, END_MEASURE, EXTENT_LENGTH, SIDE,
  Absorbent, Agare, Avstand_fr_sparmitt_m, Besiktningsklass, Bisobjektnr, Bisobjekttypnr,
  Byggar, Grundlaggningstyp, Hojd_over_rok_m, Inkopplingsdatum, Kmtal, Kmtalti,
  Not_om_grundlaggning, Sida_h_v_b, Typ, Typritningsnr, Underhallsansvarig,
  Underhallsinstruktion`

What is missing for our research:
1. Construction year (`Byggar`) for about half of the road and a quarter of the rail records.
   Most undated road records have `VALID_FROM` 2006-01-01, when the register started.
2. The road barriers are drawn on the road's centreline, so we do not know which side they stand
   on or how far from the road. Height is missing for 62% of road records.
3. Every record has `VALID_TO` 9999-12-31: we see only barriers that stand today.
4. Facade insulation records (*bullerisolering, fasadåtgärder, fönsteråtgärder*) by property.
5. Start or announcement dates of the road and rail projects that came with the barriers.
6. Train counts before the barriers were built.
7. Calculated noise levels (*bullerberäkning, bullerkartläggning*) before and after a measure.

## Task

Find out what Lastkajen offers on each of the seven points, and describe our two products
precisely. Read only.

**A. Our two products.** For *Bullerskydd - väg* and *Bullerskydd*:
- The product's ID or post number on Lastkajen. We believe they are 630 and 991; say which is
  which, or correct us.
- The product description and its documentation (*dataproduktspecifikation*, *beskrivning*,
  attribute lists; PDFs linked from the product page are fine to open). For each field above,
  especially `Byggar`, `Hojd`, `SIDE`, `Sida_h_v_b`, `Avstand_fr_sparmitt_m`,
  `Inkopplingsdatum`, `VALID_FROM` and `VALID_TO`: what does it mean? Is `Byggar` the year of
  completion? Can a rebuild overwrite it?
- Whether an order can use an earlier *Betraktelsedatum*, how far back, and whether that returns
  barriers that have since been removed. Is there any option for history (*historik*), changes
  or removed objects?
- How the road product is related to NVDB (is it an NVDB layer?), and the rail product to BIS.
  Do other deliveries of the same objects carry more attributes (for example an NVDB export with
  the barrier's side or offset)?

**B. Other products.** Browse or search the whole catalogue, in Swedish and English, for anything
that touches the seven points. Search terms to try: *buller, bullerskydd, bullerskärm,
bullervall, bullerisolering, fasad, fönster, åtgärd, bullerkartläggning, bullerberäkning,
ljudnivå, vägprojekt, investering, objekt, entreprenad, byggstart, vägarbete, ÅDT, trafikflöde,
tågtrafik, tågräkning, bandata, BIS, NVDB, historik*. For each product that could help, record:
name, ID, what it holds, format, coverage (area, years), the key attributes, and whether history
can be ordered.

**C. Help pages.** Read Lastkajen's help or FAQ on reference dates, history and data products,
and note anything relevant to the points above.

## Rules

- Read only. Do not place orders, add anything to a cart or basket, accept terms, or change
  account settings. Opening product pages and documentation is fine.
- Do not type credentials. If the session is logged out, stop and tell me.
- If a page or document is only in Swedish, read it in Swedish and report in English.
- Say "not found" where you looked and found nothing, and say where you looked. Mark anything you
  infer rather than read.

## Reply

A Markdown report:
1. **Answers**, one per point 1–7 above: available on Lastkajen (where), not available, or
   unclear. One or two sentences each, with the product name and URL.
2. **Our two products**: ID, description, the field definitions you found, reference-date and
   history options, and the URLs of their documentation.
3. **Other relevant products**: a table with name, ID, what it holds, coverage, history
   (yes/no/unclear), URL.
4. **What we could order ourselves** instead of asking Trafikverket, and what remains a question
   for them.
5. **Where you looked** and anything you could not open.
