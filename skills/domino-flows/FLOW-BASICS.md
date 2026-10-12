# Domino Flows: definitions, configuration, launching, monitoring

Applies to Domino 6.3 and Domino Cloud. Sources: https://docs.domino.ai/cloud/platform-capabilities/features/flows/define-flows, `.../launch-flows`, `.../monitor-flows`, `.../reproducibility-flows`, `.../advanced-flows` (the 6.3 pages are identical).

## Two ways to declare a task

Class constructors give full control; the helper packs config, task and call into one statement. Both run one Domino Job per task.

```python
from typing import TypeVar
from flytekit import workflow
from flytekit.types.file import FlyteFile
from flytekitplugins.domino.task import DominoJobConfig, DominoJobTask
from flytekitplugins.domino.helpers import Input, Output, run_domino_job_task

@workflow
def training_workflow(data_path: str) -> FlyteFile[TypeVar("pt")]:
    # 1. Class constructors
    prep = DominoJobTask(
        name="Prep data",
        domino_job_config=DominoJobConfig(Command="python prep-data.py"),
        inputs={"data_path": str},
        outputs={"processed_data": FlyteFile[TypeVar("csv")]},
        use_latest=True,
    )
    prep_results = prep(data_path=data_path)              # one output: the promise itself

    # 2. Helper
    train_results = run_domino_job_task(
        flyte_task_name="Train model",
        command="python train-model.py",
        inputs=[Input(name="processed_data", type=FlyteFile[TypeVar("csv")], value=prep_results)],
        output_specs=[Output(name="model", type=FlyteFile[TypeVar("pt")])],
        use_project_defaults_for_omitted=True,
    )
    return train_results
```

How to consume a task result depends on how many outputs the task declares, for both `DominoJobTask` and the helper:

- **One output**: the call returns a single promise. Pass it as is (`value=prep_results`, `return train_results`). Do not write `prep_results["processed_data"]`: it compiles, but flytekit binds it as a lookup *inside* the output value (an attribute path on the file), not as selecting the output.
- **Two or more outputs**: the call returns a namedtuple of promises. Select by attribute (`res.train`, `res.test`) or unpack (`train, test = split(...)`). String indexing (`res["train"]`) fails at compile time with `TypeError: tuple indices must be integers or slices, not str`.

The docs.domino.ai define-flows page shows string indexing (`data_prep_results["processed_data"]`); that form fails for multi-output tasks and binds the wrong thing for single-output ones (verified with `flytekit` 1.15 and `flytekitplugins-dominojob` 0.18 on an internal Domino test cluster). Passing one task's output into another creates the dependency edge; tasks without a data dependency run in parallel. A `@workflow` function may return nothing, one output, or a tuple. `@workflow` compiles lazily, so call `my_workflow.compile()` in a Workspace to surface these errors before `pyflyte run`.

## Types

- Files: `FlyteFile[TypeVar("csv")]` (the extension enables preview in the UI), or a Flow Artifact file (`Artifact(name="My Data", type=DATA).File(name="data.csv")`).
- Python base types: `str`, `bool`, `int`, `float`, `list`, `dict`, `datetime`.
- Data science types: `np.ndarray`, `pandas.DataFrame`, `pyspark.DataFrame`, `torch.Tensor`, `torch.nn.Module`, `sklearn.base.BaseEstimator`, `tf.keras.Model`.

Types drive validation at submission, cache keys, lineage and previews. When in doubt use `str` with JSON inside for structured metadata and `FlyteFile` for anything large.

## Task code: inputs and outputs

Each input is a file at `/workflow/inputs/<name>`; each declared output must be written to `/workflow/outputs/<name>` or the task fails even if the script exits 0.

```python
# prep-data.py
from pathlib import Path
import pandas as pd

data_path = Path("/workflow/inputs/data_path").read_text().strip()   # str input: the text of the value
df = pd.read_csv(data_path).dropna()
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
df.to_csv("/workflow/outputs/processed_data", index=False)            # file output: write to the output name
```

```python
# train-model.py
import pandas as pd
import torch

df = pd.read_csv("/workflow/inputs/processed_data")                   # file input: read the path directly
# ... train ...
torch.save(model.state_dict(), "/workflow/outputs/model")
```

R: `read.csv(file.path("/workflow", "inputs", "processed_data"))` and `write.csv(df, file.path("/workflow", "outputs", "processed_data"))`.

Ints and floats arrive as text (`int(Path(...).read_text())`); `bool` as `True` or `False`. Data under `/mnt` works as in a Workspace: an `Input` or `Output` with a `path` under `/mnt/data/...` or `/mnt/netapp-volumes/...` is populated there for reading and propagated downstream for writing. If a stage imports a package from the project, set `PYTHONPATH` in the command (`bash -c 'PYTHONPATH=/mnt/code python /mnt/code/stages/train.py'`), as for any Job.

## DominoJobConfig

