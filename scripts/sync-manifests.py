#!/usr/bin/env python3
# Copies shared fields from .claude-plugin/plugin.json (source of truth) into the portable
# plugin.json, the Cursor manifest .cursor-plugin/plugin.json and the Gemini CLI extension
# manifest gemini-extension.json.
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / ".claude-plugin" / "plugin.json"
PORTABLE = ROOT / "plugin.json"
CURSOR = ROOT / ".cursor-plugin" / "plugin.json"
GEMINI = ROOT / "gemini-extension.json"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
SHARED = ["name", "version", "description", "author", "homepage", "repository", "license",
          "keywords"]
ORDER = ["$schema", *SHARED, "extensions"]
# Cursor's manifest schema is closed (cursor/plugins schemas/plugin.schema.json): author takes
# only name and email, and there is no $schema. Cursor-only fields are kept from the file.
CURSOR_ONLY = ["displayName", "logo", "mcpServers", "rules", "skills", "agents", "commands",
               "hooks", "variables"]
CURSOR_ORDER = ["name", "displayName", "version", "description", "author", "homepage",
                "repository", "license", "keywords", "logo", "rules", "skills", "agents",
                "commands", "hooks", "mcpServers", "variables"]
# Gemini CLI reads only name, version and description as identity (docs/extensions/reference.md
# in google-gemini/gemini-cli); contextFileName, settings, mcpServers and the rest are
# Gemini-only and kept from the file.
GEMINI_SHARED = ["name", "version", "description"]
GEMINI_ONLY = ["contextFileName", "settings", "mcpServers", "excludeTools", "themes", "plan",
               "migratedTo"]
GEMINI_ORDER = [*GEMINI_SHARED, *GEMINI_ONLY]
# YYYY.XYY.N is semver because the OpenAI portal rejects anything else. A release candidate
# carries the semver pre-release suffix -rc.M (M >= 1), e.g. 2026.603.5-rc.1, which semver
# orders before 2026.603.5; it is copied verbatim into every manifest.
VERSION = re.compile(r"[0-9]{4}\.[1-9][0-9]{2,}\.(0|[1-9][0-9]*)(-rc\.[1-9][0-9]*)?")
# Public-directory limits from the OpenAI submission reference.
LISTING_LIMITS = {"displayName": 30, "shortDescription": 30, "longDescription": 4000,
                  "developerName": 80}
MAX_PROMPTS, MAX_PROMPT_LEN = 3, 128


def load_claude() -> dict:
    claude = json.loads(CLAUDE.read_text())
    if not VERSION.fullmatch(claude.get("version", "")):
        sys.exit(f"{CLAUDE}: version '{claude.get('version')}' is not YYYY.XYY.N or YYYY.XYY.N-rc.M "
                 f"(e.g. 2026.603.3 or 2026.603.5-rc.1)")
    return claude


def expected(claude: dict) -> dict:
    portable = json.loads(PORTABLE.read_text()) if PORTABLE.exists() else {}
    out = {"$schema": SCHEMA, **{k: claude[k] for k in SHARED if k in claude}}
    # OpenAI listing metadata lives only in plugin.json, so keep whatever is there.
    if "extensions" in portable:
        out["extensions"] = portable["extensions"]
    return {k: out[k] for k in ORDER if k in out}


def expected_cursor(claude: dict) -> dict:
    cursor = json.loads(CURSOR.read_text()) if CURSOR.exists() else {}
    out = {k: claude[k] for k in SHARED if k in claude}
    if "author" in out:
        out["author"] = {k: v for k, v in out["author"].items() if k in ("name", "email")}
    out.update({k: cursor[k] for k in CURSOR_ONLY if k in cursor})
    return {k: out[k] for k in CURSOR_ORDER if k in out}


def expected_gemini(claude: dict) -> dict:
    gemini = json.loads(GEMINI.read_text()) if GEMINI.exists() else {}
    out = {k: claude[k] for k in GEMINI_SHARED if k in claude}
    out.update({k: gemini[k] for k in GEMINI_ONLY if k in gemini})
    return {k: out[k] for k in GEMINI_ORDER if k in out}


def listing_errors(manifest: dict) -> list[str]:
    interface = manifest.get("extensions", {}).get("com.openai", {}).get("interface", {})
    errors = []
    for field, limit in LISTING_LIMITS.items():
        value = interface.get(field)
        if not isinstance(value, str) or not value.strip() or "\n" in value.strip():
            errors.append(f"interface.{field} is required and must be one non-empty string")
        elif len(value) > limit:
            errors.append(f"interface.{field} is {len(value)} chars (max {limit})")
    # The portal rejects listings without a reachable privacy policy and terms of service.
    for field in ("privacyPolicyURL", "termsOfServiceURL"):
        if not str(interface.get(field, "")).startswith("https://"):
            errors.append(f"interface.{field} is required and must be an https:// URL")
    prompts = interface.get("defaultPrompt", [])
    prompts = [prompts] if isinstance(prompts, str) else prompts
    if len(prompts) > MAX_PROMPTS:
        errors.append(f"interface.defaultPrompt has {len(prompts)} prompts (max {MAX_PROMPTS})")
    errors += [f"interface.defaultPrompt '{p[:40]}...' exceeds {MAX_PROMPT_LEN} chars"
               for p in prompts if len(p) > MAX_PROMPT_LEN]
    return errors


def dump(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync plugin.json, .cursor-plugin/plugin.json and "
                                                 "gemini-extension.json from .claude-plugin/plugin.json")
    parser.add_argument("--check", action="store_true", help="fail instead of writing if stale")
    args = parser.parse_args()

    claude = load_claude()
    targets = [(PORTABLE, dump(expected(claude))),
               (CURSOR, dump(expected_cursor(claude))),
               (GEMINI, dump(expected_gemini(claude)))]
    names = ", ".join(p.relative_to(ROOT).as_posix() for p, _ in targets)
    version = claude["version"]
    if args.check:
        problems = listing_errors(json.loads(targets[0][1]))
        if problems:
            sys.exit("plugin.json listing metadata:\n  " + "\n  ".join(problems))
        stale = [p.relative_to(ROOT).as_posix() for p, text in targets
                 if text != (p.read_text() if p.exists() else "")]
        if stale:
            sys.exit(f"{', '.join(stale)} out of sync with .claude-plugin/plugin.json; "
                     "run scripts/sync-manifests.py and commit the result")
        print(f"ok: {names} in sync (version {version})")
        return
    for path, text in targets:
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
    print(f"wrote {names} (version {version})")


if __name__ == "__main__":
    main()
