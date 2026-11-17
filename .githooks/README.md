# Repo-managed git hooks

Enable once per clone (`core.hooksPath` is local config and is not cloned):

```bash
./.githooks/install.sh        # = git config core.hooksPath .githooks
```

`pre-commit` runs three checks, all standard library only (Python 3.11+):

| Check | Blocks | Configure |
|---|---|---|
| `check-notebook-outputs.py` | cell outputs in staged notebooks that are not whitelisted (`notebooks/*` keep theirs), and in any notebook whose code reads restricted data | `notebook-output-whitelist.txt`, `restricted-patterns.txt` |
| `check-restricted.py` | staged files under `restricted/`, data files, and figures named after restricted data | `restricted-patterns.txt`, `restricted-allowlist.txt` |
| `scripts/docs.py check` | invalid doc metadata, broken links, stale derived docs, out-of-date generated tables (`docs/conventions.md`) | `docs/docs.toml` |

- Only staged content is inspected by the first two; the docs check reads the working tree.
- Fix generated tables with `python scripts/docs.py index`, then `git add` again.
- Bypass once, deliberately: `git commit --no-verify`.
