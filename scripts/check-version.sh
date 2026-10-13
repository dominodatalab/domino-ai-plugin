#!/usr/bin/env bash
# Enforces the YYYY.XYY.N release scheme on a pull request; see CONTRIBUTING.md standard 10 and
# "Release candidates".
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/check-version.sh <base-ref>        e.g. scripts/check-version.sh origin/main

Version = YYYY.XYY.N, valid semver (e.g. 2026.603.3)
  YYYY  year of the release
  XYY   Domino line floor as X*100+Y (603 = Domino 6.3 and later, incl. Cloud)
  N     release counter, monotonic within a Domino line, never reused, never reset by year
Release candidate = YYYY.XYY.N-rc.M (M >= 1), only on a branch named rc/<YYYY.XYY.N>
Tag = release-<version>, created by .github/workflows/tag-release.yml

Rules, against the PR base:
  1. version is YYYY.XYY.N (optionally -rc.M) with no leading zeros, and XYY >= 100
  2. if any content path changed, version differs from the base
  3. no release-<version> tag exists yet (never reuse)
  4. on a release-X.Y base, the version's line equals the branch's X.Y
  5. within a line N increases; the line and the year never go backwards; no future year
  6. on `develop` the version equals the base; only the develop -> main PR bumps
  7. main, develop and release-* never carry -rc.M; an rc/<version> base requires it
  8. on rc/<version>: the plain part equals <version> and is newer than main's version;
     M increases over the base and over every existing release-<version>-rc.* tag

Exit 0 = ok, 1 = violation, 2 = usage/tooling error.
EOF
}

