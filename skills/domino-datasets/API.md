# Dataset REST API

All routes below exist in both published Public API specs
(https://docs.domino.ai/api-specs/6.3/public-api.json and
https://docs.domino.ai/api-specs/cloud/public-api.json, tag `Datasets`). Every `/v4`
route named below is labelled Internal API, may change between Domino versions, at its point of
use; readers on Domino 6.3 should confirm each one in their deployment's `/docs`.
Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/create-and-manage-datasets
(REST tab) and the API reference under https://docs.domino.ai/cloud/reference/api.

## Authentication

Inside a Domino execution call the proxy with no header; it adds the starting user's token.
Outside, use a Personal Access Token or service-account token as a bearer against the
deployment URL (domino-api-intro skill). Legacy user API keys are deprecated; do not use them.

```bash
# inside a Workspace, Job or App
curl -sS "$DOMINO_API_PROXY/api/datasetrw/v2/datasets?limit=50"

# outside Domino: DOMINO_PAT holds a Personal Access Token or service-account token
curl -sS -H "Authorization: Bearer $DOMINO_PAT" "$DOMINO_API_HOST/api/datasetrw/v2/datasets?limit=50"
```

```python
import os
import requests

if os.environ.get("DOMINO_API_PROXY"):                 # in a run: the proxy adds the token
    base, headers = os.environ["DOMINO_API_PROXY"], {}
else:
    base = os.environ["DOMINO_API_HOST"]
    token = os.environ.get("DOMINO_PAT") or requests.get("http://localhost:8899/access-token").text
    headers = {"Authorization": f"Bearer {token}"}   # PAT outside Domino; sidecar token in a run without the proxy
r = requests.get(f"{base}/api/datasetrw/v2/datasets", headers=headers, params={"limit": 50})
r.raise_for_status()
```

Every 2xx response wraps the payload with `metadata` (`requestId`, `notices`; lists carry
`offset` and `limit`, and the snapshot list `totalCount` on Domino 6.4.0). The spec
describes errors as `{"code", "message"}` for 401 and 403 and `{"error"}` for 400, 404 and 500;
on 6.4.0 a 400 or 404 arrives as `{"requestId": ..., "errors": ["..."]}`, so read either shape.

## Routes

| Method and path | Purpose | Body or parameters |
|---|---|---|
| `GET /api/datasetrw/v2/datasets` | Datasets the caller can access | `limit` (default 10), `offset`, `projectIdsToInclude` or `projectIdsToExclude`, `includeProjectInfo`, `includeArchivedProjects`, `minimumPermission` (for example `ReadDatasetRwV2`, `UpdateDatasetRwV2`) |
| `POST /api/datasetrw/v1/datasets` | Create | `{"name": "...", "description": "...", "projectId": "...", "grants": [...]}`; or `snapshotId` instead of `projectId` to copy a snapshot into a new Dataset; `name` required |
| `GET /api/datasetrw/v1/datasets/{datasetId}` | Details | returns `id`, `name`, `description`, `projectId`, `createdAt`, `snapshotIds`, `tags` (tag name to snapshot ID) |
| `PATCH /api/datasetrw/v1/datasets/{datasetId}` | Rename or re-describe | `{"name": "...", "description": "..."}` (either) |
| `DELETE /api/datasetrw/v1/datasets/{datasetId}` | Soft delete (works for a non-admin Owner): returns the Dataset, which vanishes from the v2 list at once while `GET` by ID still works; internally it is `DeletionInProgress` and cancellable through `DELETE /v4/datasetrw/dataset/{id}/cancel-request-to-delete` (**Internal API, may change between Domino versions**), and it stays in that state for at least 10 minutes. The spec names the PermanentDelete permission; an admin may need to finish the deletion. Never call it without explicit user confirmation | none |
| `GET /api/datasetrw/v1/datasets/{datasetId}/snapshots` | List snapshots | `offset`, `limit` (default 10); each has `id`, `datasetId`, `creatorId`, `createdAt`, `status` |
| `POST /api/datasetrw/v1/datasets/{datasetId}/snapshots` | Create snapshot | `{"relativeFilePaths": ["*"]}` for all files (active in about 20 s with nested files; `["/*"]` is accepted but the snapshot ends `failed`), or paths such as `["a.txt", "sub/b.txt"]`; returns `status: pending`. One copy at a time: a second `POST` while one is pending returns 400 `a snapshot copy is already in progress` |
| `GET /api/datasetrw/v1/snapshots/{snapshotId}` | Snapshot details | `status` is one of `pending`, `active`, `failed`, `copying`, `markForDeletion`, `deletionInProgress`, `deleted` |
| `POST /api/datasetrw/v1/datasets/{datasetId}/tags` | Tag a snapshot; returns the Dataset with its `tags` map. Re-using a name on another snapshot returns 400 `Tag ... already exists within dataset`, so to move a tag `DELETE` it first | `{"snapshotId": "...", "tagName": "..."}` |
| `DELETE /api/datasetrw/v1/datasets/{datasetId}/tags/{tagName}` | Remove a tag | none |
| `GET /api/datasetrw/v1/datasets/{datasetId}/grants` | List grants; returns `grantDetails[{targetId, targetName, targetRole, isOrganization}]` | none |
| `POST /api/datasetrw/v1/datasets/{datasetId}/grants` | Set a target's role. One grant per target: posting a new role for an existing target **replaces** it, and demoting the last Owner returns 400 `Dataset must have at least one owner`. Returns `grants[...]` | `{"targetId": "<user-id>", "targetRole": "DatasetRwOwner" / "DatasetRwEditor" / "DatasetRwReader"}` |
| `DELETE /api/datasetrw/v1/datasets/{datasetId}/grants` | Remove a grant; 200 with no change when nothing matches | same body as add |
| `GET /api/projects/v1/projects/{projectId}/shared-datasets` | Datasets shared into a Project: `{"dataset": {"projectId", "sharedDatasetIds": [...]}}`. On Domino 6.4.0 it answers 200 with an empty `sharedDatasetIds` list when nothing is shared. Treat a 404 `sharedDatasetRwEntry ... not found` (an older shape on long-lived Projects) as the same empty case | none |
| `POST /api/projects/v1/projects/{projectId}/shared-datasets` | Mount a shared Dataset | `{"datasetId": "..."}`; needs `ManageDatasetsRw` and `UseFileStorage` on the Project |
| `DELETE /api/projects/v1/projects/{projectId}/shared-datasets/{datasetId}` | Unmount; returns `{"success": true}` | none |
| `GET /v4/datasetrw/snapshot/{snapshotId}/files/recursive?path=` | **Internal API, may change between Domino versions.** File names under a path in a snapshot; rows `[{name: {label, ...}, size, lastModified}]` | `path` required; empty for the root (`/` and `.` return 400) |
| `GET /v4/datasetrw/snapshot/{snapshotId}/file/raw?path=a.txt` | **Internal API, may change between Domino versions.** Raw file content | `path` required; `download` optional |

`GET /api/datasetrw/v1/datasets` also exists but is marked deprecated; use v2. The spec lists the
file routes as `/datasetrw/snapshot/...` without a prefix, but on Domino 6.4.0 that form (and
`/api/datasetrw/snapshot/...`) returns 404 and only the `/v4/` form answers, hence the internal
label. The chunked upload routes (`/datasetrw/datasets/{datasetId}/snapshot/file/...`) are what
the CLI (`domino upload-dataset`, [domino-cli](../domino-cli/SKILL.md)) and python-domino
`datasets_upload_files` drive; prefer those tools over calling them.

## Examples

Create a Dataset in the current Project and snapshot it after writing files:

```bash
DS=$(curl -sS -X POST "$DOMINO_API_PROXY/api/datasetrw/v1/datasets" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"training-data\", \"description\": \"Q3 features\", \"projectId\": \"$DOMINO_PROJECT_ID\", \"grants\": []}")
DATASET_ID=$(printf '%s' "$DS" | python3 -c "import sys, json; print(json.load(sys.stdin)['dataset']['id'])")

# ... write files under the mount path, then:
curl -sS -X POST "$DOMINO_API_PROXY/api/datasetrw/v1/datasets/$DATASET_ID/snapshots" \
  -H "Content-Type: application/json" -d '{"relativeFilePaths": ["*"]}'
```

The new Dataset is mounted in executions started after it exists; a
running Workspace does not see it until restarted.

Wait for a snapshot, then tag it:

```python
import time

snap = requests.post(f"{base}/api/datasetrw/v1/datasets/{dataset_id}/snapshots",
                     headers=headers, json={"relativeFilePaths": ["*"]}).json()["snapshot"]
while snap["status"] in ("pending", "copying"):
    time.sleep(5)
    snap = requests.get(f"{base}/api/datasetrw/v1/snapshots/{snap['id']}", headers=headers).json()["snapshot"]
assert snap["status"] == "active", snap
requests.post(f"{base}/api/datasetrw/v1/datasets/{dataset_id}/tags", headers=headers,
              json={"snapshotId": snap["id"], "tagName": "production"}).raise_for_status()
```

Read a snapshot you took in this execution. It is not mounted here (mounts are fixed at
execution start), so go through the internal file routes, which answer through the proxy and
from outside with a bearer. Internal API, may change between Domino
versions; `path` is relative to the snapshot root with no leading slash, and an empty `path`
lists the root:

```bash
SID=<snapshot id from the POST or the snapshots list>
curl -sS "$DOMINO_API_PROXY/v4/datasetrw/snapshot/$SID/files/recursive?path=" | python3 -m json.tool | head
curl -sS "$DOMINO_API_PROXY/v4/datasetrw/snapshot/$SID/file/raw?path=processed/features.parquet" \
  -o /tmp/features.parquet
```

```python
listing = requests.get(f"{base}/v4/datasetrw/snapshot/{snapshot_id}/files/recursive",
                       headers=headers, params={"path": ""}).json()
raw = requests.get(f"{base}/v4/datasetrw/snapshot/{snapshot_id}/file/raw",
                   headers=headers, params={"path": "processed/features.parquet"})
raw.raise_for_status()
open("/tmp/features.parquet", "wb").write(raw.content)
```

The same read without any internal route: `DatasetClient().get_dataset(...)` plus
`dataset.update(DatasetConfig(snapshot_id=snapshot_id))` in the domino-data-sdk skill. A Job
started after the snapshot is `active` simply mounts it at `.../snapshots/<name>/<n>`.

Find a Dataset by name across Projects:

```python
def find_dataset(name, page=200):
    offset = 0
    while True:
        r = requests.get(f"{base}/api/datasetrw/v2/datasets", headers=headers,
                         params={"limit": page, "offset": offset, "includeProjectInfo": "true"})
        r.raise_for_status()
        rows = r.json()["datasets"]
        match = next((d["dataset"] for d in rows if d["dataset"]["name"] == name), None)
        if match or len(rows) < page:
            return match          # None when nothing matches
        offset += page
```

Share with a user and mount in another Project (the grant call sets that user's single role;
it does not stack):

```python
requests.post(f"{base}/api/datasetrw/v1/datasets/{dataset_id}/grants", headers=headers,
              json={"targetId": user_id, "targetRole": "DatasetRwReader"}).raise_for_status()
requests.post(f"{base}/api/projects/v1/projects/{other_project_id}/shared-datasets", headers=headers,
              json={"datasetId": dataset_id}).raise_for_status()
```

Snapshot limit hit: an execution that writes a snapshot fails with an error (documented); what
`POST .../snapshots` returns at the limit is not documented, so treat any non-2xx there as the
limit until proven otherwise. The Public API has no per-snapshot delete or limit route; the
internal routes in the next section cover both.

## Snapshot deletion and limits (internal API)

Every call here is **Internal API, may change between Domino versions**; a non-admin Dataset
Owner can make them (on 6.3, confirm each in your deployment's `/docs`).

| Call (Internal API, may change between Domino versions) | Behaviour |
|---|---|
| `DELETE /v4/datasetrw/snapshot/{snapshotId}` | Requests deletion: returns the snapshot with `lifecycleStatus: DeletionInProgress` (`deletionInProgress` in the public `GET`); it stays in the public snapshot list; `GET /v4/datasetrw/snapshot/{snapshotId}/can-cancel-delete` is `true` |
| `DELETE /v4/datasetrw/snapshot/{snapshotId}/cancel-request-to-delete` | Within the grace period moves it to `MarkedForDeletion` (not back to `Active`); otherwise 400 `not in deletion in progress ... or grace period is over` |
| `PUT /v4/datasetrw/snapshot/{snapshotId}` with `{"status": "MarkedForDeletion"}` | Marks it (public status `markForDeletion`); `can-cancel-delete` is `false` and the cancel route refuses, since nothing is in progress |
| `PUT /v4/datasetrw/snapshot/{snapshotId}` with `{"status": "Active"}` | Restores a marked snapshot to `active` (from either path above). The schema also allows `Pending`, `Copying`, `Failed`, `Deleted`, `DeletionInProgress`; do not set those by hand |
| `DELETE /v4/datasetrw/marked-snapshots`, `DELETE /v4/datasetrw/marked-datasets` | Admin purge of everything marked. Admin-only; never call from a user context |
| `GET /v4/datasetrw/snapshot/limit/{projectId}/{datasetId}` | `true` once the Dataset has hit the active-snapshot cap |
| `GET /v4/datasetrw/dataset/snapshot/limit` | The deployment's cap (`20` by default) |
| `GET /v4/datasetrw/dataset/enforce-limit/{projectId}` | Whether limits apply to the Project (`true` by default) |
| `POST /v4/datasetrw/datasets/limit/{projectId}?ignoreLimit=true` (or `false`) | Sets the Project's **Ignore Dataset Limits** override; no body; returns `{projectId, ignoreLimits, id}`. A Project Owner could set and revert it on 6.4.0 |

Recipe at the limit (same Internal API label): list snapshots, `DELETE /v4/datasetrw/snapshot/{id}`
the ones you no longer need (or `PUT` them `MarkedForDeletion`), then ask an admin to purge; or
set `ignoreLimit=true` on the Project if policy allows. Only `active` snapshots mount in new executions; the files of a
marked or in-progress snapshot remain until an admin purges them.

## python-domino

The SDK wraps a subset through the legacy `/dataset` routes, which are not in the Public API:
`datasets_list(project_id=None)`, `datasets_ids(project_id)`, `datasets_names(project_id)`,
`datasets_create(dataset_name, dataset_description)` (always in the client's configured
Project), `datasets_details(dataset_id)`, `datasets_update_details(dataset_id,
dataset_name=None, dataset_description=None)`, `datasets_remove(dataset_ids)` and
`datasets_upload_files(dataset_id, local_path_to_file_or_directory, file_upload_setting=None,
max_workers=None, target_chunk_size=None, target_relative_path=None)`. It has no snapshot, tag,
grant or shared-dataset methods; use the routes above for those. The domino-python-sdk skill
covers the rest of the SDK.
