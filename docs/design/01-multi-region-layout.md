# 01 — Multi-region layout

**Status:** decided 2026-09-09; layout implemented 2026-09-10. Sources still
carry their pre-existing function-module shape (the `DataSource` /
per-region-registry conversion is a later step — see
[`00-overview.md`](00-overview.md)). See [`00-overview.md`](00-overview.md) for
how this sits against the rest of the template delta.

## The problem

The project studies traffic-noise pollution across more than one geographical
region (Sweden first, Florida next, more possible). Two people work on it, one
region each. Across regions:

- **Shared:** the pipeline framework (source base class, registry, path
  construction, plan/execute contract, verification), geospatial utilities,
  I/O conventions, and the CLI plumbing. This code is still evolving.
- **Completely separate:** every concrete data source — its on-disk format, its
  getter, its preprocessing — the analysis-ready assembly, and all analysis.
  There are no shared source *implementations*, only shared *machinery*.

We need a structure where a shared-code change is one reviewed change that both
regions pick up at once, while region work never collides.

## The decision

### One repository, with a region layer above the source registry

Keep everything in this repo. Add `region` as the outermost organizing
dimension, one level above the template's per-source registry seam
(template `docs/02`). Each region is a self-contained world: its own sources,
preprocessing, assembly, config, analysis, tests, and docs. `core/` holds
framework and utilities only — no concrete sources.

```
src/
├── core/                     # region-agnostic; the only code both regions import
│   ├── cli/                  # build_parser, shared arg helpers, region dispatch
│   ├── pipeline/
│   │   ├── base.py           # DataSource ABC, PipelineStep enum, StepTarget
│   │   ├── registry.py       # SourceRegistry as a class — one instance per region
│   │   └── layout.py         # path builder, parameterized by region + data root
│   ├── geo/                  # CRS handling, geobox, shared plotting
│   ├── io/                   # parquet / geoparquet read-write conventions
│   └── verification/         # `data summary` / `data verify` framework, region-parameterized
├── regions/
│   ├── sweden/
│   │   ├── __init__.py       # builds this region's SourceRegistry; lists its source modules
│   │   ├── sources/          # timetable.py, stations.py, network.py, noise_barriers.py
│   │   │                     #   each subclasses core.pipeline.base.DataSource
│   │   ├── analysis/         # Sweden-only analysis pipeline
│   │   └── config.py         # typed config for this region (or a thin yaml loader)
│   └── florida/
│       ├── __init__.py
│       ├── sources/          # schools.py, noise_barriers.py — own formats/getters, unrelated files
│       └── analysis/
└── cli/
    └── __main__.py           # `python -m src.cli` → core.cli.main
```

`tests/` mirrors this 1:1: `tests/core/…` and `tests/regions/<region>/…`.

### The core / region boundary

A module belongs in `core/` only if it has **no knowledge of any specific
region or source** — it is parameterized by them, never names them. Everything
that knows a column name, an API endpoint, a file format, or a study design
lives under `regions/<region>/`.

A source type that recurs across regions (e.g. `noise_barriers` in both Sweden
and Florida) is simply two unrelated files under the two regions. If shared
preprocessing genuinely emerges later, lift a *helper* into `core/geo/` or
`core/io/` — do not introduce a shared base source class per type, and do not
pre-abstract before the second implementation exists.

### CLI shape

Region is the first positional argument:

```
python -m src.cli <region> <domain> <verb> [flags]

python -m src.cli sweden  data fetch --source timetable
python -m src.cli florida data fetch --source schools
python -m src.cli sweden  analysis run ...
```

`src.core.cli.main.build_parser()` iterates a registered-regions list; each
region contributes its subparser tree via a `register(regions)` function
(`src/regions/<region>/cli.py`) — eventually built from that region's own
`SourceRegistry`. This reuses the `register(subparsers)` pattern from the
earlier "scaffolding + CLI package" work (see [`00-overview.md`](00-overview.md)),
moved up one level so `data` / `analysis` become per-region subtrees.

Error handling, exit codes, and Slurm/`--chain` flags stay exactly as the
template describes (template `docs/01`); they are region-agnostic and live in
`core/cli/`.

### Registry is a class, one instance per region

The template's `registry.py` describes a module-global registry. Here
`SourceRegistry` is a class. Each region's `__init__.py` instantiates one and
registers only its own source modules into it. This keeps Sweden sources out of
Florida's `data summary`, and lets the two registries evolve independently.

