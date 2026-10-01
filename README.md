# Domino Data Lab Plugin for Claude Code, ChatGPT, and Codex

One plugin, two distributions. This repository is a **Claude Code plugin** as checked in, and it
also builds a **ChatGPT / Codex plugin** package for the OpenAI plugin directory. Both share the
same skills and the same Domino MCP server.

## Overview

The plugin helps AI assistants with all aspects of Domino Data Lab, including:

- **Workspaces**: Jupyter, VS Code, RStudio configuration and management
- **Jobs**: Batch execution, scheduled jobs, and monitoring
- **Environments**: Custom Docker environments and package management
- **Datasets**: Data versioning with snapshots and sharing
- **NetApp Volumes**: Enterprise-grade multi-terabyte storage with near-instant snapshots
- **Apps**: Deploy React, Streamlit, and Dash applications
- **Models**: Deploy, monitor, and manage model endpoints
- **GenAI**: Trace and evaluate AI agents with the Domino SDK
- **Distributed Computing**: Spark, Ray, and Dask clusters
- **And more...**

## What ships where

| Component | Claude Code | ChatGPT / Codex |
| --- | --- | --- |
| `skills/` (30 skills) | ✅ | ✅ |
| Domino MCP server (`mcp-servers/`) | ✅ via `.mcp.json` (stdio) | Codex local install: ✅ via `mcp.json` (stdio). Public directory: needs a hosted HTTPS endpoint (see [OpenAI build](#openai-build)) |
| Subagents (`agents/`) | ✅ | ❌ Claude-only |
| Output styles (`output-styles/`) | ✅ | ❌ Claude-only |
| Hook examples (`hooks/`) | Docs only | ❌ |
| Manifest | `.claude-plugin/plugin.json` | `plugin.json` ([Agent Plugins](https://agent-plugins.org) format) |

Skills are written provider-neutral. Where an instruction really is host-specific (for example
which instructions file or MCP config file to write), the skill gives both the Claude Code and
the Codex variant. CI enforces this; see [Skill rules](#skill-rules).

---

## Installation: Claude Code

### Prerequisites

- **Claude Code CLI** v1.0.33 or later (`claude --version` to check)
- Access to a Domino Data Lab instance
- Domino API key (for API operations when running outside a Domino workspace)
- **`uv`** package manager ([install guide](https://github.com/astral-sh/uv)) — required for the bundled Domino MCP server

### Option 1: Marketplace Install (Recommended)

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

- **Marketplace install (Options 1 and 3, or the Anthropic marketplace):** Claude Code keeps a
  cached copy keyed by the plugin version. Pulling the source directory does **not** change what
  Claude loads. Run the update command and restart:

  ```bash
  claude plugin update domino-claude-plugin@domino-marketplace   # local marketplace
  claude plugin update dominodatalab@claude-plugins-official  # Anthropic marketplace
  ```

- **`--plugin-dir` (Option 2):** the plugin is read in place. `git pull`, then start a new session.

---

## Installation: Codex and the ChatGPT desktop app

### From this repository (local marketplace)

Codex reads the portable `plugin.json`, `skills/`, and `mcp.json` straight from the repo, so a
local checkout works without a build step.

```bash
git clone https://github.com/dominodatalab/domino-ai-plugin.git ~/.codex/plugins/domino-ai-plugin
```

Then add an entry to `~/.agents/plugins/marketplace.json`:

```json
{
  "name": "domino-local",
  "interface": { "displayName": "Domino" },
  "plugins": [
    {
      "name": "dominodatalab",
      "source": { "source": "local", "path": "./.codex/plugins/domino-ai-plugin" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Developer Tools"
    }
  ]
}
```

Restart the ChatGPT desktop app or Codex and install **Domino Data Lab** from the `Domino` source
in the Plugins Directory. This path includes the bundled MCP server (stdio, needs `uv`).

> **MCP credentials:** the portable `mcp.json` can't carry secrets, so the server reads
> `DOMINO_API_KEY` and `DOMINO_HOST` from the environment the host passes it. If tools fail with
> "environment variable not set", see `skills/modeling-assistant/SETUP.md` → "Register the server
> manually".

### From the public plugin directory

Once published, install **Domino Data Lab** from the Plugins Directory in ChatGPT or Codex. The
directory package is currently **skills-only**: it doesn't include the MCP server.

---

## OpenAI build

`scripts/build-openai.sh` produces the ZIP you upload at the
[OpenAI plugin submission portal](https://platform.openai.com/plugins):

```bash
scripts/build-openai.sh                               # dist/dominodatalab-openai-skills-only-<ver>.zip
scripts/build-openai.sh --mcp-url https://host/mcp    # dist/dominodatalab-openai-with-mcp-<ver>.zip
```

The script:

1. Checks that `plugin.json` is in sync with `.claude-plugin/plugin.json` and that the listing
   fields fit the directory limits (`scripts/sync-manifests.py --check`).
2. Lints every skill (`scripts/lint-skills.py`).
3. Stages only portable components (`plugin.json`, `skills/`, `assets/`, `LICENSE`) and zips them
   with the plugin root at the archive root.

Choose **Skills only** in the portal for the default ZIP. The **With MCP** path requires the
Domino MCP server to be deployed at a public HTTPS endpoint using Streamable HTTP with OAuth 2.1;
that deployment doesn't exist yet. Until it does, ship skills-only.

The listing icon is `assets/logo.svg`, used for both `logo` and `composerIcon`. It is the
pinwheel mark from `skills/domino-ui-design/assets/domino-logo.svg` on a square `#2E2E38` tile,
because the portal requires square icons of at least 48×48. The build fails if any icon or
screenshot path in `plugin.json` is missing or outside `assets/`.

---

## Versions

The version is **`YYYY.XYY.N`**, for example `2026.603.3`, and both manifests carry the same
string. It's the release year, the oldest Domino line the content supports written as X×100+Y
(`603` = Domino 6.3 and later, including Cloud), and a release counter. The format is valid
semver, which the OpenAI portal requires. Each release is tagged `release-YYYY.XYY.N`. See
CONTRIBUTING.md "Release branches, tags and backports".

Releases up to `2026.6-3.2` used the older `YYYY.X-Y.N` form of the same scheme; `2026.603.3`
is the first in the current form.

`.claude-plugin/plugin.json` is the source of truth. Never edit `plugin.json`'s identity fields
by hand; change `.claude-plugin/plugin.json` and run:

```bash
scripts/sync-manifests.py
```

---

## What's Included

### Bundled MCP Server

A vendored copy of the [Domino MCP Server](https://github.com/dominodatalab/domino_mcp_server)
provides tools for running Domino jobs, checking job status/results, and syncing files with
DFS-based projects.

- **Inside a Domino workspace:** Fully automatic — authentication uses ephemeral tokens, project info is auto-detected.
- **Outside Domino (laptop):** Set `DOMINO_API_KEY` and `DOMINO_HOST` as environment variables in your shell.

Requires `uv`.

### Skills (30 total)

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
| `domino-debug-proxy` | Diagnose reverse-proxy and routing issues in apps |
| `domino-ui-design` | Domino UI styling for integrated app design |
| `domino-ui-bootstrap` | Bootstrap a Vite + React project on the Domino design system |
| `domino-extensions` | Build and operate Domino UI Extensions |
| `domino-experiment-tracking` | MLflow experiment tracking and model registry |
| `domino-experiment-setup` | Generate MLflow experiment setup code for a project |
| `domino-genai-tracing` | `@add_tracing` decorator and `DominoRun` |
| `domino-trace-setup` | Add GenAI tracing helpers and wiring to an agent project |
| `domino-model-endpoints` | Deploy and call model APIs |
| `domino-model-serving` | Model API and registered-model lifecycle over REST |
| `domino-model-monitoring` | Drift detection and model quality tracking |
| `domino-governance` | Policies, bundles, and evidence for model risk governance |
| `domino-flows` | Flyte-based workflow orchestration |
| `domino-distributed-computing` | Spark, Ray, Dask cluster management |
| `domino-ai-gateway` | LLM proxy for OpenAI, Bedrock, etc. |
| `domino-launchers` | Parameterized web forms for self-service |
| `domino-modeling-assistant` | MCP server for AI-assisted model development |
| `domino-data-connectivity` | S3 Mountpoint, AWS IRSA, Azure credentials |
| `domino-api-intro` | Start here for Domino APIs: auth, hosts, pagination, errors |
| `domino-python-sdk` | Python SDK (python-domino) and REST API |
| `domino-data-sdk` | Data SDK (domino-data) for data sources, datasets, training sets |
| `tags-and-properties` | Taxonomy API for tags, namespaces, and typed properties |

`domino-app-init`, `domino-debug-proxy`, `domino-experiment-setup`, and `domino-trace-setup`
replace the former slash commands of the same names. In Claude Code they're still invocable as
`/dominodatalab:<name>`, and every host can also pick them up automatically from context.

### Subagents (Claude Code only)

| Agent | Description |
| --- | --- |
| `domino-deploy` | Specialized agent for deploying apps, models, and endpoints |
| `domino-debug` | Agent for debugging Domino issues and troubleshooting |
| `domino-setup` | Agent for setting up new projects and configurations |

### Output Styles (Claude Code only)

Switch output styles with `/output-style`:

| Style | Description |
| --- | --- |
| `domino-learning` | Educational mode with Domino Insights after each task |
| `domino-mlops` | Production-focused with MLOps checklists and best practices |

---

## Project Structure

```
domino-ai-plugin/
├── .claude-plugin/plugin.json   # Claude manifest — source of truth for name and version
├── plugin.json                  # Portable (Agent Plugins) manifest + OpenAI listing metadata
├── .mcp.json                    # Claude MCP config (stdio)
├── mcp.json                     # Portable MCP config (stdio) for Codex local installs
├── assets/logo.svg              # OpenAI listing icon (square)
├── skills/                      # Shared, provider-neutral skills (30)
├── mcp-servers/domino_mcp_server/
├── agents/                      # Claude-only subagents
├── output-styles/               # Claude-only output styles
├── hooks/                       # Example Claude Code hooks (docs only)
├── scripts/
│   ├── build-openai.sh          # Builds the OpenAI portal ZIP into dist/
│   ├── sync-manifests.py        # Keeps plugin.json in sync with .claude-plugin/plugin.json
│   ├── lint-skills.py           # Skill rules shared by both platforms
│   ├── claude-mentions.allow    # Skill files allowed to mention Claude, with reasons
│   ├── check-version.sh         # Release-scheme check (CI)
│   └── verify-update-flow.sh    # Claude Code cache/update behaviour check
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Skill rules

`scripts/lint-skills.py` runs in CI and enforces:

- Every `skills/<dir>/SKILL.md` has valid YAML front matter with a unique `name` and a
  `description` of at most 1,024 characters, and a non-empty body.
- `dominodatalab:<skill-name>` is at most 64 characters.
- Relative links resolve and stay inside `skills/`; the OpenAI package ships `skills/` without
  the rest of the repo. Links between skills are fine.
- Skill files don't mention Claude unless listed in `scripts/claude-mentions.allow` with a reason
  (for example, Claude as a model name, or a table that covers both Claude Code and Codex).

Run it locally with `uv run --with pyyaml python scripts/lint-skills.py`.

---

## Troubleshooting

| Issue | Solution |
| --- | --- |
| `/skills` shows "No skills found" (Claude Code) | Plugin skills don't appear in `/skills` — they are auto-invoked based on context. Check `/plugin` → Installed tab instead. |
| Plugin not loading from settings.json | Claude Code does **not** support a `"plugins"` array in `settings.json`. Use the marketplace approach or `--plugin-dir` flag. |
| `~` path not expanding | Always use absolute paths (e.g., `/home/ubuntu/...`) in marketplace commands and settings. |
| "Failed to parse marketplace file" | Ensure `marketplace.json` has the `owner` object and `source` is a string path (e.g., `"./plugins/domino-claude-plugin"`), not a nested object. |
| `domino_server` tools missing (ChatGPT / Codex) | The directory package is skills-only. Install from a local checkout, or register the server manually (`skills/modeling-assistant/SETUP.md`). |
| CI: "plugin.json is out of sync" | Run `scripts/sync-manifests.py` and commit `plugin.json`. |

---

## Documentation

- [Domino Documentation](https://docs.dominodatalab.com/en/cloud/user_guide/71a047/what-is-domino/)
- [Domino API Guide](https://docs.dominodatalab.com/en/latest/api_guide/f35c19/api-guide/)
- [python-domino GitHub](https://github.com/dominodatalab/python-domino)
- [Claude Code Plugin Docs](https://code.claude.com/docs/en/plugins)
- [OpenAI: Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [OpenAI: Submit a Claude Code plugin](https://developers.openai.com/plugins/guides/submit-claude-plugin)
- [Agent Plugins specification](https://agent-plugins.org)

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Support

- For Domino platform issues: [Domino Support](https://support.dominodatalab.com/)
- For plugin issues: [GitHub Issues](https://github.com/dominodatalab/domino-ai-plugin/issues)
