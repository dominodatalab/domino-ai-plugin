#!/usr/bin/env bash
# Domino App entry point. Runs the binary scripts/build-dist.sh produced; never compiles.
set -euo pipefail
cd "$(dirname "$0")"
bin=$(sed -n 's/^name *= *"\(.*\)"/\1/p' Cargo.toml | head -n1)
dist=${DIST_DIR:-/mnt/artifacts/dist}
[ -f "$dist/$bin" ] || dist=dist

if [ ! -f "$dist/$bin" ] || [ ! -f "$dist/$bin.stamp" ]; then
  echo "app.sh: no prebuilt binary in /mnt/artifacts/dist or ./dist; run scripts/build-dist.sh and save it" >&2
  exit 1
fi
if [ "$(head -n1 "$dist/$bin.stamp")" != "$(bash scripts/stamp.sh)" ]; then
  echo "app.sh: $dist/$bin was built from different sources; run scripts/build-dist.sh, save, and publish again" >&2
  exit 1
fi
# Hardware tiers can run on different node types; a binary only runs on the CPU architecture it was built for.
built_arch=$(sed -n 's/^arch=//p' "$dist/$bin.stamp")
if [ -n "$built_arch" ] && [ "$built_arch" != "$(uname -m)" ]; then
  echo "app.sh: $dist/$bin was built for $built_arch but this node is $(uname -m); rebuild in a Job on the App's hardware tier" >&2
  exit 1
fi

# Copy out of the Project mount: stored files can lose the executable bit.
run=$(mktemp -d)/"$bin"
cp "$dist/$bin" "$run"
chmod +x "$run"
export PORT=8888
exec "$run"
