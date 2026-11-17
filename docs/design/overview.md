---
type: design
state: current
updated: 2026-11-17
summary: "The system at a glance: two region pipelines, a shared core, three lines of work; later records are dated YYYY-MM-<topic>.md"
---

# Noise pollution: overview

## Decision

The architecture at a glance:

- **Data pipeline, by region.** `src/noise_pollution/regions/{sweden,florida}/` each hold their
  sources (`sources/<source>/{fetch,preprocess,assemble,shared}.py`) and their command-line
  subtree (`cli.py`, `handlers.py`): `noise_pollution <region> data <source> <stage>`. Each
  region's `panel assemble` joins outcomes, the school-barrier treatment and the covariate
  clusters into one event-study panel; Sweden's `grid` builds the 100 m treatment grid for the
  register design. Data lands under `<data_root>/<region>/<source>/{raw,processed,assembled}/`
  (`core/pipeline/layout.py`). See [`01-multi-region-layout.md`](01-multi-region-layout.md).
- **Shared core.** `src/noise_pollution/core/`: the path layout and the barrier geometry
  (linear referencing, the protected-area model) used by both regions.
- **Analysis.** The notebooks of each line ([`../../notebooks/`](../../notebooks/README.md))
  read the assembled panels and estimate with Stata (`csdid`, `reghdfe`) through `pystata`;
  `src/noise_pollution/analysis/spec.py` holds what they share.
- **Lines of work** ([`../lines/`](../lines/)): `sweden-schools`, `florida-schools`,
  `sweden-residents`.

## Reasoning

Florida and Sweden were built as independent pipelines with different agencies and formats but
the same design (a staggered event study of barrier construction on school achievement); the
region layer keeps them apart while the barrier geometry is shared.

## Rejected alternatives

See [`01-multi-region-layout.md`](01-multi-region-layout.md) (one repository per region) and
[`2026-11-template-port.md`](2026-11-template-port.md) (the full source rewrite at once).

## Consequences

The open delta to the template is listed in [`2026-11-template-port.md`](2026-11-template-port.md).
