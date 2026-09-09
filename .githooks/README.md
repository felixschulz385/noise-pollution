# Git hooks

Opt-in. Run `./.githooks/install.sh` once per clone to point
`core.hooksPath` at this directory.

## `pre-commit` → `check-notebook-outputs.py`

Blocks a commit that stages a notebook under `src/experiments/` with cell
outputs or execution counts, to keep rendered images and output blobs out of
repository history.

- **Allow a notebook to keep outputs:** add its repo-relative path to
  `notebook-output-whitelist.txt`.
- **Bypass once:** `git commit --no-verify`.
- **Strip outputs:** `jupyter nbconvert --clear-output --inplace <notebook>`.
