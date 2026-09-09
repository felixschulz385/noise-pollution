# 00 — Overview

This project follows the structural conventions of
[research-project-template](https://github.com/felixschulz385/research-project-template).
Read that repo's `docs/` for the full rationale behind each decision; this log
records what *this* project chose where the template leaves a per-project call,
and any deliberate deviations.

## Current state (2026-09-09)

The template has been applied at the **"scaffolding + CLI package"** level:

- Repository is now under git.
- `.gitignore`, `pyproject.toml` (build-only), `environment.yml` (conda as the
  dependency source of truth), `.env` (`PYTHONPATH=.`) added.
- `src/cli.py` split into the `src/cli/` package with the
  `main.py` / `common.py` / `<domain>/{commands,handlers}.py` layout; entry
  point is `python -m src.cli`.
- Internal imports moved from `data.…` to `src.data.…`; `src/` is now a package.
- Exploratory notebooks moved `src/notebooks/` → `src/experiments/`.
- `output/{figures,tables,presentations,analysis}/` created;
  `output/analysis/` is gitignored.
- Opt-in git hooks under `.githooks/`; a tests CI workflow under
  `.github/workflows/`.

## Not yet done (remaining template delta)

- **Data-source pipeline architecture** (template `docs/02`): the four domains
  (`timetable`, `stations`, `network`, `noise_barriers`) are still
  function-modules, not `DataSource` subclasses with `STEPS` / `REQUIRES`, a
  registry, `layout.py`, and a plan/execute split.
- **CLI command shape**: currently `data <domain> <verb>`; the template's shape
  is `data <verb> --source <name>`, which depends on the source registry above.
- **Unified config** (template `docs/03`): no `orchestration/configs/*.yaml`
  yet; settings live as argparse defaults.
- **Verification package** (template `docs/11`): no `data summary` / `data
  verify`.
- **Tests** (template `docs/05`): none yet.
- **Per-source docs** (template `docs/06`): `docs/data/<source>/README.md`
  pages not written.

## Per-project decisions still open

- **License.** Decided (2026-09-09): dual-licensed by content type — MIT for
  source code (`LICENSE`), CC BY 4.0 for written research materials
  (`output/documents/LICENSE`). Third-party input data under `data/` is not
  covered by either. Revisit if co-authors are added or if a funder (e.g.
  SNSF) or University of Basel policy imposes different terms.
- **Published output site.** None planned; `output/webpage/` not scaffolded.

## Document map

- `00-overview.md` — this file.
- `NN-<topic>.md` — one per nontrivial architectural decision, added as they
  are made.
