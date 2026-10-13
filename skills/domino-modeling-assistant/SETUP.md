# Complete Modeling Assistant Setup Guide

When the plugin is installed from the source repository (for example Claude Code, or Codex from a local marketplace), the Domino MCP server is **bundled with the plugin** and starts automatically: no manual cloning, installation, or MCP configuration is required. Skills-only distributions (such as the ChatGPT plugin directory) don't include the server; see [Register the server manually](#register-the-server-manually).

**Inside a Domino Workspace:** everything is auto-detected (project, authentication, DFS/Git mode). Skip straight to [Step 3: Test the integration](#step-3-test-the-integration).

**Outside Domino (laptop, CI):** set two environment variables and create a project settings file. Follow the full guide below.

## Prerequisites

- A Domino account with access to the project
- An MCP-enabled coding assistant (for example Claude Code, Codex, Cursor, or another host that can register a stdio MCP server)
- Python 3.11+
- `uv` package manager ([install guide](https://github.com/astral-sh/uv))
- Git

## Step 1: Set Domino credentials (laptop only)

> **Skip this step inside a Domino Workspace.** There the server calls the platform through `DOMINO_API_PROXY`, which Domino sets and which adds the user's token; no credential is configured or sent.

### Create a Personal Access Token

1. Log into Domino.
2. Go to **Account** > **Account settings** > **Personal Access Token**.
3. Click **Generate new Token**, give it a name and an expiration, and click **Create token**.
4. Copy the token now; it is shown only once. On a laptop it goes only where the next section puts it (`DOMINO_TOKEN` or the env file): that is the laptop's own copy, since Domino user and Project environment variables are not readable outside Domino. Inside a Workspace no token is needed.

Reference: https://docs.domino.ai/cloud/reference/api/domino-api-authentication (6.3: replace `cloud` with `6.3`). A Personal Access Token carries your identity and expires; rotate it before it does. For unattended automation use a Domino service account token instead. The server does not accept legacy API keys: if `DOMINO_API_KEY` is set without `DOMINO_TOKEN`, every API tool fails with a message telling you to set `DOMINO_TOKEN`.

### Set environment variables

The server reads two variables:

| Variable | Value |
|---|---|
| `DOMINO_HOST` | The deployment's HTTPS URL (the one in your browser's address bar); `DOMINO_API_HOST` is accepted as a fallback |
| `DOMINO_TOKEN` | The Personal Access Token or service account token, sent as `Authorization: Bearer` |

Either export them in your shell profile (`~/.bashrc`, `~/.zshrc`, or equivalent):

```bash
export DOMINO_HOST="https://<your Domino domain>"
export DOMINO_TOKEN="<your Personal Access Token>"
```

or, for hosts that start MCP servers with a stripped environment (Codex on a laptop does), put them in an env file the server reads when the host passes neither variable: `$DOMINO_MCP_ENV_FILE` if set, else `$XDG_CONFIG_HOME/domino-mcp-server/.env`, else `~/.config/domino-mcp-server/.env` (`KEY=value` lines; existing environment variables win):

```bash
mkdir -p ~/.config/domino-mcp-server
printf 'DOMINO_HOST=https://<your Domino domain>\nDOMINO_TOKEN=<your Personal Access Token>\n' > ~/.config/domino-mcp-server/.env
chmod 600 ~/.config/domino-mcp-server/.env
```

A `.env` in the project directory is not read. Never commit the token or paste it into a shared configuration file.

## Step 2: Configure your project (laptop only)

> **Skip this step inside a Domino Workspace.** The project owner, project name, id and DFS/Git mode are auto-detected from platform environment variables.

In your Domino project directory, create `domino_project_settings.md`:

```markdown
# Domino Project Settings

## Project Information
- **Project Owner**: your-username
- **Project Name**: your-project-name

## Default Configuration
- **Compute Environment**: the Domino Standard Environment, or your project's default
- **Hardware Tier**: small-k8s

## Data Locations
- Input data: /mnt/data/
- Imported datasets: /mnt/imported/data/
- Output artifacts: /mnt/artifacts/

## Notes
- Always commit changes before running Domino jobs
- Use MLflow for experiment tracking
```

For a DFS-based project add `- **DFS**: true` so the assistant uses the file tools instead of git.

## Step 3: Test the integration

### Create a test script

In your project, create `test_domino.py`:

```python
import os
print("Hello from Domino!")
print(f"Project: {os.environ.get('DOMINO_PROJECT_NAME', 'unknown')}")
print(f"User: {os.environ.get('DOMINO_STARTING_USERNAME', 'unknown')}")
```

### Commit the script (Git-based projects)

```bash
git add test_domino.py
git commit -m "Add test script for modeling assistant"
git push
```

For a DFS-based project, ask the assistant to sync the file instead (`smart_sync_file`).

### Run it through your AI assistant

Prompt:

```
Run test_domino.py as a Domino job
```

The assistant calls `run_domino_job(..., wait_seconds=300)` and, if the Job outlives one call, `check_domino_job_run_status(run_id, wait_seconds=300)` again instead of sleeping or polling, then reads the full output with `check_domino_job_run_results`; waiting rules and caps: [TOOLS.md](./TOOLS.md#waiting-for-a-job).

## Step 4: Choose a compute environment

Use the **Domino Standard Environment** for the project (**Settings** > **Compute Environment**). On Domino 6.3 and Cloud it ships with the coding assistants, the Domino skills, MLflow, and the common ML libraries. If your organization needs a different assistant, pinned versions, or extra tools, build a custom environment as described at https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/custom-environments (6.3: replace `cloud` with `6.3`).

## Troubleshooting

### "MCP server not found" or tools not appearing

1. Ensure `uv` is installed and in your PATH.
2. Restart your assistant after installing the plugin.
3. Check the plugin and server are enabled:
   - **Claude Code:** `/plugin` > Installed tab; `claude --debug` shows MCP server initialization errors.
   - **Codex:** `/mcp` in a session, or `codex mcp list`, should show `domino_server`.
   - **Other hosts:** open the host's MCP server list and confirm `domino_server` is connected.
4. If the server isn't listed at all, your plugin distribution may be skills-only; register it manually as described below.

### Register the server manually

Clone the plugin repository, then point your assistant at `mcp-servers/domino_mcp_server` as a stdio server. Inside a Domino Workspace no environment variables are needed. Outside Domino pass `DOMINO_HOST` and `DOMINO_TOKEN`, or rely on the env file from Step 1. For Codex:

```bash
codex mcp add domino_server \
  -- uv --directory /path/to/domino-ai-plugin/mcp-servers/domino_mcp_server run domino_mcp_server.py
```

Codex strips the shell environment from MCP servers, so on a laptop use the env file (`~/.config/domino-mcp-server/.env`) rather than `--env`, which would store the token in your Codex config. For Claude Code, `claude mcp add domino_server -- uv --directory ... run domino_mcp_server.py` works the same way and inherits your shell environment. For other assistants, register a stdio server with the same `uv` command and pass `DOMINO_HOST` and `DOMINO_TOKEN` the way the host supports, or use the env file.

### "Unauthorized" or "DOMINO_TOKEN is not set" errors

1. **Workspace:** this should not happen; the API proxy authenticates. Restart the Workspace if it persists.
2. **Laptop:** the error names the variable to fix. Verify `DOMINO_HOST` and `DOMINO_TOKEN` are set in the environment the server runs in (or in the env file), that `DOMINO_HOST` starts with `https://`, and that the Personal Access Token has not expired or been revoked (**Account settings** > **Personal Access Token** shows its status). Remove any `DOMINO_API_KEY`; it is not accepted.

### "Project not found"

1. **Workspace:** project info is auto-detected. Check that `DOMINO_PROJECT_OWNER` and `DOMINO_PROJECT_NAME` are set.
2. **Laptop:** check that `domino_project_settings.md` exists in your project root with the correct owner and project name.

### File conflicts on DFS projects

`smart_sync_file` reports a conflict, with the remote content, when the remote file changed since this session last saw it (or was never seen). Review and merge, then sync again; pass `force_overwrite=True` only when the remote version should be discarded. Overwrite rules for the other upload tools, binary content and the Git-based exclusion: [TOOLS.md](./TOOLS.md#files-text-and-binary-dfs-only).

### Jobs fail immediately

1. Check the compute environment is available.
2. If `run_domino_job` was given `hardware_tier` or `environment_id`, the server validates both against the deployment before starting and the error lists the valid values; omit them to use the project defaults.
3. Read the job's `stdErr` with `check_domino_job_run_results(run_id, log_type="stdErr")`.

### The assistant polls or gives up while a Job runs

Hosts block shell `sleep`, so a status call without `wait_seconds` returns at once. Pass `wait_seconds=300` to `run_domino_job` or `check_domino_job_run_status` and call again when the response says so ([TOOLS.md](./TOOLS.md#waiting-for-a-job), [SKILL.md](./SKILL.md#important-considerations)).

## Next steps

- [SKILL.md](./SKILL.md): overview of modeling assistant capabilities and the MCP server tool reference
- `mcp-servers/domino_mcp_server/README.md` in the plugin repository: full tool, route and environment-variable reference
- https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/modeling-assistant: the end-to-end walkthrough
- https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/domino-skills: the other Domino skills the assistant can use
