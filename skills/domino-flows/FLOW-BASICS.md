# Domino Flows: definitions, configuration, launching, monitoring

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/flows/define-flows, `.../launch-flows`, `.../monitor-flows`, `.../reproducibility-flows`, `.../advanced-flows` (the 6.3 pages are identical).

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

The define-flows docs page shows string indexing (`data_prep_results["processed_data"]`); do not copy it. Passing one task's output into another creates the dependency edge; tasks without a data dependency run in parallel. A `@workflow` function may return nothing, one output, or a tuple. `@workflow` compiles lazily, so call `my_workflow.compile()` in a Workspace to surface these errors before `pyflyte run`.

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

Ints and floats arrive as text (`int(Path(...).read_text())`); `bool` as `True` or `False`. If a stage imports a package from the project, set `PYTHONPATH` in the command (`bash -c 'PYTHONPATH=/mnt/code python /mnt/code/stages/train.py'`), as for any Job.

## Data paths under `/mnt`

A flow job mounts code, imported repositories and snapshots at the paths a Workspace or standalone Job uses, so a script that reads `/mnt/data/<dataset>/file.csv` runs unchanged in both.

| Content | Git-based project | DFS project |
|---------|-------------------|-------------|
| Project code (working directory) | `/mnt/code` | `/mnt` |
| Artifacts | `/mnt/artifacts` | alongside the code in `/mnt` |
| Project Dataset snapshot | `/mnt/data/<name>` | `/domino/datasets/local/<name>` |
| Dataset shared from another project | `/mnt/imported/data/<name>` | `/domino/datasets/<name>` |
| NetApp Volume snapshot | `/mnt/netapp-volumes/<name>` | `/domino/netapp-volumes/<name>` |
| Imported Git repository | `/mnt/imported/code/<repo>` | `/repos/<repo>` |

Differences from a Workspace:

- Dataset and NetApp Volume mounts are **snapshots**, read-only, at the `latest` path with no snapshot number in it (`/mnt/data/<name>`, not `/mnt/data/snapshots/<name>/3`); version 0 (the read-write view) cannot be mounted, and one snapshot per Dataset or Volume.
- No code or artifacts snapshot is taken when the job ends. A file written to `/mnt/artifacts` (Git-based) or into the DFS working directory survives a Workspace or Job but is lost after a flow task; declare it as an output instead.
- `Input(name, type, path="/mnt/data/<dataset>/<file>")` on the helper (or `Annotated[<type>, PathConfig(path=...)]` from `flytekitplugins.domino.file` on a `DominoJobTask` output) puts a file input at that path instead of `/workflow/inputs/<name>`, and `Output(..., path="/mnt/data/<dataset>/<file>")` collects the output from that path instead of `/workflow/outputs/<name>`, so an existing script keeps its Dataset paths. Only `/mnt/data/...` and `/mnt/netapp-volumes/...` paths are mapped this way; the output is still propagated downstream through Flow blob storage, and Domino can record a new snapshot of that Dataset at the end of the run. Example 5 in [EXAMPLES.md](./EXAMPLES.md) runs one script in a Workspace and in a flow.

## DominoJobConfig

| Parameter | Type | Notes |
|-----------|------|-------|
| `Command` (required) | str | Job command, for example `python train.py` |
| `Title` | str | Job title; ignored for the cache version |
| `CommitId` | str | DFS project: code commit; Git-based: artifacts commit |
| `MainRepoGitRef` | `GitRef(Type=, Value=)` | Git-based projects: reference of the main repository; see "Git references" |
| `ResolvedMainRepoGitRef` | str | Resolved commit to use while tracking a floating reference |
| `UseLatestGitRef` | bool (False) | True: floating refs re-resolve on relaunch; False: the first resolution is reused |
| `ImportedGitRepoOverrides` | list of `ImportedGitRepoOverride(Name=, Ref=GitRef(...))` | Pin imported repositories per task (Git-based projects); see "Git references" |
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

### Git references

