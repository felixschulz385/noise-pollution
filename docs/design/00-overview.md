# 00 — Overview

This project follows the structural conventions of
[research-project-template](https://github.com/felixschulz385/research-project-template).
Read that repo's `docs/` for the full rationale behind each decision; this log
records what *this* project chose where the template leaves a per-project call,
and any deliberate deviations.

## Current state (updated 2026-09-10)

The template has been applied at the **"scaffolding + CLI package"** level, then
restructured into the **multi-region layout**
([`01-multi-region-layout.md`](01-multi-region-layout.md)):

- Repository is under git.
- `.gitignore`, `pyproject.toml` (build-only), `environment.yml` (conda as the
  dependency source of truth), `.env` (`PYTHONPATH=.`) added.
- `src/` split into `src/core/` (region-agnostic: CLI framework in
  `core/cli/`, path layout in `core/pipeline/layout.py`) and
  `src/regions/<region>/` (`sweden/` populated, `florida/` skeleton).
- Entry point `python -m src.cli`; command shape `<region> data <domain> <verb>`.
- The four Sweden domains (`timetable`, `stations`, `network`,
  `noise_barriers`) live under `src/regions/sweden/sources/` as
  function-modules; Sweden's CLI subtree is `src/regions/sweden/cli.py` +
  `handlers.py`.
- Pipeline data is region-scoped: `data/<region>/<domain>/{raw,processed,assembled}/`.
- `orchestration/configs/{sweden,florida}.yaml` (placeholders).
- `output/{figures,tables,presentations,analysis}/` created;
  `output/analysis/` is gitignored.
- Opt-in git hooks under `.githooks/`; a tests CI workflow under
  `.github/workflows/`; `.github/CODEOWNERS` encodes the region boundaries.
- Tests mirror the tree: `tests/core/…`, `tests/regions/<region>/…`.

## Not yet done (remaining template delta)

All of the below now happens *within a region* (`src/regions/<region>/`), with
shared machinery in `src/core/`.

- **Data-source pipeline architecture** (template `docs/02`): the Sweden domains
  are still function-modules, not `DataSource` subclasses with `STEPS` /
  `REQUIRES`, a per-region registry, and a plan/execute split. `core/pipeline/`
  will gain `base.py` + `registry.py` (a `SourceRegistry` class, one instance
  per region — see [`01-multi-region-layout.md`](01-multi-region-layout.md)).
- **CLI command shape**: currently `<region> data <domain> <verb>`; the target
  is `<region> data <verb> --source <name>`, which depends on the per-region
  source registry above.
- **Unified config** (template `docs/03`): `orchestration/configs/<region>.yaml`
  exist as placeholders only; settings still live as argparse defaults.
- **Verification package** (template `docs/11`): no `data summary` / `data
  verify`. Will live in `src/core/verification/`, region-parameterized.
- **Tests** (template `docs/05`): only CLI smoke tests so far
  (`tests/core/cli/`, `tests/regions/sweden/`); no coverage of the source
  modules themselves.
- **Per-source docs** (template `docs/06`): `docs/data/<region>/README.md`
  index exists for Sweden; per-source `docs/data/<region>/<source>/README.md`
  pages not written.

## Per-project decisions still open

- **License.** Decided (2026-09-09): dual-licensed by content type — MIT for
  source code (`LICENSE`), CC BY 4.0 for written research materials
  (`output/documents/LICENSE`). Third-party input data under `data/` is not
  covered by either. Revisit if co-authors are added or if a funder (e.g.
  SNSF) or University of Basel policy imposes different terms.
- **Published output site.** None planned; `output/webpage/` not scaffolded.

## Document map

Read in order:

1. `00-overview.md` — this file: template-delta roadmap and per-project decisions.
2. [`01-multi-region-layout.md`](01-multi-region-layout.md) — one repo, a
   `region` layer above the source registry; `src/core/` vs
   `src/regions/<region>/`; CLI shape `<region> data <verb>`.

Further `NN-<topic>.md` entries added one per nontrivial architectural decision.
