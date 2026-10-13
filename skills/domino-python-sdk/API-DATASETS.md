# Domino Datasets API

Create and manage Datasets, snapshots, tags and grants with the Public API. Routes,
bodies and response envelopes below are from both published specs (identical on 6.3 and
Cloud). Product docs:
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets and the
[domino-datasets](../domino-datasets/SKILL.md) skill.

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## List datasets

```
GET /api/datasetrw/v2/datasets
```

| Parameter | Notes |
|-----------|-------|
| `projectIdsToInclude`, `projectIdsToExclude` | Repeatable project-id filters; send one or the other, not both |
| `minimumPermission` | Minimum permission the caller must hold, for example `ReadDatasetRwV2`, `UpdateDatasetRwV2`, `DeleteDatasetRwV2` |
| `includeProjectInfo` | Add `projectInfo` to each item |
| `includeArchivedProjects` | Defaults to true |
| `offset`, `limit` | Pagination (`limit` defaults to 10) |

Response: `{"datasets": [{"dataset": {...}, "projectInfo": {...}}], "metadata": {"offset", "limit", "totalCount", ...}}`.
Note the nested `dataset` key. `GET /api/datasetrw/v1/datasets` is marked deprecated in
both specs ("Use getDatasetsV2"); use v2 with `projectIdsToInclude` instead.

```python
page = requests.get(f"{base_url}/api/datasetrw/v2/datasets", headers=headers,
                    params={"projectIdsToInclude": [project_id], "limit": 50}).json()
for item in page["datasets"]:
    ds = item["dataset"]
    print(ds["name"], ds["id"], ds.get("description"), len(ds["snapshotIds"]))
```

Dataset record: `id`, `name`, `description`, `projectId`, `createdAt`, `snapshotIds`,
`tags` (a map of `tagName -> snapshotId`).

## Create a dataset

```
POST /api/datasetrw/v1/datasets
```

| Field | Notes |
|-------|-------|
| `name` | **Required**; unique within the project |
| `projectId` | Project to create the dataset in. Either `projectId` or `snapshotId` must be provided |
| `snapshotId` | Create the new dataset from an existing snapshot instead; grants are then ignored and the caller becomes owner |
| `description` | Description of the Dataset |
| `grants` | `[{"targetId": "<user-or-org-id>", "targetRole": "DatasetRwOwner" or "DatasetRwEditor" or "DatasetRwReader"}]`; organizations cannot be owners |

```python
dataset = requests.post(f"{base_url}/api/datasetrw/v1/datasets", headers=headers, json={
    "name": "customer-features",
    "description": "Processed customer features for modeling",
    "projectId": project_id,
}).json()["dataset"]
dataset_id = dataset["id"]
```

Response: `{"dataset": {...}, "metadata": {...}}`.

## Get, update, delete

```
GET    /api/datasetrw/v1/datasets/{datasetId}                 -> {"dataset": {...}, "metadata": {...}}
PATCH  /api/datasetrw/v1/datasets/{datasetId}                 body: {"name": "new-name", "description": "..."} (both optional)
DELETE /api/datasetrw/v1/datasets/{datasetId}
```

`DELETE` needs PermanentDelete access and is a soft, cancellable delete: the dataset
disappears from the v2 list at once, `GET` by id still returns it, and the internal
lifecycle stays `DeletionInProgress` for some time (more than ten minutes).
Snapshot files are read through the dataset files service; called from outside Domino, the
`/datasetrw/...` routes in the spec answer 404 while the `/v4/datasetrw/...` forms work
(internal API, may change
between Domino versions), so prefer the mount path or python-domino for file access.

## Snapshots

```
GET  /api/datasetrw/v1/datasets/{datasetId}/snapshots
POST /api/datasetrw/v1/datasets/{datasetId}/snapshots     body: {"relativeFilePaths": ["features.parquet", "labels/"]}
GET  /api/datasetrw/v1/snapshots/{snapshotId}
```

