# Domino Data Lab Plugin for Claude Code, ChatGPT, Codex, Cursor, Gemini CLI, and Antigravity

One source tree, several distributions. This repository is a **Claude Code plugin** as checked
in; the same checkout is a **Codex / ChatGPT plugin** (and builds the package for the OpenAI
plugin directory), a **Cursor plugin**, a **Gemini CLI extension**, and an **Antigravity
plugin** (`plugin.json` plus `mcp_config.json`). All of them share the
same skills; all but the OpenAI directory package, which is skills-only, also carry the same
always-on guidance and the same Domino MCP server.

> **Moved from `dominodatalab/domino-claude-plugin`.** That repository is deprecated and receives
> no new releases; this one replaces it. To switch an existing install, see
> [Updating (Claude Code)](#updating-claude-code).

## Overview

The plugin gives AI coding assistants skills for the main Domino Data Lab surfaces:

- **Workspaces**: Jupyter, VS Code, RStudio configuration and management
- **Jobs**: Batch execution, scheduled jobs, and monitoring
- **Environments**: Custom Docker environments and package management
- **Datasets**: Data versioning with snapshots and sharing
- **NetApp Volumes**: Enterprise-grade multi-terabyte storage with near-instant snapshots
- **Apps**: Deploy React, Streamlit, and Dash applications
- **Models**: Deploy, monitor, and manage model endpoints
- **GenAI**: Trace and evaluate AI agents with the Domino SDK
- **Distributed Computing**: Spark, Ray, Dask and Open MPI clusters, and Slurm HPC
- **Projects, Launchers, Flows, governance, tags and properties, LLM access, and the Domino APIs and SDKs**

Skills say which Domino versions they apply to; see [Compatibility](#compatibility).

## What ships where

| Component | Claude Code | ChatGPT / Codex | Cursor | Gemini CLI | Antigravity |
| --- | --- | --- | --- | --- | --- |
| `skills/` (35 skills) | ✅ | ✅ | ✅ | ✅ discovered from `skills/` | ✅ imported from `skills/` |
| Domino MCP server (`mcp-servers/`) | ✅ via `.mcp.json` (stdio) | Codex local install: ✅ via `mcp.json` (stdio). Public directory: needs a hosted HTTPS endpoint (see [OpenAI build](#openai-build)) | ✅ via `.cursor-plugin/mcp.json` (stdio; credentials from the env file, see [Your Domino URL and token](#your-domino-url-and-token)) | ✅ via `gemini-extension.json` (stdio; Gemini CLI asks for the same two values at install) | ✅ via `mcp_config.json` (stdio; credentials from `agy`'s environment or the env file) |
| Domino docs MCP server (`https://docs.domino.ai/mcp`) | ✅ via `.mcp.json` | Codex local install: ✅ via `mcp.json`. Not in the public directory package | ✅ via `.cursor-plugin/mcp.json` | ✅ via `gemini-extension.json` | ✅ via `mcp_config.json` |
| Always-on Domino guidance (`rules/domino.md`) | ✅ loaded at every session start by a `SessionStart` hook | Codex local install: the lead section, as the bundled MCP server's instructions. Not available to skills-only directory plugins | ✅ always-applied plugin rule (`alwaysApply: true`) | ✅ the extension's context file (`contextFileName`) | ✅ always-on rule (`trigger: always_on`) in the installed copy |
| Subagents (`agents/`) | ✅ routers that preload their skills | ❌ | Routing prompts only: Cursor loads `agents/` without `skills:` or `tools:`, so nothing is preloaded | ❌ the files are `_`-prefixed, which Gemini CLI skips (its sub-agent schema differs) | Imported as prompts (`agy` reports 3 agents); `skills:` and `tools:` are Claude Code fields |
| Output styles (`output-styles/`) | ✅ | ❌ Claude-only | ❌ | ❌ | ❌ |
| Hook examples (`hooks/`) | Docs only | ❌ | ❌ | ❌ | ❌ |
| Manifest | `.claude-plugin/plugin.json` | `plugin.json` ([Agent Plugins](https://agent-plugins.org) format) | `.cursor-plugin/plugin.json` | `gemini-extension.json` | `plugin.json`, read by `agy`, plus `mcp_config.json` |

Skills are written provider-neutral. Where an instruction really is host-specific (for example
which instructions file or MCP config file to write), the skill gives both the Claude Code and
the Codex variant. CI enforces this; see [Skill rules](#skill-rules).

---

## Your Domino URL and token

Inside a Domino Workspace, Job or App, nothing is needed: the bundled MCP server calls Domino
through `$DOMINO_API_PROXY`, which adds your identity. Leave the settings below empty there.

Everywhere else (your laptop, CI), the MCP server needs two values:

| Setting | What to enter | Where to get it |
|---|---|---|
| **Domino URL** (`DOMINO_HOST`) | The address you open Domino at in your browser: `https://` and the host name, no path, for example `https://domino.example.com` | Your browser's address bar while you use Domino. Not `DOMINO_API_HOST`, which inside Domino is an in-cluster address |
| **Token** (`DOMINO_TOKEN`) | A Personal Access Token, or a service account token for automation | In Domino: **Account** > **Account settings** > **Personal Access Token** > **Generate new Token**, choose an expiry, copy it ([docs](https://docs.domino.ai/cloud/reference/api/domino-api-authentication)). Legacy API keys don't work |

Each host takes them its own way:

| Host | How |
|---|---|
| Claude Code | Asks for both when you enable the plugin; the token goes to your system's secure credential store. Change them later in `/plugin` → **Installed** → **dominodatalab** → **Configure options**, then start a new session |
| Gemini CLI | Asks at `gemini extensions install` (the token first, then the URL); the token goes to the system keychain. Change them with `gemini extensions config dominodatalab` |
| Codex and the ChatGPT desktop app | Can't ask. Write the env file below at exactly `~/.config/domino-mcp-server/.env`: Codex starts the server with a stripped environment and passes no other location |
| Cursor | Doesn't ask. Write the env file below. `.cursor-plugin/mcp.json` also forwards `DOMINO_HOST` and `DOMINO_TOKEN` from the environment Cursor runs in, which the Cursor CLI may not share with your shell |
| Antigravity | Doesn't ask. Write the env file below, or start `agy` with `DOMINO_HOST` and `DOMINO_TOKEN` in its environment |
| Any host | The env file below, or `DOMINO_HOST` and `DOMINO_TOKEN` in the environment the host starts the server with |

**The env file** is `~/.config/domino-mcp-server/.env` (or `$XDG_CONFIG_HOME/domino-mcp-server/.env`,
or the file `$DOMINO_MCP_ENV_FILE` names; under Codex only the first, since Codex passes the server
neither variable). This writes it readable only by you, without the token
appearing on screen or in your shell history:

```bash
bash -c 'mkdir -p ~/.config/domino-mcp-server && umask 077 &&
  read -r -p "Domino URL (https://...): " host && read -rs -p "Domino token: " token && echo &&
  printf "DOMINO_HOST=%s\nDOMINO_TOKEN=%s\n" "$host" "$token" > ~/.config/domino-mcp-server/.env'
```

When values come from more than one place, the host's own settings win, then the environment, then
the env file.

**Check it:** start a new session and ask "Which Domino user am I connected as?". The assistant
calls the server's `get_domino_environment_info`, which reports where each value came from and the
user the token belongs to, or exactly what to fix:

| Message | Fix |
|---|---|
| `DOMINO_HOST is not set` or `DOMINO_TOKEN is not set` | The host passed nothing; set the values as the table above shows for your host |
| `HTTP 401` | The token is wrong, expired or revoked; generate a new one |
| `... failed: ...` (no HTTP response) | Check the URL against your browser's address bar, and your network (VPN, or `HTTPS_PROXY` on a corporate network) |
| `uses http://` or `must be a URL starting with https://` | Use the `https://` address |
| `returned a non-JSON response` | The URL points at a login page or another site; copy it from the address bar while you're in Domino |
| `DOMINO_API_KEY is set` | Legacy API keys are not supported; use a Personal Access Token |

## Installation: Claude Code

### Prerequisites

- **Claude Code CLI** v2.1.133 or later (`claude --version` to check). Plugins exist since 2.0.12,
  but the subagents need the `skills:` preload (2.0.43) and plugin skills reachable from a
  subagent through the Skill tool (2.1.133). Tested on 2.1.300.
- Access to a Domino Data Lab instance
- Outside a Domino Workspace: your Domino URL and a Personal Access Token for the bundled MCP
  server. Claude Code asks for both when you enable the plugin ([Your Domino URL and token](#your-domino-url-and-token))
- **`uv`** package manager ([install guide](https://github.com/astral-sh/uv)) — required for the bundled Domino MCP server

### Recommended: install from GitHub

The repository is its own marketplace (`.claude-plugin/marketplace.json`, named
`domino-marketplace`), so Claude Code can install and update the plugin straight from GitHub:

```bash
claude plugin marketplace add dominodatalab/domino-ai-plugin
claude plugin install dominodatalab@domino-marketplace
```

Claude Code installs a copy and replaces it when a release changes the plugin's `version`.
Auto-update is off by default for marketplaces other than Anthropic's: turn it on under
`/plugin` → **Marketplaces**, or set `autoUpdate` in your settings:

```json
{
  "extraKnownMarketplaces": {
    "domino-marketplace": {
      "source": { "source": "github", "repo": "dominodatalab/domino-ai-plugin" },
      "autoUpdate": true
    }
  }
}
```

The marketplace also maps the old entry name `domino-claude-plugin` to `dominodatalab`, so a
setting written for the old name keeps working.

**Already installed from a local marketplace (Options 1 and 3)?** Claude Code won't add a second
source under the same name, `domino-marketplace`. Remove the local one first, including any
`extraKnownMarketplaces` entry you added for it in `.claude/settings.json`, then run the two
commands above:

```bash
claude plugin marketplace remove domino-marketplace
```

Inside a Domino Workspace, leave the image's local marketplace as it is.

### Option 1: Local Marketplace Install (the Domino Workspace layout)

This approach registers the plugin through Claude Code's native marketplace system so it persists across sessions.

**Step 1: Clone the repository and create a marketplace wrapper**

```bash
git clone https://github.com/dominodatalab/domino-ai-plugin.git

mkdir -p ~/.claude/marketplaces/domino/.claude-plugin
mkdir -p ~/.claude/marketplaces/domino/plugins

mv domino-ai-plugin ~/.claude/marketplaces/domino/plugins/domino-claude-plugin
```

**Step 2: Create the marketplace manifest**

```bash
cat > ~/.claude/marketplaces/domino/.claude-plugin/marketplace.json << 'EOF'
{
  "name": "domino-marketplace",
  "owner": {
    "name": "Domino Data Lab",
    "email": "support@dominodatalab.com"
  },
  "plugins": [
    {
      "name": "domino-claude-plugin",
      "description": "Domino Data Lab plugin - workspaces, jobs, environments, datasets, apps, models, and more",
      "source": "./plugins/domino-claude-plugin",
      "category": "development"
    }
  ]
}
EOF
```

> **Why `domino-claude-plugin`?** Claude Code tracks a marketplace install as
> `<entry name>@<marketplace>`, so the entry keeps the name it had before the repo moved.
> Existing installs and Domino workspaces keep updating without a reinstall. Only the clone URL
> changed.

**Step 3: Register the marketplace and install the plugin**

Launch Claude Code and run:

```
/plugin marketplace add /home/<your-username>/.claude/marketplaces/domino
/plugin install domino-claude-plugin@domino-marketplace
```

> **Note:** Replace `<your-username>` with your actual username, or use the full absolute path (e.g., `/home/ubuntu/.claude/marketplaces/domino`). The `~` shorthand may not expand correctly.

**Step 4: Restart Claude Code**, then verify with `/plugin` → **Installed** tab.

### Option 2: Direct Plugin Directory (Development / Quick Start)

```bash
git clone https://github.com/dominodatalab/domino-ai-plugin.git
claude --plugin-dir ./domino-ai-plugin
```

Loaded this way the plugin is read in place: a `git pull` (or checking out a `release-*` branch
or tag) takes effect at the next session with no reinstall.

### Option 3: Team / Project-Level Install

For teams sharing a project, add the marketplace to your project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "domino-marketplace": {
      "source": {
        "source": "directory",
        "path": "/path/to/domino-marketplace"
      }
    }
  },
  "enabledPlugins": {
    "domino-claude-plugin@domino-marketplace": true
  }
}
```

When team members trust the repository folder, Claude Code will prompt them to install the marketplace and plugin automatically.

### Updating (Claude Code)

- **Installed from GitHub (recommended above):** with auto-update on, Claude Code updates the
  copy after a release on its own. To update now:

  ```bash
  claude plugin marketplace update domino-marketplace
  claude plugin update dominodatalab@domino-marketplace
  ```

- **Local marketplace install (Options 1 and 3):** Claude Code reads the clone in place, so
  checking out a newer commit is the update; start a new session afterwards. `git pull` fails on
  a detached checkout, so fetch and check out `main` instead:

  ```bash
  git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin fetch origin main
  git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin checkout -B main origin/main
  ```

  If `git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin remote get-url origin`
  still names `domino-claude-plugin`, run `git -C <that path> remote set-url origin
  https://github.com/dominodatalab/domino-ai-plugin.git` first. The two repositories have
  unrelated histories, so `git pull` alone can't switch a clone; the fetch and `checkout -B` above
  can.

- **Migrate a clone of `domino-claude-plugin`, or update any clone by hand:** point it at this
  repository, check out the latest release and start a new session:

  ```bash
  P=~/.claude/marketplaces/domino/plugins/domino-claude-plugin   # or the path of your clone
  git -C $P remote set-url origin https://github.com/dominodatalab/domino-ai-plugin.git
  git -C $P fetch origin main
  git -C $P checkout -B main origin/main
  grep '"version"' $P/.claude-plugin/plugin.json                 # the version now loaded
  ```

- **Anthropic marketplace:** `claude plugin update dominodatalab@claude-plugins-official`, then
  restart. That entry follows whatever commit Anthropic pins, which still points at the deprecated
  `domino-claude-plugin` repository.

- **`--plugin-dir` (Option 2):** the plugin is read in place. `git pull`, then start a new session.

---

## Installation: Codex and the ChatGPT desktop app

### From GitHub (recommended)

The repository is also a Codex marketplace (`.agents/plugins/marketplace.json`, named
`domino-marketplace`). Codex reads the portable `plugin.json`, `skills/`, and `mcp.json` from it,
with no build step:

```bash
codex plugin marketplace add dominodatalab/domino-ai-plugin
codex plugin add dominodatalab@domino-marketplace
```

Codex refreshes Git marketplaces when it starts, and `codex plugin marketplace upgrade
domino-marketplace` refreshes it now. Add `--ref <tag>` to `marketplace add` to stay on one release.
This path includes the bundled MCP server (stdio, needs `uv`). Restart the ChatGPT desktop app to
see the plugin there.

> **MCP credentials:** the portable `mcp.json` can't carry secrets, and Codex starts the server
> with a stripped environment. Inside a Domino Workspace nothing is needed: the server calls
> `$DOMINO_API_PROXY` and recovers the Workspace's variables itself. On a laptop write the env file
> as [Your Domino URL and token](#your-domino-url-and-token) shows.

### From the public plugin directory

Once published, install **Domino Data Lab** from the Plugins Directory in ChatGPT or Codex. The
directory package is currently **skills-only**: it doesn't include the MCP server.

## Installation: Cursor

Cursor reads `.cursor-plugin/plugin.json`: the skills, the always-on rule `rules/domino.md`, the
subagents in `agents/`, and both MCP servers (`.cursor-plugin/mcp.json`). Cursor support is new and
not yet tested in a logged-in Cursor; please report what you find.

- **Cursor desktop:** Customize → From GitHub Repository → `https://github.com/dominodatalab/domino-ai-plugin`,
  then install `dominodatalab` at user or project scope.
- **Cursor CLI (`agent`):** `agent plugin marketplace add https://github.com/dominodatalab/domino-ai-plugin`,
  then `/plugin` in a session. Update with `agent plugin marketplace update domino-marketplace`.
- **Local checkout:** clone (don't symlink) into `~/.cursor/plugins/local/dominodatalab` and run
  Developer: Reload Window, or run `agent --plugin-dir /path/to/domino-ai-plugin`.

The bundled MCP server needs `uv` on `PATH` and, outside a Domino Workspace, your Domino URL and a
Personal Access Token. Cursor doesn't ask for them: write the env file
([Your Domino URL and token](#your-domino-url-and-token)).

If the plugin is also installed in Claude Code, Cursor may import that copy too (Settings → Agents →
Third-Party Imports). Install it in Cursor only once.

## Installation: Gemini CLI

The repository root is a Gemini CLI extension (`gemini-extension.json`): the skills, the always-on
guidance `rules/domino.md` as the extension's context file, and both MCP servers.

```bash
gemini extensions install https://github.com/dominodatalab/domino-ai-plugin
```

Gemini CLI installs the repository's latest GitHub Release when one exists and the default branch
otherwise; add `--ref release-YYYY.XYY.N` to pin a release. `release-2026.603.5` is the first
release that includes `gemini-extension.json`; earlier tags fail. Install asks a consent question
first (`--consent` answers it, for a script; installing from a local path also asks whether to
trust the folder, which `--consent` doesn't answer). It then asks for the two settings the bundled
MCP server needs outside a Domino Workspace, the token first: `DOMINO_TOKEN`, a Personal Access
Token or service account token, and the Domino URL (`DOMINO_HOST`), kept in the system keychain (or in an encrypted
file where there is no keychain, such as a Domino Workspace). Inside a Workspace leave both empty,
or pass `--skip-settings`: the server calls `$DOMINO_API_PROXY` and picks up the Workspace's own
variables. Gemini CLI never hands your shell's `DOMINO_TOKEN` to an MCP server: it drops every
variable whose name contains TOKEN, KEY, SECRET, AUTH, CREDENTIAL, PASSWORD or similar, and a
declared setting is injected from Gemini's own store instead, which is why the token is a setting
rather than something read from your shell. Stdio MCP servers start only in a folder you have
trusted (`gemini trust`, or answer the prompt). Update with `gemini extensions update
dominodatalab`; for a local checkout, `gemini extensions link /path/to/domino-ai-plugin` loads it
in place. The bundled MCP server needs `uv` on `PATH`; see
[mcp-servers/domino_mcp_server/README.md](mcp-servers/domino_mcp_server/README.md).

Gemini CLI rewrites `${name}` in skill text before the model reads it, using its own variables,
the declared settings and every key of a trusted workspace's `.env` file. Lint therefore rejects
`${` in any `SKILL.md`, except files listed in `scripts/gemini-substitution.allow` for product
syntax such as Launcher `${param}` placeholders, which Gemini would rewrite only if a project
`.env` defined those names.
The `agents/` and `output-styles/` directories are Claude Code formats. Gemini CLI ignores
`output-styles/`, and the agent files are named `_<name>.md` because Gemini CLI skips
underscore-prefixed files in `agents/` (its own sub-agent schema would reject Claude's `skills:`
field); the skills, context file and MCP servers load, and nothing is logged.

## Installation: Antigravity

Antigravity's `agy` CLI (tested on 1.3.5) installs a plugin from a **local directory**: it reads
`plugin.json`, imports `skills/`, `agents/` and both MCP servers from `mcp_config.json`, and copies the whole checkout under `~/.gemini/config/plugins/dominodatalab`.
A git URL is rejected (`install target must be a directory`), so clone first; `main` is the
public release:

```bash
git clone https://github.com/dominodatalab/domino-ai-plugin ~/domino-ai-plugin
agy plugin validate ~/domino-ai-plugin   # optional: 35 skills, 3 agents, 2 MCP servers
agy plugin install ~/domino-ai-plugin
```

`agy plugin list` shows the import with its components (35 skills, 3 agents, 1 rule, 2 MCP servers). The
installed copy includes `rules/domino.md`, which Antigravity reads as an always-on rule
(`trigger: always_on`). The bundled Domino MCP server (Antigravity shows it as
`dominodatalab_domino_server`) needs `uv` on `PATH`; outside a Domino Workspace it reads
`DOMINO_HOST` and `DOMINO_TOKEN` from the environment `agy` starts with, else the env file
([Your Domino URL and token](#your-domino-url-and-token)).

- **Update:** the install is a copy and does not follow the clone, so pull and install again:
  `git -C ~/domino-ai-plugin pull && agy plugin install ~/domino-ai-plugin`.
- **Uninstall:** `agy plugin uninstall dominodatalab`.
- `agy plugin import claude` does not find this plugin even when it is installed in Claude Code;
  install from the checkout as above.

---

## OpenAI build

`scripts/build-openai.sh` produces the ZIP you upload at the
[OpenAI plugin submission portal](https://platform.openai.com/plugins):

```bash
scripts/build-openai.sh                                                # dist/dominodatalab-openai-skills-only-<ver>.zip
scripts/build-openai.sh --mcp-url https://host/mcp --mcp-name NAME     # dist/dominodatalab-openai-with-mcp-<ver>.zip
```

The script:

1. Checks that `plugin.json` is in sync with `.claude-plugin/plugin.json` and that the listing
   fields fit the directory limits (`scripts/sync-manifests.py --check`).
2. Lints every skill (`scripts/lint-skills.py`).
3. Packages only portable components that git tracks (`plugin.json`, `skills/`, `assets/`,
   `LICENSE`), with the plugin root at the archive root, and warns about untracked files it leaves
   out. Build a release from a clean checkout of its tag.
4. Leaves `domino-modeling-assistant` out of the skills-only package: it is built around the
   plugin's local MCP server, which a skills-only install doesn't have.

The listing ships **Skills only**. OpenAI's
[submission rules](https://developers.openai.com/plugins/deploy/submission) for an MCP server:
a local stdio server such as `domino_server` needs the submitting organization allowlisted by
OpenAI and makes the listing desktop-only; a remote server needs a public HTTPS endpoint with no
authentication or OAuth (no Personal Access Tokens), and a listing connects at most one; and an
MCP server can't be added to a listing first published skills-only. `--mcp-url` with `--mcp-name`
builds the **With MCP** variant for a remote server.

The listing icon is `assets/logo.svg`, used for both `logo` and `composerIcon`. It is the
Domino pinwheel mark on a square `#2E2E38` tile with a 48×48 `viewBox`,
because the portal requires square icons of at least 48×48. The build fails if any icon or
screenshot path in `plugin.json` is missing or outside `assets/`.

---

## Compatibility

- **Supported targets:** Domino 6.3 (self-managed) and Domino Cloud. Skills declare this in
  `compatibility:` frontmatter and open with `Applies to Domino 6.3 and Domino Cloud.`; where the
  two differ, the skill reads `GET $DOMINO_API_HOST/version` and branches. (Lint does not enforce
  the frontmatter yet, so a skill without it still targets both.)
- **Domino 6.2 and earlier:** not supported. The content targets 6.3 and later; for an older
  version use its own documentation at `https://docs.dominodatalab.com/en/<version>/`.
- **`main`** is where releases are cut and it is correct for both targets: version-specific
  behaviour is gated inside the skills, never by branch. A GitHub marketplace install follows
  `main`, Gemini CLI follows its tagged GitHub Releases, and the Anthropic marketplace pins a
  commit (see [Updating](#updating-claude-code)). `release-X.Y` branches exist per shipped
  self-managed line (see CONTRIBUTING.md "Release branches, tags and backports").

---

## Versions

The version is **`YYYY.XYY.N`**, for example `2026.603.3`, and all four manifests
(`.claude-plugin/plugin.json`, `plugin.json`, `.cursor-plugin/plugin.json`,
`gemini-extension.json`) carry the same string. It's the release year, the oldest Domino line the content supports written as X×100+Y
(`603` = Domino 6.3 and later, including Cloud), and a release counter. The format is valid
semver, which the OpenAI portal requires. Each release is tagged `release-YYYY.XYY.N`. A release
candidate for internal testing is `YYYY.XYY.N-rc.M` on an `rc/<YYYY.XYY.N>` branch, tagged
`release-YYYY.XYY.N-rc.M` as a GitHub pre-release (see
[Testing a release candidate](#testing-a-release-candidate)). See CONTRIBUTING.md "Release
branches, tags and backports".

Releases up to `2026.6-3.2` used the older `YYYY.X-Y.N` form of the same scheme; `2026.603.3`
is the first in the current form.

`.claude-plugin/plugin.json` is the source of truth. Never edit the name, version or description
in `plugin.json`, `.cursor-plugin/plugin.json` or `gemini-extension.json` by hand; change
`.claude-plugin/plugin.json` and run:

```bash
scripts/sync-manifests.py
```

### Testing a release candidate

A candidate such as `2026.603.6-rc.1` lives on the branch `rc/2026.603.6` and is tagged
`release-2026.603.6-rc.1` as a pre-release; nothing installs it unless you ask for that ref,
and `rc.1` < `rc.2` < `2026.603.6`, so each candidate and the final release update an
installed copy. The commands below use `rc/2026.603.6` as the example: replace it with the
candidate's branch (the [Releases](https://github.com/dominodatalab/domino-ai-plugin/releases)
page lists them). The tag works in place of the branch.

- **Claude Code** (if the GitHub marketplace is already added, remove it first: `claude plugin
  marketplace remove domino-marketplace`):

  ```bash
  claude plugin marketplace add dominodatalab/domino-ai-plugin#rc/2026.603.6
  claude plugin install dominodatalab@domino-marketplace
  ```

  If `dominodatalab@claude-plugins-official` (the Anthropic directory copy) is installed too, both
  load under the same `dominodatalab:` prefix and every skill appears twice: run `claude plugin
  disable dominodatalab@claude-plugins-official` while testing and `claude plugin enable
  dominodatalab@claude-plugins-official` afterwards. Newer candidate: `claude plugin marketplace
  update domino-marketplace`, then `claude plugin update dominodatalab@domino-marketplace`, then
  restart. Back to the public release: remove the marketplace again, add it without `#rc/...`,
  install.
- **Codex**: `codex plugin marketplace add dominodatalab/domino-ai-plugin@rc/2026.603.6`, then
  `codex plugin add dominodatalab@domino-marketplace`. Newer candidate: `codex plugin marketplace
  upgrade domino-marketplace`, then `codex plugin add dominodatalab@domino-marketplace` again.
  Back: `codex plugin marketplace remove domino-marketplace`, add it without the ref, `codex
  plugin add` again.
- **Gemini CLI**: `gemini extensions install https://github.com/dominodatalab/domino-ai-plugin --ref rc/2026.603.6`
  (or `--pre-release` for the newest candidate; `npx -y @google/gemini-cli` stands in for `gemini`
  when it isn't installed). It asks a `[Y/n]` consent question (`--consent` answers it), then for the Domino URL and token,
  which can be left empty (`--skip-settings` skips them).
  Newer candidate: `gemini extensions update dominodatalab`. Back: `gemini extensions uninstall
  dominodatalab`, then install without the ref.
- **Cursor**: choosing a ref for a GitHub-imported marketplace isn't documented, so clone the
  branch into the local plugins folder: `git clone -b rc/2026.603.6
  https://github.com/dominodatalab/domino-ai-plugin ~/.cursor/plugins/local/dominodatalab`, then
  Developer: Reload Window. Newer candidate: `git -C ~/.cursor/plugins/local/dominodatalab pull`,
  then Developer: Reload Window. Back: delete that folder and reinstall from GitHub.
- **Antigravity**: `agy` installs a copy of a local checkout, so clone the branch and install it:
  `git clone -b rc/2026.603.6 https://github.com/dominodatalab/domino-ai-plugin ~/domino-ai-plugin-rc && agy plugin install ~/domino-ai-plugin-rc`.
  Newer candidate: `git -C ~/domino-ai-plugin-rc pull && agy plugin install ~/domino-ai-plugin-rc`.
  Back: `agy plugin uninstall dominodatalab`, then `agy plugin install` from a `main` checkout.
- **Domino Workspaces**: the image's updater follows `release-X.Y` by name and never an `rc/`
  branch, so check the candidate out by hand in the image's clone, which Claude Code reads in
  place (see [Updating](#updating-claude-code)). The clone's `origin` may still point at the old
  `domino-claude-plugin` repository, which has no `rc/` branches, so set it first:

  ```bash
  git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin remote set-url origin https://github.com/dominodatalab/domino-ai-plugin.git
  git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin fetch origin rc/2026.603.6
  git -C ~/.claude/marketplaces/domino/plugins/domino-claude-plugin checkout -B rc/2026.603.6 origin/rc/2026.603.6
  ```

  Start a new session. `claude plugin list` keeps showing the image's marketplace entry
  (`1.0.0`) even while the candidate is loaded; check the loaded version with
  `grep '"version"' ~/.claude/marketplaces/domino/plugins/domino-claude-plugin/.claude-plugin/plugin.json`.
  Newer candidate: the same `fetch` and `checkout -B` again. Back: check out the release branch
  the image expects (`release-X.Y` for your Domino version, or `main`), for example
  `... checkout -B main origin/main`; if unsure, start a new Workspace.

---

## What's Included

### Bundled MCP Server

A vendored copy of the [Domino MCP Server](https://github.com/dominodatalab/domino_mcp_server)
provides tools for running Domino jobs, checking job status/results, and syncing files with
DFS-based projects.

- **Inside a Domino execution (Workspace, Job, App):** nothing to configure. The server calls
  `$DOMINO_API_PROXY`, which adds your token, and reads the project from Domino's own variables.
- **Outside Domino (laptop, CI):** your Domino URL (`DOMINO_HOST`) and a Personal Access Token or
  service account token (`DOMINO_TOKEN`), sent as `Authorization: Bearer`. How each host takes
  them, the env file, and how to check the connection: [Your Domino URL and token](#your-domino-url-and-token).

Requires `uv`. Tools, routes and each host's registration are documented in
[mcp-servers/domino_mcp_server/README.md](mcp-servers/domino_mcp_server/README.md).

### Skills (34 total)

| Skill | Description |
| --- | --- |
| `domino-workspaces` | Jupyter, VS Code, RStudio workspace management |
| `domino-jobs` | Jobs and scheduled jobs execution |
| `domino-environments` | Compute environments and Dockerfile customization |
| `domino-datasets` | Data management, snapshots, and versioning |
| `netapp-volumes` | Enterprise-grade NetApp ONTAP storage with near-instant snapshots |
| `domino-projects` | Git integration and project collaboration |
| `domino-apps` | Deploy web apps (React, Streamlit, Dash) behind Domino's proxy |
| `domino-app-init` | Scaffold a new Domino-ready app with framework templates |
| `domino-rust-apps` | Build a Rust (axum) App: pinned toolchain in an environment, Clippy, nextest, cargo-deny, rust-analyzer, and a prebuilt binary that Apps start without compiling |
| `domino-debug-proxy` | Diagnose reverse-proxy and routing issues in apps |
| `domino-ui-bootstrap` | Bootstrap a Vite + React project on the Domino design system |
| `domino-extensions` | Build and operate Domino UI Extensions |
| `domino-experiment-tracking` | MLflow experiment tracking and model registry |
| `domino-experiment-setup` | Generate MLflow experiment setup code for a project |
| `domino-genai-tracing` | `@add_tracing` decorator and `DominoRun` |
| `domino-trace-setup` | Add GenAI tracing helpers and wiring to an agent project |
| `domino-model-endpoints` | Deploy and call model APIs |
| `domino-model-serving` | Model API and registered-model lifecycle over REST |
| `domino-model-monitoring` | Drift detection and model quality tracking |
| `domino-model-delivery` | Batch scoring Jobs, the Model Export API for CI/CD, NVIDIA Fleet Command and Snowflake exports |
| `domino-governance` | Policies, bundles, and evidence for model risk governance |
| `domino-flows` | Flyte-based workflow orchestration |
| `domino-airflow-kubeflow` | Trigger and wait for Domino Jobs from an existing Apache Airflow or Kubeflow Pipelines deployment (inside Domino, use `domino-flows`) |
| `domino-distributed-computing` | Spark, Ray, Dask cluster management |
| `domino-hpc-slurm` | Slurm HPC: a Slurm cluster attached to a Workspace (`sbatch`, `squeue`, `sacct`) and HPC Jobs over `/api/hpc/v1/jobs` |
| `domino-llm-access` | Which LLM path to use: LLM Gateway 2.0 where deployed (`domino-llm-gateway`), else Domino-hosted vLLM endpoints or provider SDKs; legacy AI Gateway (6.3) |
| `domino-llm-gateway` | Call models through LLM Gateway 2.0: aliases, in-run token, OpenAI and Anthropic SDKs, coding assistants, admin overview |
| `domino-launchers` | Parameterized web forms for self-service |
| `domino-modeling-assistant` | MCP server for AI-assisted model development |
| `domino-data-connectivity` | Choosing a mechanism (Data Source first), External Data Volumes, S3 Mountpoint, AWS IRSA, Azure credentials |
| `domino-api-intro` | Start here for Domino APIs: auth, hosts, pagination, errors |
| `domino-python-sdk` | Python SDK (python-domino) and REST API |
| `domino-cli` | Domino CLI and the R package: sync project files, run Jobs, upload to Datasets from a laptop |
| `domino-data-sdk` | Data SDK (domino-data) for data sources, datasets, training sets |
| `tags-and-properties` | Taxonomy API for tags, namespaces, and typed properties |

`domino-app-init`, `domino-debug-proxy`, `domino-experiment-setup`, and `domino-trace-setup`
replace the former slash commands of the same names. In Claude Code they're still invocable as
`/dominodatalab:<name>`, and every host can also pick them up automatically from context.

### Subagents (Claude Code and Cursor)

Each agent is a thin router: in Claude Code it preloads the skills for its area, can load the
others through the Skill tool, and reaches the plugin's MCP servers; it says which skill applies
to which request and holds no procedure of its own. Cursor loads the same files as plain prompts
without skill preload; Codex and Gemini CLI don't use them.

| Agent | Routes to |
| --- | --- |
| `domino-deploy` | `domino-apps`, `domino-app-init`, `domino-debug-proxy`, `domino-ui-bootstrap`, `domino-model-endpoints`, `domino-model-serving`, `domino-environments` for deploying apps and model endpoints |
| `domino-debug` | `domino-apps`, `domino-jobs`, `domino-environments`, `domino-api-intro` and the skill for the failing workload, with the log locations and Public API routes for fetching evidence |
| `domino-setup` | `domino-projects`, `domino-environments`, `domino-experiment-setup`, `domino-trace-setup`, `domino-datasets`, `domino-data-sdk`, `domino-data-connectivity`, `domino-llm-gateway`, `domino-llm-access`, `domino-model-monitoring` for new projects and configuration |

### Output Styles (Claude Code only)

Switch output styles with `/output-style`:

| Style | Description |
| --- | --- |
| `domino-learning` (shown as **Domino Learning**) | Educational mode with Domino Insights after each task |
| `domino-mlops` (shown as **Domino MLOps**) | Production-focused with MLOps checklists and best practices |

---

## Project Structure

```
domino-ai-plugin/
├── .claude-plugin/plugin.json   # Claude manifest — source of truth for name, version, description
├── plugin.json                  # Portable (Agent Plugins) manifest + OpenAI listing metadata
├── .cursor-plugin/              # Cursor manifest, MCP config and marketplace
├── gemini-extension.json        # Gemini CLI extension manifest (synced from the Claude manifest)
├── .mcp.json                    # Claude MCP config (stdio)
├── mcp.json                     # Portable MCP config (stdio) for Codex local installs
├── mcp_config.json              # MCP servers for Antigravity
├── rules/domino.md              # Always-on guidance for every host
├── assets/logo.svg              # OpenAI listing icon (square)
├── skills/                      # Shared, provider-neutral skills (35)
├── mcp-servers/domino_mcp_server/
├── evals/                       # claude plugin eval cases (not shipped to OpenAI)
├── agents/                      # Subagents: thin routers to skills (Claude Code; Cursor reads them too)
├── output-styles/               # Claude-only output styles
├── hooks/                       # Hook documentation (nothing is loaded from here)
├── scripts/
│   ├── build-openai.sh          # Builds the OpenAI portal ZIP into dist/
│   ├── sync-manifests.py        # Syncs plugin.json, .cursor-plugin/plugin.json, gemini-extension.json from the Claude manifest
│   ├── lint-skills.py           # Skill rules every host relies on
│   ├── claude-mentions.allow    # Skill files allowed to mention Claude, with reasons
│   ├── check-version.sh         # Release-scheme check (CI)
│   └── verify-update-flow.sh    # checks Claude Code reads a local marketplace clone in place
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Skill rules

`scripts/lint-skills.py` runs in CI and enforces:

- Every `skills/<dir>/SKILL.md` has valid YAML front matter with a unique `name` equal to its
  directory name, a `description` of at most 1,024 characters, and a non-empty body.
- `SKILL.md` is at most 8,000 bytes; Codex truncates anything longer. Detail goes in sibling files.
- `SKILL.md` contains no `${` at all, because Gemini CLI rewrites `${name}` in skill text with its
  own variables, the settings declared in `gemini-extension.json` and every key of a trusted
  workspace's `.env`. Files that document product syntax written that way (Launcher `${param}`
  placeholders) are listed in `scripts/gemini-substitution.allow` with a reason; even there,
  Gemini's own names and the declared settings are rejected.
- `dominodatalab:<skill-name>` is at most 64 characters.
- Relative links resolve and stay inside `skills/`; the OpenAI package ships `skills/` without
  the rest of the repo. Links between skills are fine.
- Skill files don't mention Claude unless listed in `scripts/claude-mentions.allow` with a reason
  (for example, Claude as a model name, or a table that covers both Claude Code and Codex).
- Skill, agent and rule text states facts and instructions only: content-noise rules L1 to L16
  (CONTRIBUTING standards 12 and 13) fail on provenance narrative, test logs, change history,
  process jargon, shouting labels, when-to-use headings, self-describing preambles and names of
  removed skills, and warn on timings, stage labels and spec attestations.

Run it locally with `uv run --with pyyaml python scripts/lint-skills.py`.

## Evals

`evals/` holds behaviour tests for [`claude plugin eval`](https://code.claude.com/docs/en/plugin-evals):
realistic prompts plus graders that check the right skill fired and the result is correct. They
cover the converted commands, the provider-neutral `domino-ui-bootstrap` wording, the "no MCP
server" fallback, and a negative case. Each run is a model call billed to your account:

```bash
claude plugin eval . --scaffold --allow-tools Write Edit --runs 1 --ablation none --no-publish  # quick
claude plugin eval . --scaffold --allow-tools Write Edit --no-publish                           # 3 runs + baseline
```

`--scaffold` runs each case's `fixture.sh`, which writes the files the prompt refers to. Results
go to `evals/results/`, which is git-ignored. `evals/` is not part of the OpenAI package.

`evals/e2e/` is a separate harness, not an eval case: it runs a weak model with the plugin inside real
Domino Workspaces and grades what happened in Domino. See [evals/e2e/README.md](evals/e2e/README.md)
and AGENTS.md "Testing new and updated skills".

---

## Troubleshooting

| Issue | Solution |
| --- | --- |
| `/skills` shows "No skills found" (Claude Code) | Plugin skills don't appear in `/skills` — they are auto-invoked based on context. Check `/plugin` → Installed tab instead. |
| Plugin not loading from settings.json | Claude Code does **not** support a `"plugins"` array in `settings.json`. Use the marketplace approach or `--plugin-dir` flag. |
| `~` path not expanding | Always use absolute paths (e.g., `/home/ubuntu/...`) in marketplace commands and settings. |
| "Failed to parse marketplace file" | Ensure `marketplace.json` has the `owner` object and `source` is a string path (e.g., `"./plugins/domino-claude-plugin"`), not a nested object. |
| `domino_server` tools missing (ChatGPT / Codex) | The directory package is skills-only. Install from a local checkout, or register the server yourself ("How each host registers the server" in `mcp-servers/domino_mcp_server/README.md`). |
| `domino_server` tools fail naming `DOMINO_TOKEN` | Outside Domino the server needs `DOMINO_HOST` and `DOMINO_TOKEN` (a Personal Access Token or service account token); `DOMINO_API_KEY` is no longer accepted. See [Your Domino URL and token](#your-domino-url-and-token). |
| CI: "out of sync with .claude-plugin/plugin.json" | Run `scripts/sync-manifests.py` and commit `plugin.json`, `.cursor-plugin/plugin.json` and `gemini-extension.json`. |

---

## Documentation

- [Domino Documentation](https://docs.domino.ai/cloud)
- [Domino API reference](https://docs.domino.ai/cloud/reference/api)
- [python-domino GitHub](https://github.com/dominodatalab/python-domino)
- [Claude Code Plugin Docs](https://code.claude.com/docs/en/plugins)
- [Gemini CLI extensions](https://geminicli.com/docs/extensions/)
- [OpenAI: Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [OpenAI: Submit a Claude Code plugin](https://developers.openai.com/plugins/guides/submit-claude-plugin)
- [Agent Plugins specification](https://agent-plugins.org)

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Support

- For Domino platform issues: [Domino Support](https://support.domino.ai/)
- For plugin issues: [GitHub Issues](https://github.com/dominodatalab/domino-ai-plugin/issues)