| Parameter | Type | Notes |
|-----------|------|-------|
| `Command` (required) | str | Job command, for example `python train.py` |
| `Title` | str | Job title; ignored for the cache version |
| `CommitId` | str | DFS project: code commit; Git-based: artifacts commit |
| `MainRepoGitRef` | `GitRef(Type="branches"\|"commitId"\|..., Value=...)` | Git-based projects: branch, tag or commit of the main repository |
| `ResolvedMainRepoGitRef` | str | Resolved commit to use while tracking a floating reference |
| `UseLatestGitRef` | bool (False) | True: floating refs re-resolve on relaunch; False: the first resolution is reused |
| `ImportedGitRepoOverrides` | list of `ImportedGitRepoOverride(Name=, Ref=GitRef(...))` | Pin imported repositories per task (Git-based projects) |
| `HardwareTierId` | str | Tier **id**, not name (for example `small-k8s`); ignored for the cache version |
| `EnvironmentId` | str | Environment **id**, not name or revision |
| `EnvironmentRevisionSpec` | `EnvironmentRevisionSpecification(EnvironmentRevisionType.SomeRevision, "<revisionId>")` | Pin a revision; the second argument is the revision **id** (a 24-character id), not the revision number shown in the UI |
| `ComputeClusterProperties` | `ClusterProperties(ClusterType=ComputeClusterType.Dask, ComputeEnvironmentId=, WorkerHardwareTierId=, WorkerCount=, MaxWorkerCount=, WorkerStorageGiB=, MasterHardwareTierId=, ComputeEnvironmentRevisionSpec=, ExtraConfigs=)` | On-demand cluster for the task |
| `VolumeSizeGiB` | float | Disk; ignored for the cache version |
| `DatasetSnapshots` | list of `DatasetSnapshot(Id=, Version=)` | Snapshot version 1 or later only |
| `NetAppVolumeSnapshots` | list of `NetAppVolumeSnapshot(Id=, Version=)` | Snapshot version 1 or later only |
| `ExternalVolumeMountIds` | list of str | External data volumes |
| `cache_ignore_vars` | tuple of str | Config arguments to leave out of the cache version |

`GitRef(Type=, Value=)`, `ImportedGitRepoOverride`, `EnvironmentRevisionSpecification`, `EnvironmentRevisionType`, `DatasetSnapshot(Id=, Version=)`, `NetAppVolumeSnapshot(Id=, Version=)` and `ClusterProperties` are all importable from `flytekitplugins.domino.task`.

### Complete config or `use_latest`

`use_latest` on `DominoJobTask` and `use_project_defaults_for_omitted` on the helper both default to **False**. With False, the constructor raises `DominoFlyteException: The following fields are not defined: [...]` unless every one of these is set: `CommitId`, `HardwareTierId`, `EnvironmentId`, `EnvironmentRevisionSpec`, `VolumeSizeGiB`, `DatasetSnapshots`, `NetAppVolumeSnapshots`, `ExternalVolumeMountIds` (empty lists count as set) and, in a Git-based project, a `MainRepoGitRef` that is commit-pinned (or has `ResolvedMainRepoGitRef`, or `UseLatestGitRef=True`); a floating branch ref with `use_latest=False` raises. A `ComputeClusterProperties`, if given, needs `ComputeEnvironmentRevisionSpec` and `MasterHardwareTierId` (MPI excepted). With True, the omitted fields are read from the project defaults at launch. To see what the defaults resolve to, build the config in a Workspace and call `DominoJobConfig(Command="python train.py").resolve_job_properties()`; it prints the resolved values, which you can then paste in as pinned settings.

## DominoJobTask

`name` (required), `domino_job_config` (required), `use_latest` (default False; see above), `inputs` (dict of name to type), `outputs` (dict of name to type), `cache` (bool or Flyte `Cache`), `cache_version`, `cache_ignore_input_vars`, `retries` (default 0), `timeout` (`timedelta` or seconds; default 3 hours).

## run_domino_job_task

`flyte_task_name`, `command` (positional), then keyword-only: `job_title`, `use_project_defaults_for_omitted` (default False; see above), `dfs_repo_commit_id`, `main_git_repo_ref`, `resolved_main_git_repo_ref`, `use_latest_git_ref`, `imported_git_repo_overrides`, `environment_name` or `environment_id` (+ `environment_revision_id`), `hardware_tier_name` or `hardware_tier_id`, `inputs=[Input(...)]`, `output_specs=[Output(...)]`, `volume_size_gib`, `dataset_snapshots`, `netapp_volume_snapshots`, `external_data_volume_ids`, `compute_cluster_properties`, `cache`, `cache_version`, `cache_ignore_input_vars`, `retries`, `timeout`. Prefer ids over names: renaming an environment or tier would otherwise change what the flow resolves to.

