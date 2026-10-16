#!/usr/bin/env bash
# Domino App entry point. Runs a binary scripts/build-dist.sh produced; never compiles.
# It picks the newest build, in /mnt/artifacts/dist/<name> (or $DIST_DIR) and then ./dist, whose stamp
# matches these sources and this node's CPU architecture.
set -euo pipefail
cd "$(dirname "$0")"
bin=$(sed -n 's/^name *= *"\(.*\)"/\1/p' Cargo.toml | head -n1)
want=$(bash scripts/stamp.sh)
arch=$(uname -m)
build=
found=
other_arch=
roots=("${DIST_DIR:-/mnt/artifacts/dist/$bin}")
[ "${roots[0]}" = dist ] || roots+=(dist)

for root in "${roots[@]}"; do
  for stamp in $(printf '%s\n' "$root"/*.stamp | sort -rV); do
    [ -f "$stamp" ] && [ -f "${stamp%.stamp}/$bin" ] || continue
    label=${stamp##*/}
    found="$found ${label%.stamp}"
    [ "$(head -n1 "$stamp")" = "$want" ] || continue
    built_arch=$(sed -n 's/^arch=//p' "$stamp")
    if [ -n "$built_arch" ] && [ "$built_arch" != "$arch" ]; then
      other_arch=$built_arch
      continue
    fi
    build=${stamp%.stamp}
    break 2
  done
done

if [ -z "$build" ]; then
  if [ -n "$other_arch" ]; then
    # Hardware tiers can run on different node types; a binary only runs on the architecture it was built for.
    echo "app.sh: the build for these sources is for $other_arch but this node is $arch; rebuild in a Job on the App's hardware tier" >&2
  else
    echo "app.sh: no build matches these sources (found:${found:- none}); run scripts/build-dist.sh, save, and publish again" >&2
  fi
  exit 1
fi

# Copy out of the Project mount: stored files can lose the executable bit.
run=$(mktemp -d)/"$bin"
cp "$build/$bin" "$run"
chmod +x "$run"
export APP_BUILD=${build##*/}
echo "app.sh: starting build $APP_BUILD from ${build%/*}"
export PORT=8888
exec "$run"
