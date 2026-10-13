# Domino MCP server

A stdio [MCP](https://modelcontextprotocol.io) server, bundled with the `dominodatalab` plugin,
that lets an AI coding assistant work with a Domino project: start Jobs, read their status and
output, and read, upload and sync the files of a DFS (non-Git) project. The
`domino-modeling-assistant` skill describes the workflow built on it.

It runs on `uv` from this directory (`uv --directory <here> run domino_mcp_server.py`); the
committed `uv.lock` pins the dependencies. Python 3.11 or later; the standalone
[FastMCP](https://gofastmcp.com) framework on the official `mcp` SDK 2.x, which speaks MCP
protocol 2026-07-28 and still answers handshake-era clients (2024-11-05 to 2025-11-25): the
server negotiates whatever the host speaks and prints the client's name and protocol version on
stderr at its first tool call.

## Tools

| Tool | Kind | What it does | Domino route |
|---|---|---|---|
| `get_domino_environment_info` | read, local | Inside or outside Domino, project owner, name and id, Git-based or DFS, auth mode, what is missing | none (environment variables) |
| `run_domino_job` | write | Starts a Job with one command string; optional `commit_id`, `hardware_tier`, `environment_id`, `git_branch`; pins the commit after recent uploads; with `wait_seconds` waits on the server and returns the final status and the end of the stdout | `POST /api/jobs/v1/jobs`; `GET /api/hardwaretiers/v1/hardwaretiers` and `GET /api/environments/beta/environments` to validate the ids (Public API) |
| `check_domino_job_run_status` | read | Execution status of a job (`Queued`, `Running`, `Succeeded`, `Failed`, ...); with `wait_seconds` waits on the server until it completes or the cap is reached | `GET /api/jobs/beta/jobs/{jobId}` (Public API) |
| `check_domino_job_run_results` | read | Job output: `stdOut` by default, or `stdErr`, `prepareOutput`, `complete` | `GET /api/jobs/beta/jobs/{jobId}/logs` (Public API) |
| `list_domino_project_files` | read | Files and subdirectories of one directory of a DFS project (not recursive) | `GET /v4/files/browseFiles`, `GET /v4/files/browseDirectories` (Internal API) |
| `download_file_from_domino_project` | read | Content of a file at the latest commit (text as `content`, binary as `content_base64`); records the version for `smart_sync_file` | `GET /api/projects/beta/projects/{id}/commits/latest`, `GET /api/projects/v1/projects/{id}/files/{commitId}/{path}/content` (Public API) |
| `upload_file_to_domino_project` | write | Creates a file of any type in a DFS project (`file_content` text or `content_base64`); replaces an existing one only with `overwrite=True`; refuses Git-based projects; returns the `commitId` that contains the file | `PUT /v1/projects/{owner}/{project}/{path}` (legacy API) |
| `sync_local_file_to_domino` | write | Reads a local file as bytes (model artifacts, images, text) and uploads it unchanged; returns `commitId` | as above |
| `smart_sync_file` | write | Upload of any file type (`content` text or `content_base64`) with conflict detection; never replaces a file it has not seen unless `force_overwrite=True`; refuses Git-based projects; returns `commitId` | the read routes above plus the legacy upload |
| `open_web_browser` | local side effect | Opens a URL in the default browser of the machine running the server; inside a Domino execution it returns `False` without doing anything | none |

A job id and a run id are the same value, so `run_id` from `run_domino_job` goes straight into
the status and results tools. `user_name` and `project_name` on those two tools are optional and
kept for compatibility.

### Which commit a Job runs

For some seconds after an upload, the Jobs, Apps and Model API services still resolve the
previous DFS head, even once the files API shows the new commit (seen on Domino Cloud 6.4: a
Job submitted 5 s after an upload ran from the project-creation commit and could not find the
file). So:

- Every upload tool (`upload_file_to_domino_project`, `sync_local_file_to_domino`,
  `smart_sync_file`) waits until the files API shows the upload and returns `commitId`, the
  project commit that contains it.
- `run_domino_job` takes `commit_id` and sends it as `NewJobV1.commitId` (both specs). When it is
  omitted on a DFS project and this process uploaded files in the last 15 minutes, the server
  pins the Job itself: the latest commit if it contains all of those files, else the newest
  commit confirmed to contain them; if an upload is not in any commit yet after 45 s the call
  fails rather than start a Job without the file. The commit used comes back as `commit_id`
  (`null` when the head was taken). On a Git-based project `commit_id` is the main-repository
  commit, sent as `mainRepoGitRef` with `refType` `commitId` (the Cloud spec rejects `commitId`
  there); it cannot be combined with `git_branch`.

The same applies to Apps and Model API versions started through the REST API: pin the commit an
upload tool returned instead of taking the head.

### Waiting for a Job

Hosts block a standalone `sleep` and a status call returns at once, so waiting happens on the
server: `check_domino_job_run_status(run_id, wait_seconds=300)` polls `GET /api/jobs/beta/jobs/{jobId}`
with a 3 s to 10 s backoff until the Job completes or the budget is spent, then returns the last
status with `waited_seconds` and, if not complete, a `message` saying to call again.
`run_domino_job(..., wait_seconds=300)` does the same right after starting the Job and, once it
completes, adds `results` (the last 100 lines or 8,000 characters of stdout, `results_truncated`
when cut) and the MLflow link if the output printed one.

Every tool call runs under a time budget, 600 s or 50 s under Codex: HTTP timeouts shrink to
what is left of it, no request starts once it is spent, a status read is never started after the
deadline, and once a Job has been submitted the call returns its id with a "call again" message
rather than fail. Claude Code allows hours per MCP call (`MCP_TOOL_TIMEOUT`, default
about 28 hours; a call past two minutes moves to a background task) and aborts a stdio call only
after 30 minutes without a response. Codex ends a tool call after 60 s by default
(`tool_timeout_sec`), so when the connected client calls itself `codex` the server caps one wait
at 50 s and the model calls again; set `tool_timeout_sec` higher in `~/.codex/config.toml` to
wait longer per call. Other hosts: check their per-tool timeout and pass a smaller `wait_seconds`
if needed.

### Hardware tier and environment

`run_domino_job` accepts `hardware_tier` (id such as `small-k8s`, or name) and `environment_id`
(id or name). Domino silently runs a Job on the project default for an unknown hardware tier id,
so both values are checked against `GET /api/hardwaretiers/v1/hardwaretiers` (archived tiers
excluded, list cached per process) and `GET /api/environments/beta/environments` before the Job
starts; an unknown value is an error that lists what exists. Omit both for the project defaults.

Project ids come from `DOMINO_PROJECT_ID` inside Domino when the names match the current
project, otherwise from `GET /api/projects/beta/projects`, scanned page by page until an empty
page (cached per process). The same lookup says whether the project is Git-based
(`mainRepository`, or `DOMINO_IS_GIT_BASED` inside Domino): the write tools refuse Git-based
projects, because Jobs there run the repository, not uploaded files; commit and push instead.

### Conflict detection

`download_file_from_domino_project` and the upload tools remember the version key of each file
they saw (Domino's key for a DFS file is the SHA-1 of its content). `smart_sync_file` reads the
remote file at the latest commit before every upload:

| Remote file | Baseline in this session | Result |
|---|---|---|
| does not exist | any | created |
| identical to your content | any | `no_change`, nothing uploaded |
| differs, none | none | **conflict**: remote content returned, nothing uploaded |
| differs, key equals baseline | yes | uploaded |
| differs, key differs from baseline | yes | **conflict**: remote content, baseline content and both keys returned, nothing uploaded |

Only `force_overwrite=True` replaces a conflicting file; the response then carries
`previous_remote_key`. Within one server process, read-check-write-confirm on a path is
serialized (tool calls run in worker threads), and a Job's commit selection waits for in-flight
uploads to the project; two clients of the same project, or two Workspaces, are not serialized,
because Domino has no conditional write. `upload_file_to_domino_project` and `sync_local_file_to_domino` refuse an
existing, different file unless `overwrite=True`. The baseline lives in the server process: a
new session starts without one, which is the safe direction (a conflict, never an overwrite).

"Does not exist" is concluded only from a 404, or from a 403 (what Domino answers for a missing
path) confirmed by a listing of the parent directory that does not contain the file. Any other
failure to read the file is an error, and nothing is written over a file that could not be read.

Domino's project-file reads (latest commit and file content) lag a write by up to about 20
seconds (observed on Domino Cloud 6.4): a read in that window returns the previous version. The
server remembers the files it wrote in this process and, before trusting a read of one of them,
re-reads (every 2 s, up to 45 s) until the read shows the version it wrote, a newer one (another
client wrote after it: a real conflict), or the timeout passes (the result then carries a note
saying to retry). The upload tools do this wait themselves so that they can return `commitId`,
and `run_domino_job` pins that commit (see "Which commit a Job runs"). What this cannot cover: a write by another client in the
last ~20 s is not visible yet, so a sync in that window may miss it. For shared projects, give
other people's edits a minute before syncing over them.

Files are bytes: text files travel as `content` / `file_content`, binary files (model artifacts
such as `.joblib` or `.pkl`, images) as `content_base64`, and `sync_local_file_to_domino` reads
any local file as bytes. Version keys and conflict checks compare bytes. A tool returns file
content (text, or base64 for binary) up to 2 MiB; larger files are still compared by key, with
`content_omitted` in place of the content. Paths are project-relative; `..` is rejected.

## Environment variables

### Inside a Domino execution (Workspace, Job, App)

Nothing to configure. Domino sets these and the server reads them:

| Variable | Used for |
|---|---|
| `DOMINO_API_PROXY` | Base URL for every API call; the proxy adds the starting user's token, so no `Authorization` header is sent. Its presence is what "inside Domino" means to this server. |
| `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_OWNER`, `DOMINO_PROJECT_NAME` | The current project, reported by `get_domino_environment_info` and used instead of a lookup |
| `DOMINO_IS_GIT_BASED` | Git-based (`true`) or DFS (`false`) project. If unset, `git rev-parse` runs in `DOMINO_WORKING_DIR`; never in the server's own directory |
| `DOMINO_WORKING_DIR`, `DOMINO_RUN_ID` | Reported for context |
| `VSCODE_PROXY_URI` | The user-facing Domino URL, for the MLflow run link in job results. Without it the result carries only `mlflow_path` (`DOMINO_API_HOST` is the in-cluster URL and would give unreachable links) |

Some hosts start stdio MCP servers with a stripped environment (Codex passes only `HOME`,
`LANG`, `LC_ALL`, `LOGNAME`, `PATH`, `SHELL`, `USER`). On Linux the server then copies the
variables above from the nearest ancestor process that has `DOMINO_API_PROXY` or
`DOMINO_API_HOST` set (`/proc/<pid>/environ`, same user), so it still works inside a Workspace.

### Outside Domino (laptop, CI)

| Variable | Value |
|---|---|
| `DOMINO_HOST` | Your Domino URL, for example `https://domino.example.com` (`DOMINO_API_HOST` is accepted as a fallback). `http://` is refused except for localhost, because it would send the token in clear text; set `DOMINO_INSECURE_HTTP=true` to allow it deliberately |
| `DOMINO_TOKEN` | A [Personal Access Token](https://docs.domino.ai/cloud/reference/api/domino-api-authentication) (Account settings > Personal Access Token) or a service account token, sent as `Authorization: Bearer`. Surrounding whitespace is stripped; a value with whitespace inside is rejected. Ignored when `DOMINO_API_PROXY` is set. The token never appears in tool results, errors or logs. |

Legacy user API keys (`DOMINO_API_KEY`, `X-Domino-Api-Key`) are deprecated by Domino and not
supported by this server: a PAT is rejected on that header, and a legacy key is not sent. If
`DOMINO_API_KEY` is set and `DOMINO_TOKEN` is not, every API tool fails with a message that says
to set `DOMINO_TOKEN`, and the server prints the same warning on stderr at start.

When the host does not pass these variables, the server reads an env file (`KEY=value` lines,
existing non-empty variables win): `$DOMINO_MCP_ENV_FILE` if set, else
`$XDG_CONFIG_HOME/domino-mcp-server/.env`, else `~/.config/domino-mcp-server/.env`. Make it
readable only by you (`chmod 600`). A `.env` in the project directory or next to the server is
not read: `uv --directory` starts the server with the plugin directory as its working directory,
and earlier versions that walked up from the server directory found files by accident. The
"not set" errors name the env file path, since under Codex it is the only route that works.

Errors from the API say which variable to fix: a 401 or 403 outside Domino names `DOMINO_TOKEN`
and `DOMINO_HOST`; a missing variable names both and links the authentication page.

## How each host registers the server

| Host | File | Environment |
|---|---|---|
| Claude Code | `.mcp.json` (plugin root): `uv --directory ${CLAUDE_PLUGIN_ROOT}/mcp-servers/domino_mcp_server run domino_mcp_server.py` | Inherits your shell; the `env` block forwards `DOMINO_HOST` and `DOMINO_TOKEN` as `${VAR}`. An unset variable arrives as the literal text `${DOMINO_TOKEN}` (documented Claude Code behaviour), which the server treats as unset. |
| Codex and the ChatGPT desktop app (local marketplace) | `mcp.json` (Agent Plugins format, `${PLUGIN_ROOT}`) | No `env` block (the format forbids secrets there) and Codex strips the shell environment. Inside a Workspace the server recovers the Domino variables itself; on a laptop use the env file above. |
| Cursor | `.cursor-plugin/mcp.json` (`${CURSOR_PLUGIN_ROOT}`) | `${env:DOMINO_HOST}` and `${env:DOMINO_TOKEN}`, resolved from your environment. Whether Cursor passes literal text or an empty string for an unset variable is not documented; the server treats both as unset. |
| Any other host | register a stdio server with the same `uv --directory <path to this directory> run domino_mcp_server.py` command | pass `DOMINO_HOST` and `DOMINO_TOKEN` the way the host supports, or use the env file |

The server's `instructions` (sent in the MCP `initialize` response) are the lead section of
`rules/domino.md` two directories up, so hosts that only surface server instructions, such as
Codex, get the plugin's always-on guidance. The server name is `domino_server`; Claude Code
exposes the tools as `mcp__plugin_dominodatalab_domino_server__<tool>`.

## Routes outside the Public API

Everything with an equivalent in both published Public API specs
(`https://docs.domino.ai/api-specs/6.3/public-api.json`,
`https://docs.domino.ai/api-specs/cloud/public-api.json`) uses it. Two operations have none:

| Operation | Route | Status |
|---|---|---|
| List the files of a DFS project directory | `GET /v4/files/browseFiles`, `GET /v4/files/browseDirectories` | Domino Internal API, may change between Domino versions (documented per cluster at `https://<domino-domain>/docs`) |
| Upload a file to a DFS project | `PUT /v1/projects/{owner}/{project}/{path}` | Legacy API, in no published spec |

Both are labelled at the point of use in `domino_mcp_server.py`. For Git-based projects, commit
and push instead of uploading.

## Development

```bash
cd mcp-servers/domino_mcp_server
uv run --with pytest pytest          # unit tests with mocked HTTP (auth, env recovery, DFS detection, sync)
uv lock                              # after changing pyproject.toml; commit uv.lock
claude --plugin-dir ../.. mcp list   # expect domino_server: Connected
```

Every HTTP call has a 10 s connect and 60 s read timeout and runs in a worker thread, so the
stdio event loop keeps answering pings while Domino is slow. Tool failures are raised as MCP
tool errors with the message the user needs, not returned as data; the bearer token is redacted
from every error text. Running the tests inside a Domino Workspace is fine: the fixtures pin the
environment and disable the ancestor-process recovery.
