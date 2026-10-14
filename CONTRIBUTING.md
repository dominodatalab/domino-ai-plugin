# Contributing to Domino Data Lab Plugin

Thank you for your interest in contributing to the Domino Data Lab Plugin for Claude Code,
ChatGPT, Codex, Cursor, Gemini CLI, and Antigravity. One source tree serves every host; see
README "What ships where".

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a feature branch

```bash
git clone https://github.com/YOUR_USERNAME/domino-ai-plugin.git
cd domino-ai-plugin
git checkout -b feature/your-feature-name
```

## Development Setup

Test the plugin locally with Claude Code:

```bash
claude --plugin-dir /path/to/domino-ai-plugin
```

Test it with Codex or the ChatGPT desktop app from a local marketplace (README "Installation:
Codex and the ChatGPT desktop app"), and check the OpenAI package builds:

```bash
scripts/build-openai.sh   # runs the manifest sync check and the skill linter first
```

Validate the other manifests from the same checkout:

```bash
npx -y @google/gemini-cli@0.63.0 extensions validate .   # Gemini CLI extension (gemini-extension.json)
agy plugin validate .                              # Antigravity (plugin.json, skills/, agents/)
```

## Plugin Structure

```
domino-ai-plugin/
├── .claude-plugin/plugin.json   # Claude manifest; source of truth for name, version, description
├── plugin.json                  # Portable (Agent Plugins) manifest + OpenAI listing (synced)
├── .cursor-plugin/plugin.json   # Cursor manifest (synced)
├── gemini-extension.json        # Gemini CLI extension manifest (synced)
├── .mcp.json / mcp.json         # MCP config for Claude Code / for Codex (portable)
├── .cursor-plugin/mcp.json      # MCP config for Cursor; mcp_config.json registers the docs server for Antigravity
├── rules/domino.md              # Always-on guidance (Claude Code hook, Cursor rule, Gemini CLI context file)
├── skills/                      # Shared skills; ship to every host
├── mcp-servers/                 # Vendored Domino MCP server
├── agents/                      # Subagents: thin routers to skills (Claude Code; Cursor reads them too)
├── output-styles/               # Custom output styles (Claude Code only)
├── hooks/                       # Hook documentation only; no hooks.json is shipped
├── evals/                       # claude plugin eval cases; evals/e2e/ is the live end-to-end harness
└── scripts/                     # Build, lint, sync, and version checks
```

There is no `commands/` or `templates/` directory: OpenAI plugins can't load slash commands,
so user-invoked workflows are skills, and their templates live in the skill's `assets/`.

## Contribution Guidelines

### Adding a New Skill

1. Create a new directory under `skills/`. Its name must equal the `name` in the frontmatter.
2. Add a line for it to `.github/CODEOWNERS` naming its owners (`scripts/check-codeowners.py`
   fails CI otherwise; see [MAINTAINERS.md](MAINTAINERS.md) for how owners are chosen).
3. Add a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: domino-your-skill
description: Brief description of what this skill does. Include trigger keywords.
compatibility: Domino 6.3 and Domino Cloud. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a Personal Access Token.
---

# Your Skill Name

Applies to Domino 6.3 and Domino Cloud.

## Description
Detailed description of the skill...
```

The directory name **must equal** `name` (agentskills.io rule; Codex and OpenCode key on
`name`, Antigravity on the folder).

4. Keep SKILL.md under 500 lines; use supporting files for details. Keep every file the skill
   needs (references, scripts, templates under `assets/`) inside the skill's own directory.
5. Follow the [Skill Authoring Standards](#skill-authoring-standards) — auth
   pattern, host env vars, no `python-domino` SDK, verified endpoints,
   smoke-tested payloads, provider-neutral wording, and only what belongs in a skill
   (standard 13)
6. Run `uv run --with pyyaml python scripts/lint-skills.py`

### Adding a User-Invoked Workflow

Write it as a skill, not a slash command: OpenAI plugins can't load `commands/`, and Claude Code
exposes plugin skills as `/dominodatalab:<skill-name>` anyway. Give it a description that names
the request it answers (for example "Use when the user asks to scaffold a new Domino app"), list
the inputs to collect, and put any template files in the skill's `assets/` folder. See
`skills/domino-app-init/` for an example.

### Adding a New Agent

1. Create `agents/_<agent-name>.md`. The leading underscore keeps Gemini CLI from loading a
   Claude-format file (it skips `_`-prefixed files in `agents/`, and its schema would reject
   `skills:`); the agent's name comes from the frontmatter, not the file name.
2. Include full frontmatter:

```yaml
---
name: domino-agent-name
description: When to use this agent. Use PROACTIVELY when...
tools: Read, Edit, Write, Bash, Grep, Glob, Skill
model: inherit
skills:
  - domino-skill-one
  - domino-skill-two
---
```

`skills:` preloads the full text of each named skill into the agent's context (Claude Code
2.0.43 or later); `Skill` in `tools:` lets the agent load any other plugin skill on demand
(2.1.133 or later), and `mcp__plugin_dominodatalab_<server>__*` grants it the plugin's MCP
tools. Agents are a Claude Code component and aren't in the OpenAI package; Cursor loads them
as plain prompts without `skills:` or `tools:`, and Gemini CLI skips them. So an agent is a
thin router: it names the skills that apply and the order to apply them, and holds no
procedure of its own. Anything users on other hosts also need goes into a skill.

## Skill Authoring Standards

These rules came out of PR #8 (NetApp Volumes skill) review and the September 2026
coverage audit. Skim them before authoring or editing a `SKILL.md`.

### 1. Authenticate with the local token endpoint, not API keys

**NEVER use `DOMINO_USER_API_KEY`, not even as a fallback.** It is not a
secure pattern. The API keys are deprecated and will be removed in a future
Domino release. The local access-token endpoint is Domino's forward-looking
auth architecture for in-cluster execution.

Skills running inside Domino (workspace, job, app, model) should fetch a
short-lived bearer token from the local sidecar, or, where the platform injects
`DOMINO_API_PROXY` (JWT credential propagation), call `$DOMINO_API_PROXY/<path>` with
no `Authorization` header at all; the proxy adds the starting user's token. Outside a
run (laptop, CI) use a Personal Access Token or service-account token as a bearer. See
https://docs.domino.ai/cloud/reference/api/domino-api-authentication.

Do:

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
curl -H "Authorization: Bearer $TOKEN" "$DOMINO_API_HOST/api/..."
```

Don't (deprecated, will be removed):

```bash
curl -H "X-Domino-Api-Key: $DOMINO_USER_API_KEY" "$DOMINO_API_HOST/api/..."
```

Why: tokens fetched from the local endpoint are short-lived and scoped to
the current workspace/job. API keys are long-lived, leak into shell history
and process listings, tie requests to the user rather than the execution,
and are slated for removal. (PR #8: *"we should remove all the stuff here
about using X-Domino-Api-Key. We should have these examples fetch tokens
from localhost:8899/access-token"*.)

### 2. Use Domino-injected environment variables for hosts

| Variable | Use for |
|----------|---------|
| `$DOMINO_API_HOST` | Platform REST API (most endpoints) |
| `$DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` | remotefs / NetApp APIs |
| `$DOMINO_PROJECT_ID`, `$DOMINO_PROJECT_OWNER`, `$DOMINO_PROJECT_NAME` | Project identifiers |
| `$DOMINO_RUN_ID` | Current job/workspace run ID |

Don't write `https://your-domino.com`, `<domino-host>`, or
`<your-domino-instance>` placeholders — they fail when the user copy-pastes
and they signal the example was never run.

### 3. Don't use the `python-domino` SDK in examples

The `python-domino` package wraps older API versions and lacks coverage for
newer features (e.g. NetApp volume mounts on jobs). Show REST + `curl` (or
`requests`) instead. (PR #8: *"a lot of its methods use older APIs and won't
support things like specifying NetApp volume mounts"*.)

Exception: the `domino-data-sdk` and `domino-python-sdk` skills exist specifically to
document the SDK. They should clearly mark which methods are still supported
vs deprecated. All other skills should not pull `from domino import Domino`
into their examples.

### 4. Verify endpoints against the API specs before writing examples

Don't guess endpoints from memory, and don't carry them forward from older skills. Sources,
in order:

1. **Published Public API specs, both supported targets.** A route must exist in the spec for
   every Domino version the skill claims:
   `https://docs.domino.ai/api-specs/6.3/public-api.json` and
   `https://docs.domino.ai/api-specs/cloud/public-api.json`.
2. **A deployment's own API reference** at `https://<domino-domain>/docs` (Scalar,
   unauthenticated, available from Domino 6.3). It serves one OpenAPI document per service
   under `/docs/openapi/`: `openapi-public.json` is that deployment's full Public API;
   `openapi-internal.json` is the Domino Internal API (the `/v4/*` routes); governance,
   taxonomy, model monitoring, NetApp volumes and dataset files each have their own file.
   `$DOMINO_API_HOST/assets/public-api.json` is only a subset of the Public API and omits
   those services; do not treat it as complete.
3. **Product docs** on docs.domino.ai for workflow context and field meaning (`/cloud/...`
   and `/6.3/...`; `https://docs.domino.ai/llms.txt` indexes every page, and any page is
   readable as Markdown by appending `.md`).

```bash
# Published spec, Cloud target (swap cloud for 6.3):
curl -s https://docs.domino.ai/api-specs/cloud/public-api.json | jq '.paths | keys[]' | grep governance
# A specific deployment's complete Public API and its per-service documents:
curl -s https://<domino-domain>/docs/configuration.json | jq '.sources[] | {title, url}'
curl -s https://<domino-domain>/docs/openapi/openapi-public.json | jq '.paths | keys | length'
```

Do not derive hosts from the JWT `iss` claim, and do not cite `docs.dominodatalab.com`;
those patterns are what earlier skills got wrong. PR #8 caught a wrong jobs endpoint
(`/api/jobs/v1/runs` → `/api/jobs/v1/jobs`) carried forward from an older version; the
2026 audit found invented routes in six more skills.

### 5. Smoke-test payloads against the live API

Required fields and field names drift between releases. Examples from PR #8
that took multiple iterations to get right:

- `commandToRun` → `runCommand`
- `externalVolumeMounts` → `netAppVolumeIds`
- `hardwareTierId` → `hardwareTier`: on `POST /api/jobs/v1/jobs` only `projectId` and
  `runCommand` are required; `environmentId` and `hardwareTier` are optional and default to
  the project's environment and hardware tier (both published specs agree)

Run each documented payload at least once against a live Domino instance and
confirm a 2xx before merging. Note your test result (status code, any
clean-up steps) in the PR description.

### 6. `.gitignore` edits are additive

If a PR removes lines from `.gitignore`, justify it in the PR description.
Accidental removals of existing rules will be flagged in review.

### 7. Declare which Domino versions a skill applies to

The plugin targets **Domino 6.3 (self-managed)** and **Domino Cloud**, and `main` must be
correct for both. Every `SKILL.md`:

- carries a `compatibility:` frontmatter field (agentskills.io optional field, ≤ 500
  characters), for example
  `compatibility: Domino 6.3 and Domino Cloud. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a Personal Access Token.`
- opens its body with a one-line scope statement: `Applies to Domino 6.3 and Domino Cloud.`
- if behaviour genuinely differs between the two targets, includes a short **"Which path
  applies"** section that reads `GET $DOMINO_API_HOST/version` and branches on the result.
  Only add this where behaviour differs; do not add it everywhere.
- never tells the agent to reinstall, downgrade or repin the plugin. If the deployment is
  older than 6.3, say the skill targets 6.3 and later and point to
  `docs.dominodatalab.com` for that version.

Verify cited API routes against **both** published specs:
`https://docs.domino.ai/api-specs/6.3/public-api.json` and
`https://docs.domino.ai/api-specs/cloud/public-api.json`. Every Domino deployment from 6.3
also serves its own cluster-specific API reference at `https://<domino-domain>/docs`
(Scalar, unauthenticated), with one OpenAPI document per service under
`/docs/openapi/`: `openapi-public.json` is the deployment's Public API, and
`openapi-internal.json` is the **Domino Internal API**, where the `/v4/*` routes live.
`$DOMINO_API_HOST/assets/public-api.json` is only a subset of the public one and omits
governance, taxonomy, model monitoring, NetApp volumes and dataset file routes, so do not
treat it as complete. Routes that exist only in the Internal API (`/v4/*`) are not part of
the Public API and are not versioned for external use: prefer the `/api/...` equivalent,
and where none exists label the call `(non-public route; may change in a future Domino version)`
at the point of use, linking the canonical note in `skills/domino-api-intro/SKILL.md` ("Route
types") from any file that does not already point to that skill. The
verified divergence between the two targets is recorded in `coverage/COMPAT.md` (maintainers’ audit workspace, not yet in this repo).

Nothing about versions goes in `description`; it is loaded for every skill on every turn
and exists for triggering only.

### 8. Author skill content with a Fable-class or Astra-class model, and attest to it

Skill content is instructions that another model will follow. Authoring it with a weaker
model produces plausible-looking procedure that is wrong in the details, which is exactly
the failure the coverage audit found across the repo (invented SDK methods, invented YAML
formats, routes that do not exist).

- New skills and substantive rewrites **must** be authored with a Fable-class or
  Astra-class model. Drafting with a smaller model and then polishing does not qualify.
- The PR template asks for the model identifier and a human attestation. The person
  opening the PR is attesting; do not have an agent tick the box.
- Small edits to existing content (a corrected field name, a fixed link) do not require
  the attestation, but still require verification against the spec and SDK source.

### 9. Keep internal references out of a public repository

This repository is public and its skills are installed into customer environments. Skill
content must not contain links to Jira, Confluence, Slack or internal repositories, ticket
keys, internal ranking artefacts, or paths to scripts users cannot obtain. If an example
script is worth citing, add it to the repo under the skill (for example
`skills/<name>/examples/`).

### 10. Bump `plugin.json` on every content change, using the release scheme

Installs from a git source (the Anthropic marketplace, a marketplace added as `owner/repo`, the
OpenAI directory) are copies that update only when the `plugin.json` `version` string changes.
Any change under `skills/`, `agents/`, `commands/`, `templates/`,
`mcp-servers/`, `output-styles/`, `hooks/`, `rules/`, `assets/`, `bin/`, `workflows/`,
`themes/`, `monitors/`, `.agents/`, `.cursor-plugin/`, `.mcp.json`, `mcp.json`,
`mcp_config.json`, `gemini-extension.json`, `.lsp.json`, `settings.json`,
`.claude-plugin/marketplace.json` or either `plugin.json` must
therefore bump `version` **when it reaches `main`**, or nothing reaches installed copies
(`scripts/check-version.sh` holds the authoritative list).
Feature PRs land on `develop` with the version untouched; the promotion PR from `develop` to
`main` carries the bump. CI (`scripts/check-version.sh`) rejects a promotion without a bump
and a `develop` PR with one.

The version is **`YYYY.XYY.N`**, for example `2026.603.3`. It is valid semver because the
OpenAI portal accepts nothing else, and all four manifests carry the same string:

| Part | Meaning |
|---|---|
| `YYYY` | Year of the release. |
| `XYY` | The Domino line the content is correct for, as X×100+Y (`603` is Domino 6.3, `610` would be 6.10), as a **floor**: `603` means Domino 6.3 and later, including Domino Cloud. `main` carries the current floor. |
| `N` | Skill release counter. Increases with every release on that line, is never reused, and is **not** reset by the year (`2026.603.14` is followed by `2027.603.15`). |

Releases up to `2026.6-3.2` wrote the line as `X-Y`; `2026.603.3` is the same scheme in
semver form, and `scripts/check-version.sh` still reads the old form on a base branch. A release
candidate adds the semver pre-release suffix `-rc.M` and lives only on an `rc/<YYYY.XYY.N>`
branch; see [Release candidates](#release-candidates).

The git tag `release-YYYY.XYY.N` is created automatically from the manifest on every push to
`main` or a `release-*` branch (`.github/workflows/tag-release.yml`), so tag and manifest
always agree. Plugin version is independent of Domino's own version numbers; the line states
compatibility, not identity.

Bump the version only in `.claude-plugin/plugin.json`, then run `scripts/sync-manifests.py` to
copy it into the portable `plugin.json`, `.cursor-plugin/plugin.json` and
`gemini-extension.json`. CI fails if any of them drifts.

### 11. Write skills provider-neutral

Skills ship to Claude Code, ChatGPT, Codex, Cursor, Gemini CLI and Antigravity. Say "the model" or "the assistant", not
"Claude", and don't depend on one host's tools (for example a named user-input tool). When an
instruction really differs per host, such as which instructions file or MCP config to write,
give a variant for each host in one place (see "Host-specific files" in
`skills/domino-ui-bootstrap/SKILL.md`). `scripts/lint-skills.py` fails on any skill file that
mentions Claude unless it is listed in `scripts/claude-mentions.allow` with a reason; Claude as
a model name in an LLM example is a valid reason. It also fails on any `${` in a `SKILL.md`:
Gemini CLI rewrites `${name}` in skill text with its own variables, the extension's declared
settings and every key of a trusted workspace's `.env`. Put such examples in a sibling file, or
list the file in `scripts/gemini-substitution.allow` with a reason when the braces are product
syntax (Launcher `${param}` placeholders).

### 12. State facts and instructions only, no provenance

Skill content states facts and instructions only: no provenance (how, when or where something
was verified, audits, reviews, test clusters). Put verification evidence in the PR description.
A skill says what is true and what to do ("Starting a stopped Model API version returns 400;
restart it in the UI"), never how that was learned ("our live test showed", "verified on an
internal cluster", "the audit found"). Where real uncertainty changes what the agent should do,
state it as reader guidance ("if this returns 404, confirm the route in your deployment's
`/docs`"), not as a test log. Version facts stay as facts ("on Domino 6.4 the response is X"),
and the labels "non-public route; may change in a future Domino version" and "on 6.3, confirm in your
deployment's `/docs`" stay.

### 13. What belongs in a skill

A skill is read by a model in the middle of a task, in a context window it shares with the
user's files and conversation, so every sentence costs attention and every stale one misleads.
Write and revise skills with the `skill-creator` skill from Anthropic's `claude-plugins-official`
marketplace (`claude plugin install skill-creator@claude-plugins-official`, then `/skill-creator`):
its Skill Writing Guide and "How to think about improvements" are the house style
here (imperative instructions; progressive disclosure, so `SKILL.md` carries the workflow and
reference files carry the detail; the reason behind each instruction instead of all-caps MUSTs,
because a model that knows why handles the case the text did not foresee).

Belongs in a skill:

- Facts the model acts on: routes with method and the fields that matter, config formats,
  paths, environment variables, limits and defaults.
- Steps in the order the model performs them, in the imperative.
- Real constraints, and the decision rules for choosing between options ("if
  `DOMINO_API_PROXY` is set, call it with no header; otherwise send a bearer token").
- Short reasons that change behaviour ("listen on `0.0.0.0:8888`; the proxy reaches nothing
  else").
- Reader guidance where genuine uncertainty changes the next step (standard 12).

Does not belong, because it costs tokens, dates fast or sends the model the wrong way:

- Provenance (standard 12) and change history: "now", "no longer", "previously", "was fixed",
  "as of this release". The model acts on the present state; history lives in git.
- Project and process jargon: PR, audit, round, release candidate, E2E, harness, eval, ticket
  keys. They mean nothing to the user or the model.
- Ids, hashes, timestamps or error text copied from a test run.
- Long rationale, debate or alternatives considered; empty hedging ("it may be possible that").
- A paragraph that another skill already owns: link the canonical place (`domino-api-intro`
  for authentication and hosts) instead of repeating it.
- Tangents outside what the `description` triggers on; host-specific asides beyond standard 11.
- Marketing, all-caps emphasis, roadmap, "early access" or "coming soon".

When-to-use guidance goes in the `description` (standard 7), not the body. Before opening a PR,
read the draft as the model would and delete every sentence that does not change what it does
next. `scripts/lint-skills.py` enforces the mechanical part of standards 12 and 13 as rules L1
to L16 over `skills/`, `agents/` and `rules/domino.md` (provenance and "live" markers, past-tense
test logs, skill self-history, dated parentheticals, shouting labels, process jargon,
first-person provenance, when-to-use headings, self-describing preambles, and names of removed
skills from `scripts/removed-skills.txt` fail CI; "today", observed timings, stage labels,
"smoke test" and spec attestations print a warning for a human to judge). Each message names
the rule, the file and line, and the standard.

### 14. Test new and updated skills at three levels

A skill can pass every static check and still lead an agent astray in a real Workspace, so testing
has three levels (AGENTS.md "Testing new and updated skills" has the commands):

1. Static checks on every change (`scripts/build-openai.sh`, `scripts/check-version.sh`,
   `scripts/check-codeowners.py`, `claude plugin validate`).
2. A `claude plugin eval` case for every skill, whose prompt should trigger it.
3. For every new skill and every change to a write path (anything that starts, creates, uploads or
   deploys in Domino), a live end-to-end round with `evals/e2e/`: Claude Haiku runs inside real Domino
   Workspaces and each session is graded by what happened in Domino. Include a no-plugin baseline the
   first time, write prompts as a user would without naming the skill, run each scenario at least twice,
   record each skill-caused failure against the owning file for the skill's author to fix (standard 8),
   re-run until the runs pass, verify that every scratch resource was cleaned up, and put pass rates,
   turns and cost in the PR description, never in the skill (standard 12). Method and configuration:
   `evals/e2e/README.md`.

## Release branches, tags and backports

### Where PRs go

| Change | Base branch | Version |
|---|---|---|
| Skills, agents, MCP server, output styles, assets (any content) | **`develop`** | Unchanged. CI fails a PR to `develop` that touches `plugin.json` `version`. |
| Release: promote `develop` to `main` | `main`, head `develop` | The one bump to the next `YYYY.XYY.N`; CI requires it; the tag follows on merge. |
| Repo mechanics only (`.github/`, `scripts/`, CONTRIBUTING, README) | `main` | Unchanged; no content paths, so no bump and no tag. |
| Backport onto a `release-X.Y` branch | that branch | Bump `N` on that line. |
| Release candidate for internal testing | `rc/<YYYY.XYY.N>`, cut from `develop` | `YYYY.XYY.N-rc.M`; bump `M` on every change. CI rejects a plain version there and a suffix anywhere else. See [Release candidates](#release-candidates). |

`develop` is the integration branch: it batches content changes so that `main` receives one
release per promotion instead of one per PR. Nothing resolves `develop`: the Anthropic
marketplace pins `main` by commit and the DSE updater probes only `release-X.Y.Z`,
`release-X.Y` and `main`. Never name an integration branch `release-*`; the updater would
serve it to every matching cluster on the next Workspace launch.

Three things carry a version, and they are deliberately different:

| Object | Form | Who reads it |
|---|---|---|
| Branch | `main`, `release-6.3`, `release-6.4` … | The Domino Standard Environment (DSE) update script, which resolves **by exact branch name**: `release-X.Y.Z`, then `release-X.Y`, then `main`, from the cluster's `DOMINO_VERSION`. Any other branch name, `develop` and `rc/<version>` included, is invisible to it. The script ships in the DSE image; Domino 6.3 runs it at Workspace launch when the `updateSkillsOnLaunch` setting is on. Domino Cloud doesn't run it at launch, so Cloud Workspaces keep the version their image installed, and a Workspace that persists `~/.claude` keeps its earlier copy. |
| Tag | `release-YYYY.XYY.N`, or `release-YYYY.XYY.N-rc.M` for a release candidate | Humans, and admins pinning a Workspace to one release through the script's override argument (`DOMINO_CLAUDE_SKILLS_BRANCH`), which accepts a branch, tag or commit. |
| `plugin.json` `version` | `YYYY.XYY.N`; `YYYY.XYY.N-rc.M` on an `rc/` branch | Claude Code, to decide whether an installed copy is stale; the OpenAI portal, to order uploads; Gemini CLI, which shows it for the installed extension. |

Rules:

- `main` is correct for every supported target (Domino 6.3 and Cloud today). Version-specific
  behaviour is gated inside the skill, not by branch. `XYY` in the version is the **floor** of
  what the content is correct for, so `main` carries `YYYY.603.N` for as long as it is still
  correct for 6.3, even after 6.4 ships.
- Each self-managed Domino line that has shipped has a `release-X.Y` branch (`release-6.3`
  today), so the Domino Workspace updater and pinned installs can name it. While `main`'s floor
  is at or below `X.Y`, `main` is correct for that line, and
  `.github/workflows/advance-release-branches.yml` fast-forwards `release-X.Y` to `main` on every
  push: the two are identical and nobody commits to the branch directly. When the floor moves
  past `X.Y` (say `main` drops 6.3 and becomes `YYYY.604.N`), the workflow stops advancing
  `release-6.3`; from then on it receives cherry-picks only and its versions stay on the `6.3`
  line. Never create `release-X.Y` for a Domino version that hasn't shipped as self-managed:
  Domino Cloud reports newer versions than self-managed and would resolve to it. The branch
  name and the floor name the same Domino version (`release-6.3` carries `603`).
- **Backport** = cherry-pick the fix onto `release-X.Y`, bump `N` on that line, open the PR
  against the branch. CI checks that the version's line matches the branch (`603` for
  `release-6.3`). The tag follows
  automatically on merge.
- Never reuse a version string; installs from a git source treat a reused string as no change. A
  `git revert` of a content change is itself a content change and needs its own bump. Any edit
  to `plugin.json` counts as content.
- If `tag-release` fails with "already exists at a different commit", two PRs landed with the
  same version (usually a stale green check). Recover with a bump-only PR to the next `N`;
  do not move or delete the existing tag.
- The version check is only a gate if the repository requires it: maintainers keep
  `Version check / version` as a required status check with "require branches to be up to
  date" on `main` and every `release-*` branch, so a PR re-runs against the moved base.

How each channel receives a release:

- **Anthropic official marketplace**: the entry pins `main` by commit sha. Anthropic advances
  the pin on its own schedule (an automated bump job that is sometimes paused), and Claude
  Code installs the new copy once the manifest string differs. After a release, check the
  `sha` for `dominodatalab` in `anthropics/claude-plugins-official` and request a bump if it
  lags.
- **Domino DSE Workspaces**: the image clones this repository into a local-directory
  marketplace, and Claude Code reads that clone in place (verified on 2.1.294), so whatever
  commit the clone has checked out is what loads at the next session, with or without a
  version bump. Domino 6.3 runs the update script at Workspace launch when
  `updateSkillsOnLaunch` is on, which checks out the resolved branch. Domino Cloud doesn't
  run it, so a Cloud Workspace keeps the commit its image cloned, and a Workspace that
  persists `~/.claude` keeps its earlier clone. A local-directory marketplace can't
  auto-update: Claude Code has nothing to fetch.
- **`--plugin-dir`**: loads in place; `git pull` or checking out a tag is the update.
- **OpenAI plugin directory (ChatGPT and Codex)**: nothing is pulled automatically. After a
  release, build the ZIP with `scripts/build-openai.sh` from the release tag and upload it to
  the existing plugin in the portal; the portal rejects an upload whose `plugin.json` version
  is unchanged. Upload only releases from `main`: a backport on `release-X.Y` can carry a later
  year than `main`, so it would sort as newer and roll the listing back.
- **Gemini CLI**: `gemini extensions install https://github.com/dominodatalab/domino-ai-plugin`
  installs from the repository's latest GitHub Release once one exists (otherwise from the
  default branch). `tag-release.yml` publishes a Release on every push to `main` and marks only
  releases from `main` as latest, so a backport never moves default users; `gemini extensions
  update dominodatalab` picks up the next release. Nothing else to do.

### Release candidates

A release that should be tested internally before it goes public is cut as a candidate first.

- **Version:** `YYYY.XYY.N-rc.M` with `M >= 1`, for example `2026.603.5-rc.1`. It is semver
  pre-release syntax, so `2026.603.5-rc.1` < `2026.603.5-rc.2` < `2026.603.5`, and every
  candidate changes the string, so installed copies update. `scripts/sync-manifests.py` copies
  the suffixed string into all four manifests; `claude plugin validate`, `agy plugin validate`,
  Gemini CLI's `extensions validate` and `scripts/build-openai.sh` all accept it.
- **Branch:** `rc/<YYYY.XYY.N>`, for example `rc/2026.603.5`, cut from `develop` (the content
  that will become that release). `main`, `develop` and `release-*` never carry the suffix:
  `scripts/check-version.sh` (rule 7) and `tag-release.yml` both refuse it there, and an `rc/`
  base refuses a plain version. The DSE updater never resolves `rc/` branches, so a candidate
  reaches nobody who did not ask for it.
- **Cut and bump:** `git switch -c rc/2026.603.5 origin/develop && git push -u origin rc/2026.603.5`,
  then a PR to that branch that sets `version` to `2026.603.5-rc.1` in `.claude-plugin/plugin.json`
  and runs `scripts/sync-manifests.py`. On merge, `tag-release.yml` creates
  `release-2026.603.5-rc.1` and a GitHub Release marked **pre-release** and never **latest**, so
  Gemini CLI's default install and update ignore it. Fixes land on `develop` as usual; merge
  `develop` into the `rc/` branch (or cherry-pick) with the bump to `rc.2`, and so on. CI
  (rule 8) checks that the plain part equals the branch's version and is newer than `main`'s,
  and that `M` increases over the base and over every `release-<version>-rc.*` tag already
  created. Maintainers add `rc/**` to the ruleset that requires the `Version check / version`
  status, as for `main` and `release-*`.
- **Ship:** promote `develop` to `main` with the plain `2026.603.5` exactly as without a
  candidate. A candidate branch is never renamed into a release; delete it afterwards, the
  tags stay.
- **Install a candidate** (the branch name or the tag both work as the ref):
  - Claude Code: `claude plugin marketplace remove domino-marketplace` if the GitHub marketplace
    is already added, then `claude plugin marketplace add dominodatalab/domino-ai-plugin#rc/2026.603.5`
    and `claude plugin install dominodatalab@domino-marketplace`. If
    `dominodatalab@claude-plugins-official` is installed too, both load under the same
    `dominodatalab:` prefix and every skill appears twice: `claude plugin disable
    dominodatalab@claude-plugins-official` while testing, `claude plugin enable
    dominodatalab@claude-plugins-official` afterwards. Newer candidate: `claude plugin marketplace
    update domino-marketplace`, `claude plugin update dominodatalab@domino-marketplace`, restart.
    Back to the release: remove the marketplace again and add it without `#ref`.
  - Codex: `codex plugin marketplace add dominodatalab/domino-ai-plugin@rc/2026.603.5` (or
    `--ref rc/2026.603.5`), then `codex plugin add dominodatalab@domino-marketplace`. Newer
    candidate: `codex plugin marketplace upgrade domino-marketplace`, then `codex plugin add
    dominodatalab@domino-marketplace` again. Back: `codex plugin marketplace remove
    domino-marketplace` and add it without the ref.
  - Gemini CLI: `gemini extensions install https://github.com/dominodatalab/domino-ai-plugin --ref rc/2026.603.5`
    (or `--ref release-2026.603.5-rc.1`, or `--pre-release` for the newest candidate;
    `npx -y @google/gemini-cli` stands in for `gemini`). Run it in a terminal: it asks a `[Y/n]`
    consent question, then for the Domino URL and token, which can be left empty; without a
    terminal it waits at the consent prompt. Newer candidate: `gemini extensions update
    dominodatalab`. Back: `gemini extensions uninstall dominodatalab`, then install without the ref.
  - Cursor: its docs don't document choosing a ref for a GitHub-imported marketplace (an
    import tracks one branch). Use a local checkout instead:
    `git clone -b rc/2026.603.5 https://github.com/dominodatalab/domino-ai-plugin ~/.cursor/plugins/local/dominodatalab`,
    then Developer: Reload Window. Newer candidate: `git -C ~/.cursor/plugins/local/dominodatalab pull`,
    then Developer: Reload Window. Back: delete that folder and reinstall from GitHub.
  - Antigravity: `agy plugin install` takes a local directory and installs a copy, so
    `git clone -b rc/2026.603.5 https://github.com/dominodatalab/domino-ai-plugin ~/domino-ai-plugin-rc`
    and `agy plugin install ~/domino-ai-plugin-rc`. Newer candidate:
    `git -C ~/domino-ai-plugin-rc pull && agy plugin install ~/domino-ai-plugin-rc`. Back:
    `agy plugin uninstall dominodatalab`, then `agy plugin install` from a `main` checkout.
  - Domino Workspaces: the DSE updater follows `release-X.Y` by name, so test by hand in the
    image's clone, which Claude Code reads in place. Its `origin` may still be the old
    `domino-claude-plugin` repository, which has no `rc/` branches, so first
    `git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin remote set-url origin https://github.com/dominodatalab/domino-ai-plugin.git`,
    then `... fetch origin rc/2026.603.5` and `... checkout -B rc/2026.603.5 origin/rc/2026.603.5`,
    then start a new session. `claude plugin list` keeps showing the image's marketplace entry
    (`1.0.0`); check the loaded version with `grep '"version"' <clone>/.claude-plugin/plugin.json`.
    Newer candidate: the same `fetch` and `checkout -B`. Back: check out the release branch the
    image expects (`release-X.Y` for the Domino version, or `main`); if unsure, start a new
    Workspace.
- **Dry run of the gate:** there are no automated tests for `scripts/`; before changing
  `check-version.sh`, build a scratch origin (`git init --bare`, a clone with
  `.claude-plugin/plugin.json` at the shipped version on `main`, `develop`, `release-6.3` and
  `rc/<next>`), commit one PR head per rule and run `scripts/check-version.sh origin/<base>`
  for each, expecting exit 1 for: a suffix on `develop`, `main` or `release-*`; a plain version,
  another release's version, or a version not newer than `main` on `rc/`; a content change
  without a bump; `rc.M` at or below an existing `release-<version>-rc.*` tag. Expect exit 0
  for the frozen `develop` version, a plain bump on `main`, and `rc.1`, then `rc.2` on `rc/`.

`scripts/verify-update-flow.sh` reproduces the DSE install layout in a throwaway Claude Code
configuration and asserts that the clone is read in place. Run it when Claude Code changes its
plugin loading; if it fails, Claude Code copies this layout again and the DSE paragraph above
needs updating.

## Code Style

- Use consistent YAML frontmatter format
- Include code examples with proper language tags
- Use tables for reference documentation
- Keep descriptions actionable and specific

## Testing Changes

Before submitting:

1. Run `scripts/build-openai.sh`; it checks manifests, front matter, links, and Claude mentions
2. Run the evals that cover what you changed (README "Evals"), and add a case for a new skill
3. Test skills trigger correctly in Codex or ChatGPT when the wording of a trigger-sensitive
   description changed
4. Smoke-test every API payload documented in a skill against a live Domino
   instance and record the result in the PR description (see
   [Skill Authoring Standards #5](#5-smoke-test-payloads-against-the-live-api))
5. For a new skill or a change to a write path, run a live end-to-end round with `evals/e2e/` and
   report its results in the PR description (see
   [Skill Authoring Standards #14](#14-test-new-and-updated-skills-at-three-levels))


## Pull Request Process

The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) is the checklist; fill every section.
Reviewers will send back PRs with unticked required sections.

1. Link the Jira ticket. Skills work lives under the DOCS-6840 epic.
2. Declare Domino version applicability and confirm both specs were checked (standard 7).
3. For new or rewritten skill content, name the model used and tick the attestation
   (standard 8).
4. Confirm no internal references (standard 9) and leave `plugin.json` `version` unchanged on a PR to `develop`; the `develop` to `main` release PR carries the bump (standard 10). CI fails either the other way round.
5. Update the README skill table and counts for any added, renamed or removed component.
6. Describe what you tested and against which deployment version.
7. Target `develop` for content and `main` only for release promotions and repo mechanics
   (see "Where PRs go"). One approving review, a code-owner review where `.github/CODEOWNERS`
   matches, and the `version` check
   are required to merge. Note in the PR if the change must be cherry-picked to a
   `release-X.Y` branch.

## Reporting Issues

Use the issue forms (bug report or skill request); they ask for the agent, plugin version and
Domino version. Report security problems privately as described in [SECURITY.md](SECURITY.md).
Help with the Domino platform itself goes to Domino support; see [SUPPORT.md](SUPPORT.md).

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

- Open an issue for bugs or feature requests
- See [Domino Documentation](https://docs.domino.ai) for platform questions
- [MAINTAINERS.md](MAINTAINERS.md) lists who maintains this repository
