# Working on domino-ai-plugin

Instructions for agents and people changing **this repository**. Claude Code, Codex and
OpenCode all read this file. Rules for what a skill may tell an agent at runtime live in the
skills and in `CONTRIBUTING.md`.

## What this is

A Claude Code plugin (`.claude-plugin/plugin.json`, name `dominodatalab`) that is also an
Agent Plugins package (`plugin.json`, `mcp.json`) for ChatGPT and Codex. `scripts/build-openai.sh`
builds the OpenAI plugin-directory ZIP from `skills/` alone. Copilot, OpenCode and Antigravity
read the same agentskills.io layout from their own skills directories. Content here ships to
customer environments from a **public** repository. Three facts drive most rules below:

1. Installs from a git source (the Anthropic marketplace, `claude plugin marketplace add
   owner/repo`, the OpenAI directory) are copies that update only when the `plugin.json`
   `version` string changes, so a content change without a version change reaches none of
   them. A local-directory marketplace, which the Domino Workspace image uses, is read in place
   from its clone: a checkout there is the whole update (verified on Claude Code 2.1.294 by
   `scripts/verify-update-flow.sh`; re-run it when Claude Code changes).
2. One tree targets **Domino 6.3 (self-managed) and Domino Cloud**. Where the product differs,
   the skill branches at runtime; content is never forked per version.
3. The same skills run under Claude Code, ChatGPT and Codex, so skill text is provider-neutral
   ("the model", not "Claude"). Where a step is host-specific, the skill covers each host in one
   place. `scripts/lint-skills.py` enforces this (CONTRIBUTING standard 11).

## Layout

| Path | Contents |
|---|---|
| `skills/<name>/SKILL.md` | One skill per directory. Reference files sit beside `SKILL.md`. |
| `skills/<name>/assets/` | Templates a skill copies into the user's project (no `templates/` or `commands/` dirs) |
| `agents/`, `output-styles/` | Claude-only components; not in the OpenAI package |
| `hooks/` | Documentation only today; no `hooks.json` is shipped |
| `mcp-servers/` | Bundled MCP server, started by `.mcp.json` (Claude Code) and `mcp.json` (Codex) |
| `.claude-plugin/plugin.json` | Claude manifest and source of truth for name and `version`; see the rules below before touching it |
| `plugin.json` | Portable manifest plus OpenAI listing metadata; identity fields are copied by `scripts/sync-manifests.py` |
| `assets/` | OpenAI listing icon |
| `scripts/check-version.sh` | The CI version gate; run it locally before opening a PR |
| `scripts/build-openai.sh` | Builds the OpenAI ZIP; runs `sync-manifests.py --check` and `lint-skills.py` first |
| `scripts/verify-update-flow.sh` | Reproduces how Claude installs and updates this plugin |
| `.github/` | PR template, issue forms, `version-check.yml`, `tag-release.yml`, `CODEOWNERS` (one line per skill), `dependabot.yml` |
| `MAINTAINERS.md`, `SECURITY.md`, `SUPPORT.md` | Who is accountable, how to report vulnerabilities, where users get help |

## Branches and versions

| Branch | Role | Version rule |
|---|---|---|
| `develop` | Integration branch. All content PRs target it. | `plugin.json` `version` unchanged; CI fails a bump here |
| `main` | What ships. The Anthropic marketplace pins a commit on it; Domino Workspaces fall back to it | Changed only by the `develop` → `main` promotion PR, which bumps once and is tagged on merge |
| `release-X.Y` | One per shipped self-managed Domino line (`release-6.3`). Equals `main` while `main`'s floor is at or below X.Y: CI fast-forwards it on every push to `main` | Never commit to it while it follows `main`; after `main` moves past the line, cherry-picks only and the version stays on that line |

- Version format is `YYYY.XYY.N`, for example `2026.603.3`: year, Domino line as a floor
  written X×100+Y (`603` = 6.3 and later including Cloud), release counter. It is semver
  because the OpenAI portal requires it. `N` never repeats and never resets. Releases up to
  `2026.6-3.2` wrote the line as `6-3`.
  CI creates the tag `release-<version>` on merge to `main` or `release-*`. After a bump, run
  `scripts/sync-manifests.py` so `plugin.json` carries it too; CI fails if they drift.
