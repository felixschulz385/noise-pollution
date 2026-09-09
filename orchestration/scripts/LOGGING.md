# Orchestration script logging

Conventions for how scripts in this directory handle and redirect logs.

_No orchestration scripts exist yet._ When one is added, record here where it
writes stdout/stderr (e.g. `/log/<task>-<date>.log`), whether it tees to the
console, and how it behaves under Slurm (`sbatch` output file conventions).
