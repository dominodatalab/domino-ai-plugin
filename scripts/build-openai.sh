#!/usr/bin/env bash
# Builds the ZIP for the OpenAI plugin portal from the shared repo; see README "OpenAI build".
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build-openai.sh [--mcp-url https://host/mcp] [--out dist]
  default         skills-only package (portal path "Skills only"); MCP config is excluded
  --mcp-url URL   adds a streamable-http mcp.json for the portal path "With MCP"
EOF
}

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/dist"
mcp_url=""
while [ $# -gt 0 ]; do
  case "$1" in
    --mcp-url) mcp_url="${2:?--mcp-url needs a value}"; shift 2 ;;
    --out) out="${2:?--out needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$mcp_url" in ""|https://*) ;; *) echo "--mcp-url must be an https:// URL" >&2; exit 2 ;; esac
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }
command -v zip >/dev/null || { echo "zip is required" >&2; exit 2; }

cd "$root"
python3 scripts/sync-manifests.py --check
if python3 -c "import yaml" 2>/dev/null; then
  python3 scripts/lint-skills.py
else
  uv run --quiet --with pyyaml python scripts/lint-skills.py
fi

name="$(jq -r .name plugin.json)"
version="$(jq -r .version plugin.json)"
stage="$out/openai/$name"
rm -rf "$out/openai"
mkdir -p "$stage"

# Only portable components ship; agents, output styles, hooks, and Claude config stay behind.
cp plugin.json LICENSE "$stage/"
cp -R skills "$stage/skills"
[ -d assets ] && cp -R assets "$stage/assets"
find "$stage" \( -name .DS_Store -o -name __pycache__ -o -name '*.pyc' \) -prune -exec rm -rf {} +

if [ -n "$mcp_url" ]; then
  jq -n --arg url "$mcp_url" '{
    "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
    mcpServers: {domino_server: {type: "streamable-http", url: $url}}
  }' > "$stage/mcp.json"
  kind="with-mcp"
else
  # Skills-only uploads reject screenshots, which the portal allows only with MCP and custom UI.
  if jq -e '.extensions["com.openai"].interface.screenshots // empty' plugin.json >/dev/null; then
    echo "::error::skills-only packages must not declare interface.screenshots" >&2; exit 1
  fi
  kind="skills-only"
fi

zipfile="$out/$name-openai-$kind-$version.zip"
rm -f "$zipfile"
(cd "$stage" && zip -qrX "$zipfile" .)
echo "built $zipfile"
echo "  $(find "$stage/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') skills, version $version"
