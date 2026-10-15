#!/usr/bin/env python3
"""End-of-turn gate: run clippy and the tests; if they fail, send the agent back once.

Usage: rust_gate.py [--format standard|cursor|antigravity]
  standard (default): {"decision": "block", "reason": ...}; read by the Stop hooks of Claude Code and
                      Codex, Copilot CLI agentStop, Gemini CLI AfterAgent, and Cursor's import of
                      .claude/settings.json
  cursor:             {"followup_message": ...} for a native .cursor/hooks.json "stop" hook
  antigravity:        {"decision": "continue", "reason": ...} for .agents/hooks.json
The exit code is always 0; the decision travels as JSON on stdout.
"""
import atexit
import hashlib
import json
import os
import subprocess
import sys
import tempfile

emitted = False


def _default():
    # Gemini CLI and Codex parse stdout as JSON: never leave it empty.
    if not emitted:
        print("{}")


atexit.register(_default)

fmt = sys.argv[sys.argv.index("--format") + 1] if "--format" in sys.argv else "standard"
try:
    payload = json.loads(sys.stdin.read() or "{}")
except ValueError:
    payload = {}

start = (payload.get("cwd") or (payload.get("workspace_roots") or payload.get("workspacePaths") or [None])[0]
         or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
located = subprocess.run(["cargo", "locate-project", "--workspace", "--message-format", "plain"],
                         cwd=start, capture_output=True, text=True)
if located.returncode != 0:
    sys.exit(0)  # not inside a Cargo workspace
root = os.path.dirname(located.stdout.strip())

changed = subprocess.run(["git", "status", "--porcelain", "--", "*.rs", "*Cargo.toml", "Cargo.lock"],
                         cwd=root, capture_output=True, text=True)
if changed.returncode == 0 and not changed.stdout.strip():
    sys.exit(0)  # Git repository with no Rust changes since HEAD

for cmd in (["cargo", "clippy", "--locked", "--workspace", "--all-targets", "--", "-D", "warnings"],
            ["cargo", "test", "--locked", "--workspace"]):
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if result.returncode == 0:
        continue
    text = f"`{' '.join(cmd)}` failed in {root}. Fix it, then finish.\n\n{(result.stdout + result.stderr)[-6000:]}"
    # Loop guard: the agent's own flag, Cursor's counter, or the same failure already reported once.
    key = payload.get("session_id") or payload.get("sessionId") or payload.get("conversation_id") or root
    mark = os.path.join(tempfile.gettempdir(), "rust-gate-" + hashlib.sha256((key + text).encode()).hexdigest()[:16])
    retried = (payload.get("stop_hook_active") is True or (payload.get("loop_count") or 0) >= 1
               or os.path.exists(mark))
    if retried:
        out = {} if fmt == "cursor" else {"systemMessage": "Rust checks still failing; stopping.\n" + text[:2000]}
    else:
        open(mark, "w").close()
        out = {"standard": {"decision": "block", "reason": text},
               "cursor": {"followup_message": text},
               "antigravity": {"decision": "continue", "reason": text}}[fmt]
    print(json.dumps(out))
    emitted = True
    sys.exit(0)
