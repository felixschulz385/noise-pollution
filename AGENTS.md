# AGENTS.md

Working notes for coding agents in this repository (`CLAUDE.md` imports this file). Keep it to
rules and pointers: status lives in the docs (`docs/conventions.md`), and the State table below
is generated from the line charters. Update this file in the same commit as any change to the
layout or rules below.

## State

Generated from the line charters (`docs/lines/<slug>/README.md`) by `python scripts/docs.py
index`; edit a charter, not this table. Each line's next step is in its charter.

<!-- docs:begin lines -->
| Line of work | State | Branch | Updated | Summary |
|---|---|---|---|---|
| [Florida: noise walls and school test scores](docs/lines/florida-schools/) | active | line/florida-schools | 2026-11-18 | Do FDOT noise walls raise test scores at the schools they protect? So far a clean null (CS ATT -0.051, RI p=0.456); post-wall cohorts at affluent-intake schools score lower |
| [Sweden: growing up behind a noise barrier](docs/lines/sweden-residents/) | active | line/sweden-residents | 2026-11-19 | Does growing up behind a noise barrier change children's school achievement and later outcomes? A cohort-exposure design on the 100 m grid and Swedish registers; design written, no estimate yet |
| [Sweden: noise barriers and school achievement](docs/lines/sweden-schools/) | active | line/sweden-schools | 2026-11-18 | Do Swedish road and rail noise barriers raise grade-9 achievement at the schools they protect? So far no effect beyond chance (RI p=0.186); a parental-education gradient survives |
<!-- docs:end -->

- **Start of a session:** read the charter of the line you work on, then its `results.md` (the
  record; `sweden-residents` has none yet, as no estimate exists).
- **New work** starts as a new line: `python scripts/docs.py new line <slug>`, a branch
  `line/<slug>` from `master`, and a pre-spec (`new prespec <slug> <name>`) before anything
  runs.
- **`sweden-residents` is the exception:** its record is the LaTeX pre-spec
  `docs/lines/sweden-residents/prespec-cohort-exposure.tex` (coauthors edit it on Overleaf;
  estimation runs on the register data outside this repository). Its `.md` is a metadata stub:
  keep its `state`/`updated` in step with the `.tex`. The slides follow the `.tex`.
- **Open questions:** under `## Open questions` in the doc they belong to (answered ones move to
  `## Resolved questions`); [`docs/open-questions.md`](docs/open-questions.md) collects them.
- **How this project departs from the template**, and the open delta:
  [`docs/design/2026-11-template-port.md`](docs/design/2026-11-template-port.md).

## Hard rules

- **Pre-specification:** every analysis step has rules (◇) written before it loads an outcome;
  change them only through the pre-spec's change log, never after seeing a result the change
  could be fitted to. The steps run before 2026-11-17 had none; say so when citing them.
- Commit only when asked. On `master`, branch first for anything that is not documentation.
- Never commit data: everything under the data root is git-ignored; secrets live in
  `setup/secrets/` (git-ignored).

## Environment

- **Python:** the `noise_pollution` conda environment, installed from `conda-lock.yml`
  (osx-64 and linux-64; `environment.yml` is the input, regenerate the lock when it changes),
  then `pip install -e .`. Notebooks also run without the install: they put `src/` on
  `sys.path`.
- **Data root** is `data/` in the repository (`data_root` in
  `orchestration/configs/noise_pollution.yaml`; override per machine in
  `noise_pollution.local.yaml`). Layout: `<data_root>/<region>/<source>/{raw,processed,assembled}/`.
- **Stata:** the analysis notebooks estimate with Stata (`csdid`, `drdid`, `reghdfe`) through
  StataCorp's `pystata`, not a Python package; conda does not provide it.
- **Credentials:** Trafikverket API key and Lastkajen login in `setup/secrets/` (or
  `TRAFIKVERKET_API_KEY`); the Census API key in `CENSUS_API_KEY`. Some sources are manual
  downloads (NVDB via Lastkajen, FLDOE assessments); their pages say how.

## Data pipeline

- Two regions, each its own pipeline: `src/noise_pollution/regions/{sweden,florida}/` with
  `sources/<source>/{fetch,preprocess,assemble,shared}.py`, `cli.py` (argparse) and
  `handlers.py`. Shared machinery in `src/noise_pollution/core/` (path layout, barrier
  geometry); nothing there names a region.
- CLI: `noise_pollution <region> data <source> <stage>` (e.g.
  `noise_pollution sweden data panel assemble`); `python -m noise_pollution` is the same.
- Paths come from the region's `sources/_layout.py` (`domain_dirs`) and each source's
  `shared.py`; no source builds a data path inline. Cross-source inputs are read by path, never
  by importing another source's internals.
- A new source: a package under `regions/<region>/sources/`, its commands in the region's
  `cli.py` and `handlers.py`, tests under `tests/regions/<region>/`, and a page
  `docs/data/<region>/<source>/README.md` with front matter.
- **Raw-only domains** (data downloaded and inspected, no module yet): `sweden/road_projects`
  and `sweden/inspire_noise`. Each has a source page and no code reads it; a step that uses
  one needs a package as above and a pre-spec step first.
- **Data checks** live in `scripts/checks/<yyyy-mm>-<topic>/` (a README says what each script
  checks): read-only, standard library or the project environment, aggregates only. They are
  not pre-specified analysis steps and feed no estimate.

## Analysis

- **Specification:** one module per line of work, `src/noise_pollution/analysis/<slug>*.py`
  (`sweden_schools.py`, `florida_schools.py`): outcome, tier, sample, covariates, baselines,
  sites, clusters. Shared pieces: `did.py` (Python CS ATT and RI, Stata start and programs) and
  `spec.py` (display options, palette). Notebooks import them and keep only the estimation
  (`%%stata` cells), descriptives and prose; tests on synthetic panels in `tests/analysis/`.
- **Notebooks:** `notebooks/<slug>/`, numbered across the project in run order; they find the
  project root by searching upward for `pyproject.toml` and keep their outputs (runs of record).
  Execute with `jupyter nbconvert --to notebook --execute --inplace <nb>`.

## Docs conventions

The rules are in [`docs/conventions.md`](docs/conventions.md): docs by line of work, front
matter on every doc, generated tables (`python scripts/docs.py index`), `depends_on` for derived
docs, and `python scripts/docs.py check` in the pre-commit hook and CI. Bump a doc's `updated`
when a change is of substance. Design records are dated (`YYYY-MM-<topic>.md`) and never
renamed; the two numbered ones (`00-`, `01-`) keep their names.
