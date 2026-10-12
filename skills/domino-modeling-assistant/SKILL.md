---
name: domino-modeling-assistant
description: Enable AI-assisted model development (vibe modeling) in Domino. The assistant writes the data-analysis, model and training code and uses the bundled Domino MCP server to run it as Domino Jobs, check job status and output, and read, upload and sync files for DFS projects, so work stays reproducible, governed and tracked in Experiment Manager. Use when setting up an AI coding assistant to work with Domino, configuring or troubleshooting the Domino MCP server, or when the user asks to analyze a dataset, train or compare models, or run scripts as Domino Jobs from a coding assistant.
compatibility: Domino 6.3 and Domino Cloud. Inside a Domino Workspace the bundled MCP server calls the platform through DOMINO_API_PROXY with no credentials; outside Domino it needs DOMINO_HOST and DOMINO_TOKEN (a Personal Access Token or service account token).
---

# Modeling assistant

Applies to Domino 6.3 and Domino Cloud.

This skill enables a modeling assistant within Domino Data Lab: an AI coding assistant that writes code and runs it on the platform through the Domino MCP server.

Vibe modeling means using the assistant beyond code generation, for:
- Experiment setup and configuration
- Data analysis and exploration
- Model training and evaluation
- Results interpretation

## Key components

### MCP (Model Context Protocol)

The Domino MCP server bridges the coding assistant and the Domino platform APIs needed for running Jobs (analysis and training scripts run better as Jobs than on the local terminal), checking job status and output, and reading, uploading and syncing files of a Domino File System (DFS) project when it does not use a Git repository.

The server is **bundled with this plugin** (`mcp-servers/domino_mcp_server/`, name `domino_server`) and starts automatically when the plugin is installed from its source repository. Skills-only distributions do not include it.

If the `domino_server` tools (such as `run_domino_job`) are not available in this session, do not pretend to call them. Tell the user, point them at [SETUP.md](./SETUP.md#register-the-server-manually), and meanwhile use the `domino-jobs` and `domino-python-sdk` skills to run work through the Domino REST API.

- **Inside a Domino Workspace:** nothing to configure. The server calls the platform through `DOMINO_API_PROXY` (no `Authorization` header; the proxy adds the user's token) and reads the project from `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_OWNER`, `DOMINO_PROJECT_NAME` and `DOMINO_IS_GIT_BASED`. On hosts that start MCP servers with a stripped environment (Codex), it recovers these variables from its parent process.
- **Outside Domino (laptop, CI):** set `DOMINO_HOST` (the deployment's HTTPS URL) and `DOMINO_TOKEN` (a Personal Access Token or service account token, sent as `Authorization: Bearer`). When the host does not pass environment variables, the server reads `$DOMINO_MCP_ENV_FILE`, else `$XDG_CONFIG_HOME/domino-mcp-server/.env`, else `~/.config/domino-mcp-server/.env`. Legacy user API keys (`DOMINO_API_KEY`, `X-Domino-Api-Key`) are deprecated and not accepted. See [SETUP.md](./SETUP.md).

Tool failures (missing variable, 401/403, conflict, file too large) come back as MCP tool errors whose message says what to fix; relay it to the user instead of retrying blindly.

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/modeling-assistant (6.3: replace `cloud` with `6.3`).

## Important considerations

You are a Domino Data Lab powered agentic coding tool that helps write code in addition to running tasks on the Domino Data Lab platform on behalf of the user using the tool functions provided by the `domino_server` MCP server. Whenever possible run commands as Domino Jobs rather than on the local terminal.

At the start of every session, call `get_domino_environment_info`. It tells you whether you are inside a Domino Workspace or on a laptop, the project owner, name and id, whether the project is Git-based or DFS, which authentication mode is active, and what is missing. Inside a Workspace everything is auto-detected; you do not need `domino_project_settings.md`. Outside Domino, fall back to `domino_project_settings.md` for the project name, user name, and dfs setting.

After `run_domino_job`, poll `check_domino_job_run_status` with the returned `run_id` until the response's `is_completed` is true (`status` is Domino's free-form execution status: `Queued`, `Preparing`, `Running`, `Succeeded`, `Failed`, `Stopped`, ...), then read the output with `check_domino_job_run_results` (`stdOut` by default; use `log_type="stdErr"` when the status is not `Succeeded`) and briefly explain the conclusions. If the output includes an MLflow or experiment run URL, share it with the user using `open_web_browser`.

Assume project data is already in the Domino project and accessible from job runs, under `/mnt/data/` or `/mnt/imported/data/` (Git-based) or `/domino/datasets/` (DFS); confirm the full path by running a job that lists the folder contents recursively. Always create scripts to understand and transform data and run them as jobs; print analytical output as plain-text tables on stdout so job results are easy to check. Do not delete analysis scripts; save summary charts as image files in the project.

Always check whether the local project has uncommitted changes. For Git-based projects, commit and push before running any Domino job, otherwise Domino cannot see the new files. For DFS-based projects, use the MCP server file tools instead of git before running any jobs: prefer `smart_sync_file`, which detects conflicts; it never replaces a remote file it has not seen in this session unless `force_overwrite=True`, and a conflict returns the remote content so you can merge. `upload_file_to_domino_project` and `sync_local_file_to_domino` refuse to replace an existing, different file unless `overwrite=True`. Do not force an overwrite without telling the user what will be replaced.

When training a model, use MLflow instrumentation and assume the tracking server is configured by Domino; do not set a tracking URI.

## MCP server tools

| Tool | Description |
|------|-------------|
| `get_domino_environment_info()` | Inside or outside Domino, project owner, name and id, Git-based or DFS, auth mode, what is missing |
| `run_domino_job(user_name, project_name, run_command, title)` | Start a Job with one command string; returns the `run_id` |
| `check_domino_job_run_status(run_id, user_name=None, project_name=None)` | Execution status (`Queued`, `Running`, `Succeeded`, `Failed`, ...) |
| `check_domino_job_run_results(run_id, user_name=None, project_name=None, log_type="stdOut")` | Job output; `log_type` is `stdOut`, `stdErr`, `prepareOutput` or `complete` |
| `open_web_browser(url)` | Open a URL in the default browser of the machine running the server (no-op in a Workspace) |
| `list_domino_project_files(user_name, project_name, path="/")` | Files and subdirectories of one directory of a DFS project (not recursive) |
| `download_file_from_domino_project(...)` | Content of a text file at the latest commit; remembers the version for `smart_sync_file` |
| `upload_file_to_domino_project(..., overwrite=False)` | Create a text file; replaces an existing one only with `overwrite=True` |
| `sync_local_file_to_domino(..., overwrite=False)` | Read a local file and upload it (same overwrite rule) |
| `smart_sync_file(..., force_overwrite=False)` | Upload with conflict detection; `no_change`, uploaded, or conflict with the remote content returned |

A job id and a run id are the same value. Files are UTF-8 text up to 2 MiB; paths are project-relative. Full tool reference and routes: `mcp-servers/domino_mcp_server/README.md` in the plugin repository. Upstream source: https://github.com/dominodatalab/domino_mcp_server
