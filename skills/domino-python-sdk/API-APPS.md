# Domino Apps API (beta catalog)

Catalog of the `/api/apps/beta/apps` routes, the only Public Apps API on Domino 6.1. App
lifecycle and publishing: [domino-apps/API-APPS.md](../domino-apps/API-APPS.md). Bodies can
differ by deployment: confirm them in your deployment's `/docs`
([API-SPECS.md](../domino-api-intro/API-SPECS.md)).

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## List apps

```
GET /api/apps/beta/apps
```

| Parameter | Notes |
|-----------|-------|
| `projectId`, `ownerId`, `publisherId`, `name` | Filters |
| `status` | Most recent instance status: `Queued`, `Scheduled`, `Pending`, `Preparing`, `Building`, `Pulling`, `Running`, `Serving`, `StopRequested`, `StopAndDiscardRequested`, `Stopping`, `Finishing`, `Stopped`, `Succeeded`, `Failed`, `Error` |
| `includeTemplateApps` | Default false |
| `sortField` (`name`, `lastUpdated`, `status`, `views`, `lastViewed`), `sortOrder` (`asc`, `desc`) | |
| `limit`, `offset` | `limit` defaults to no limit |

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
`discoverable`, `mountDatasets`, `renderIFrame`, `sendNotifications`, `accessStatuses[]`
(`userId`, `status` `ALLOWED` / `DENIED` / `PENDING`).

`version` fields (none required by the schema): `hardwareTierId`, `environmentId`,
`environmentRevisionId`, `description`, `entryScript` (inline script that overrides the
entry point), `gitRef` (`{"type": "head" | "commitId" | "branches" | "tags" | "custom", "value": "..."}`),
`dfsCommitId`, `externalVolumeMountIds`, `netAppVolumeIds`, `dataPlaneId` (auto-filled from
the hardware tier; 422 if both are given and disagree), `vanityUrl`, `tags`
(`[{"key", "value"}]`).

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
POST  /api/apps/beta/apps/{appId}/versions                       body: the version object above
GET   /api/apps/beta/apps/{appId}/versions/{versionId}
PATCH /api/apps/beta/apps/{appId}/versions/{versionId}
```

The Public API has no route to start a version. Start (publish) the App from the UI or with
python-domino `app_publish(app_id=...)`, then poll the version until `Running`; stop it by
deleting its running instance (below) or with `app_unpublish(app_id=...)`. Both
python-domino methods call `/v4/modelProducts/{appId}/start` and `/stop` (non-public route;
may change in a future Domino version). A version record carries `currentInstance`
(`id`, `status`, `createdAt`, `dfsCommitId`, `gitCommitId`). Instance statuses include:
`Queued`, `Pending`, `Preparing`, `Running`, `Stopped`.

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

## Workflow: create, start, wait, read logs, stop

```python
import time
from domino import Domino

app = requests.post(f"{base_url}/api/apps/beta/apps", headers=headers, json={
    "name": "ml-dashboard", "projectId": project_id, "visibility": "GRANT_BASED",
    "version": {"hardwareTierId": "small-k8s", "environmentId": env_id},
}).json()
app_id, version_id = app["id"], app["currentVersion"]["id"]

domino = Domino(f"{owner}/{project_name}")             # client setup: SKILL.md#authentication
domino.app_publish(app_id=app_id, hardware_tier_id="small-k8s", environment_id=env_id,
                   unpublish_running_apps=False)

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

domino.app_unpublish(app_id=app_id)
```

## App requirements

Apps need an `app.sh` entry point that binds to `0.0.0.0:8888`; see
[domino-apps](../domino-apps/SKILL.md) for framework-specific scripts and proxy rules.
