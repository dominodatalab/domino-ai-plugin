# NetApp Volumes REST API

The API page: https://docs.domino.ai/cloud/reference/api/domino-volumes-api. Mount paths and
in-run file access: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Base path

The service is served under `/remotefs/v1` or `/domino-netapp-volumes/v1` depending on the
deployment. Confirm which one yours serves, and the request bodies, in its own reference at
`https://<domino-domain>/docs` (`/docs/openapi/openapi-public.json`, or the service document
`/docs/openapi/data_remotefs_service-swagger.json`). A quick probe: `GET <base>/filesystems`
returns 200 on the right base and 404 on the other. The examples below set `nv` once; change it
if your deployment uses the other path. The route lists write the path relative to that base.

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

nv = f"{remotefs_url}/remotefs/v1"                     # or /domino-netapp-volumes/v1; see "Base path"
```

Error bodies from this service are `{"message": "..."}`, optionally with `status`,
`errorCode` and `details`. The access token is short-lived; re-read it for long-running scripts.
List routes return `{"items": [...], "totalCount": n}`.

## Filesystems

```
GET  /filesystems?limit=&offset=&order=&search=&sort_by=&data_plane_id=
GET  /filesystems/{id}
POST /filesystems            admin: name, dataPlaneId, isDataPlaneDefault, rootPvc, storageClass
PUT, DELETE /filesystems/{id}
```

```python
filesystems = requests.get(f"{nv}/filesystems", headers=remotefs_headers).json()["items"]
for fs in filesystems:
    print(fs["id"], fs["name"], fs["dataPlaneId"])
```

Registering a filesystem is an administrator task that also needs Kubernetes and Trident
setup: https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes.

## Create a volume

```
POST /volumes            body: name, filesystemId, capacity (integer, bytes); optional projectId (attach on creation)
```

```python
volume = requests.post(f"{nv}/volumes", headers=remotefs_headers, json={
    "name": "large-training-data",
    "filesystemId": filesystems[0]["id"],
    "capacity": 5_000_000_000_000,            # 5 TB in bytes
    "projectId": os.environ.get("DOMINO_PROJECT_ID"),
}).json()
print(volume["id"], volume["name"], volume["status"])
```

Set roles with the grants route below. The volume record: `id`, `name`, `capacity`, `dataPlaneId`, `filesystemId`, `projectId`, `status`
(`Active`, `Deleted`, `Pending`, `Failed`), `grants[]`, `createdAt`, `createdBy`, `updatedAt`,
`updatedBy`, `deletedAt`. If the deployment returns 400 for this body, read the
`CreateVolumeRequest` schema in its `/docs`.

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
PUT /volumes/{id}/grants      body: {"volumeId": "...", "grants": [{"entityId", "entityType", "accessLevel"}]} (replaces the grant list)
```

The body replaces every grant, so keep an owner in the list. Read `GET /volumes/{id}/grants`
on an existing volume first and copy the `entityType` and `accessLevel` values it returns; the
UI roles are Reader, Editor and Owner.

```python
user_id = requests.get(f"{base_url}/api/users/v1/self", headers=headers).json()["user"]["id"]
current = requests.get(f"{nv}/volumes/{volume_id}/grants", headers=remotefs_headers).json()
print(current)                                   # copy the field values from here
requests.put(f"{nv}/volumes/{volume_id}/grants", headers=remotefs_headers, json={
    "volumeId": volume_id,
    "grants": [
        {"entityId": user_id, "entityType": "<as returned>", "accessLevel": "<as returned>"},
    ],
})
```

## Snapshots

```
GET  /snapshots?volume_id=<id>&project_id=&limit=&offset=&order=&sort_by=&search=
GET  /snapshots/{id}
PUT  /snapshots/{id}                     body: {"name": "..."}
POST /snapshots                          body: {"volumeId": "...", "name": "..."}
POST /rpc/restore-snapshot               body: {"snapshotId": "..."}
POST /rpc/delete-snapshot                body: {"snapshotId": "..."}   -> 204
```

Query filters on the snapshot list are snake_case (`volume_id`), unlike the Nucleus routes.

```python
snapshot = requests.post(f"{nv}/snapshots", headers=remotefs_headers, json={
    "volumeId": volume_id,
    "name": "q4-customer-records",
}).json()
print(snapshot["id"], snapshot.get("version"))
```

Snapshot record: `id`, `name`, `volumeId`, `projectId`, `createdAt`, `createdBy`,
`updatedAt`, `deletedAt`, and on most deployments `version`, the `<number>` in
`snapshots/<name>/<number>` mount paths.

## List volumes

```
GET /volumes?limit=&offset=&search=&sort_by=&order=&project_id=&data_plane_id=&filesystem_id=&show_deleted=
GET /volumes/{id}
```

```python
volumes = requests.get(f"{nv}/volumes", headers=remotefs_headers,
                       params={"project_id": project_id, "limit": 50}).json()
for v in volumes["items"]:
    print(f"{v['name']}  {v['capacity'] / 1e12:.1f} TB  id={v['id']}")
print(volumes["totalCount"])
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
`netAppVolumeIds`, confirm the Jobs request body in its `/docs`. To snapshot at the end of a
job, call `POST <base>/snapshots` from the job's last step.

Only `projectId` and `runCommand` are required; `environmentId` is optional. Full body:
[API-JOBS.md](../domino-python-sdk/API-JOBS.md#start-a-job). Workspace sessions take the
same ids as `netAppVolumeMounts` on
`POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions`.

## Other routes

`POST /downloads` and `GET /downloads/{id}?volume_id=` (archive a set of volume paths),
`POST /rpc/check-is-over-limit` and the `/account/authz/...` permission checks are in the
deployment's `/docs`; pull their schemas from there when needed.

## Spec discovery

Published specs: [API-SPECS.md](../domino-api-intro/API-SPECS.md). Your deployment's copy of
this service's document is `https://<domino-domain>/docs/openapi/data_remotefs_service-swagger.json`
(unauthenticated); the deployment reference at `https://<domino-domain>/docs` lists the base path.
