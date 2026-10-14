#!/bin/bash
# Starts one Claude Code session for the e2e harness inside a Domino Workspace, detached from SSH.
# usage: run-claude.sh RUN_DIR CFG_DIR OUT TIMEOUT_S MODEL MAX_TURNS [PLUGIN_DIR]
# stdin: line 1 = Claude Code OAuth token, the rest = the prompt.
#
# The token is held in memory only: it reaches `claude` as CLAUDE_CODE_OAUTH_TOKEN and the redaction filter
# as an environment variable. Tool subprocesses run through CLAUDE_CODE_SHELL_PREFIX, which drops it.
# stdout (stream-json) is redacted by redact.py before it is written to OUT; sessions are not persisted;
# the config dir is deleted when the run ends. Writes OUT.rc (exit code) and OUT.pid.
set -u
export PATH="$HOME/.local/bin:$PATH"
RUN_DIR=$1 CFG_DIR=$2 OUT=$3 TMO=$4 MODEL=$5 MAXT=$6 PLUG=${7:-}
HERE=$(cd "$(dirname "$0")" && pwd)
IFS= read -r T
P=$(cat)
mkdir -p "$RUN_DIR" "$CFG_DIR" "$(dirname "$OUT")" && cd "$RUN_DIR" || exit 97
rm -f "$OUT" "$OUT.rc" "$OUT.err" "$OUT.pid"
W="$CFG_DIR.noauth.sh"
cat > "$W" <<'EOS'
#!/bin/bash
unset CLAUDE_CODE_OAUTH_TOKEN E2E_REDACT
if [ "$#" -eq 1 ]; then exec /bin/bash -c "$1"; else exec "$@"; fi
EOS
chmod 700 "$W"
export CLAUDE_CONFIG_DIR="$CFG_DIR" CLAUDE_CODE_SHELL_PREFIX="$W"
args=(-p "$P" --model "$MODEL" --output-format stream-json --verbose --max-turns "$MAXT"
      --permission-mode bypassPermissions --no-session-persistence)
[ -n "$PLUG" ] && args+=(--plugin-dir "$PLUG")
export E2E_REDACT="$T"
unset T P
export OUT CFG_DIR W TMO HERE
setsid bash -c '
  ( exec env -u E2E_REDACT CLAUDE_CODE_OAUTH_TOKEN="$E2E_REDACT" timeout -k 30 "$TMO" claude "$@" < /dev/null 2>"$OUT.err" ) \
    | python3 -u "$HERE/redact.py" > "$OUT"
  echo "${PIPESTATUS[0]}" > "$OUT.rc"
  rm -rf "$CFG_DIR" "$W"
' _ "${args[@]}" > /dev/null 2>&1 < /dev/null &
echo $! > "$OUT.pid"
unset E2E_REDACT
echo "STARTED $(cat "$OUT.pid")"
