---
type: index
state: current
updated: 2026-11-17
summary: "Index of the data sources: one index page per region, then one page per source"
---

# Data sources

Sources are organised by region ([`../design/01-multi-region-layout.md`](../design/01-multi-region-layout.md)).
Each region has an index page with every source's steps, prerequisites and module, and each
source has its own page (what the dataset is, where each stage's output lands, its columns and
caveats). Facts only a real run can confirm are marked **needs live data**. The table of every
page, with its summary, is generated in [`../README.md`](../README.md#data-sources).

- [`sweden/README.md`](sweden/README.md): Trafikverket barriers, roads, rail and traffic;
  Skolverket schools and results; SCB neighbourhoods; the barrier audit and the 100 m grid.
- [`florida/README.md`](florida/README.md): FDOT walls, roads, traffic and road projects;
  FLDOE and NCES schools and assessments; staff, neighbourhood and disaster covariates.

Pipeline data lands under `<data_root>/<region>/<source>/{raw,processed,assembled}/`, with
`data_root` set in `orchestration/configs/noise_pollution.yaml` (default `data/`).
