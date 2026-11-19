# NetApp Volumes REST API

The API page: https://docs.dominodatalab.com/en/6.1/api_guide/b3b2a1/domino-netapp-volumes-api/. Mount paths and
in-run file access: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Base path and shapes

The service answers on `/remotefs/v1`; the route lists below are relative to it. The 6.1 API
page gives `/domino-netapp-volumes/v1` as the base path and shows request and response shapes
the service does not use (`items` and `totalCount` lists, a `{"volumeId", "grants"}` grants
body, a snapshot `name`). Use the shapes on this page.

## Authentication and base URLs

Two bases:

- `base_url` and `headers` for the Nucleus Public API (`/api/users/v1/self`,
  `/api/jobs/v1/jobs`): the Python setup block in
  [domino-api-intro](../domino-api-intro/SKILL.md#authentication).
- `remotefs_url` for the volume, filesystem, snapshot and grant routes. In a run use
  `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` (an in-cluster `host:port` value; add `http://` if it has
  no scheme; use the variable, never a copied hostname) with the
  `http://localhost:8899/access-token` bearer (also served at `$DOMINO_API_PROXY/access-token`);
  the proxy and `DOMINO_API_HOST` may not route this service, and the hostport without a header
  returns 401. Outside Domino, the deployment URL with a service-account token as a bearer (or a
  user API key in `X-Domino-Api-Key`).

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
else:                                                  # outside Domino: deployment URL + service-account token or API key
    remotefs_url, remotefs_headers = base_url, headers

nv = f"{remotefs_url}/remotefs/v1"
```

Error bodies from this service are `{"message": "..."}`, optionally with `status`,
`errorCode` and `details`. The access token is short-lived; re-read it for long-running scripts.
List routes return `{"data": [...], "meta": {...}}`.

## Filesystems

```
GET  /filesystems?limit=&offset=&order=&search=&sort_by=&data_plane_id=
GET  /filesystems/{id}
POST /filesystems            admin: name, dataPlaneId, isDataPlaneDefault, rootPvc, storageClass
PUT, DELETE /filesystems/{id}
```

```python
filesystems = requests.get(f"{nv}/filesystems", headers=remotefs_headers).json()["data"]
for fs in filesystems:
    print(fs["id"], fs["name"], fs["dataPlaneId"])
```

Registering a filesystem is an administrator task that also needs Kubernetes and Trident
setup: https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes.

## Create a volume

```
POST /volumes
```

Required: `name`, `filesystemId`, `capacity` (integer, bytes) and `grants`
(`[{"targetId": "<user-id>", "targetRole": "VolumeOwner"}]`; without it the call returns 400).
Optional: `projectId` (attach on creation).

```python
user_id = requests.get(f"{base_url}/api/users/v1/self", headers=headers).json()["user"]["id"]

volume = requests.post(f"{nv}/volumes", headers=remotefs_headers, json={
    "name": "large-training-data",
    "filesystemId": filesystems[0]["id"],
    "capacity": 5_000_000_000_000,            # 5 TB in bytes
    "grants": [{"targetId": user_id, "targetRole": "VolumeOwner"}],
    "projectId": os.environ.get("DOMINO_PROJECT_ID"),
}).json()
print(volume["id"], volume["name"], volume["status"])
```

The volume record: `id`, `name`, `capacity`, `dataPlaneId`, `filesystemId`, `status`
(`Active`, `Deleted`, `Pending`, `Failed`), `grants[]`, `createdAt`, `createdBy`, `updatedAt`,
`updatedBy`, `deletedAt`.

## Edit, attach, detach, delete

```
PATCH /volumes/{id}                          body: {"name": "new-name"} (a rename changes the mount path)
POST  /rpc/attach-volume-to-project          body: {"projectId": "...", "volumeId": "..."}
POST  /rpc/detach-volume-from-project        body: {"projectId": "...", "volumeId": "..."}
POST  /rpc/mark-volume-for-deletion          body: {"volumeId": "..."}
POST  /rpc/restore-volume                    body: {"volumeId": "..."}   (undo mark-for-deletion)
POST  /rpc/delete-volume                     body: {"volumeId": "..."}   -> 204 (permanent; needs delete permission)
```

Accept 200 or 204 from these RPCs; after `delete-volume` the volume and its snapshots return 404.

```python
requests.post(f"{nv}/rpc/attach-volume-to-project", headers=remotefs_headers,
              json={"volumeId": volume["id"], "projectId": project_id})
```

## Grants

```
GET /volumes/{id}/grants
PUT /volumes/{id}/grants      body: a JSON array of {"targetId", "targetRole"} (replaces the grant list)
```

`targetRole` is `VolumeOwner`, `VolumeEditor` or `VolumeReader` (the UI's Owner, Editor and
Reader). The body replaces every grant, so keep an owner in the list.

```python
requests.put(f"{nv}/volumes/{volume_id}/grants", headers=remotefs_headers, json=[
    {"targetId": user_id, "targetRole": "VolumeOwner"},
    {"targetId": "<other-user-id>", "targetRole": "VolumeEditor"},
])
```

## Snapshots

```
GET  /snapshots?volume_id=<id>&project_id=&limit=&offset=&order=&sort_by=&search=
GET  /snapshots/{id}
PUT  /snapshots/{id}                     body: {"description": "..."} (required)
POST /snapshots                          body: {"volumeId": "...", "description": "..."}
POST /rpc/restore-snapshot               body: {"snapshotId": "..."}
POST /rpc/delete-snapshot                body: {"snapshotId": "..."}   -> 204
```

Snapshots take a `description`, not a `name`. Query filters on the snapshot list are
snake_case (`volume_id`), unlike the Nucleus routes.

```python
snapshot = requests.post(f"{nv}/snapshots", headers=remotefs_headers, json={
    "volumeId": volume_id,
    "description": "Q4 customer records",
}).json()
print(snapshot["id"], snapshot.get("version"))
```

Snapshot record: `id`, `volumeId`, `description`, `createdAt`, `createdBy`, and on most
deployments `version`, the `<number>` in `snapshots/<name>/<number>` mount paths.

## List volumes

```
GET /volumes?limit=&offset=&search=&sort_by=&order=&project_id=&data_plane_id=&filesystem_id=&show_deleted=
GET /volumes/{id}
```

```python
volumes = requests.get(f"{nv}/volumes", headers=remotefs_headers,
                       params={"project_id": project_id, "limit": 50}).json()
for v in volumes["data"]:
    print(f"{v['name']}  {v['capacity'] / 1e12:.1f} TB  id={v['id']}")
print(volumes["meta"])
```

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
with snapshots under `/domino/netapp-volumes/snapshots/<name>`. If the deployment rejects
`netAppVolumeIds`, check the Jobs request body in the
[6.1 Platform API reference](https://docs.dominodatalab.com/en/6.1/api_guide/8c929e/domino-platform-api-reference/).
To snapshot at the end of a job, call `POST <base>/snapshots` from the job's last step.

Only `projectId` and `runCommand` are required; `environmentId` is optional. Full body:
[API-JOBS.md](../domino-python-sdk/API-JOBS.md#start-a-job). Workspace sessions take the
same ids as `netAppVolumeMounts` on
`POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions`.

## Other routes

`POST /downloads` and `GET /downloads/{id}?volume_id=` (archive a set of volume paths),
`POST /rpc/check-is-over-limit` and the `/account/authz/...` permission checks are listed on
the 6.1 API page above; send a minimal body and read the `{"message"}` of a 400 for the
fields it needs.
