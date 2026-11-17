#!/usr/bin/env python3
"""Fixture test for lint rule L17 (features that need Domino 6.2 or later)."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("lint", Path(__file__).with_name("lint-skills.py"))
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)

FAIL = [  # (text, why)
    ('"clusterType": "spark" | "ray" | "dask" | "mpi" | "slurm"', "bare slurm in an enum"),
    ("- GenAI tracing patterns", "bare GenAI tracing topic"),
    ("Authenticate with a Personal Access Token as a bearer.", "Domino PAT"),
    ("POST /api/apps/v1/apps", "apps v1 route"),
]
PASS = [
    ("Slurm clusters are not available on Domino 6.1.", "negative statement"),
    ("GenAI tracing requires Domino 6.2 or later.", "version statement"),
    ("with an SSH key, a personal access token for the Git host, or a password", "Git credential"),
]


def flagged(text: str) -> bool:
    hit = lint.LATER_TERMS.search(text)
    return bool(hit and not lint.LATER_ALLOWED.search(text))


bad = [w for t, w in FAIL if not flagged(t)] + [w for t, w in PASS if flagged(t)]
for why in bad:
    print(f"FAIL: {why}", file=sys.stderr)
print("ok: L17 fixtures" if not bad else f"{len(bad)} fixture(s) wrong")
sys.exit(1 if bad else 0)
