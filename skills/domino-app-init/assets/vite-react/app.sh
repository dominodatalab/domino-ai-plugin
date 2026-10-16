#!/usr/bin/env bash
# Domino App entry point for a Vite + React app. Serves a build that scripts/build-dist.sh made, with
# server.js (Node built-ins only); never installs or builds, so it starts in seconds and needs no npm.
# It picks the newest build, in /mnt/artifacts/dist/<package name> (or $DIST_DIR) and then ./dist, whose stamp
# matches these sources.
set -euo pipefail
cd "$(dirname "$0")"
want=$(bash scripts/stamp.sh)
build=
found=
name=$(node -p "require('./package.json').name" | tr -c 'A-Za-z0-9._\n-' '-')
roots=("${DIST_DIR:-/mnt/artifacts/dist/$name}")
[ "${roots[0]}" = dist ] || roots+=(dist)

for root in "${roots[@]}"; do
  for stamp in $(printf '%s\n' "$root"/*.stamp | sort -rV); do
    [ -f "$stamp" ] && [ -f "${stamp%.stamp}/index.html" ] || continue
    label=${stamp##*/}
    found="$found ${label%.stamp}"
    if [ "$(head -n1 "$stamp")" = "$want" ]; then
      build=${stamp%.stamp}
      break 2
    fi
  done
done

if [ -z "$build" ]; then
  echo "app.sh: no build matches these sources (found:${found:- none}); run scripts/build-dist.sh, save, and publish again" >&2
  exit 1
fi

export BUILD_DIR=$build APP_BUILD=${build##*/}
echo "app.sh: serving build $APP_BUILD from ${build%/*}"
exec node server.js
