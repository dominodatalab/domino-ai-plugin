# NetApp Volumes REST API (`/remotefs/v1`)

Every route and body below is in both published Public API specs
(https://docs.domino.ai/api-specs/6.3/public-api.json and
https://docs.domino.ai/api-specs/cloud/public-api.json). The API page:
https://docs.domino.ai/cloud/reference/api/domino-volumes-api. Mount paths and in-run
file access: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Authentication and base URLs

Follow [domino-api-intro](../domino-api-intro/SKILL.md#authentication). Two bases:

- `base_url` for the Nucleus Public API (`/api/users/v1/self`, `/api/jobs/v1/jobs`):
  `$DOMINO_API_PROXY` with no header, else `$DOMINO_API_HOST` with the access token, else
  the deployment URL with a PAT or service account token.
- `remotefs_url` for `/remotefs/v1/*` volume, filesystem, snapshot and grant operations.
  **Inside a run these are reachable only on `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT`**
  (the volumes API page reserves the variable for these operations) **and only with an
  explicit `Authorization: Bearer`**: the same `GET /remotefs/v1/volumes` returns 404 through
  `$DOMINO_API_PROXY` (with or without a header) and through the in-run
  `$DOMINO_API_HOST`, 401 `Authorization header not found` on the hostport without a
  header, and 200 on the hostport (an in-cluster `http://host:port` value; use the
  variable, never a copied hostname) with the token from
  `http://localhost:8899/access-token`. The same token is served at
  `$DOMINO_API_PROXY/access-token`. Outside Domino, the deployment URL with a PAT or
  service account token works (200).

```python
import os
import requests

def access_token():
    return requests.get("http://localhost:8899/access-token").text.strip()

if os.environ.get("DOMINO_API_PROXY"):                 # inside a run
    base_url, headers = os.environ["DOMINO_API_PROXY"].rstrip("/"), {}
elif os.environ.get("DOMINO_RUN_ID"):                  # inside a run, proxy not injected
    base_url = os.environ["DOMINO_API_HOST"].rstrip("/")
    headers = {"Authorization": f"Bearer {access_token()}"}
else:                                                  # outside Domino
    base_url = os.environ["DOMINO_API_HOST"].rstrip("/")
    headers = {"Authorization": f"Bearer {os.environ['DOMINO_API_TOKEN']}"}

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
POST /remotefs/v1/filesystems            admin: name, dataPlaneId, isDataPlaneDefault, rootPvc, storageClass required; maxSnapshotsPerVolume optional
PUT, DELETE /remotefs/v1/filesystems/{id}
```

```python
filesystems = requests.get(f"{remotefs_url}/remotefs/v1/filesystems", headers=remotefs_headers).json()["data"]
for fs in filesystems:
    print(fs["id"], fs["name"], fs["dataPlaneName"], fs.get("numVolumes"), fs["maxSnapshotsPerVolume"])
```

Registering a filesystem is an administrator task that also needs Kubernetes and Trident
setup: https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes.

## Create a volume

```
POST /remotefs/v1/volumes
```

Required: `name`, `filesystemId`, `capacity` (integer, bytes), `grants`
(`[{"targetId": "<user-or-org-id>", "targetRole": "VolumeOwner" | "VolumeEditor" | "VolumeReader"}]`).
Optional: `description`, `projectId` (attach on creation).

```python
user_id = requests.get(f"{base_url}/api/users/v1/self", headers=headers).json()["user"]["id"]

volume = requests.post(f"{remotefs_url}/remotefs/v1/volumes", headers=remotefs_headers, json={
    "name": "large-training-data",
    "description": "Multi-TB training dataset for vision models",
    "filesystemId": filesystems[0]["id"],
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
POST  /remotefs/v1/rpc/bulk-attach-volumes-to-project, /rpc/bulk-copy-volumes-to-project
```

The spec lists 204 for the attach, detach, mark and restore RPCs; in practice
all four return 200 with the volume record, and `delete-volume`
returns 204 (volume and its snapshot 404 afterwards). Accept either.

```python
requests.post(f"{remotefs_url}/remotefs/v1/rpc/attach-volume-to-project", headers=remotefs_headers,
              json={"volumeId": volume["id"], "projectId": project_id})
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
characters**: a dotted name such as `v2.0` is rejected (live: `500 Tags can only contain
letters, numbers, underscores, and hyphens with maximum length 50`), so use `v2-0`. A tag
name is unique within the volume: adding one that already sits on another snapshot
returns `409 Duplicate Snapshot tag in Volume`; delete it from the old snapshot first. A
snapshot created without tags comes back with `tags: null`, not `[]`. Query filters on
the snapshot list are snake_case (`volume_id`, `run_id`), unlike the Nucleus routes.

`create-snapshot-from-run` is reserved for super users: for a normal user it returned
`403 Missing required permissions for this action` both from a run and from outside
(it needs the `data.manage_volumes_for_execution` action). As a user, snapshot a volume
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
GET /remotefs/v1/volumes?limit=&offset=&search=&sort_by=&order=&project_id=&data_plane_id=&status=&tag_ids=&filter_strictly_by_volume_roles=
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
  remotefs routes. The published spec binds no security scheme to any `/remotefs/v1`
  operation, so the auth mode comes from the live behaviour above; if a deployment rejects
  the bearer on a file route, check its `/docs/openapi/data_webvfs_service-swagger.json`.

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
with snapshots under `/domino/netapp-volumes/snapshots/<name>`, and can write to it. Adding `"snapshotNetAppVolumesOnCompletion": true` (snapshot every mounted volume
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
(unauthenticated, from the `/docs` reference). Do not derive the deployment hostname from
a JWT; read `DOMINO_API_HOST` or use the URL you sign in at.