`Input(name, type, value, path=None)` (`value` is required: a literal, a workflow parameter or another task's output promise) and `Output(name, type, path=None)`; a `path` under `/mnt/data/...` or `/mnt/netapp-volumes/...` maps the file to the data location instead of `/workflow`.

## Finding ids

Ids are deployment-specific; look them up rather than copying them from another cluster.

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)   # outside a run: PAT or service-account token
curl -s -H "Authorization: Bearer $TOKEN" "$DOMINO_API_HOST/api/hardwaretiers/v1/hardwaretiers?limit=100"   # id, name, resources
curl -s -H "Authorization: Bearer $TOKEN" "$DOMINO_API_HOST/api/environments/beta/environments?limit=100"   # id, name
```

Dataset ids and snapshot versions come from the Dataset page in the project or the datasets API (`domino-datasets`). With `DOMINO_API_PROXY` set, call `$DOMINO_API_PROXY/api/...` without the header. Inside a Workspace the plugin can also print the valid values for the current project in one call: `from flytekitplugins.domino.helpers import retrieve_valid_properties; retrieve_valid_properties()` (it reads the `/v4/jobs/.../retrieveValidProperties` route through the API proxy, a Domino Internal API route that may change between Domino versions, and prints environments with their revisions and the other job properties; `page_size` raises the number of environments listed).

## Launch

```bash
pyflyte run --remote workflow.py training_workflow --data_path /mnt/data/raw/train.csv
pyflyte run --remote --name nightly-2026-10-12 --tag team=risk workflow.py training_workflow --data_path /mnt/data/raw/train.csv
```

Run from a Workspace terminal or as a Job command on an environment built from the Domino Standard Environment 6.0 or later. The flow is registered and started immediately; any change to `workflow.py` registers a new flow version on the next launch, and runs are grouped by version in the UI. Run names are unique per project. Commit the flow code: Domino stores the serialized definition, not its source.

Re-run from the UI (**Flows** > flow > version > run > **Re-run**): new name, cache overwrite choice, same or new inputs, and per-task overrides of environment, hardware tier or Git reference. **Recover** resumes a run after a transient failure (timeout, capacity, spot pre-emption, server error), reusing finished outputs. **Rerun Node** re-executes one node with new inputs. All three need an unchanged definition; code changes go through the CLI.

## Monitor

- **Flows** page: flows and tasks registered in the project, active or archived, lineage of artifacts attached to Datasets.
- Flow details: run list per version, **Graph** of the structure, run or archive.
- Run details: nodes with status, Graph view, **Launch Inputs**, rerun or archive.
- Node details: versioned inputs and outputs (previews need a typed file), a link to the Domino Job, execution logs.
- Flyte console: `<deployment URL>/flows/console/select-project` (timeline view, blob URIs of outputs); some native Flyte actions are not supported.
- Jobs started by a flow show the flow and task in the Job details and cannot be re-run from the Jobs UI.

## Reproducibility checklist

Every launch serializes the flow structure, each task's job config (commit, environment revision, tier, snapshots) and the inputs; identical definitions reuse the version. For deterministic reruns:

1. Replace `use_latest=True` with a complete config: `CommitId`, `MainRepoGitRef` pinned to a commit (Git-based projects), `EnvironmentId`, `EnvironmentRevisionSpec`, `HardwareTierId`, `VolumeSizeGiB`, `DatasetSnapshots`, `NetAppVolumeSnapshots` and `ExternalVolumeMountIds` (empty lists where unused); the constructor raises if any is missing. Example 3 in [EXAMPLES.md](./EXAMPLES.md) shows the full set.
2. Snapshot external data in a first task that copies it to an output.
3. Write results only as outputs, never to a shared mutable location.

## Caching, subflows, approvals

- `cache=True, cache_version="1.0"` on a task reuses a result when the project, task name, cache version (job config minus `Title`, `VolumeSizeGiB`, `HardwareTierId` and cluster sizing, plus resolved git commits and the input/output signature) and input values all match; bump `cache_version` to force recomputation. `cache_ignore_input_vars` and `DominoJobConfig(cache_ignore_vars=...)` exclude parameters. Cached nodes show a cache symbol in the graph. With Flyte 1.15+, `cache=Cache(policies=...)` replaces the version string with a policy.
- Subflows: call one `@workflow` function from another; it appears as a single node.
- Approvals: `from flytekit import approve`; `approve(task_result, "Approval", timeout=timedelta(hours=2))` pauses until someone clicks **Resume** and approves in the UI; rejecting stops the run.

## Documented pitfalls

- Version 0 of a Dataset or NetApp Volume cannot be mounted; take a snapshot first.
- Outputs not written to `/workflow/outputs/<name>` fail the task.
- A changed flow definition relaunched from the UI runs the old version; launch from the CLI.
- Stopping a flow's Job in the Jobs UI stops the whole flow.
- `use_latest` picks up the project defaults at launch time, so a later change to the project's default environment changes what a new flow version runs on.
