#!/bin/bash
# Return a shared Workspace to its baseline between e2e runs.
# usage: reset.sh RUN_ROOT          (baselines recorded by `reset.sh --baseline RUN_ROOT`)
# Removes: processes started from a run directory, user-installed Python packages, new ~/.local/bin
# entries, and new top-level entries in the project root (the parent of RUN_ROOT). Local only: files
# already uploaded to the Project stay in the Project.
set -u
B=/tmp/e2e/baseline-local-bin.txt
R=/tmp/e2e/baseline-project-root.txt
if [ "${1:-}" = "--baseline" ]; then
  ls -1 "$HOME/.local/bin" > "$B" 2>/dev/null
  ls -1A "$(dirname "$2")" > "$R" 2>/dev/null
  exit 0
fi
RUN_ROOT=$1
ROOT=$(dirname "$RUN_ROOT")
# processes left behind by earlier runs (servers started from a run directory)
for p in $(pgrep -u "$(id -u)"); do
  c=$(readlink "/proc/$p/cwd" 2>/dev/null) || continue
  case "$c" in "$RUN_ROOT"/*) kill "$p" 2>/dev/null;; esac
done
# user-installed Python packages and their entry points
rm -rf "$HOME"/.local/lib/python3*/site-packages
if [ -f "$B" ]; then
  for f in "$HOME"/.local/bin/*; do grep -qxF "$(basename "$f")" "$B" || rm -f "$f"; done
fi
if [ -f "$R" ]; then
  for f in "$ROOT"/* "$ROOT"/.[!.]*; do
    [ -e "$f" ] || continue
    grep -qxF "$(basename "$f")" "$R" || rm -rf "$f"
  done
fi
echo reset-ok
