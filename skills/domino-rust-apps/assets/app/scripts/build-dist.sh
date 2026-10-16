#!/usr/bin/env bash
# Build the shipping binary once and store it as a dated build next to the previous one:
#   <root>/2026.10.15/<name>  and  <root>/2026.10.15.stamp   (.2, .3, ... for later builds that day)
# Roots:
#   Git-based Project (default): /mnt/artifacts/dist/<name>, saved to Domino storage and pinned by each App
#                                version; one folder per App, so Apps in one Project never prune each other
#   DIST_DIR=dist:               inside the repository (DFS Projects, or a binary committed to Git)
# app.sh runs the newest build whose stamp matches the App's sources, so after a code revert the
# previous build starts without a rebuild. KEEP_BUILDS (default 2) builds of different sources are kept.
# BUILD_LABEL overrides the label (CI).
set -euo pipefail
cd "$(dirname "$0")/.."
bin=$(sed -n 's/^name *= *"\(.*\)"/\1/p' Cargo.toml | head -n1)
root=${DIST_DIR:-/mnt/artifacts/dist/$bin}
keep=${KEEP_BUILDS:-2}

if [ -n "$(git status --porcelain -- Cargo.toml Cargo.lock rust-toolchain.toml src 2>/dev/null)" ]; then
  echo "warning: uncommitted source changes; commit them so the App's code matches this binary" >&2
fi

cargo build --locked --profile dist
# CARGO_BUILD_TARGET (set for target-cpu or PGO builds) moves the output under target/<triple>/.
out="target/${CARGO_BUILD_TARGET:+$CARGO_BUILD_TARGET/}dist/$bin"

mkdir -p "$root"
# Label: today's UTC date; later builds that day add .2, .3, ... past the highest one in use, so a
# label is never reused and version order (sort -V) is build order. Folders count as well as stamps:
# Domino storage keeps the folder of a deleted build as an empty placeholder.
day=$(date -u +%Y.%m.%d)
last=0
for entry in "$root/$day" "$root/$day".*; do
  [ -e "$entry" ] || continue
  n=${entry#"$root/$day"}
  n=${n%.stamp}
  n=${n#.}
  case $n in *[!0-9]*) continue ;; esac
  if [ "${n:-1}" -gt "$last" ]; then last=${n:-1}; fi
done
label=$day
[ "$last" -eq 0 ] || label="$day.$((last + 1))"
label=${BUILD_LABEL:-$label}
hash=$(bash scripts/stamp.sh)
arch=$(uname -m)

# Write the build under a temporary name; the stamp, written last, marks it complete.
rm -rf "$root/.$label.tmp"
mkdir "$root/.$label.tmp"
cp "$out" "$root/.$label.tmp/$bin"
mv "$root/.$label.tmp" "$root/$label"
{
  echo "$hash"
  echo "build=$label"
  echo "commit=$(git rev-parse HEAD 2>/dev/null || echo none)"
  rustc --version
  echo "RUSTFLAGS=${RUSTFLAGS:-}"
  echo "arch=$arch"
} > "$root/$label.stamp.tmp"
mv "$root/$label.stamp.tmp" "$root/$label.stamp"

# A rebuild of the same sources replaces the older copy, so the kept builds are different versions.
for stamp in "$root"/*.stamp; do
  old=${stamp%.stamp}
  [ "$old" = "$root/$label" ] && continue
  if [ "$(head -n1 "$stamp")" = "$hash" ] && [ "$(sed -n 's/^arch=//p' "$stamp")" = "$arch" ]; then
    rm -rf "$old" "$stamp"
  fi
done
# Keep the newest $keep builds.
for stamp in $(printf '%s\n' "$root"/*.stamp | sort -rV | tail -n +"$((keep + 1))"); do
  rm -rf "${stamp%.stamp}" "$stamp"
done

echo "built $root/$label/$bin ($(du -h "$root/$label/$bin" | cut -f1)); kept: $(printf '%s\n' "$root"/*.stamp | sed 's#.*/##; s#\.stamp$##' | sort -rV | tr '\n' ' ')"
