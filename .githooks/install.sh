#!/usr/bin/env bash
# Point this repo's git at the tracked hooks in .githooks/.
# Opt-in: a fresh clone does not run this automatically.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
git -C "$repo_root" config core.hooksPath .githooks
chmod +x "$repo_root/.githooks/pre-commit" "$repo_root/.githooks/check-notebook-outputs.py"
echo "core.hooksPath set to .githooks"
