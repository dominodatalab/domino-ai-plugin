# Domino Apps API (beta catalog)

Catalog of the `/api/apps/beta/apps` routes, the only Public Apps API on Domino 6.1. App
lifecycle and publishing: [domino-apps/API-APPS.md](../domino-apps/API-APPS.md). Schemas:
the 6.1 Platform API reference ([API-SPECS.md](../domino-api-intro/API-SPECS.md)).

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## List apps

```
GET /api/apps/beta/apps
```

| Parameter | Notes |
|-----------|-------|
| `projectId`, `name` | The only filters; `name` is a substring match |
| `includeTemplateApps` | Default false |
| `sortField` (`name`, `lastUpdated`, `status`, `views`), `sortOrder` (`asc`, `desc`) | |
| `limit`, `offset` | `limit` defaults to no limit |

There is no status, owner or publisher filter (unknown parameters are ignored, so every App
comes back): filter on `currentVersion.currentInstance.status` in the response.

Response: `{"items": [...], "metadata": {...}}`. Each item has `id`, `name`, `description`,
`project` (`id`, `name`, `ownerUsername`, `projectType`), `publisher`, `entryPoint`, `url`,
`visibility`, `discoverable`, `mountDatasets`, `renderIFrame`, `isPinned`, `views`,
`currentVersion` (`id`, `hardwareTierId`, `environmentId`, `resolvedCommits`,
`currentInstance`, ...).

```python
apps = requests.get(f"{base_url}/api/apps/beta/apps", headers=headers,
                    params={"projectId": project_id, "limit": 20}).json()["items"]
for app in apps:
    print(app["name"], app["id"], app["url"])
```

## Create an app

```
POST /api/apps/beta/apps
```

Required: `name`, `projectId`, `visibility` (`AUTHENTICATED`, `GRANT_BASED`,
`GRANT_BASED_STRICT`, `PUBLIC`), `version`. Optional: `description`, `entryPoint`,
`discoverable`, `mountDatasets`, `renderIFrame`, `accessStatuses[]`
(`userId`, `status` `ALLOWED` / `DENIED` / `PENDING`).

`version` fields (`AppVersionCreationRequest`, none required): `hardwareTierId`,
`environmentId`, `environmentRevisionId`, `gitRef`
(`{"type": "head" | "commitId" | "branches" | "tags" | "custom", "value": "..."}`; Git-based
Projects), `externalVolumeMountIds`, `netAppVolumeIds`, `vanityUrl`. `dfsCommitId` is in the
schema but ignored: a DFS Project's version runs its latest commit. There is no version
`description`.

```python
app = requests.post(f"{base_url}/api/apps/beta/apps", headers=headers, json={
    "name": "customer-insights",
    "description": "Customer analytics dashboard",
    "projectId": project_id,
    "visibility": "GRANT_BASED",
    "entryPoint": "app.sh",
    "version": {"hardwareTierId": "small-k8s", "environmentId": env_id},
}).json()
app_id, version_id = app["id"], app["currentVersion"]["id"]
```

The response is the app record (`id`, `url`, `visibility`, `currentVersion`, ...).

## Get, update, delete

```
GET    /api/apps/beta/apps/{appId}
PATCH  /api/apps/beta/apps/{appId}        body: metadata fields such as name, description, discoverable
DELETE /api/apps/beta/apps/{appId}
```

## Versions

```
GET   /api/apps/beta/apps/{appId}/versions
POST  /api/apps/beta/apps/{appId}/versions                       body: the version object above; starts the App
GET   /api/apps/beta/apps/{appId}/versions/{versionId}
PATCH /api/apps/beta/apps/{appId}/versions/{versionId}            body: {"vanityUrl": "..."}
```

`POST .../versions` is the start and restart route: it creates the version and starts an
instance of it, so do not create a version only for bookkeeping. Stop the running instance
first (below), then poll the new version until `Running`. A version record carries
`currentInstance` (`id`, `status`, `createdAt`, `dfsCommitId`, `gitCommitId`). Instance
statuses include: `Queued`, `Pending`, `Preparing`, `Running`, `Stopped`. Do not start Apps
with python-domino `app_publish`: it calls the Domino Internal API (non-public route; may
change in a future Domino version), and the `dominodatalab` 1.4.4 in the Domino 6.1 image
takes neither an App ID nor a commit.

## Instances and logs

```
GET    /api/apps/beta/apps/{appId}/versions/{versionId}/instances
GET    /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}
DELETE /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}     stops that instance
GET    /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}/logs
GET    /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}/realTimeLogs
POST   /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}/views
```

```python
instances = requests.get(f"{base_url}/api/apps/beta/apps/{app_id}/versions/{version_id}/instances",
                         headers=headers).json()          # {"items": [{"id", "createdAt", "status", "dfsCommitId"}], "metadata": {...}}
instance_id = instances["items"][0]["id"]
logs = requests.get(
    f"{base_url}/api/apps/beta/apps/{app_id}/versions/{version_id}/instances/{instance_id}/logs",
    headers=headers)
print(logs.text)
```

## Views, vanity URLs, access

```
GET /api/apps/beta/apps/{appId}/views?startTimestamp=&endTimestamp=&granularity=     (epoch ms; granularity default 86400000)
GET /api/apps/beta/apps/vanityUrls/{vanityUrl}
POST /api/apps/beta/apps/{appId}/access/requests
```

There is no Public roles route. App access is managed through the
`/v4/modelProducts/{appId}` family (`visibility`, `grantAccess`, `denyAccess`, `invite`,
`uninvite`; non-public route; may change in a future Domino version; python-domino's
`app_*` methods use the same family): bodies and responses in
[domino-apps/API-APPS.md](../domino-apps/API-APPS.md).

## Workflow: create, restart, wait, stop

```python
import time

apps_url = f"{base_url}/api/apps/beta/apps"
app = requests.post(apps_url, headers=headers, json={
    "name": "ml-dashboard", "projectId": project_id, "visibility": "GRANT_BASED",
    "version": {"hardwareTierId": "small-k8s", "environmentId": env_id},
}).json()
app_id = app["id"]

def stop_running(app_id):
    current = requests.get(f"{apps_url}/{app_id}", headers=headers).json().get("currentVersion") or {}
    instance = current.get("currentInstance") or {}
    if instance.get("id") and instance.get("status") not in ("Stopped", "Succeeded", "Failed", "Error"):
        requests.delete(f"{apps_url}/{app_id}/versions/{current['id']}/instances/{instance['id']}",
                        headers=headers)

# Restart on new code: stop the running instance, then create a version (this starts it)
stop_running(app_id)
version = requests.post(f"{apps_url}/{app_id}/versions", headers=headers, json={
    "hardwareTierId": "small-k8s", "environmentId": env_id,
    # Git-based Project: "gitRef": {"type": "commitId", "value": "<sha>"}
}).json()
version_id = version["id"]

deadline = time.time() + 900
while time.time() < deadline:
    version = requests.get(f"{base_url}/api/apps/beta/apps/{app_id}/versions/{version_id}",
                           headers=headers).json()
    status = (version.get("currentInstance") or {}).get("status", "Pending")
    if status in ("Running", "Serving"):
        print("App is up:", app["url"]); break
    if status in ("Failed", "Error", "Stopped", "Succeeded"):
        print("App is not serving:", status); break
    time.sleep(10)
else:
    print("Timed out waiting for the app")

stop_running(app_id)                                   # stop the App when done
```

## App requirements

Apps need an `app.sh` entry point that binds to `0.0.0.0:8888`; see
[domino-apps](../domino-apps/SKILL.md) for framework-specific scripts and proxy rules.
