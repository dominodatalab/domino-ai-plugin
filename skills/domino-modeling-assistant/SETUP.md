# Complete Modeling Assistant Setup Guide

When the plugin is installed from the source repository (for example Claude Code, or Codex from a local marketplace), the Domino MCP server is **bundled with the plugin** and starts automatically: no manual cloning, installation, or MCP configuration is required. Skills-only distributions (such as the ChatGPT plugin directory) don't include the server; see [Register the server manually](#register-the-server-manually).

**Inside a Domino Workspace:** the Workspace needs a custom Compute Environment with the coding assistant, this plugin and `uv` ([Step 4](#step-4-choose-a-compute-environment)). With that in place everything is auto-detected (project, authentication, DFS/Git mode); skip straight to [Step 3: Test the integration](#step-3-test-the-integration).

**Outside Domino (laptop, CI):** set two environment variables and create a project settings file. Follow the full guide below.

## Prerequisites

- A Domino account with access to the project
- An MCP-enabled coding assistant (for example Claude Code, Codex, Cursor, or another host that can register a stdio MCP server)
- Python 3.11+
- `uv` package manager ([install guide](https://github.com/astral-sh/uv))
- Git

## Step 1: Set Domino credentials (laptop only)

> **Skip this step inside a Domino Workspace.** There the server calls the platform through `DOMINO_API_PROXY`, which Domino sets and which adds the user's token; no credential is configured or sent.

### Get a credential

- **Service account token (first choice):** a Domino administrator creates a service account and a token for it and gives you the value. It goes in `DOMINO_TOKEN`.
- **User API key (fallback):** **Account** > **Account Settings** > **API Key**, then **Regenerate**; the key is shown once, and regenerating it invalidates the previous key. It carries your identity. It goes in `DOMINO_API_KEY`, which the server sends as `X-Domino-Api-Key` when `DOMINO_TOKEN` is not set.

On a laptop the value goes only where the next section puts it: that is the laptop's own copy, since Domino user and Project environment variables are not readable outside Domino. Inside a Workspace no credential is needed.

Reference: https://docs.dominodatalab.com/en/6.1/user_guide/40b91f/domino-api-authentication/

### Give the URL and token to the server

| Variable | Value |
|---|---|
| `DOMINO_HOST` | The address you open Domino at in your browser, for example `https://domino.example.com`; `DOMINO_API_HOST` is accepted as a fallback |
| `DOMINO_TOKEN` | A service account token, sent as `Authorization: Bearer` |
| `DOMINO_API_KEY` | Your user API key, used only when `DOMINO_TOKEN` is not set; sent as `X-Domino-Api-Key`. Put it in the env file: the plugin settings below ask only for the token |

Claude Code asks for both when the plugin is enabled (change them under `/plugin` > Installed > dominodatalab > Configure options), and Gemini CLI asks at install (change them with `gemini extensions config dominodatalab`). Every other host, including Codex, Cursor and Antigravity, reads them from the env file `~/.config/domino-mcp-server/.env`. Have the user write it themselves; this keeps the token off the screen and out of shell history, and makes the file readable only by them:

```bash
bash -c 'mkdir -p ~/.config/domino-mcp-server && umask 077 &&
  read -r -p "Domino URL (https://...): " host && read -rs -p "Domino token: " token && echo &&
  printf "DOMINO_HOST=%s\nDOMINO_TOKEN=%s\n" "$host" "$token" > ~/.config/domino-mcp-server/.env'
```

With a user API key instead of a token, write `DOMINO_API_KEY=%s` in place of `DOMINO_TOKEN=%s`.

The server also reads `$DOMINO_MCP_ENV_FILE` or `$XDG_CONFIG_HOME/domino-mcp-server/.env` where the host passes those variables (Codex passes neither), and `DOMINO_HOST` and `DOMINO_TOKEN` from the environment where the host passes it (Gemini CLI drops TOKEN-named variables). Plugin settings win over the environment, which wins over the env file. A `.env` in the project directory is not read. Never ask the user to paste the token into the conversation, and never commit it or put it in a shared configuration file.

To check the setup, call `get_domino_environment_info`: `credential_sources` says where each value came from, and `connection` names the Domino user the token belongs to or the error to fix.

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

Jobs started by the assistant run in the project's default environment; the Domino Standard Environment ships MLflow and the common ML libraries. To run the assistant inside a Workspace, the Domino 6.1 Standard Environment is not enough: it does not include a coding assistant, the Domino skills or `uv`. Build a custom Compute Environment on top of it whose Dockerfile installs `uv`, the assistant's CLI and this plugin, and select it for the Workspace (**Settings** > **Compute Environment**). Dockerfile instructions and builds: the `domino-environments` skill.

## Troubleshooting

### "MCP server not found" or tools not appearing

1. Ensure `uv` is installed and in your PATH.
2. Restart your assistant after installing the plugin.
3. Check the plugin and server are enabled:
   - **Claude Code:** `/plugin` > Installed tab; `claude --debug` shows MCP server initialization errors.
   - **Codex:** `/mcp` in a session, or `codex mcp list`, should show `domino_server`.
   - **Other hosts:** open the host's MCP server list and confirm `domino_server` is connected.
4. If the server isn't listed at all, your plugin distribution may be skills-only; register it manually as described below.

### Domino 6.1 Workspace image

The standard Domino 6.1 Workspace image has no Node or npm, `python3 -m venv` can fail at
`ensurepip` (use `uv venv`), and git needs `safe.directory` for a clone owned by another user.
`uv` must be able to write `.venv` inside the plugin directory. The docs server (`domino_docs`)
covers Domino 6.3 and Cloud; for 6.1 use https://docs.dominodatalab.com/en/6.1/.

### Register the server manually

Clone the plugin repository, then point your assistant at `mcp-servers/domino_mcp_server` as a stdio server. Inside a Domino Workspace no environment variables are needed. Outside Domino pass `DOMINO_HOST` and `DOMINO_TOKEN`, or rely on the env file from Step 1. For Codex:

```bash
codex mcp add domino_server \
  -- uv run --frozen --directory /path/to/domino-ai-plugin/mcp-servers/domino_mcp_server domino_mcp_server.py
```

Codex strips the shell environment from MCP servers, so on a laptop use the env file (`~/.config/domino-mcp-server/.env`) rather than `--env`, which would store the token in your Codex config. For Claude Code, `claude mcp add domino_server -- uv run --frozen --directory ... domino_mcp_server.py` works the same way and inherits your shell environment. For other assistants, register a stdio server with the same `uv` command and pass `DOMINO_HOST` and `DOMINO_TOKEN` the way the host supports, or use the env file.

### "Unauthorized" or "DOMINO_TOKEN is not set" errors

1. **Workspace:** this should not happen; the API proxy authenticates. Restart the Workspace if it persists.
2. **Laptop:** the error names the variable to fix. Verify `DOMINO_HOST` and `DOMINO_TOKEN` (or `DOMINO_API_KEY`) are set in the environment the server runs in (or in the env file), that `DOMINO_HOST` starts with `https://`, and that the service account token has not expired or been invalidated, or the API key has not been regenerated since you copied it.

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
