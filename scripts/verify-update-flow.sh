#!/usr/bin/env bash
# Check how Claude Code loads this plugin from a local-directory marketplace, the layout the
# Domino Standard Environment (DSE) image uses:
#
#   <home>/marketplaces/domino/.claude-plugin/marketplace.json  (source: ./plugins/domino-claude-plugin)
#   <home>/marketplaces/domino/plugins/domino-claude-plugin      (git clone)
#   claude plugin marketplace add <dir> && claude plugin install domino-claude-plugin@domino-marketplace
#
# Behaviour asserted (observed on Claude Code 2.1.294, 2026-10-08):
#   A. a session loads the plugin from the clone itself, not from the copy under plugins/cache
#   B. a skill added to the clone without changing plugin.json `version` is loaded by the next
#      session, so a `git checkout` in the clone is the whole update for this layout
#
# Git-sourced marketplaces (the Anthropic marketplace, `claude plugin marketplace add owner/repo`)
# are different: Claude Code copies them into its cache and updates only when the `version` string
# changes. This script covers the local-directory layout only.
#
# The check runs in a throwaway CLAUDE_CONFIG_DIR, so it never touches your own settings or
# plugins. It reads Claude Code's session `init` event and stops the session before any model call.
#
# Usage: scripts/verify-update-flow.sh [git-url-or-path]      default: this repository's origin
# Requires: claude (Claude Code CLI), git, python3.
set -euo pipefail

repo="${1:-$(git -C "$(dirname "$0")/.." remote get-url origin)}"
work="$(mktemp -d /tmp/dse-mirror.XXXXXX)"
fails=0
log()  { printf '[verify-update-flow] %s\n' "$*"; }
pass() { printf '  PASS %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*"; fails=$((fails+1)); }
trap 'rm -rf "$work"' EXIT

export CLAUDE_CONFIG_DIR="$work/config"
mkt="$work/marketplaces/domino"
clone="$mkt/plugins/domino-claude-plugin"
mkdir -p "$CLAUDE_CONFIG_DIR" "$mkt/.claude-plugin" "$mkt/plugins"
cat > "$mkt/.claude-plugin/marketplace.json" <<'JSON'
{"name": "domino-marketplace", "owner": {"name": "Domino Data Lab"},
 "plugins": [{"name": "domino-claude-plugin", "source": "./plugins/domino-claude-plugin", "category": "development"}]}
JSON

log "claude $(claude --version 2>/dev/null | head -1); cloning $repo"
git clone --quiet --depth 1 "$repo" "$clone"
claude plugin marketplace add "$mkt" >/dev/null
claude plugin install domino-claude-plugin@domino-marketplace >/dev/null

# Prints "<plugin path>|<comma-separated skill names>" from the session init event, then stops
# the session so no model request is made.
session_view() {
  python3 - "$work" <<'PY'
import json, subprocess, sys
proc = subprocess.Popen(["claude", "-p", "ok", "--output-format", "stream-json", "--verbose", "--max-turns", "1"],
                        cwd=sys.argv[1], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
try:
    for line in proc.stdout:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            path = next((p.get("path", "") for p in event.get("plugins", []) if p.get("source") == "domino-claude-plugin@domino-marketplace"), "")
            skills = [s for s in event.get("skills", []) if isinstance(s, str) and s.startswith("dominodatalab:")]
            print(f"{path}|{','.join(skills)}")
            break
finally:
    proc.kill()
PY
}

log "A. the session loads the plugin from the clone"
IFS='|' read -r path skills < <(session_view)
if [ "$path" = "$clone" ]; then pass "plugin path is the clone ($path)"
else fail "plugin path is '$path', expected the clone $clone (Claude Code copies this layout again; update CONTRIBUTING)"; fi

log "B. a skill added without a version bump loads in the next session"
probe="verify-update-flow-probe"
mkdir -p "$clone/skills/$probe"
printf -- '---\nname: %s\ndescription: Probe skill created by scripts/verify-update-flow.sh.\n---\nProbe.\n' "$probe" > "$clone/skills/$probe/SKILL.md"
IFS='|' read -r _ skills < <(session_view)
case ",$skills," in
  *",dominodatalab:$probe,"*) pass "dominodatalab:$probe loaded with plugin.json version unchanged" ;;
  *) fail "dominodatalab:$probe not loaded; the layout no longer reads the clone in place" ;;
esac

if [ "$fails" -eq 0 ]; then log "all checks passed"; else log "$fails check(s) failed"; exit 1; fi
