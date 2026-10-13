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
GEMINI_ALLOW_FILE = ROOT / "scripts" / "gemini-substitution.allow"
MAX_DESCRIPTION = 1024
# Codex truncates each plugin skill to 8,000 bytes when it loads it into the prompt
# (openai/codex codex-rs ext/skills host_prompt.rs). Keep SKILL.md under that and move detail
# into sibling reference files, which every host reads on demand.
MAX_SKILL_BYTES = 8000
# Gemini CLI rewrites every `${name}` in an extension's SKILL.md before the model sees it
# (extension-manager.ts, recursivelyHydrateStrings): its built-in variables, the value of every
# setting declared in gemini-extension.json, and every key of a trusted workspace's .env file.
# The last set is unbounded (a project .env can define any name), so SKILL.md may not contain
# `${` at all. Files that document product syntax written with `${...}` are listed in
# scripts/gemini-substitution.allow with a reason; even there, Gemini's own names and the
# declared settings stay forbidden, because those are substituted for every user.
GEMINI_BUILTINS = {"extensionPath", "workspacePath", "/", "pathSeparator"}
GEMINI_VAR = re.compile(r"\$\{([A-Za-z_/][A-Za-z0-9_]*|/)(?=[}:])")
BRACE = "${"
MAX_IDENTITY = 64
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)
LINK = re.compile(r"\]\(([^)#\s]+)")
CLAUDE = re.compile(r"claude", re.I)
# Portal review flags installs from moving refs; git sources must pin a full commit SHA.
GIT_SOURCE = re.compile(r"git\+[a-z]+://[^\s\"'#]+", re.I)
PINNED_SHA = re.compile(r"@[0-9a-f]{40}$")

# Content-noise rules, the mechanical part of CONTRIBUTING standards 12 (facts and instructions,
# no provenance) and 13 (what belongs in a skill). Checked line by line over every .md under
# skills/ and agents/ and over rules/domino.md. The error tier fails CI; the warn tier prints
# ::warning:: for a human to judge. Columns: id, label, pattern, flags, tier, standard, scope
# ("all", or "skill_md" for SKILL.md only), exempt (True: skip files in claude-mentions.allow,
# which may name models). Patterns match fixed collocations; a hit that is a false positive is
# fixed by tightening the pattern here, not by rewording the skill.
AGENTS = ROOT / "agents"
RULES_FILE = ROOT / "rules" / "domino.md"
REMOVED_SKILLS_FILE = ROOT / "scripts" / "removed-skills.txt"
DENYLIST = [
    ("L1", "provenance narrative",
     r"\b(live (test|records|run|call|behaviou?r)|test (cluster|deployment)|internal (Domino )?(test )?cluster|our (test|run|cluster|live)|no other credential existed|the audit (found|showed)|(verified|confirmed|validated|tested|smoke-tested|run|ran) live\b|(verified|confirmed|validated|tested) (on|against) (a |the |this )?(deployment|cluster|instance|DSE|Domino Cloud|Cloud|6\.\d)|from one deployment|one (Domino )?(Cloud )?cluster's reference|from the (Cloud/)?6\.4(\.0)? internal reference)",
     re.I, "error", 12, "all", False),
    ("L2", "'live' as an observation marker",
     r"(?<=; )live\b|\(live:|(?<!\()\blive\)|\blive \(Domino|a record live\b",
     0, "error", 12, "all", False),
    ("L3", "past-tense test log with a version",
     r"\b(returned|answered|appeared|listed|reported|came back|could set|crash-looped|was built|were absent|fired|went)\b[^.\n]{0,80}\b(on (Domino )?(Cloud )?6\.\d|on (a |the )?(6\.\d(\.\d)?|Cloud|DSE|test) deployment|from a DSE Workspace)\b|\bon (Domino )?Cloud 6\.\d[^.\n]{0,40}\b(returned|came back|created|reaches|reached)\b",
     re.I, "error", 12, "all", False),
    ("L4", "skill self-history",
     r"\b(earlier|previous|older|prior) (versions? of )?(this|the) skill\b|\bthis skill (previously|used to|no longer|now)\b|at the time this skill was written",
     re.I, "error", 13, "all", False),
    ("L5", "dated snapshot in parentheses",
     r"(?<!`)\([^()\n`]{0,40}\b(20\d\d-[01]\d-[0-3]\d|(January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d)\b[^()\n]{0,25}\)",
     0, "error", 12, "all", False),
    ("L6", "shouting label",
     r"\*\*(IMPORTANT|CRITICAL|NOTE|WARNING|MUST|NEVER|ALWAYS)\*\*|^\s*#\s*(IMPORTANT|CRITICAL|WARNING)\b",
     0, "error", 13, "all", False),
    ("L7", "process jargon",
     r"\b(this PR|PR #\d+|the audit (found|showed)|coverage audit|workstream|release candidate|weak[- ]model|grader|E2E)\b",
     0, "error", 13, "all", False),
    ("L7", "model name (process jargon)",
     r"\b(Haiku|Sonnet|Opus|Fable|Astra)\b",
     0, "error", 13, "all", True),
    ("L8", "first-person provenance",
     r"\b(we|our team|I) (tested|verified|ran|saw|found|observed|confirmed|checked)\b",
     re.I, "error", 12, "all", False),
    ("L9", "when-to-use heading; that guidance belongs in the description",
     r"^##+ (Activation|When to use( this skill)?)\s*$",
     0, "error", 13, "skill_md", False),
    ("L10", "self-describing preamble",
     r"^(This (skill|guide|document|file) (provides|enables|covers|explains|describes|is for)|Use this skill when)\b",
     0, "error", 13, "all", False),
    ("L5b", "'today' qualifier",
     r"\btoday\)",
     0, "warn", 13, "all", False),
    ("L11", "observed timing",
     r"\b(in|within|after|takes?|took|later|reaches \w+ in) about \d+(\.\d+)? ?(seconds|s|minutes|min)\b|\bevery \d+ seconds or so\b|\bwithin seconds\b|\bseconds? later\b",
     re.I, "warn", 12, "all", False),
    ("L12", "stage label",
     r"\b(early access|coming soon|roadmap|in a future release)\b|\(preview\)",
     re.I, "warn", 13, "all", False),
    ("L14", "smoke test",
     r"\bSmoke[- ]test\b",
     re.I, "warn", 12, "all", False),
    ("L15", "spec attestation",
     r"\b(exists?|is|are|present) (present )?(,? with the same bodies,? )?in both (public |published )?(API )?specs\b|\b(from|taken from) (both|the) published specs?\b|\(6\.3\.1 and 6\.4\.0\)|\bidentical in both public API specs\b|\(cluster reference\)|on the cluster reference\b",
     re.I, "warn", 12, "all", False),
]


