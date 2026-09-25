#!/bin/bash
# Starts the barrier-audit app with Anaconda's Python. Double-click me.
cd "$(dirname "$0")" || exit 1

PY=""
for p in \
    "$HOME/anaconda3/bin/python" \
    "$HOME/miniconda3/bin/python" \
    "$HOME/miniforge3/bin/python" \
    "/opt/anaconda3/bin/python" \
    "/opt/miniconda3/bin/python" \
    "/opt/homebrew/anaconda3/bin/python" \
    "/usr/local/anaconda3/bin/python"; do
    if [ -x "$p" ]; then PY="$p"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then PY="$(command -v python3)"; fi

if [ -z "$PY" ]; then
    echo "Could not find Anaconda's Python."
    echo "Open Terminal and type:"
    echo "    cd \"$(pwd)\""
    echo "    python -m barrier_audit"
    read -r -p "Press Enter to close."
    exit 1
fi

echo "Using $PY"
"$PY" -m barrier_audit "$@"
