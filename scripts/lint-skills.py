#!/usr/bin/env python3
# Validates skills/ against the rules both Claude Code and the OpenAI plugin portal enforce.
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml (or run via `uv run --with pyyaml`)")

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
ALLOW_FILE = ROOT / "scripts" / "claude-mentions.allow"
MAX_DESCRIPTION = 1024
# Codex truncates each plugin skill to 8,000 bytes when it loads it into the prompt
# (openai/codex codex-rs ext/skills host_prompt.rs). Keep SKILL.md under that and move detail
# into sibling reference files, which every host reads on demand.
MAX_SKILL_BYTES = 8000
# Gemini CLI substitutes these into extension SKILL.md text before the model sees it, plus the
# value of every environment variable declared in gemini-extension.json `settings`. A literal
# reference to a declared credential would put the user's secret into the prompt.
GEMINI_BUILTINS = {"extensionPath", "workspacePath", "/", "pathSeparator"}
GEMINI_VAR = re.compile(r"\$\{([A-Za-z_/][A-Za-z0-9_]*|/)(?=[}:])")
MAX_IDENTITY = 64
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)
LINK = re.compile(r"\]\(([^)#\s]+)")
CLAUDE = re.compile(r"claude", re.I)
# Portal review flags installs from moving refs; git sources must pin a full commit SHA.
GIT_SOURCE = re.compile(r"git\+[a-z]+://[^\s\"'#]+", re.I)
PINNED_SHA = re.compile(r"@[0-9a-f]{40}$")


def load_allowlist() -> set[str]:
    lines = ALLOW_FILE.read_text().splitlines() if ALLOW_FILE.exists() else []
    return {ln.split("#", 1)[0].strip() for ln in lines if ln.split("#", 1)[0].strip()}


def gemini_substituted_names() -> set[str]:
    names = set(GEMINI_BUILTINS)
    manifest = ROOT / "gemini-extension.json"
    if manifest.is_file():
        for setting in json.loads(manifest.read_text()).get("settings") or []:
            if isinstance(setting, dict) and setting.get("envVar"):
                names.add(setting["envVar"])
    return names


def main() -> int:
    errors: list[str] = []
    plugin = json.loads((ROOT / "plugin.json").read_text())["name"]
    substituted = gemini_substituted_names()
    allowed = load_allowlist()
    seen: dict[str, Path] = {}
    cross_links = 0

    for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        rel = skill_dir.relative_to(ROOT)
        if skill_dir.name.startswith("."):
            errors.append(f"{rel}: skill directory names must not start with '.'")
        manifest = skill_dir / "SKILL.md"
        if not manifest.is_file():
            errors.append(f"{rel}: missing SKILL.md")
            continue
        m = FRONTMATTER.match(manifest.read_text(encoding="utf-8"))
        if not m:
            errors.append(f"{rel}/SKILL.md: must start with YAML front matter between --- lines")
            continue
        try:
            meta = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            errors.append(f"{rel}/SKILL.md: front matter is not valid YAML: {exc}")
            continue
        if not isinstance(meta, dict):
            errors.append(f"{rel}/SKILL.md: front matter must be a mapping")
            continue
        name, description = meta.get("name"), meta.get("description")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{rel}/SKILL.md: `name` is required")
        else:
            if name in seen:
                errors.append(f"{rel}/SKILL.md: name '{name}' duplicates {seen[name]}")
            seen[name] = rel
            if name != skill_dir.name:
                errors.append(f"{rel}/SKILL.md: name '{name}' must equal the directory name "
                              f"'{skill_dir.name}' (agentskills.io; Agent Plugins clients skip "
                              f"skills that differ)")
            if len(f"{plugin}:{name}") > MAX_IDENTITY:
                errors.append(f"{rel}/SKILL.md: '{plugin}:{name}' exceeds {MAX_IDENTITY} chars")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{rel}/SKILL.md: `description` is required")
        elif len(description) > MAX_DESCRIPTION:
            errors.append(f"{rel}/SKILL.md: description is {len(description)} chars "
                          f"(max {MAX_DESCRIPTION})")
        if not m.group(2).strip():
            errors.append(f"{rel}/SKILL.md: body must not be empty")
        size = manifest.stat().st_size
        if size > MAX_SKILL_BYTES:
            errors.append(f"{rel}/SKILL.md: {size} bytes exceeds {MAX_SKILL_BYTES} (Codex truncates "
                          f"the rest); move detail into sibling reference files")
        for var in GEMINI_VAR.findall(manifest.read_text(encoding="utf-8")):
            if var in substituted:
                errors.append(f"{rel}/SKILL.md: '${{{var}}}' is substituted by Gemini CLI before the "
                              f"model reads the skill; write it without braces or rephrase")

        for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
            try:
                body = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for src in GIT_SOURCE.findall(body):
                if not PINNED_SHA.search(src):
                    errors.append(f"{path.relative_to(ROOT)}: '{src}' is a mutable git source; "
                                  f"use a PyPI release or pin a commit SHA")

        for doc in sorted(skill_dir.rglob("*.md")):
            text = doc.read_text(encoding="utf-8")
            doc_rel = doc.relative_to(ROOT).as_posix()
            # The OpenAI package ships skills/ without the rest of the repo, so links must stay in it.
            for target in LINK.findall(text):
                if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                    continue
                resolved = (doc.parent / target).resolve()
                if not resolved.is_relative_to(SKILLS.resolve()):
                    errors.append(f"{doc_rel}: link '{target}' points outside skills/")
                elif not resolved.exists():
                    errors.append(f"{doc_rel}: link '{target}' does not exist")
                elif not resolved.is_relative_to(skill_dir.resolve()):
                    cross_links += 1
            if CLAUDE.search(text) and doc_rel not in allowed:
                errors.append(f"{doc_rel}: mentions Claude; use provider-neutral wording or add "
                              f"the file to {ALLOW_FILE.relative_to(ROOT)} with a reason")

    for stale in sorted(allowed):
        path = ROOT / stale
        if not path.exists() or not CLAUDE.search(path.read_text(encoding="utf-8")):
            errors.append(f"{ALLOW_FILE.relative_to(ROOT)}: '{stale}' no longer needs an entry")

    for err in errors:
        print(f"::error::{err}")
    if errors:
        print(f"{len(errors)} problem(s) in skills/", file=sys.stderr)
        return 1
    print(f"ok: {len(seen)} skills valid ({cross_links} links between skills)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