- Never create a branch named `release-*` for anything but a real snapshot. The Domino
  Workspace updater resolves `release-X.Y.Z`, `release-X.Y`, `main` by exact name and would
  serve an integration branch to every matching cluster on its next launch.
- Repo mechanics only (`.github/`, `scripts/`, `CONTRIBUTING.md`, `README.md`, this file) may
  target `main` directly; they touch no content paths, so no bump and no tag.
- The marketplace pin advances on Anthropic's schedule, not on merge. After a release, check
  the `sha` for `dominodatalab` in `anthropics/claude-plugins-official`.
- Run `scripts/check-version.sh origin/<your PR's base branch>` before pushing. It applies
  the rules CI applies and prints why it fails.

## Requirements for skill content

Skills here have shipped invented REST routes, invented YAML formats and non-existent SDK
methods. Each was plausible and each was wrong, so verification is not optional. The detailed
standards are CONTRIBUTING.md 1, 4, 7, 9 and 10; the requirements are:

- Every REST route must exist in the published spec for each Domino version the skill claims:
  `https://docs.domino.ai/api-specs/6.3/public-api.json` and
  `https://docs.domino.ai/api-specs/cloud/public-api.json`. For a specific deployment, use its
  own reference at `https://<domino-domain>/docs` (`/docs/openapi/openapi-public.json`);
  `$DOMINO_API_HOST/assets/public-api.json` is a subset and misses whole services.
- `/v4/*` routes are the Domino Internal API (documented per cluster under `/docs`, absent from
  the Public API). Use the `/api/...` equivalent; where none exists, label the call
  "internal API, may change between Domino versions" where it appears.
- Product behaviour comes from docs.domino.ai (`/cloud/...` and `/6.3/...`; `llms.txt` indexes
  every page, and any page is Markdown with `.md` appended). Cite docs.domino.ai, not
  `docs.dominodatalab.com/en/latest`.
- `python-domino` methods must exist in `domino/domino.py` on `master` of
  `github.com/dominodatalab/python-domino`.
- Authentication: in a run, `DOMINO_API_PROXY` with no header or a bearer from
  `http://localhost:8899/access-token`; outside a run, a Personal Access Token or service
  account token. Legacy user API keys are described as deprecated, never recommended.
- Every `SKILL.md` must carry `compatibility:` frontmatter and open its body with
  `Applies to Domino 6.3 and Domino Cloud.` Add a "Which path applies" section, keyed on
  `GET $DOMINO_API_HOST/version`, only where behaviour differs between the two. Never tell an
  agent to reinstall, downgrade or repin the plugin.
- `name` in frontmatter must equal the directory name; `description` under 1,024 characters
  and about triggering only, nothing about versions; `SKILL.md` under 500 lines with detail in
  sibling files; cross-references by current skill names.
- No internal references in skill content: no Jira, Confluence, Slack or internal-repo links,
  ticket keys, or paths users cannot obtain. No placeholder hosts such as `your-domino.com`;
  use `$DOMINO_API_HOST` or the value an API response returns.

Existing skills predate these requirements and many violate them (missing
frontmatter, stale links). Fix violations in the files you are already changing. Do not sweep
the tree in an unrelated PR; tree-wide fixes have their own tracked work.

## Commands

```bash
claude plugin validate .claude-plugin/plugin.json     # plugin manifest and structure
claude plugin validate .                              # marketplace manifest (.claude-plugin/marketplace.json)
scripts/build-openai.sh                               # manifest sync, skill lint, OpenAI ZIP in dist/
scripts/check-version.sh origin/develop               # what CI will say (use your PR's base)
scripts/check-codeowners.py                           # every skill has its own CODEOWNERS line
scripts/verify-update-flow.sh                         # install/update behaviour (needs the claude CLI, ~2 min)
claude --plugin-dir .                                 # load this checkout in place; replaces a same-named installed plugin for the session
/reload-plugins                                       # inside a session, after editing a skill
```

