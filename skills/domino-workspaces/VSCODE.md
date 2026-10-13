# VS Code Workspaces in Domino

Launching, persistence, SSH and the session API are in [SKILL.md](./SKILL.md).

Domino serves VS Code in the browser with code-server. The Domino Standard Environment includes it with the Python and Jupyter tooling and the AI coding-assistant extensions pre-installed.

## Start a VS Code Workspace

1. **Workspaces** > **+ Create New Workspace**.
2. Select an environment whose Pluggable Workspace Tools include `vscode` (the DSE does), then **VS Code** as the IDE.
3. Choose the hardware tier and data mounts, then **Launch**.

Resume a stopped Workspace with **Start** or `POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions` (SKILL.md). There is no Public API route that creates a Workspace.

## Extensions

Extensions installed from the Extensions panel land in `$HOME/.local/share/code-server/extensions` and disappear on restart unless **Home Directory Persistence** is on. To make them part of the environment, install them from its **Pre Run Script** or **Dockerfile Instructions** (`code-server --install-extension ...`, also for a downloaded `.vsix`): [WORKSPACE-TOOLS.md](../domino-environments/WORKSPACE-TOOLS.md#vs-code).

## Settings that survive restarts

The documented VS Code start script runs `code-server --user-data-dir $DOMINO_WORKING_DIR/.vscode`, so user settings live with the Project files and persist; check the running flags with `ps aux | grep code-server` if your environment differs. Workspace settings in `.vscode/settings.json` of the working directory persist and sync as well. Example:

```json
{
  "editor.tabSize": 4,
  "files.autoSave": "afterDelay",
  "python.defaultInterpreterPath": "/opt/conda/bin/python"
}
```

Check the interpreter path in the environment with `which python` before pinning it.

## Local VS Code over SSH

Prerequisites and `dom connect` are in SKILL.md ("SSH from a local IDE"). Summary:

1. Launch with **Enable SSH access**; install the Dom CLI from the Workspace **Settings > SSH connection** pane.
2. `dom connect <workspace_id> --domino-api-host=https://<the URL you open Domino at in the browser> -l ubuntu`
3. Add `Include ~/.domino/ssh/config` to `~/.ssh/config` (or set `Remote.SSH: ConfigFile` to `~/.domino/ssh/config`).
4. **Remote Explorer > SSH** > pick the workspace entry. Files, terminal and debugger then run in the Workspace with your local extensions.

Cursor users import the Remote-SSH extension the same way. Custom TLS CAs must be trusted on the local machine.

## Python, notebooks, terminal

- `Ctrl+Shift+P` > **Python: Select Interpreter** picks the environment's Python.
- `.ipynb` files open natively; cells run on the same kernel the Jupyter IDE would use.
- Integrated terminal: Ctrl+backtick. `git`, `pip`, `python` and the Domino env vars (`DOMINO_WORKING_DIR`, `DOMINO_API_PROXY`, ...) are available.

## Files and Git

- DFS Project: work under `/mnt`; **File Changes > Sync to Domino** pushes to the Project.
- Git-based Project: the repository is at `/mnt/code`; use the Source Control panel or terminal for commits, and **File Changes > Sync to Git / Pull** in the Workspace pane for Domino-managed sync. Artifacts go to `/mnt/artifacts`.
- Files outside `/mnt` are not persisted or synced.

## Coding assistants

The DSE pre-installs AI coding-assistant extensions and CLIs; sign in once in the extension panel (copy the login URL manually if the link does not open) and keep **Home Directory Persistence** on so the login survives restarts. Where an administrator has installed the LLM Gateway 2.0 Extension, offer to route the assistant through it, never by default ([CODING-ASSISTANTS.md](../domino-llm-gateway/CODING-ASSISTANTS.md)). Details and troubleshooting: https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants

## Troubleshooting

- **Slow or unresponsive**: hardware tier too small; close heavy extensions; check **Usage**.
- **Extension missing after restart**: install it through the environment or enable Home Directory Persistence.
- **Remote-SSH cannot connect**: SSH not enabled at launch, Dom CLI not authenticated, the include line missing from `~/.ssh/config`, or a custom CA not trusted locally.
- **Blank extension panel**: reload the browser tab.

## Docs

- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/launch-a-workspace/launch-a-vs-code-workspace
- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/launch-a-workspace/streamline-local-development-ssh
- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/work-with-pluggable-workspaces/configure-native-workspaces
