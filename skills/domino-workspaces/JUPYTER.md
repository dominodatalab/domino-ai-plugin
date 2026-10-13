# Jupyter and JupyterLab Workspaces in Domino

Applies to Domino 6.3 and Domino Cloud. Launching, persistence, SSH and the session API are in [SKILL.md](./SKILL.md).

## Jupyter Notebook vs JupyterLab

Both ship in the Domino Standard Environment and run on port 8888 behind the Domino proxy. Domino recommends JupyterLab (file browser, terminals, multi-tab editing, extensions). Classic Jupyter remains available for single-notebook work.

## Start a Jupyter Workspace

1. **Workspaces** > **+ Create New Workspace**.
2. Select an environment that includes Jupyter tools (the DSE does), then **JupyterLab** or **Jupyter** as the IDE.
3. Choose the hardware tier and data mounts, then **Launch**.

A stopped Workspace is resumed with **Start** in the UI or `POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions` (see SKILL.md). Creating one has no public route; the internal `POST /v4/workspace/project/{projectId}/workspace` does it (non-public route; may change in a future Domino version; [API.md](./API.md)).

## Where files live

| | DFS Project | Git-based Project |
|---|---|---|
| Working directory (`DOMINO_WORKING_DIR`) | `/mnt` | `/mnt/code` |
| Notebooks you want tracked | under `/mnt` | under `/mnt/code` (Git) or `/mnt/artifacts` (DFS artifacts) |
| Datasets | `/domino/datasets/local/<name>` | `/mnt/data/<name>` |
| Job results written from a notebook | Project root | `/mnt/artifacts/results/` |

JupyterLab opens in `DOMINO_WORKING_DIR` and can browse the whole filesystem, but only files under `/mnt` persist and sync. Save, then **File Changes > Sync** in the Workspace pane; the IDE's save does not push to Domino.

```python
import os
from pathlib import Path

work = Path(os.environ["DOMINO_WORKING_DIR"])
git_based = os.environ.get("DOMINO_IS_GIT_BASED", "false").lower() == "true"
datasets = Path("/mnt/data") if git_based else Path("/domino/datasets/local")
df = pd.read_csv(datasets / "my-dataset" / "data.csv")
```

Domino also sets `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_NAME`, `DOMINO_PROJECT_OWNER`, `DOMINO_RUN_ID`, `DOMINO_USER_NAME`, `DOMINO_HARDWARE_TIER_ID` and `DOMINO_API_PROXY`; project, user and environment variables you define appear in the same `os.environ`. Full list: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/manage-compute-environments/manage-environment-variables/5-glossary-default-variables

## External data and the Domino API from a notebook

```python
from domino_data.data_sources import DataSourceClient   # domino-data SDK, see domino-data-sdk skill

df = DataSourceClient().get_datasource("my-datasource").query("SELECT * FROM customers").to_pandas()
```

Platform API calls go through `os.environ["DOMINO_API_PROXY"]` with no `Authorization` header ([domino-api-intro](../domino-api-intro/SKILL.md)).

## Packages

- `!pip install --user <package>` installs for the current session only, unless Package Persistence is enabled for the environment and toggled on for the Workspace.
- `requirements.txt` in `DOMINO_WORKING_DIR` is installed at every start (skipped for packages already persisted).
- Permanent packages belong in the environment Dockerfile ([domino-environments](../domino-environments/SKILL.md)).

## Coding assistants in Jupyter

The DSE includes CLI coding agents that work from a JupyterLab terminal; VS Code adds the extension panels. Jupyter AI is not part of the Domino Standard Environment and Domino's docs do not cover it; if a custom environment installs it, follow the jupyter-ai project documentation, not Domino's. Current Domino guidance: https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants

## Notebooks as Jobs

- A Job whose command is `notebook.ipynb` executes the notebook and saves the executed copy as a result.
- Convert to a script for scheduling: `jupyter nbconvert --to script notebook.ipynb`.
- Parameterize with papermill:

```python
import papermill as pm

pm.execute_notebook("input.ipynb", "output.ipynb", parameters={"data_path": "/mnt/data/my-dataset/new.csv"})
```

See [domino-jobs](../domino-jobs/SKILL.md) for scheduling and the Jobs API.

## Keyboard basics

`Shift+Enter` run and advance, `Ctrl+Enter` run in place, `Alt+Enter` run and insert below.

## Troubleshooting

- **Kernel dies**: memory limit of the hardware tier; check **Usage** on the Workspace, pick a larger tier, or process data in chunks.
- **Module not found after restart**: the package was installed outside the environment without Package Persistence.
- **Notebook will not open**: validate the JSON (`python -m json.tool notebook.ipynb`); very large outputs can be cleared with `jupyter nbconvert --clear-output --inplace notebook.ipynb`.
- **Another app's port is unreachable**: only the IDE port is proxied; use jupyter-server-proxy (SKILL.md, "Coding assistants and extra apps").

## Docs

- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/launch-a-workspace
- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/use-package-persistence
- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/run-multiple-apps-in-a-workspace
