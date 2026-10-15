#!/usr/bin/env bash
# Build the shipping binary once and store it, with its source stamp, where the App runs it.
#   Git-based Project (default): /mnt/artifacts/dist, saved to Domino storage and pinned by each App version
#   DIST_DIR=dist:               inside the repository, for Projects that commit the binary to Git
set -euo pipefail
cd "$(dirname "$0")/.."
bin=$(sed -n 's/^name *= *"\(.*\)"/\1/p' Cargo.toml | head -n1)
dist=${DIST_DIR:-/mnt/artifacts/dist}

if [ -n "$(git status --porcelain -- Cargo.toml Cargo.lock rust-toolchain.toml src 2>/dev/null)" ]; then
  echo "warning: uncommitted source changes; commit them so the App's code matches this binary" >&2
fi

cargo build --locked --profile dist
# CARGO_BUILD_TARGET (set for target-cpu or PGO builds) moves the output under target/<triple>/.
out="target/${CARGO_BUILD_TARGET:+$CARGO_BUILD_TARGET/}dist/$bin"
mkdir -p "$dist"
cp "$out" "$dist/$bin.tmp"
mv "$dist/$bin.tmp" "$dist/$bin"
{
  bash scripts/stamp.sh
  rustc --version
  git rev-parse HEAD 2>/dev/null || echo "no-git"
  echo "RUSTFLAGS=${RUSTFLAGS:-}"
} > "$dist/$bin.stamp"
echo "built $dist/$bin ($(du -h "$dist/$bin" | cut -f1)); stamp $(head -n1 "$dist/$bin.stamp")"