def load_allowlist(path: Path) -> set[str]:
    lines = path.read_text().splitlines() if path.exists() else []
    return {ln.split("#", 1)[0].strip() for ln in lines if ln.split("#", 1)[0].strip()}


def gemini_substituted_names() -> set[str]:
    names = set(GEMINI_BUILTINS)
    manifest = ROOT / "gemini-extension.json"
    if manifest.is_file():
        for setting in json.loads(manifest.read_text()).get("settings") or []:
            if isinstance(setting, dict) and setting.get("envVar"):
                names.add(setting["envVar"])
    return names


def lint_content(errors: list[str], warnings: list[str], claude_allowed: set[str]) -> int:
    """DENYLIST over skills/, agents/ and rules/domino.md, plus L16 (names of removed skills,
    backticked or as a path, under skills/, agents/ and README.md). Returns the files checked."""
    paths = [p for d in (SKILLS, AGENTS) if d.is_dir() for p in sorted(d.rglob("*.md"))]
    if RULES_FILE.is_file():
        paths.append(RULES_FILE)
    compiled = [(rid, label, re.compile(pat, flags), tier, std, scope, exempt)
                for rid, label, pat, flags, tier, std, scope, exempt in DENYLIST]
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").split("\n")
        for rid, label, rx, tier, std, scope, exempt in compiled:
            if scope == "skill_md" and path.name != "SKILL.md":
                continue
            if exempt and rel in claude_allowed:
                continue
            for n, line in enumerate(lines, 1):
                hit = rx.search(line)
                if hit:
                    msg = (f"{rel}:{n}: {rid} {label}: '{hit.group(0).strip()[:70]}' "
                           f"(CONTRIBUTING standard {std})")
                    (errors if tier == "error" else warnings).append(msg)
    removed = load_allowlist(REMOVED_SKILLS_FILE)
    readme = ROOT / "README.md"
    targets = [p for p in paths if p != RULES_FILE] + ([readme] if readme.is_file() else [])
    for name in sorted(removed):
        rx = re.compile(rf"`{re.escape(name)}`|(?<![A-Za-z0-9_-]){re.escape(name)}/")
        for path in targets:
            rel = path.relative_to(ROOT).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
                if rx.search(line):
                    errors.append(f"{rel}:{n}: L16 removed skill name '{name}' "
                                  f"({REMOVED_SKILLS_FILE.relative_to(ROOT)}); point at the current "
                                  f"skill (CONTRIBUTING standard 13)")
    return len(paths)


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    plugin = json.loads((ROOT / "plugin.json").read_text())["name"]
    substituted = gemini_substituted_names()
    allowed = load_allowlist(ALLOW_FILE)
    gemini_allowed = load_allowlist(GEMINI_ALLOW_FILE)
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
        skill_text = manifest.read_text(encoding="utf-8")
        skill_rel = f"{rel.as_posix()}/SKILL.md"
        if skill_rel in gemini_allowed:
            for var in GEMINI_VAR.findall(skill_text):
                if var in substituted:
                    errors.append(f"{skill_rel}: '${{{var}}}' is substituted by Gemini CLI for every "
                                  f"user (built-in variable or declared setting); write it without "
                                  f"braces or rephrase")
        elif BRACE in skill_text:
            errors.append(f"{skill_rel}: contains '${{': Gemini CLI substitutes `${{name}}` in skill "
                          f"text before the model reads it (its variables, the declared settings, and "
                          f"any key in a trusted workspace's .env). Rephrase, move the example into a "
                          f"sibling file, or list the file in "
                          f"{GEMINI_ALLOW_FILE.relative_to(ROOT)} with a reason")

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
    # A skill may drop `${` in its own PR; a stale entry here is a note so that merge order
    # between content PRs never breaks the integration branch.
    for stale in sorted(gemini_allowed):
        path = ROOT / stale
        if not path.exists() or BRACE not in path.read_text(encoding="utf-8"):
            notes.append(f"{GEMINI_ALLOW_FILE.relative_to(ROOT)}: '{stale}' no longer contains "
                         f"'${{'; drop the entry")

    content_files = lint_content(errors, warnings, allowed)
    rules_count = lint_rules(errors)

    for note in notes:
        print(f"::notice::{note}")
    for warning in warnings:
        print(f"::warning::{warning}")
    for err in errors:
        print(f"::error::{err}")
    if errors:
        print(f"{len(errors)} problem(s) in skills/", file=sys.stderr)
        return 1
    print(f"ok: {len(seen)} skills valid ({cross_links} links between skills); "
          f"{rules_count} always-on rules file(s) valid; content rules clean over "
          f"{content_files} files ({len(warnings)} warning(s))")
    return 0


