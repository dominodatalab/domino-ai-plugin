#!/usr/bin/env bash
# Build the Vite app once and store it as a dated build next to the previous one:
#   <root>/2026.10.15/  and  <root>/2026.10.15.stamp   (.2, .3, ... for later builds that day)
# Roots:
#   Git-based Project (default): /mnt/artifacts/dist/<package name>, saved to Domino storage and pinned by each
#                                App version; one folder per App, so Apps in one Project never prune each other
#   DIST_DIR=dist:               inside the project (DFS Projects, or builds committed to Git by CI)
# app.sh serves the newest build whose stamp matches the App's sources, so after a code revert the
# previous build is served without a rebuild. KEEP_BUILDS (default 2) builds of different sources are
# kept. BUILD_LABEL overrides the label (CI). Needs Node 20.19+ and npm; the App itself needs only node.
set -euo pipefail
cd "$(dirname "$0")/.."
name=$(node -p "require('./package.json').name" | tr -c 'A-Za-z0-9._\n-' '-')
root=${DIST_DIR:-/mnt/artifacts/dist/$name}
keep=${KEEP_BUILDS:-2}

command -v npm >/dev/null || { echo "npm not found: build with Node 20.19 or later and npm (see the domino-apps REACT-VITE-GUIDE.md)" >&2; exit 1; }
if [ -n "$(git status --porcelain -- index.html package.json package-lock.json src public 2>/dev/null)" ]; then
  echo "warning: uncommitted source changes; commit them so the App's code matches this build" >&2
fi

npm ci
npm run build            # vite build into build/ (vite.config.js outDir); scratch output, never served

# Label: today's UTC date; later builds that day add .2, .3, ... past the highest one in use, so a
# label is never reused and version order (sort -V) is build order. Folders count as well as stamps:
# Domino storage keeps the folder of a deleted build as an empty placeholder.
mkdir -p "$root"
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

# Copy under a temporary name; the stamp, written last, marks the build complete.
rm -rf "$root/.$label.tmp"
cp -R build "$root/.$label.tmp"
mv "$root/.$label.tmp" "$root/$label"
{
  echo "$hash"
  echo "build=$label"
  echo "commit=$(git rev-parse HEAD 2>/dev/null || echo none)"
  echo "node=$(node --version)"
} > "$root/$label.stamp.tmp"
mv "$root/$label.stamp.tmp" "$root/$label.stamp"

# A rebuild of the same sources replaces the older copy, so the kept builds are different versions.
for stamp in "$root"/*.stamp; do
  [ "${stamp%.stamp}" = "$root/$label" ] && continue
  if [ "$(head -n1 "$stamp")" = "$hash" ]; then rm -rf "${stamp%.stamp}" "$stamp"; fi
done
# Keep the newest $keep builds.
for stamp in $(printf '%s\n' "$root"/*.stamp | sort -rV | tail -n +"$((keep + 1))"); do
  rm -rf "${stamp%.stamp}" "$stamp"
done

echo "built $root/$label; kept: $(printf '%s\n' "$root"/*.stamp | sed 's#.*/##; s#\.stamp$##' | sort -rV | tr '\n' ' ')"
