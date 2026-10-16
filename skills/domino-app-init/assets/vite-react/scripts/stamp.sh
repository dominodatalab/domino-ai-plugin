#!/usr/bin/env bash
# Print one hash of every committed input of the Vite build. build-dist.sh stores it with each build;
# app.sh recomputes it at start and serves only a build made from these sources. Add any other build
# input to the list. .env files are left out: they are not committed, so the App could not hash them.
set -euo pipefail
cd "$(dirname "$0")/.."
inputs=(index.html package.json package-lock.json src)
for optional in public vite.config.js vite.config.ts vite.config.mjs tsconfig.json tsconfig.app.json tsconfig.node.json; do
  [ -e "$optional" ] && inputs+=("$optional")
done
find "${inputs[@]}" -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