`relativeFilePaths` (required) lists the paths, relative to the dataset root, to include
in the snapshot
(https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/version-data-with-snapshots).
Use `["*"]` for every file; `["/*"]` returns 200 and
the snapshot then goes to `failed`. File paths (`sub/b.txt`) and directory paths
(`labels/`) both work and include only what you list. Only one snapshot copy runs at a
time; a second POST while one is `pending` returns 400. Tags are added separately
(below). Response: `{"snapshot": {"id", "datasetId", "createdAt", "creatorId", "status"}, "metadata": {...}}`
(the schema's `description` and `lastMounted` were absent live) with `status` one of
`active`, `pending`, `copying`, `markForDeletion`, `deletionInProgress`, `deleted`,
`failed`; poll `GET /api/datasetrw/v1/snapshots/{snapshotId}` until `active`. To create a
new editable dataset from a snapshot, `POST /api/datasetrw/v1/datasets` with `name`,
`snapshotId` and `description` (it lands in the source's project with its
own snapshot).

```python
snapshot = requests.post(f"{base_url}/api/datasetrw/v1/datasets/{dataset_id}/snapshots",
                         headers=headers, json={"relativeFilePaths": ["*"]}).json()["snapshot"]
```

## Tags

```
POST   /api/datasetrw/v1/datasets/{datasetId}/tags            body: {"snapshotId": "<snapshot-id>", "tagName": "v1-0"}
DELETE /api/datasetrw/v1/datasets/{datasetId}/tags/{tagName}
```

Both body fields are required. Tag names must start with a letter and contain only
letters, digits and hyphens: `v1.0` is rejected with
`400 Tags must start with a letter and contain only alphanumeric, dashes, and hyphen characters`,
so write `v1-0`. The response is the updated `{"dataset": {...}}`; the
dataset's `tags` map shows every `tagName -> snapshotId`. A tag name is unique within the
dataset: pointing an existing tag at another snapshot returns
`400 Tag <name> already exists within dataset`, so `DELETE` it first and re-`POST`.

## Grants (permissions)

```
GET    /api/datasetrw/v1/datasets/{datasetId}/grants
POST   /api/datasetrw/v1/datasets/{datasetId}/grants     body: {"targetId": "<user-or-org-id>", "targetRole": "DatasetRwReader"}
DELETE /api/datasetrw/v1/datasets/{datasetId}/grants     body: {"targetId": "<user-or-org-id>", "targetRole": "DatasetRwReader"}
```

`targetRole` is `DatasetRwOwner`, `DatasetRwEditor` or `DatasetRwReader`; organizations
cannot be owners. `POST` sets (replaces) the target's role rather than adding a second
grant, and a dataset must keep at least one owner (`400 Dataset must have at least one
owner` otherwise). `DELETE` takes the same body and is a no-op 200 when no such grant
exists. `GET` returns `{"grantDetails": [{"targetId", "targetName", "targetRole", "isOrganization"}]}`;
`POST` returns `{"grants": [...]}`.

## Mount paths inside executions

From https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/use-datasets-and-snapshots:

| Project type | Dataset of this project (read-write) | Its snapshots by tag / by number (read-only) |
|--------------|--------------------------------------|----------------------------------------------|
| DFS | `/domino/datasets/local/<name>` | `/domino/datasets/local/snapshots/<name>/<tag>` and `/<number>` |
| Git-based | `/mnt/data/<name>` | `/mnt/data/snapshots/<name>/<tag>` and `/<number>` |

Datasets shared from another project mount read-only at `/domino/datasets/<name>` (DFS) or
`/mnt/imported/data/<name>` (Git-based), with snapshots under `.../snapshots/<name>/<tag>`.

```python
import pandas as pd
df = pd.read_parquet("/mnt/data/customer-features/features.parquet")                   # live
df_v1 = pd.read_parquet("/mnt/data/snapshots/customer-features/v1-0/features.parquet")  # tag (no dots in tag names)
```

The job object from [API-JOBS.md](./API-JOBS.md) lists the actual mounts under
`datasetMounts[].containerPath`.

## Uploading files

Writing to the mount path inside a Workspace or Job is the normal way to add data.
From outside an execution, python-domino `datasets_upload_files(dataset_id, local_path, ...)`
performs the chunked upload against the dataset files service
([SDK-EXAMPLES.md](./SDK-EXAMPLES.md#datasets)). It calls the
`/v4/datasetrw/datasets/{datasetId}/snapshot/file/*` routes (internal API, may change
between Domino versions; the spec lists the same protocol under `/datasetrw/...`), a
multi-step resumable upload, so use the SDK rather than calling them directly.

## python-domino

`datasets_list(project_id=None)`, `datasets_ids(project_id)`, `datasets_names(project_id)`,
`datasets_create(dataset_name, dataset_description)` (returns a record with `datasetId`
and `datasetName`), `datasets_details(dataset_id)`,
`datasets_update_details(dataset_id, dataset_name=None, dataset_description=None)`,
`datasets_remove(dataset_ids)`, `datasets_upload_files(...)`. There is no
`datasets_snapshot` or `datasets_tag`; use the REST routes above.

## Workflow example

```python
dataset = requests.post(f"{base_url}/api/datasetrw/v1/datasets", headers=headers,
                        json={"name": "feature-store", "description": "Centralized features",
                              "projectId": project_id}).json()["dataset"]

# ... write files to the mount path inside a job, then:
snapshot = requests.post(f"{base_url}/api/datasetrw/v1/datasets/{dataset['id']}/snapshots",
                         headers=headers, json={"relativeFilePaths": ["features.parquet"]}).json()["snapshot"]

requests.post(f"{base_url}/api/datasetrw/v1/datasets/{dataset['id']}/tags", headers=headers,
              json={"snapshotId": snapshot["id"], "tagName": "baseline"})
requests.post(f"{base_url}/api/datasetrw/v1/datasets/{dataset['id']}/grants", headers=headers,
              json={"targetId": colleague_user_id, "targetRole": "DatasetRwReader"})
```
