# Notebooks

One folder per line of work, named by the line's slug (`docs/lines/<slug>/`). Numbers run across
folders in the order the work was done. Every notebook finds the project root by searching
upward for `pyproject.toml`, so it runs from its own folder. Notebooks keep their outputs (they
are the runs of record) unless they read restricted data (`.githooks/`).

| Folder | Line of work | Notebooks | Record |
|---|---|---|---|
| [`sweden-schools/`](sweden-schools/) | [`sweden-schools`](../docs/lines/sweden-schools/README.md) | 01–02 rail timetable and network, 12–16 barriers, schools, lineage, assessments, traffic, 17 shared methodology (both regions), 19 descriptives, 20 analysis (Stata) | [`results.md`](../docs/lines/sweden-schools/results.md) (from the Summary of [`20_analysis.ipynb`](sweden-schools/20_analysis.ipynb)) |
| [`florida-schools/`](florida-schools/) | [`florida-schools`](../docs/lines/florida-schools/README.md) | 03–06, 08–10 barriers, assessments, roads, schools, road projects, shocks, traffic; 07 descriptives; 11 analysis (Stata) | [`results.md`](../docs/lines/florida-schools/results.md) (from the Summary of [`11_analysis.ipynb`](florida-schools/11_analysis.ipynb)) |
| [`sweden-residents/`](sweden-residents/) | [`sweden-residents`](../docs/lines/sweden-residents/README.md) | 18 the 100 m treatment grid | — (design stage) |

The outputs of every notebook here are from runs before the November 2026 move; only their
imports and root-finding changed with it.
