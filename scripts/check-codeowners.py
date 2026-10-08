#!/usr/bin/env python3
"""Check that every skill directory has its own line in .github/CODEOWNERS.

Fails when:
  - a directory under skills/ has no exact `/skills/<name>/` line, or
  - a `/skills/<name>/` line points at a directory that does not exist, or
  - a `/skills/<name>/` line appears more than once, or
  - a line under skills/ lists no owners.

Usage: scripts/check-codeowners.py        Exit 0 = ok, 1 = violation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
SKILLS = ROOT / "skills"
SKILL_LINE = re.compile(r"^/skills/([^/\s]+)/(\s+.*)?$")


def main() -> int:
    errors: list[str] = []
    skill_dirs = {p.name for p in SKILLS.iterdir() if p.is_dir() and not p.name.startswith(".")}
    seen: dict[str, int] = {}

    for lineno, raw in enumerate(CODEOWNERS.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line.startswith("/skills/"):
            continue
        match = SKILL_LINE.match(line)
        if not match:
            errors.append(f"CODEOWNERS:{lineno}: skill rules must be exactly '/skills/<name>/ @owner ...', got '{line}'")
            continue
        name, owners = match.group(1), (match.group(2) or "").split()
        if not owners:
            errors.append(f"CODEOWNERS:{lineno}: /skills/{name}/ lists no owners")
        if name in seen:
            errors.append(f"CODEOWNERS:{lineno}: /skills/{name}/ already listed on line {seen[name]}")
        seen[name] = lineno
        if name not in skill_dirs:
            errors.append(f"CODEOWNERS:{lineno}: /skills/{name}/ does not exist (renamed or removed skill?)")

    for name in sorted(skill_dirs - seen.keys()):
        errors.append(f"skills/{name}/ has no '/skills/{name}/' line in .github/CODEOWNERS; add one with its owners")

    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    print(f"ok: {len(skill_dirs)} skills, each with its own CODEOWNERS line")
    return 0


if __name__ == "__main__":
    sys.exit(main())
