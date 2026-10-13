# Domino Apps API (beta catalog)

Catalog of the `/api/apps/beta/apps` routes, present in both published specs. For
the v1 publish chain (`/api/apps/v1/apps`, drafts, `createAndStart`, `liveSync`) and the
app lifecycle, use [domino-apps/API-APPS.md](../domino-apps/API-APPS.md); prefer v1 routes
for new automation. Product docs:
https://docs.domino.ai/cloud/platform-capabilities/features/apps.

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
| `tagIds` | Taxonomy tag ids, comma-separated, AND semantics |
| `includeTemplateApps` | Default false |
| `sortField` (`name`, `lastUpdated`, `status`, `views`, `lastViewed`; `published` on **Cloud** only), `sortOrder` (`asc`, `desc`) | |
| `limit`, `offset` | `limit` defaults to no limit |
| `configurationType` (`STANDARD`, `AISYSTEM`), `accessStatus` (`granted`, `pending`, `noAccess`), `prioritizePinned` | **Cloud** only |

Response: `{"items": [...], "metadata": {...}}`. Each item has `id`, `name`, `description`,
`project` (`id`, `name`, `ownerUsername`, `projectType`), `publisher`, `entryPoint`, `url`,
`visibility`, `discoverable`, `mountDatasets`, `renderIFrame`, `isPinned`, `views`,
`currentVersion` (`id`, `hardwareTierId`, `environmentId`, `resolvedCommits`,
`currentInstance`, ...), `taxonomyTags`; `iconId` and `latestVersion` on **Cloud**.

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
`discoverable`, `mountDatasets`, `renderIFrame`, `sendNotifications`, `configurationType`
(`STANDARD` default, `AISYSTEM`), `accessStatuses[]` (`userId`, `status` `ALLOWED` /
`DENIED` / `PENDING`); `iconId` (Font Awesome identifier) on **Cloud**.

`version` fields (none required by the schema): `hardwareTierId`, `environmentId`,
`environmentRevisionId`, `description`, `entryScript` (inline script that overrides the
entry point), `gitRef` (`{"type": "head" | "commitId" | "branches" | "tags" | "custom", "value": "..."}`),
`dfsCommitId`, `externalVolumeMountIds`, `netAppVolumeIds`, `dataPlaneId` (auto-filled from
the hardware tier; 422 if both are given and disagree), `autoscalingSpecification`
(`enabled` required; `minReplicas`, `maxReplicas` 1 to 30, CPU/memory targets,
stabilization windows, `useSessionAffinity`), `bundleId` (governance; immutable),
`extendedIdentityPropagationToAppsEnabled`, `vanityUrl`, `tags` (`[{"key", "value"}]`).

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
POST  /api/apps/beta/apps/{appId}/versions/{versionId}/start
POST  /api/apps/beta/apps/{appId}/versions/{versionId}/stop
```

Use `start` and `stop` on a version to run or halt the app; the beta routes accept an
empty request (start with no body returns 200 and the instance is `Running` about 35 s
later). A version record carries `currentInstance`
(`id`, `status`, `createdAt`, `dfsCommitId`, `gitCommitId`). Instance statuses include:
`Queued`, `Pending`, `Preparing`, `Running`, `Stopped`.

## Instances and logs

```
GET    /api/apps/beta/apps/{appId}/versions/{versionId}/instances
GET    /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}
DELETE /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}
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

## Thumbnail, views, vanity URLs, filters, access

```
GET, POST, DELETE /api/apps/beta/apps/{appId}/thumbnail;  GET .../thumbnail/metadata
GET /api/apps/beta/apps/{appId}/views?startTimestamp=&endTimestamp=&granularity=     (epoch ms; granularity default 86400000)
GET /api/apps/beta/apps/vanityUrls/{vanityUrl}
GET /api/apps/beta/apps/projectFilterOptions;  GET /api/apps/beta/apps/publisherFilterOptions
POST /api/apps/beta/apps/{appId}/access/requests
GET, PUT /api/apps/beta/apps/{appId}/roles        (Cloud only; 6.3 alternative below)
```

Domino 6.3 has no Public roles route. The Domino Internal API manages App access on
both targets: `POST /v4/modelProducts/{appId}/visibility` with
`{"visibility": "PUBLIC" | "AUTHENTICATED" | "GRANT_BASED" | "GRANT_BASED_STRICT"}`,
`POST .../grantAccess` and `POST .../denyAccess` with `{"userId": "<user-id>"}`, plus
`.../invite` (several users at once) and `.../uninvite`. non-public route; may change in a future Domino version; taken from the Cloud/6.4 internal reference (python-domino's `app_*`
methods use the same `/v4/modelProducts` family); confirm the routes
in your deployment's `/docs` first.

## Workflow: create, start, wait, read logs, stop

```python
import time

app = requests.post(f"{base_url}/api/apps/beta/apps", headers=headers, json={
    "name": "ml-dashboard", "projectId": project_id, "visibility": "GRANT_BASED",
    "version": {"hardwareTierId": "small-k8s", "environmentId": env_id},
}).json()
app_id, version_id = app["id"], app["currentVersion"]["id"]

requests.post(f"{base_url}/api/apps/beta/apps/{app_id}/versions/{version_id}/start", headers=headers)

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

requests.post(f"{base_url}/api/apps/beta/apps/{app_id}/versions/{version_id}/stop", headers=headers)
```

## App requirements

Apps need an `app.sh` entry point that binds to `0.0.0.0:8888`; see
[domino-apps](../domino-apps/SKILL.md) for framework-specific scripts and proxy rules.
