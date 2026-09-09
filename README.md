# Noise pollution

Research project on rail-traffic noise pollution in Sweden. Assembles rail
network geometry, station locations, timetable / train-announcement records,
and noise-barrier data from Trafikverket into an analysis-ready dataset.

## Quick start

```bash
conda env create -f environment.yml
conda activate noise-pollution
pip install -e .
./.githooks/install.sh          # opt-in git hooks (notebook-output check)
```

Example commands:

```bash
python -m src.cli data stations fetch
python -m src.cli data stations preprocess
python -m src.cli data network preprocess
```

## Layout

| Path | What |
|---|---|
| `src/cli/` | CLI package — entry point is `python -m src.cli` |
| `src/data/` | Per-domain data pipeline (`fetch` / `preprocess` / `assemble`) |
| `src/experiments/` | Exploratory notebooks — unmaintained, not covered by tests |
| `orchestration/` | Configuration files and HPC/Slurm scripts |
| `data/` | Raw + processed pipeline data (gitignored; regenerate via the pipeline) |
| `output/` | Deliverables — figures, documents, tables, presentations |
| `docs/` | Design decision log + per-source reference docs |

See [`docs/design/00-overview.md`](docs/design/00-overview.md) for architecture
and the structural conventions this repo follows
([research-project-template](https://github.com/felixschulz385/research-project-template)).

## Secrets

Trafikverket API credentials live under `setup/secrets/` (gitignored). See
[`setup/secrets/`](setup/secrets/) for the expected file names.

## License

Two licenses, by content type:

- **Source code** (the `src/` tree, configuration, pipeline scripts) — MIT.
  See [`LICENSE`](LICENSE).
- **Written research materials** (literature review, text, figures, tables under
  `output/documents/`) — Creative Commons Attribution 4.0 International
  (CC BY 4.0). See [`output/documents/LICENSE`](output/documents/LICENSE).

Bulk input data under `data/` is third-party (Trafikverket) and is not covered
by either license; it is subject to the data provider's own terms.
