#!/usr/bin/env bash
# Enforces the YYYY.XYY.N release scheme on a pull request; see CONTRIBUTING.md standard 10.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/check-version.sh <base-ref>        e.g. scripts/check-version.sh origin/main

Version = YYYY.XYY.N, valid semver (e.g. 2026.603.3)
  YYYY  year of the release
  XYY   Domino line floor as X*100+Y (603 = Domino 6.3 and later, incl. Cloud)
  N     release counter, monotonic within a Domino line, never reused, never reset by year
Tag = release-<version>, created by .github/workflows/tag-release.yml

Rules, against the PR base:
  1. version is YYYY.XYY.N with no leading zeros, and XYY >= 100
  2. if any content path changed, version differs from the base
  3. no release-<version> tag exists yet (never reuse)
  4. on a release-X.Y base, the version's line equals the branch's X.Y
  5. within a line N increases; the line and the year never go backwards; no future year
  6. on `develop` the version equals the base; only the develop -> main PR bumps

Exit 0 = ok, 1 = violation, 2 = usage/tooling error.
EOF
}

base_ref="${1:-}"
[ -n "$base_ref" ] || { usage >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

manifest=".claude-plugin/plugin.json"
content_paths=(skills commands agents templates mcp-servers output-styles hooks bin workflows themes monitors assets .mcp.json .lsp.json settings.json mcp.json plugin.json "$manifest")

fail() { echo "::error::$*" >&2; exit 1; }
note() { echo "$*"; }

# parse sets year/line/n; accepts the pre-2026.603 form YYYY.X-Y.N so old bases still compare.
parse() {
  local v="$1"
  if [[ "$v" =~ ^([0-9]{4})\.([1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] && [ "${BASH_REMATCH[2]}" -ge 100 ]; then
    year="${BASH_REMATCH[1]}"; line="${BASH_REMATCH[2]}"; n="${BASH_REMATCH[3]}"
  elif [[ "$v" =~ ^([0-9]{4})\.([0-9]+)-([0-9]+)\.([0-9]+)$ ]]; then
    year="${BASH_REMATCH[1]}"; line=$(( BASH_REMATCH[2] * 100 + BASH_REMATCH[3] )); n="${BASH_REMATCH[4]}"
  else
    return 1
  fi
}

head_version="$(jq -r '.version // empty' "$manifest")"
[ -n "$head_version" ] || fail "$manifest has no version"

if ! git rev-parse --verify --quiet "$base_ref" >/dev/null; then
  fail "base ref '$base_ref' not found; fetch it first (git fetch origin <base>)"
fi
base_version="$(git show "$base_ref:$manifest" 2>/dev/null | jq -r '.version // empty' || true)"

# 1. format: only the current form is accepted for the head.
[[ "$head_version" =~ ^[0-9]{4}\.[1-9][0-9]*\.(0|[1-9][0-9]*)$ ]] && parse "$head_version" \
  || fail "version '$head_version' is not YYYY.XYY.N (e.g. 2026.603.3: Domino 6.3 is 603)"
head_year="$year"; head_line="$line"; head_n="$n"

# 6. integration branch: no bumps here
if [ "${base_ref#origin/}" = "develop" ]; then
  if [ "$head_version" != "$base_version" ]; then
    fail "develop is the integration branch and keeps the version frozen (base $base_version, head $head_version). Bump N only in the develop -> main release PR."
  fi
  note "ok: integration branch develop, version unchanged at $head_version"
  exit 0
fi

# 2. bump required when content changed
changed="$(git diff --name-only "$base_ref"...HEAD -- "${content_paths[@]}" || git diff --name-only "$base_ref" HEAD -- "${content_paths[@]}")"
if [ -n "$changed" ]; then
  if [ "$head_version" = "$base_version" ]; then
    fail "content changed but $manifest version is still '$head_version'. Bump N (or the line) so installed copies receive this change:
$(echo "$changed" | sed 's/^/  - /')"
  fi
  note "content changed; version $base_version -> $head_version"
else
  note "no content paths changed; version bump not required (version is $head_version)"
fi

# 3. never reuse: tag must not exist for a *new* version
if [ "$head_version" != "$base_version" ]; then
  if git ls-remote --exit-code --tags origin "refs/tags/release-$head_version" >/dev/null 2>&1 \
     || git rev-parse --verify --quiet "refs/tags/release-$head_version" >/dev/null; then
    fail "tag release-$head_version already exists; versions are never reused"
  fi
fi

# 4. release-X.Y base must keep its line
base_branch="${base_ref#origin/}"
if [[ "$base_branch" =~ ^release-([0-9]+)\.([0-9]+)$ ]]; then
  branch_line=$(( BASH_REMATCH[1] * 100 + BASH_REMATCH[2] ))
  [ "$head_line" = "$branch_line" ] || fail "base branch $base_branch requires line $branch_line, got '$head_version'"
fi

# 5. monotonic within the scheme, when the base is already on it
this_year="$(date +%Y)"
[ "$head_year" -le "$this_year" ] || fail "year $head_year is in the future (today is $this_year)"
if [ -n "$base_version" ] && [ "$head_version" != "$base_version" ] && parse "$base_version"; then
  base_year="$year"; base_line="$line"; base_n="$n"
  [ "$head_year" -ge "$base_year" ] || fail "year must not go backwards: base $base_version, head $head_version"
  if [ "$head_line" = "$base_line" ]; then
    [ "$head_n" -gt "$base_n" ] || fail "N must increase within line $head_line: base $base_version, head $head_version"
  else
    [ "$head_line" -gt "$base_line" ] || fail "the Domino line must not go backwards: base $base_version, head $head_version"
    [[ "$base_branch" =~ ^release- ]] && fail "a release-X.Y branch never changes line: base $base_version, head $head_version"
  fi
fi

note "ok: $manifest version $head_version"