Behaviour tests live in `evals/` (one directory per case) and run with `claude plugin eval`.
Each run is a real model call on your account, so iterate with one arm and one run:

```bash
claude plugin eval . --scaffold --allow-tools Write Edit --runs 1 --ablation none --no-publish
```

Drop `--runs 1 --ablation none` for the default three runs plus the no-plugin baseline before
trusting a change. When adding a skill, add a case whose prompt should trigger it.

## Pull requests

- Fill every section of `.github/PULL_REQUEST_TEMPLATE.md`. Under **Model attestation**,
  write the model identifier and tick neither box: the human who reviews and opens the PR
  ticks one. An agent never attests for a human.
- Base branch: `develop` for content, `main` for the promotion PR and repo mechanics.
- A new or renamed skill directory needs its own line in `.github/CODEOWNERS` in the same PR;
  `scripts/check-codeowners.py` fails CI otherwise.
- Merging needs the `version` check, one approving review, a code-owner review where
  `.github/CODEOWNERS` matches, and an up-to-date branch. When the base moves, rebase or use
  "Update branch".

## Things that will bite you

- Test changes with `claude --plugin-dir .`. A git-sourced install of this plugin is a copy that
  ignores your checkout until the version changes; a local-directory install reads its clone
  in place, so editing that clone changes the next session immediately.
- The Domino Workspace image installs this plugin from a local-directory marketplace, which is
  read in place. A release reaches a Workspace when its clone checks out the new commit: at
  launch on Domino 6.3 with `updateSkillsOnLaunch`, and only through a newer image on Domino
  Cloud. Laptops on the Anthropic marketplace get it once Anthropic advances its pin.
- `SKILL_AUDIT.md` is from May 2026 and stale; do not treat it as current.
- Every skill's directory name equals its frontmatter `name` (`skills/domino-jobs/` is
  `domino-jobs`), and `scripts/lint-skills.py` fails otherwise. This matters across hosts:
  Claude Code invokes a plugin skill by its directory name (`dominodatalab:domino-jobs`), Codex
  and Gemini CLI by `name`, and Agent Plugins clients skip a skill whose two differ. An agent's
  `skills:` preload list resolves the frontmatter `name`; an unknown name is skipped silently.
- `SKILL.md` stays at or under 8,000 bytes (lint-enforced): Codex truncates the rest when it
  loads the skill. Put detail in sibling reference files and link them from `SKILL.md`.
- `mcp-servers/domino_mcp_server` needs `mcp<2`; mcp 2.x renamed `FastMCP` and the server dies
  on import. Check it starts with `claude --plugin-dir . mcp list` (expect `✔ Connected`).

## Domino API, SDK, and platform skills

Before you write or change Domino API, SDK, app, extension, or governance automation in this repo:

1. Read **`skills/domino-api-intro/SKILL.md`** and apply its authentication rules.
2. Open sibling files in that folder when needed:
   - **`HOSTS.md`** for base URL and gateway vs public URL
   - **`LIMITS.md`** for pagination and legacy API key guidance
   - **`ERRORS.md`** for retries and known failure patterns
   - **`SDK-MAP.md`** to pick a domain skill
   - **`API-SPECS.md`** for OpenAPI files and route discovery
3. Follow https://docs.domino.ai/cloud/reference/api/domino-api-authentication for all HTTP auth (proxy, access token, PAT, service account). Legacy user API keys are described as deprecated, never recommended.
4. For API paths and pages, use [API-SPECS.md](skills/domino-api-intro/API-SPECS.md) (public routes section) before guessing routes.
5. Then use the relevant skill under `skills/` (python-sdk, apps, domino-governance, domino-extensions, and others).

This applies even when another Domino skill is already active. The intro skill takes precedence for auth, host, and retry rules.

Product doc links in new material: full **`https://docs.domino.ai/...`** URLs only.
