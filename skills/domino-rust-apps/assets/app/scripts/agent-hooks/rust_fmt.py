#!/usr/bin/env python3
"""After an agent edits files: run `cargo fmt --all` in each Cargo workspace that owns an edited .rs file.

Reads the hook payload on stdin. Works with any agent whose payload names the edited path
(tool_input.file_path, file_path, toolArgs.path, toolCall.args, or apply_patch text).
Exit 0 with "{}" when there is nothing to report; exit 2 with stderr when rustfmt fails
(usually a syntax error the model must fix).
"""
import json
import os
import re
import subprocess
import sys

try:
    payload = json.loads(sys.stdin.read())
except ValueError:
    print("{}")
    sys.exit(0)

paths = set()


def walk(value):
    if isinstance(value, dict):
        for item in value.values():
            walk(item)
    elif isinstance(value, list):
        for item in value:
            walk(item)
    elif isinstance(value, str):
        paths.update(re.findall(r"[^\s'\"`:*]+\.rs\b", value))


walk(payload)
if not paths:
    print("{}")
    sys.exit(0)

base = payload.get("cwd") or (payload.get("workspace_roots") or payload.get("workspacePaths") or [None])[0] or os.getcwd()
roots = set()
for path in paths:
    path = path if os.path.isabs(path) else os.path.join(base, path)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        continue
    located = subprocess.run(["cargo", "locate-project", "--workspace", "--message-format", "plain"],
                             cwd=directory, capture_output=True, text=True)
    if located.returncode == 0:
        roots.add(os.path.dirname(located.stdout.strip()))

failed = []
for root in sorted(roots):
    result = subprocess.run(["cargo", "fmt", "--all"], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        failed.append(f"cargo fmt failed in {root}:\n{(result.stderr or result.stdout)[-4000:]}")
if failed:
    print("\n\n".join(failed), file=sys.stderr)
    sys.exit(2)
print("{}")
