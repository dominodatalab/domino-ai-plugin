#!/usr/bin/env bash
# Builds the ZIP for the OpenAI plugin portal from the shared repo; see README "OpenAI build".
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build-openai.sh [--mcp-url https://host/mcp --mcp-name NAME] [--out dist]
  default         skills-only package (portal path "Skills only"); MCP config is excluded
  --mcp-url URL   adds a streamable-http mcp.json for the portal path "With MCP"
  --mcp-name NAME the server's name in that mcp.json (required with --mcp-url)
Only files git tracks are packaged; build a release from a clean checkout of its tag.
EOF
}

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/dist"
mcp_url=""
mcp_name=""
while [ $# -gt 0 ]; do
  case "$1" in
    --mcp-url) mcp_url="${2:?--mcp-url needs a value}"; shift 2 ;;
    --mcp-name) mcp_name="${2:?--mcp-name needs a value}"; shift 2 ;;
    --out) out="${2:?--out needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$mcp_url" in ""|https://*) ;; *) echo "--mcp-url must be an https:// URL" >&2; exit 2 ;; esac
# The name tells the model which server it is; a docs URL named domino_server would claim the job tools.
[ -z "$mcp_url" ] || [ -n "$mcp_name" ] || { echo "--mcp-url needs --mcp-name (for example domino_docs)" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }
command -v zip >/dev/null || { echo "zip is required" >&2; exit 2; }

cd "$root"
python3 scripts/sync-manifests.py --check
if python3 -c "import yaml" 2>/dev/null; then
  python3 scripts/lint-skills.py
else
  uv run --quiet --with pyyaml python scripts/lint-skills.py
fi

# The portal rejects listings whose icon or screenshot paths don't resolve inside the package.
jq -r '.extensions["com.openai"].interface | [.logo, .logoDark, .composerIcon, .composerIconDark,
  (.screenshots // [])[]] | .[] | select(. != null)' plugin.json | while read -r asset; do
  case "$asset" in ./assets/*) ;; *) echo "::error::$asset must live under ./assets/" >&2; exit 1 ;; esac
  [ -f "$asset" ] || { echo "::error::plugin.json references missing $asset" >&2; exit 1; }
done

# domino.ai answers 200 for missing pages, so match the page title instead of the status code.
privacy="$(jq -r '.extensions["com.openai"].interface.privacyPolicyURL' plugin.json)"
page="$(curl -fsSL --max-time 20 "$privacy" || true)"
if ! grep -qiE '<title>[^<]*privacy policy' <<<"$page"; then
  echo "::error::privacyPolicyURL $privacy is unreachable or is not a privacy policy page" >&2
  exit 1
fi

name="$(jq -r .name plugin.json)"
version="$(jq -r .version plugin.json)"
stage="$out/openai/$name"
rm -rf "$out/openai"
mkdir -p "$stage"

# Only portable components ship; agents, output styles, hooks, and Claude config stay behind.
# Only files git tracks are packaged, so untracked or ignored files in the working tree (target/,
# node_modules/, a real .env) never reach the ZIP. Tracked files are taken as they are on disk.
untracked="$(git ls-files --others --exclude-standard -- skills assets)"
if [ -n "$untracked" ]; then
  echo "::warning::not packaged because git does not track them (git add to include):" >&2
  echo "$untracked" >&2
fi
git ls-files -z -- plugin.json LICENSE skills assets | tar --null -T - -cf - | tar -xf - -C "$stage"
find "$stage" \( -name .DS_Store -o -name __pycache__ -o -name '*.pyc' \) -prune -exec rm -rf {} +

if [ -n "$mcp_url" ]; then
  jq -n --arg url "$mcp_url" --arg name "$mcp_name" '{
    "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
    mcpServers: {($name): {type: "streamable-http", url: $url}}
  }' > "$stage/mcp.json"
  kind="with-mcp"
else
  # Skills-only uploads reject screenshots, which the portal allows only with MCP and custom UI.
  if jq -e '.extensions["com.openai"].interface.screenshots // empty' plugin.json >/dev/null; then
    echo "::error::skills-only packages must not declare interface.screenshots" >&2; exit 1
  fi
  # Skills built around the plugin's local MCP server have nothing to work with in a skills-only
  # install, so they stay out of this package.
  local_mcp_skills="domino-modeling-assistant"
  for skill in $local_mcp_skills; do rm -rf "$stage/skills/$skill"; done
  kind="skills-only"
fi

zipfile="$out/$name-openai-$kind-$version.zip"
rm -f "$zipfile"
(cd "$stage" && zip -qrX "$zipfile" .)
echo "built $zipfile"
echo "  $(find "$stage/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') skills, version $version"