Git-based projects only. `GitRef(Type=, Value=)` names a reference of a repository: `Type` is `head` (the repository's default branch, no `Value`), `branches`, `tags`, `commitId` or `custom` (any other Git reference), and `Value` is the branch name, tag, commit SHA or reference. `MainRepoGitRef` sets the main repository's reference for the task; `ImportedGitRepoOverrides` pins one or more of the project's imported repositories for that task, each by its `Name` as configured in the project's **Code** section; repositories not listed check out their project default. Inside the task the main repository is at `/mnt/code` and each imported repository at `/mnt/imported/code/<name>`. The helper takes the same values as `main_git_repo_ref` and `imported_git_repo_overrides`.

```python
DominoJobConfig(
    Command="python train-model.py",
    MainRepoGitRef=GitRef(Type="branches", Value="main"),
    ImportedGitRepoOverrides=[
        ImportedGitRepoOverride(Name="shared-utils", Ref=GitRef(Type="commitId", Value="2f1cb9bf696921f0858e4a1c0b3d7f2a9c5e8d41")),
    ],
)
```

A branch, tag or `head` reference is **floating**: it is resolved to a commit when the flow is first run and, with `UseLatestGitRef=False` (the default), that commit is reused on every UI relaunch; with `UseLatestGitRef=True` each run or relaunch resolves it again. `ResolvedMainRepoGitRef` tracks a floating main-repository reference while running an older commit. Resolved commits of the main and imported repositories are part of the cache version, so a new commit on a floating reference invalidates cached results only when it is resolved again. With `use_latest=False`, `MainRepoGitRef` must be a `commitId` reference (or carry `ResolvedMainRepoGitRef` or `UseLatestGitRef=True`); `ImportedGitRepoOverrides` is a per-task override and may be omitted when the project imports no repositories (if the constructor reports it as undefined, pass `ImportedGitRepoOverrides=[]`).

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

Dataset ids and snapshot versions come from the Dataset page in the project or the datasets API (`domino-datasets`). With `DOMINO_API_PROXY` set, call `$DOMINO_API_PROXY/api/...` without the header. Inside a Workspace the plugin can also print the valid values for the current project in one call: `from flytekitplugins.domino.helpers import retrieve_valid_properties; retrieve_valid_properties()` (it reads the `/v4/jobs/.../retrieveValidProperties` route through the API proxy, a non-public route that may change in a future Domino version ([route types](../domino-api-intro/SKILL.md#route-types)), and prints environments with their revisions and the other job properties; `page_size` raises the number of environments listed).

## Launch

```bash
pyflyte run --remote workflow.py training_workflow --data_path /mnt/data/raw/train.csv
pyflyte run --remote --name nightly-2026-10-12 --tag team=risk workflow.py training_workflow --data_path /mnt/data/raw/train.csv
```

Run from a Workspace terminal or as a Job command on an environment built from the Domino Standard Environment 6.0 or later. The flow is registered and started immediately; any change to `workflow.py` registers a new flow version on the next launch, and runs are grouped by version in the UI. Run names are unique per project. Commit the flow code: Domino stores the serialized definition, not its source.

## Re-run, recover, stop and archive

UI (**Flows** > flow > version > run): **Re-run** starts a new run with a new name, a cache-overwrite choice, the same or new inputs, and per-task overrides of environment, hardware tier or Git reference; **Recover** resumes a run after a transient failure (timeout, capacity, spot pre-emption, server error), reusing finished outputs; **Rerun Node** re-executes one node with new inputs. All three use the run's registered definition; code changes go through the CLI.

Override rules: an override is set per task and applies to that run only; the registered definition is unchanged. A Git reference override checks out the task's code at the new reference, so every file the task uses from the repository (the script in `Command`, anything it reads under `/mnt/code` or `/mnt/imported/code/<repo>`) must exist at that reference. Tasks without an override keep their configured references, and whether a floating reference is resolved again on relaunch follows the task's `UseLatestGitRef` ("Git references" above). The UI's **Re-run** with overrides is the `POST /executions/v1/execution/{execution-id}/rerunWithOverrides` route of the Flyte extensions API (base `<deployment URL>/flows/api`, browser login only); its body is a protojson `admin.ExecutionCreateRequest` whose override fields the spec does not describe, so run overrides from the UI and script only the native routes below.

The same actions are Flyte API calls, documented at https://docs.domino.ai/cloud/reference/api/flyte/flyte-native-api (the routes below) and https://docs.domino.ai/cloud/reference/api/flyte/flyte-extensions-api (artifact routes). Run them from inside a Workspace or Job: `$FLYTE_PLATFORM_URL_HTTP` (`http://127.0.0.1:7180`) takes the REST routes with no auth header, and `$FLYTE_PLATFORM_URL` is the gRPC address `pyflyte` uses. From outside Domino, `<deployment URL>/flows/api/v1/...` accepts only the browser login and rejects Domino API tokens, so script these actions as a Job or from a Workspace terminal. The Flyte `project` is the Domino project id (`$DOMINO_PROJECT_ID`, also exported as `$FLYTE_DEFAULT_PROJECT`), the `domain` is `development`, and `name` is the run name shown in the UI.

| Action | Call (base `$FLYTE_PLATFORM_URL_HTTP`) |
|--------|----------------------------------------|
| Inspect a run | `GET /api/v1/executions/{project}/development/{name}`: `spec.launchPlan` identifies what it ran, `closure.phase` is `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `ABORTED` or `TIMED_OUT`; inputs from `GET /api/v1/data/executions/{project}/development/{name}` (`fullInputs`) |
| Re-launch with the same inputs | `POST /api/v1/executions/relaunch` with `{"id": {"project", "domain", "name"}, "name": "<new run name>", "overwrite_cache": false}` |
| Re-run with new inputs | `POST /api/v1/executions` with `{"project", "domain", "name": "<new run name>", "spec": {"launchPlan": <the run's spec.launchPlan>, "overwrite_cache": false}, "inputs": {"literals": {...}}}`, literals in the shape `fullInputs` returns |
| Recover | `POST /api/v1/executions/recover` with `{"id": {"project", "domain", "name"}}`; finished nodes are reused, the failed ones run again |
| Stop | `DELETE /api/v1/executions/{project}/development/{name}` (optional `{"cause": "..."}`); the run ends `ABORTED` |
| Archive or restore | `PUT /api/v1/executions/{project}/development/{name}` with `{"state": "EXECUTION_ARCHIVED"}` or `{"state": "EXECUTION_ACTIVE"}` |

Omit `name` on re-launch or recover and Flyte generates one. Each create call returns the new run's `id` (`{project, domain, name}`); poll `GET /api/v1/executions/{project}/development/{name}` until `closure.phase` is terminal.

## Monitor

- **Flows** page: flows and tasks registered in the project, active or archived, lineage of artifacts attached to Datasets.
- Flow details: run list per version, **Graph** of the structure, run or archive.
- Run details: nodes with status, Graph view, **Launch Inputs**, rerun or archive.
- Node details: versioned inputs and outputs (previews need a typed file), a link to the Domino Job, execution logs.
- Flyte console: `<deployment URL>/flows/console/select-project` (timeline view, blob URIs of outputs); its **Relaunch** and **Recover** are the API calls above.
- Jobs started by a flow show the flow and task in the Job details and cannot be re-run from the Jobs UI.

## Reproducibility checklist

Every launch serializes the flow structure, each task's job config (commit, environment revision, tier, snapshots) and the inputs; identical definitions reuse the version. For deterministic reruns:

1. Replace `use_latest=True` with a complete config (the field list in "Complete config or `use_latest`" above); Example 3 in [EXAMPLES.md](./EXAMPLES.md) shows the full set.
2. Read external data from a pinned Dataset or NetApp Volume snapshot (`DatasetSnapshots`, `NetAppVolumeSnapshots`); for anything else (a Data Source table, a bucket), snapshot it in a first task that copies it to an output.
3. Write results only as outputs, never to a shared mutable location.

## Flow Artifacts and export

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/flows/define-flow-artifacts. `Artifact(name=, type=)` with `type` `DATA`, `MODEL` or `REPORT`, and `MyArtifact.File(name="file.ext")` as an output type, group task outputs under a named artifact with lineage in the Flows UI (all from `flytekitplugins.domino.artifact`). To copy an artifact's files into a Dataset or a NetApp Volume when the run finishes, call `run_launch_export_artifacts_task` inside the `@workflow`:

```python
from datetime import timedelta
from flytekitplugins.domino.artifact import (
    Artifact, DATA, ExportArtifactToDatasetsSpec, ExportArtifactToNetAppVolumesSpec, FileCollisionSetting,
    run_launch_export_artifacts_task,
)

DataArtifact = Artifact(name="Training splits", type=DATA)   # used as an output type by one or more tasks

run_launch_export_artifacts_task(
    spec_list=[
        ExportArtifactToDatasetsSpec(artifact=DataArtifact, dataset_id="<dataset id>"),
        ExportArtifactToNetAppVolumesSpec(
            artifact=DataArtifact,
            netapp_volume_id="<volume id>",                 # a UUID; the Volume's page, or GET /remotefs/v1/volumes?project_id= (netapp-volumes skill)
            target_relative_path="flows-data",              # directory on the Volume; default "" is the root
            file_collision_setting=FileCollisionSetting.RENAME,   # RENAME (default), IGNORE or OVERWRITE
        ),
    ],
    environment_id="<environment id>",                      # Domino Standard Environment 6.0+ or built on it
    hardware_tier_id="small-k8s",                           # a small tier; the task only launches the export
    use_project_defaults_for_omitted=True,
    timeout=timedelta(hours=6),                             # longer than the whole run; default 3 hours
)
```

- `spec_list` mixes both spec types; one entry per artifact and destination. `ExportArtifactToDatasetsSpec(artifact, dataset_id)` copies into the Dataset. `ExportArtifactToNetAppVolumesSpec(artifact, netapp_volume_id, target_relative_path="", file_collision_setting=FileCollisionSetting.RENAME)` copies under the given directory of the Volume; `file_collision_setting` decides what happens when a file of the same name already exists there (`RENAME`, `IGNORE` or `OVERWRITE`).
- Other parameters: `use_project_defaults_for_omitted`, `environment_name` or `environment_id` (+ `environment_revision_id`), `hardware_tier_name` or `hardware_tier_id`, `retries`, `timeout`. The environment must be the Domino Standard Environment 6.0 or later, or one built on it (the export needs its Flyte Python and `jq`); prefer ids over names.
- The task launches a **separate export execution** that waits for the main run to finish and for every referenced artifact to exist, then copies the files; its node can therefore appear at the start of the graph (`n0`) and complete before downstream tasks. Progress and per-file logs are in that export execution, linked from the launch task's logs. The `timeout` covers the wait as well as the copy, so set it longer than the whole run.
- Assigning a DATA artifact to a Dataset from the UI (**Examine Flow Artifacts**) is not scriptable; the export task is the programmatic path.

## Caching, subflows, approvals

- `cache=True, cache_version="1.0"` on a task reuses a result when the project, task name, cache version (job config minus `Title`, `VolumeSizeGiB`, `HardwareTierId` and cluster sizing, plus resolved git commits and the input/output signature) and input values all match; bump `cache_version` to force recomputation. `cache_ignore_input_vars` and `DominoJobConfig(cache_ignore_vars=...)` exclude parameters. Cached nodes show a cache symbol in the graph. With Flyte 1.15+, `cache=Cache(policies=...)` replaces the version string with a policy.
- Subflows: call one `@workflow` function from another; it appears as a single node.
- Approvals: `from flytekit import approve`; `approve(task_result, "Approval", timeout=timedelta(hours=2))` pauses until someone clicks **Resume** and approves in the UI; rejecting stops the run.

## Documented pitfalls

- Version 0 of a Dataset or NetApp Volume cannot be mounted; take a snapshot first.
- Outputs not written to `/workflow/outputs/<name>` fail the task.
- Files written to `/mnt/artifacts` or the DFS working directory are not kept after a flow task (no end-of-job snapshot); make them outputs, or give the `Output` a `path` under `/mnt/data/...`.
- A Git reference override on **Re-run** fails a task whose script or input files are missing at the new reference.
- A changed flow definition relaunched from the UI runs the old version; launch from the CLI.
- Stopping a flow's Job in the Jobs UI stops the whole flow.
- `use_latest` picks up the project defaults at launch time, so a later change to the project's default environment changes what a new flow version runs on.