### On-disk data, config, docs

| Concern | Shape |
|---|---|
| Pipeline data | `data/<region>/raw/<source>/…`, `data/<region>/processed/<source>/…`, `data/<region>/assembled/…` — built only through `core/pipeline/layout.py`, which takes `region` as a parameter. All of `data/` stays gitignored. |
| Config | `orchestration/configs/<region>.yaml`, one per region. `--config` defaults to the file matching the region argument. Slurm job keys become `<region>.<source>.<step>`. |
| Docs | `docs/data/<region>/README.md` index + `docs/data/<region>/<source>/README.md` per source (template `docs/06`). |
| Notebooks | `src/experiments/<region>/…`, still flat and unmaintained within each region. |

### Ownership and collaboration

Each person owns, with no file overlap:

```
src/regions/<region>/   data/<region>/   orchestration/configs/<region>.yaml
tests/regions/<region>/  docs/data/<region>/
```

Shared changes land only in `src/core/` and are reviewed by both. Encode this
in `.github/CODEOWNERS`:

```
/src/core/            @felixschulz385 @collaborator
/src/regions/sweden/  @felixschulz385
/src/regions/florida/ @collaborator
```

Feature branches, PR into `main`. CI (template `docs/07`) runs every region's
test suite, so a `core/` change that breaks a region is caught before merge.

## Migration path

Executed 2026-09-10, from the post-"CLI package" state described in
[`00-overview.md`](00-overview.md):

1. Created `src/core/` (`core/cli/` from the old `src/cli/{common,main}.py`;
   `core/pipeline/layout.py` from `src/data/shared/paths.py`, now region-aware).
   `src/cli/` keeps only the `__main__` shim.
2. Added `src/regions/sweden/`; moved the four domains (`timetable`, `stations`,
   `network`, `noise_barriers`) to `src/regions/sweden/sources/`. Kept as
   function-modules; `DataSource` conversion deferred (see
   [`00-overview.md`](00-overview.md)). `src/data/shared/trafikverket.py` →
   `src/regions/sweden/sources/_trafikverket.py`; a `_layout.py` binds the
   region name so source modules don't repeat it.
3. Added the `region` positional to the CLI (`sweden` / `florida`); the `data`
   subtree moved under `src/regions/sweden/cli.py`'s `register()`.
4. `mv data/{network,stations,timetable,noise_barriers} → data/sweden/`
   (`data/` is gitignored, so plain `mv`). `data/florida/` already fit.
5. Scaffolded `src/regions/florida/` (`sources/`, `analysis/`, stub `cli.py`).
6. `orchestration/configs/noise_pollution.yaml` → `sweden.yaml`; added
   `florida.yaml`.

Also: notebooks → `src/experiments/<region>/`; `docs/data/` → per-region index;
`.github/CODEOWNERS` added; tests split into `tests/core/` + `tests/regions/`.

## Rejected alternatives

**Separate `core` package + one repo per region.** Publish `core` as an
installable package with a stable plugin API (entry points); each region a
standalone repo depending on it. Rejected: with two people and a `core` that is
still churning, every cross-cutting change becomes a coordinated multi-repo
release with version bumps. The isolation it buys (independent CI, independent
history) is not worth that overhead at this stage. Revisit only if a region
becomes a deliverable that must ship and version on its own — extract it then.

**Region as a flat prefix on source names** (`sweden_timetable`,
`florida_schools`) inside one shared `sources/` tree, with a `--region` filter.
Rejected: nothing enforces separation, the two registries and their configs
tangle, and "completely separate analyses" has nowhere clean to live.

**Branch or worktree per region.** Rejected outright: shared code is expected to
change often, and every such change would be a cross-branch merge. Branches are
for in-progress work, not for a permanent parallel-track split.

**Nest regions under `src/data/regions/…`.** Rejected as too deep and
mis-framed: regions own analysis too, not just data, so they belong directly
under `src/`, peer to `core/`.

## Related

- [`00-overview.md`](00-overview.md) — template-delta roadmap; this doc wraps
  its "data-source pipeline architecture" and "CLI command shape" items in a
  region layer.
- Template `docs/02` (source registry), `docs/03` (config), `docs/08`
  (skeleton) — the conventions this layout extends.