base_ref="${1:-}"
[ -n "$base_ref" ] || { usage >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

manifest=".claude-plugin/plugin.json"
content_paths=(skills commands agents templates mcp-servers output-styles hooks bin workflows themes monitors assets rules .agents .cursor-plugin .mcp.json .lsp.json settings.json mcp.json mcp_config.json plugin.json gemini-extension.json .claude-plugin/marketplace.json "$manifest")

fail() { echo "::error::$*" >&2; exit 1; }
note() { echo "$*"; }

# parse sets year/line/n/rc (rc is empty for a plain version, M for YYYY.XYY.N-rc.M); accepts
# the pre-2026.603 form YYYY.X-Y.N so old bases still compare.
parse() {
  local v="$1"
  rc=""
  if [[ "$v" =~ ^([0-9]{4})\.([1-9][0-9]*)\.(0|[1-9][0-9]*)(-rc\.([1-9][0-9]*))?$ ]] && [ "${BASH_REMATCH[2]}" -ge 100 ]; then
    year="${BASH_REMATCH[1]}"; line="${BASH_REMATCH[2]}"; n="${BASH_REMATCH[3]}"; rc="${BASH_REMATCH[5]}"
  elif [[ "$v" =~ ^([0-9]{4})\.([0-9]+)-([0-9]+)\.([0-9]+)$ ]]; then
    year="${BASH_REMATCH[1]}"; line=$(( BASH_REMATCH[2] * 100 + BASH_REMATCH[3] )); n="${BASH_REMATCH[4]}"
  else
    return 1
  fi
}

# newer A B: exit 0 when plain version A sorts after plain version B (year, line, N).
newer() {
  parse "$1" || return 2; local ay="$year" al="$line" an="$n"
  parse "$2" || return 2; local by="$year" bl="$line" bn="$n"
  [ "$ay" -gt "$by" ] && return 0; [ "$ay" -lt "$by" ] && return 1
  [ "$al" -gt "$bl" ] && return 0; [ "$al" -lt "$bl" ] && return 1
  [ "$an" -gt "$bn" ]
}

head_version="$(jq -r '.version // empty' "$manifest")"
[ -n "$head_version" ] || fail "$manifest has no version"

if ! git rev-parse --verify --quiet "$base_ref" >/dev/null; then
  fail "base ref '$base_ref' not found; fetch it first (git fetch origin <base>)"
fi
base_version="$(git show "$base_ref:$manifest" 2>/dev/null | jq -r '.version // empty' || true)"
base_branch="${base_ref#origin/}"

# 1. format: only the current form (plain or -rc.M) is accepted for the head.
[[ "$head_version" =~ ^[0-9]{4}\.[1-9][0-9]*\.(0|[1-9][0-9]*)(-rc\.[1-9][0-9]*)?$ ]] && parse "$head_version" \
  || fail "version '$head_version' is not YYYY.XYY.N or YYYY.XYY.N-rc.M (e.g. 2026.603.3: Domino 6.3 is 603)"
head_year="$year"; head_line="$line"; head_n="$n"; head_rc="$rc"
head_plain="${head_version%%-rc.*}"

# 6. integration branch: no bumps here (and so no candidate suffix either)
if [ "$base_branch" = "develop" ]; then
  if [ "$head_version" != "$base_version" ]; then
    fail "develop is the integration branch and keeps the version frozen (base $base_version, head $head_version). Bump N only in the develop -> main release PR; release candidates live on rc/<version> branches."
  fi
  note "ok: integration branch develop, version unchanged at $head_version"
  exit 0
fi

# 2. bump required when content changed
changed="$(git diff --name-only "$base_ref"...HEAD -- "${content_paths[@]}" || git diff --name-only "$base_ref" HEAD -- "${content_paths[@]}")"
if [ -n "$changed" ]; then
  if [ "$head_version" = "$base_version" ]; then
    fail "content changed but $manifest version is still '$head_version'. Bump N (or the line; on an rc/ branch bump M) so installed copies receive this change:
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

# 7 and 8. release candidates: only on rc/<version>, and always there
if [[ "$base_branch" =~ ^rc/(.+)$ ]]; then
  rc_target="${BASH_REMATCH[1]}"
  [[ "$rc_target" =~ ^[0-9]{4}\.[1-9][0-9]*\.(0|[1-9][0-9]*)$ ]] \
    || fail "branch $base_branch is not named rc/<YYYY.XYY.N> (e.g. rc/2026.603.5)"
  [ -n "$head_rc" ] || fail "branch $base_branch carries release candidates: version must be $rc_target-rc.M (M >= 1), got '$head_version'"
  [ "$head_plain" = "$rc_target" ] || fail "branch $base_branch candidates version $rc_target, got '$head_version'"
  # the candidate is for a release newer than what main ships
  if ! git rev-parse --verify --quiet origin/main >/dev/null; then
    git fetch --quiet origin main 2>/dev/null || { echo "origin/main is needed to compare against the shipped version; git fetch origin main" >&2; exit 2; }
  fi
  main_version="$(git show origin/main:"$manifest" 2>/dev/null | jq -r '.version // empty' || true)"
  [ -n "$main_version" ] || { echo "cannot read $manifest on origin/main" >&2; exit 2; }
  newer "$head_plain" "$main_version" || fail "candidate $head_version must be newer than main's version $main_version"
  # M increases over the base ...
  if [ "$head_version" != "$base_version" ] && parse "$base_version" && [ -n "$rc" ] && [ "${base_version%%-rc.*}" = "$head_plain" ]; then
    [ "$head_rc" -gt "$rc" ] || fail "rc.M must increase on $base_branch: base $base_version, head $head_version"
  fi
  # ... and over every candidate already tagged for this version
  max_tagged=0
  while read -r tag; do
    [[ "$tag" =~ -rc\.([1-9][0-9]*)$ ]] && [ "${BASH_REMATCH[1]}" -gt "$max_tagged" ] && max_tagged="${BASH_REMATCH[1]}"
  done < <( { git ls-remote --tags origin "refs/tags/release-$head_plain-rc.*" 2>/dev/null | sed 's#.*refs/tags/##; s#\^{}$##'; git tag --list "release-$head_plain-rc.*"; } | sort -u )
  if [ "$head_version" != "$base_version" ] && [ "$head_rc" -le "$max_tagged" ]; then
    fail "release-$head_plain-rc.$max_tagged is already tagged; the next candidate must be rc.$((max_tagged + 1)) or higher, got '$head_version'"
  fi
  note "ok: release candidate $head_version on $base_branch (main ships $main_version)"
  exit 0
fi
[ -z "$head_rc" ] || fail "main, develop and release-* never carry a release-candidate suffix; put '$head_version' on a branch named rc/$head_plain"

# 4. release-X.Y base must keep its line
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