RULES = ROOT / "rules"
# rules/*.md is loaded into every session of every user (Claude Code session-start hook, Gemini CLI
# contextFileName, Antigravity always-on rule), and its lead section is the bundled MCP server's
# instructions, which Codex truncates at 1,000 bytes. Keep it short, plain and host-neutral.
MAX_RULES_CHARS = 2600
MAX_RULES_LEAD_BYTES = 900
# Product names, matched case-sensitively so ordinary words ("a pagination cursor") pass.
HOST_NAMES = re.compile(r"\b(Claude|Codex|ChatGPT|Gemini|Antigravity|Copilot|Cursor)\b")


def lint_rules(errors: list[str]) -> int:
    if not RULES.is_dir():
        return 0
    files = sorted(RULES.glob("*.md"))
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            errors.append(f"{rel}: must be ASCII only (some hosts read it without a UTF-8 BOM)")
            text = raw.decode("utf-8", "replace")
        if "\r" in text:
            errors.append(f"{rel}: must use LF line endings (.gitattributes sets eol=lf for rules/*.md)")
            text = text.replace("\r\n", "\n")
        m = FRONTMATTER.match(text)
        if not m:
            errors.append(f"{rel}: must start with YAML front matter between --- lines")
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: front matter is not valid YAML: {exc}")
            continue
        if not isinstance(meta, dict):
            errors.append(f"{rel}: front matter must be a mapping with `trigger` and `description`")
            continue
        if meta.get("trigger") != "always_on":
            errors.append(f"{rel}: front matter needs `trigger: always_on`")
        if meta.get("alwaysApply") is not True:
            errors.append(f"{rel}: front matter needs `alwaysApply: true` (Cursor's always-on key; it ignores `trigger`)")
        if not meta.get("description"):
            errors.append(f"{rel}: front matter needs a `description`")
        body = m.group(2)
        if len(text) > MAX_RULES_CHARS:
            errors.append(f"{rel}: {len(text)} characters exceeds {MAX_RULES_CHARS}; every session pays for it")
        lead = body.split("\n## ", 1)[0].strip()
        lead_bytes = len(lead.encode("utf-8"))
        if lead_bytes > MAX_RULES_LEAD_BYTES:
            errors.append(f"{rel}: lead section (before the first ## heading) is {lead_bytes} bytes; "
                          f"keep it under {MAX_RULES_LEAD_BYTES}, since it is also the MCP server instructions")
        if "${" in text:
            errors.append(f"{rel}: must not contain '${{'; hosts substitute variables in context files")
        neutral = f"{meta.get('description') or ''}\n{body}"   # hosts show the description too
        for name in sorted({mm.group(0) for mm in HOST_NAMES.finditer(neutral)}):
            errors.append(f"{rel}: names the host '{name}'; keep always-on text host-neutral")
    return len(files)


if __name__ == "__main__":
    sys.exit(main())
