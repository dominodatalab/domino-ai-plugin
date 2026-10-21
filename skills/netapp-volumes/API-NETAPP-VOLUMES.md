# NetApp Volumes REST API (`/remotefs/v1`)

The API page: https://docs.domino.ai/cloud/reference/api/domino-volumes-api. Mount paths and
in-run file access: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Authentication and base URLs

Two bases:

- `base_url` and `headers` for the Nucleus Public API (`/api/users/v1/self`,
  `/api/jobs/v1/jobs`): the Python setup block in
  [domino-api-intro](../domino-api-intro/SKILL.md#authentication).
- `remotefs_url` for `/remotefs/v1/*` volume, filesystem, snapshot and grant operations. In a
  run use `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` (an in-cluster `host:port` value; add `http://`
  if it has no scheme; use the variable, never a copied hostname) with the
  `http://localhost:8899/access-token` bearer (also served at `$DOMINO_API_PROXY/access-token`);
  the proxy and `DOMINO_API_HOST` do not route `/remotefs`, and the hostport without a header
  returns 401. Outside Domino, the deployment URL with a PAT or service account token.

```python
import os
import requests

# base_url and headers: the Python setup block in domino-api-intro/SKILL.md#authentication

def access_token():
    return requests.get("http://localhost:8899/access-token").text.strip()

if os.environ.get("DOMINO_RUN_ID"):                    # inside a run: hostport + bearer, never the proxy
    remotefs_url = os.environ["DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT"].rstrip("/")
    if "://" not in remotefs_url:
        remotefs_url = "http://" + remotefs_url
    remotefs_headers = {"Authorization": f"Bearer {access_token()}"}
else:                                                  # outside Domino: deployment URL + PAT/SA token
    remotefs_url, remotefs_headers = base_url, headers
```

Error bodies from this service are `{"message": "..."}`. The access token is short-lived;
re-read it for long-running scripts.

## Filesystems

```
GET  /remotefs/v1/filesystems?limit=&offset=&data_plane_id=
GET  /remotefs/v1/filesystems/{id}
POST /remotefs/v1/filesystems            admin: name, dataPlaneId, isDataPlaneDefault, rootPvc, storageClass required; maxSnapshotsPerVolume, maxVolumes (6.4+) optional
PUT, DELETE /remotefs/v1/filesystems/{id}   PUT takes the same body as POST; maxVolumes must be > 0
```

```python
filesystems = requests.get(f"{remotefs_url}/remotefs/v1/filesystems", headers=remotefs_headers).json()["data"]
for fs in filesystems:
    print(fs["id"], fs["name"], fs["dataPlaneName"], fs["isDataPlaneDefault"],
          fs.get("numVolumes"), fs.get("maxVolumes"), fs["maxSnapshotsPerVolume"])
```

From Domino 6.4 each filesystem carries `maxVolumes` (default 490, sized for one ONTAP HA
pair with its 500-volume cap; administrators raise it per filesystem with `PUT`) and
`numVolumes` (volumes not in `Deleted` status). A filesystem with
`numVolumes >= maxVolumes` is full: creating or copying onto it explicitly returns `409`,
and automatic placement skips it.

Registering a filesystem is an administrator task that also needs Kubernetes and Trident
setup: https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes.

## Create a volume

```
POST /remotefs/v1/volumes
```

Required: `name`, `capacity` (integer, bytes), `grants`
(`[{"targetId": "<user-or-org-id>", "targetRole": "VolumeOwner" | "VolumeEditor" | "VolumeReader"}]`).
Optional: `description`, `projectId` (attach on creation), `filesystemId`, `dataPlaneId`.

Placement (Domino 6.4+): `filesystemId` is optional. When omitted, send `dataPlaneId` and
the service picks a filesystem on that data plane with free volume slots (the data plane
default first, then the one with the most headroom); `409` means no filesystem on that
data plane has capacity. With `filesystemId` set, a full filesystem returns `409` and a
`dataPlaneId` that does not match the filesystem returns `400`. On Domino 6.3
`filesystemId` is required.

```python
user_id = requests.get(f"{base_url}/api/users/v1/self", headers=headers).json()["user"]["id"]

volume = requests.post(f"{remotefs_url}/remotefs/v1/volumes", headers=remotefs_headers, json={
    "name": "large-training-data",
    "description": "Multi-TB training dataset for vision models",
    "dataPlaneId": filesystems[0]["dataPlaneId"],   # automatic placement (6.4+); or "filesystemId": filesystems[0]["id"]
    "capacity": 5_000_000_000_000,            # 5 TB in bytes
    "grants": [{"targetId": user_id, "targetRole": "VolumeOwner"}],
    "projectId": os.environ.get("DOMINO_PROJECT_ID"),
}).json()
print(volume["id"], volume["uniqueName"], volume["status"])
```

The volume record: `id`, `name`, `uniqueName`, `description`, `filesystemId`,
`filesystemName`, `capacity` (maximum bytes), `storageSize` (used bytes), `path`, `status`
(`Active`, `MarkedForDeletion`, `Deleted`), `numSnapshots`, `maxSnapshots`, `dataPlaneId`,
`grants[]` (`targetId`, `targetName`, `targetRole`, `isOrganization`), `projects[]`,
`createdAt`, `createdBy`, `updatedAt`, `updatedBy`, `taxonomyTags`, `properties`.

## Edit, attach, detach, delete

```
PATCH /remotefs/v1/volumes/{id}                          body: {"name": "new-name", "description": "..."} (both optional; a rename changes the mount path)
POST  /remotefs/v1/rpc/attach-volume-to-project          body: {"projectId": "...", "volumeId": "..."}   -> 200, the volume record
POST  /remotefs/v1/rpc/detach-volume-from-project        body: {"projectId": "...", "volumeId": "..."}   -> 200, the volume record
POST  /remotefs/v1/rpc/mark-volume-for-deletion          body: {"volumeId": "..."}   -> 200, status MarkedForDeletion
POST  /remotefs/v1/rpc/restore-volume                    body: {"volumeId": "..."}   -> 200, status Active (undo mark-for-deletion)
POST  /remotefs/v1/rpc/delete-volume                     body: {"volumeId": "..."}   -> 204 (permanent; needs delete permission; works on an Active volume, marking first is not required)
POST  /remotefs/v1/rpc/bulk-attach-volumes-to-project    body: {"projectId": "...", "volumeIds": ["..."]}
POST  /remotefs/v1/rpc/bulk-copy-volumes-to-project      body: {"projectId": "...", "volumes": [{"sourceVolumeId": "...", "targetFilesystemId": "..." (optional, 6.4+), "grants": [...]}]}
```

Accept 200 or 204 from these RPCs; after `delete-volume` the volume and its snapshots return 404.

```python
requests.post(f"{remotefs_url}/remotefs/v1/rpc/attach-volume-to-project", headers=remotefs_headers,
              json={"volumeId": volume["id"], "projectId": project_id})
```

`bulk-copy-volumes-to-project` copies data (not snapshots) into new volumes attached to
`projectId` and always answers `200` with `results[]`, one entry per source volume:
`sourceVolumeId`, `status` (`200`, or an error code such as `409`), `error`, and `data`
(the new volume record on success). From Domino 6.4 a copy stays on the source volume's
filesystem and moves to an automatically selected filesystem on the same data plane only
when the source one is full; `targetFilesystemId` pins it to a filesystem on that data
plane instead, in which case a full target is a per-item `409` rather than a fallback.
Check every `results[i].status`; one failed copy does not fail the others.

```python
copies = requests.post(f"{remotefs_url}/remotefs/v1/rpc/bulk-copy-volumes-to-project", headers=remotefs_headers, json={
    "projectId": project_id,
    "volumes": [{"sourceVolumeId": volume["id"], "grants": [{"targetId": user_id, "targetRole": "VolumeOwner"}]}],
}).json()["results"]
for r in copies:
    print(r["sourceVolumeId"], r["status"], r.get("error") or r["data"]["filesystemId"])
```

## Grants

```
GET /remotefs/v1/volumes/{id}/grants
PUT /remotefs/v1/volumes/{id}/grants      body: a JSON array of {"targetId", "targetRole"} (replaces the grant list)
```

```python
requests.put(f"{remotefs_url}/remotefs/v1/volumes/{volume_id}/grants", headers=remotefs_headers, json=[
    {"targetId": user_id, "targetRole": "VolumeOwner"},
    {"targetId": "<other-user-id>", "targetRole": "VolumeEditor"},
    {"targetId": "<org-id>", "targetRole": "VolumeReader"},
])
```

Keep an owner in the list; the body replaces all grants. `Service` is a fourth role value
reserved for Domino services.

## Snapshots

```
GET  /remotefs/v1/snapshots?volume_id=<id>&run_id=<runId>&limit=&offset=
GET  /remotefs/v1/snapshots/{id}
PUT  /remotefs/v1/snapshots/{id}                     body: {"description": "..."} (required; edits the commit message)
POST /remotefs/v1/snapshots                          body: {"volumeId": "...", "description": "...", "tagNames": ["v2-0"]} (volumeId required)
POST /remotefs/v1/snapshots/{id}/tags                body: {"name": "production"}
DELETE /remotefs/v1/snapshots/{id}/tags/{name}       -> 204
POST /remotefs/v1/rpc/restore-snapshot               body: {"snapshotId": "..."}   -> 200, the snapshot record (spec says 204)
POST /remotefs/v1/rpc/delete-snapshot                body: {"snapshotId": "..."}   -> 204 (also deletes the snapshot's tags)
POST /remotefs/v1/rpc/create-snapshot-from-run       body: {"volumeId", "runId", "userId", "description"}; spec: "must be called by super user"
GET  /remotefs/v1/volumes/{id}/snapshots/{version}
```

`description` is the commit message shown in the UI; `tagNames` are applied in the order
given. **Tag names may contain only letters, numbers, underscores and hyphens, at most 50
characters**: a dotted name such as `v2.0` is rejected (`500 Tags can only contain
letters, numbers, underscores, and hyphens with maximum length 50`), so use `v2-0`. A tag
name is unique within the volume: adding one that already sits on another snapshot
returns `409 Duplicate Snapshot tag in Volume`; delete it from the old snapshot first. A
snapshot created without tags comes back with `tags: null`, not `[]`. Query filters on
the snapshot list are snake_case (`volume_id`, `run_id`), unlike the Nucleus routes.

`create-snapshot-from-run` is reserved for super users: non-super-users get
`403 Missing required permissions for this action` (it needs the
`data.manage_volumes_for_execution` action). As a user, snapshot a volume
with `POST /remotefs/v1/snapshots`, or, where the deployment enables it, set
`snapshotNetAppVolumesOnCompletion: true` on the job (see "Mount volumes in a job").

```python
snapshot = requests.post(f"{remotefs_url}/remotefs/v1/snapshots", headers=remotefs_headers, json={
    "volumeId": volume_id,
    "description": "Added Q4 customer records, 50M new rows",
    "tagNames": ["v2-0"],
}).json()
print(snapshot["id"], snapshot["version"], [t["name"] for t in (snapshot.get("tags") or [])])

requests.post(f"{remotefs_url}/remotefs/v1/snapshots/{snapshot['id']}/tags",
              headers=remotefs_headers, json={"name": "production"})

# Edit the commit message later
requests.put(f"{remotefs_url}/remotefs/v1/snapshots/{snapshot['id']}", headers=remotefs_headers,
             json={"description": "Q4 customer records (validated)"})
```

Snapshot record: `id`, `volumeId`, `version` (links to the ONTAP snapshot name and is the
`<number>` in `snapshots/<name>/<number>` mount paths), `description`, `status`, `tags[]`
(`name`, `addedAt`, `addedBy`; sorted by creation time ascending, so the last entry is the
tag that mounts), `labels` (system-set), `runId`, `createdAt`, `createdBy`.

## List volumes

```
GET /remotefs/v1/volumes?limit=&offset=&search=&sort_by=&order=&project_id=&data_plane_id=&filesystem_id=&status=&tag_ids=&filter_strictly_by_volume_roles=
GET /remotefs/v1/volumes/{id}
GET /remotefs/v1/volumes/ids;  GET /remotefs/v1/volumes/unique-name/{uniqueName}
```

```python
volumes = requests.get(f"{remotefs_url}/remotefs/v1/volumes", headers=remotefs_headers,
                       params={"project_id": project_id, "limit": 50}).json()
for v in volumes["data"]:
    print(f"{v['name']}  {v['capacity'] / 1e12:.1f} TB  snapshots={v['numSnapshots']}/{v['maxSnapshots']}  id={v['id']}")
print(volumes["meta"]["pagination"])
```

`filesystem_id` (repeatable, Domino 6.4+) narrows the list to one or more filesystems and
`sort_by=filesystem_name` sorts by the filesystem's name; the other `sort_by` values are
volume columns such as `name`, `created_at` and `updated_at`.

## Files

```
GET    /remotefs/v1/volumes/{id}/files?path=<subpath>            -> {"rows": [{"name", "size", "lastModified"}], "directorySize"}
GET    /remotefs/v1/volumes/{id}/files/raw/{path}, /files/preview/{path}, /files/metadata, /files/recursive
PATCH, DELETE /remotefs/v1/volumes/{id}/files
POST   /remotefs/v1/volumes/{id}/uploads/start, /uploads, GET /uploads/status, /uploads/{uploadID}, /uploads/{uploadID}/complete
GET    /remotefs/v1/snapshots/{id}/files, /files/raw/{path}, /files/preview/{path}, /files/metadata, /files/recursive
```

File operations run on a different host than volume operations
(https://docs.domino.ai/6.3/reference/api/domino-volumes-api):

- Outside a Domino execution: prefix the path with `/webvfs` on the deployment URL, for
  example `GET https://<deployment>/webvfs/remotefs/v1/volumes/{id}/files?path=raw`, with
  your PAT or service account token. `path=` (empty) lists the root and
  `path=/` returns `400 invalid path input`; without the prefix the route is 404. Rows
  look like `{"name": {"label", "isDirectory"}, "size": {"label", "sizeInBytes"}, "lastModified"}`,
  and `/files/raw/{path}` returns the file body.
- Inside an execution: call `http://data-webvfs-service.domino-compute:80` with the path
  exactly as above (no prefix). Send the same access-token bearer as for the other
  remotefs routes; if a deployment rejects the bearer on a file route, check its
  `/docs/openapi/data_webvfs_service-swagger.json`.

Inside a Workspace or Job, reading and writing the mount path is simpler than the file API
([DATA-ACCESS.md](./DATA-ACCESS.md)).

## Mount volumes in a job

`POST /api/jobs/v1/jobs` (Nucleus `base_url`, not `remotefs_url`):

```python
requests.post(f"{base_url}/api/jobs/v1/jobs", headers=headers, json={
    "projectId": project_id,
    "runCommand": "python train.py",
    "title": "train on shared volume",               # optional
    "hardwareTier": "small-k8s",                     # optional hardware tier id
    "netAppVolumeIds": [volume_id],
})
```

The job mounts the volume read-write at `/domino/netapp-volumes/<name>` (DFS project)
with snapshots under `/domino/netapp-volumes/snapshots/<name>`. Adding
`"snapshotNetAppVolumesOnCompletion": true` (snapshot every mounted volume
when the job ends) depends on deployment configuration: where the flag is off it returns
`400 feature flag EnableDominoNetAppSnapshotsOnExecutionCompletion is disabled for user`.
Send it only where an administrator has enabled that flag, and fall back to
`POST /remotefs/v1/snapshots` from the job's last step otherwise.

Only `projectId` and `runCommand` are required; `environmentId` is optional. Full body:
[API-JOBS.md](../domino-python-sdk/API-JOBS.md#start-a-job). Workspace sessions take the
same ids as `netAppVolumeMounts` on
`POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions`.

## Transfers and other routes

`GET, POST /remotefs/v1/data-transfers`, `/data-transfers/{id}`, `POST /remotefs/v1/downloads`,
`/rpc/download-archive`, `/rpc/get-volume-mounts`, `/rpc/check-is-over-limit`,
`/remotefs/v1/root-pvcs`, `/remotefs/v1/staging-volume` and the
`/remotefs/v1/account/authz/...` permission checks are in the spec; pull their schemas from
[API-SPECS.md](../domino-api-intro/API-SPECS.md) when needed.

## Spec discovery

Published specs: [API-SPECS.md](../domino-api-intro/API-SPECS.md). Your deployment's copy
of this service's document is `https://<domino-domain>/docs/openapi/data_remotefs_service-swagger.json`
(unauthenticated).
