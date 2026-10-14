#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Smoke test: one tiny Claude Code run per build in a Workspace. Verifies auth, model id, plugin load,
MCP server status and that the OAuth token is not visible to tool subprocesses.
usage: smoke.py CONFIG [PROJECT_TYPE] [VARIANT,VARIANT,...]   (after provision and prep)"""
import json, sys, time
from pathlib import Path
import yaml
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from e2elib.runner import run_one

cfg = yaml.safe_load(open(sys.argv[1]))
st = json.loads((HERE / "state/state.json").read_text())
ptype = sys.argv[2] if len(sys.argv) > 2 else "git"
variants = sys.argv[3].split(",") if len(sys.argv) > 3 else ["next"]
scen = {"id": "smoke", "project_type": ptype, "timeout_s": 300, "setup": [], "check": [], "cleanup": [],
        "prompt": "Run exactly this bash command and report its output verbatim, nothing else: "
                  "`env | grep -E 'OAUTH|ANTHROPIC' | cut -d= -f1; echo token=${CLAUDE_CODE_OAUTH_TOKEN:+set}; echo prefix=$CLAUDE_CODE_SHELL_PREFIX; echo proxy=${DOMINO_API_PROXY:+set}`"}
out = HERE / "runs" / ("smoke-" + time.strftime("%H%M%S"))
for v in variants:
    r = run_one(cfg, st, HERE, out, scen, v, print, do_check=False)
    print(json.dumps({k: r.get(k) for k in ("variant", "exit_code", "model", "num_turns", "cost_usd", "mcp_servers", "final_text", "wall_s")}, indent=1))
