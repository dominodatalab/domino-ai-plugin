#!/usr/bin/env python3
"""Fixture test for lint rule L17 (features that need Domino 6.2 or later).

Calls the same function `lint-skills.py` runs on every file, so a broken rule fails here.
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("lint", Path(__file__).with_name("lint-skills.py"))
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)

# (lines of one file, line numbers L17 must flag, why)
CASES = [
    (['"clusterType": "spark" | "ray" | "dask" | "mpi" | "slurm"'], [1], "bare slurm in an enum"),
    (["- GenAI tracing patterns"], [1], "bare GenAI tracing topic"),
    (["Authenticate with a Personal Access Token as a bearer."], [1], "Domino PAT"),
    (["POST /api/apps/v1/apps"], [1], "apps v1 route"),
    (["Slurm clusters are not available on Domino 6.1."], [], "negative statement"),
    (["GenAI tracing requires Domino 6.2 or later."], [], "version statement"),
    (["with an SSH key, a personal access token for the Git host, or a password"], [], "Git credential"),
    (["Slurm clusters on Domino", "are not available on 6.1."], [], "allow phrase on the next line"),
    (["Slurm clusters on Domino.", "", "They are not available on 6.1."], [1], "allow phrase two lines down"),
    (["Not available on Domino 6.1.", "Slurm clusters"], [2], "allow phrase on the line before"),
    (["Use Slurm.", "Use /api/apps/v1/apps."], [1, 2], "one hit per line"),
]

bad = []
for lines, want, why in CASES:
    got = [n for n, _ in lint.later_term_hits(lines)]
    if got != want:
        bad.append(f"{why}: flagged lines {got}, expected {want}")
for msg in bad:
    print(f"FAIL: {msg}", file=sys.stderr)
print("ok: L17 fixtures" if not bad else f"{len(bad)} fixture(s) wrong")
sys.exit(1 if bad else 0)
