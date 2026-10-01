#!/usr/bin/env python3
# Copies shared fields from .claude-plugin/plugin.json (source of truth) into portable plugin.json.
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / ".claude-plugin" / "plugin.json"
PORTABLE = ROOT / "plugin.json"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
SHARED = ["name", "version", "description", "author", "homepage", "repository", "license",
          "keywords"]
ORDER = ["$schema", *SHARED, "extensions"]
# YYYY.XYY.N is semver because the OpenAI portal rejects anything else.
VERSION = re.compile(r"[0-9]{4}\.[1-9][0-9]{2,}\.(0|[1-9][0-9]*)")
# Public-directory limits from the OpenAI submission reference.
LISTING_LIMITS = {"displayName": 30, "shortDescription": 30, "longDescription": 4000,
                  "developerName": 80}
MAX_PROMPTS, MAX_PROMPT_LEN = 3, 128


def expected() -> dict:
    claude = json.loads(CLAUDE.read_text())
    if not VERSION.fullmatch(claude.get("version", "")):
        sys.exit(f"{CLAUDE}: version '{claude.get('version')}' is not YYYY.XYY.N (e.g. 2026.603.3)")
    portable = json.loads(PORTABLE.read_text()) if PORTABLE.exists() else {}
    out = {"$schema": SCHEMA, **{k: claude[k] for k in SHARED if k in claude}}
    # OpenAI listing metadata lives only in plugin.json, so keep whatever is there.
    if "extensions" in portable:
        out["extensions"] = portable["extensions"]
    return {k: out[k] for k in ORDER if k in out}


def listing_errors(manifest: dict) -> list[str]:
    interface = manifest.get("extensions", {}).get("com.openai", {}).get("interface", {})
    errors = []
    for field, limit in LISTING_LIMITS.items():
        value = interface.get(field)
        if not isinstance(value, str) or not value.strip() or "\n" in value.strip():
            errors.append(f"interface.{field} is required and must be one non-empty string")
        elif len(value) > limit:
            errors.append(f"interface.{field} is {len(value)} chars (max {limit})")
    prompts = interface.get("defaultPrompt", [])
    prompts = [prompts] if isinstance(prompts, str) else prompts
    if len(prompts) > MAX_PROMPTS:
        errors.append(f"interface.defaultPrompt has {len(prompts)} prompts (max {MAX_PROMPTS})")
    errors += [f"interface.defaultPrompt '{p[:40]}...' exceeds {MAX_PROMPT_LEN} chars"
               for p in prompts if len(p) > MAX_PROMPT_LEN]
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync plugin.json from .claude-plugin/plugin.json")
    parser.add_argument("--check", action="store_true", help="fail instead of writing if stale")
    args = parser.parse_args()

    want = json.dumps(expected(), indent=2, ensure_ascii=False) + "\n"
    have = PORTABLE.read_text() if PORTABLE.exists() else ""
    version = json.loads(want)["version"]
    if args.check:
        problems = listing_errors(json.loads(want))
        if problems:
            sys.exit("plugin.json listing metadata:\n  " + "\n  ".join(problems))
        if want != have:
            sys.exit("plugin.json is out of sync with .claude-plugin/plugin.json; "
                     "run scripts/sync-manifests.py and commit the result")
        print(f"ok: plugin.json in sync (version {version})")
        return
    PORTABLE.write_text(want)
    print(f"wrote plugin.json (version {version})")


if __name__ == "__main__":
    main()
