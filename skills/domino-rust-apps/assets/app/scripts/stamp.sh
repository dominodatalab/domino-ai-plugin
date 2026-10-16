#!/usr/bin/env bash
# Print one hash of every input that changes the binary. build-dist.sh stores it next to the
# binary; app.sh recomputes it at start and refuses to run a binary built from other sources.
set -euo pipefail
cd "$(dirname "$0")/.."
inputs=(Cargo.toml Cargo.lock rust-toolchain.toml src)
for optional in build.rs .cargo templates static migrations pgo; do
  [ -e "$optional" ] && inputs+=("$optional")
done
find "${inputs[@]}" -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
