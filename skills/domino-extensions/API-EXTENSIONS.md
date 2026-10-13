# Extensions REST surface

Routes under `/api/extensions/beta/` exist, with identical bodies, in both public API specs (`https://docs.domino.ai/api-specs/6.3/public-api.json`, `https://docs.domino.ai/api-specs/cloud/public-api.json`). Authentication and base URL follow the `domino-api-intro` skill: in a run `DOMINO_API_PROXY` with no header, or a bearer from `http://localhost:8899/access-token` on `DOMINO_API_HOST`; outside a run a Personal Access Token or service account bearer on the deployment's public URL. The docs describe Extension creation as an Admin task; on Domino Cloud a user who is not a SysAdmin but holds admin-panel system operations can create, patch and delete Extensions over this API, so expect a permission check rather than a SysAdmin-only gate, and read a 403 as missing permissions.

## Routes

| Route | Purpose |
|---|---|
| `GET /api/extensions/beta/extensions` | List. Filters: `mount_point_type`, `exclude_mount_points`, `project_id`, `enabled`, `mount_point_enabled`, `deleted`, `kind` (`DominoOfficial`, `Uncategorized`), `search_query`, `limit`, `offset`, `sort_by`, `order_by`. Response `{"meta": {"pagination": {...}}, "data": [...]}` |
| `POST /api/extensions/beta/extensions` | Create (body below) |
| `GET /api/extensions/beta/extensions/{extensionId}` | Read one |
| `PATCH /api/extensions/beta/extensions/{extensionId}` | Update any of `name`, `description`, `enabled`, `appVersionId`, `uiMountPointTypeConfigs` |
| `DELETE /api/extensions/beta/extensions/{extensionId}` | Soft-delete |
| `POST /api/extensions/beta/extensions/{extensionId}/views` | Record a view |
| `GET /api/extensions/beta/extensions-ui`, `GET .../extensions-ui/{extensionId}` | What the Domino UI renders at mount points |
| `GET /api/extensions/beta/official-install-menu` | Catalog of Domino Official Extensions and installable versions |
| `POST /api/extensions/beta/official-installs` | Start an official install (`InitiateOfficialExtensionInstallRequest`) |
| `GET /api/extensions/beta/official-installs/{id}` | Install status, steps and logs |
| `POST .../official-installs/{id}/retry`, `.../cancel`, `.../uninstall` | Retry a failed step, cancel, uninstall |
| `GET .../official-installs/{installId}/snapshots/{snapshotId}/liveDiff` | Drift between the installed configuration and the live entities |

## Create an Extension

`ExtensionCreationRequest` requires `name`, `enabled`, `appId`, `appVersionId` and `uiMountPointTypeConfigs`; `description` is optional and stored. **The App version must have extended identity propagation enabled**: with a version whose `content.extendedIdentityPropagationToAppsEnabled` is `false` the server answers `400 App version <id> does not have extended identity propagation enabled`. Create such a version with `POST /api/apps/v1/apps/{appId}/versions` and `{"content": {"environmentId": "...", "extendedIdentityPropagationToAppsEnabled": true}, "deployment": {"hardwareTierId": "..."}}`. Publishing an App with extended identity propagation requires a SysAdmin or CloudAdmin; do not set `extendedIdentityPropagationToAppsEnabled` unless the user confirms they hold that role, and otherwise ask an admin to publish the Extension App. Get `appId` from `GET /api/apps/v1/apps?projectId=...&name=...` and the version id from `currentVersion.id` (the most recently started version). The Cloud spec also returns `latestVersion.id` (most recently created version, started or not); the 6.3 spec does not, so on 6.3 list `GET /api/apps/v1/apps/{appId}/versions` (`items[]` newest first, with `id`, `versionNumber`, `createdAt`) and take the highest `versionNumber`.

```python
import os
import requests

if os.environ.get("DOMINO_API_PROXY"):
    base_url = os.environ["DOMINO_API_PROXY"].rstrip("/")
    headers = {}
else:
    base_url = os.environ["DOMINO_API_HOST"].rstrip("/")
    token = requests.get("http://localhost:8899/access-token").text.strip()
    headers = {"Authorization": f"Bearer {token}"}

body = {
    "name": "My Extension",
    "description": "What the Extension does",   # optional
    "enabled": True,
    "appId": "<appId>",
    "appVersionId": "<appVersionId>",
    "uiMountPointTypeConfigs": {
        "projectSidebar": {
            "enabled": True,
            "allProjects": True,   # or "mountPoints": [{"enabled": True, "projectId": "<projectId>"}]
            "urlConfig": {"contextualQueryParams": ["projectId"]},
        },
        "dataset": {
            "enabled": True,
            "urlConfig": {"contextualQueryParams": ["datasetId"]},
        },
    },
}
response = requests.post(f"{base_url}/api/extensions/beta/extensions", headers=headers, json=body, timeout=30)
response.raise_for_status()
extension = response.json()          # ExtensionResponse: id, name, enabled, appId, appVersionId, kind, ...
```

Mount config shapes (both specs): every config has `enabled` (required) and `urlConfig` (`contextualQueryParams`, optional `route`); `projectSidebar` adds `allProjects` and `mountPoints[{enabled, projectId}]`; `datasetFileContext` and `netAppVolumeFileContext` add `allProjects`, `mountPoints` and `fileTypes`; `dataset`, `modelDetails`, `adminPanel` and `netAppVolume` take only `enabled` and `urlConfig`. `contextualQueryParams` values come from the enum `projectId`, `datasetId`, `datasetSnapshotId`, `filePath`, `modelId`, `modelVersionId`, `netAppVolumeId`, `netAppVolumeSnapshotId`; the server stores and returns them capitalized (`ProjectId`), so compare case-insensitively when reading them back. `DELETE` is a soft delete: `GET` still returns the record with `deletedAt`, the default list omits it, and `?deleted=true` lists it.

## Handle the context in the App

The parameters an App receives are the ones its `urlConfig.contextualQueryParams` lists, drawn from the spec enum. Typical configurations: `projectSidebar` passes `projectId`; `dataset` passes `datasetId`; `datasetFileContext` passes `datasetId`, `datasetSnapshotId` and `filePath`; `modelDetails` passes `modelId` and `modelVersionId`; `adminPanel` passes none; the NetApp mounts pass `netAppVolumeId`, `netAppVolumeSnapshotId` and `filePath`. Note that the create-manage-extensions docs page calls the file parameter `datasetFilePath`, but the spec enum and Domino's own clinical-data-explorer read `filePath`; that extension also reads a `mountPointType` parameter to learn where it was opened from. Validate what you need and fail clearly, because a user can open the App URL without any parameters.

```python
# Flask App mounted on Datasets: read the context, call Domino as the viewer
import os
import flask
import requests

@app.route("/")
def index():
    dataset_id = flask.request.args.get("datasetId")
    if not dataset_id:
        return flask.Response("Missing required query parameter: datasetId", status=400)
    auth_header = flask.request.headers.get("Authorization", "")   # viewer token (extended identity propagation)
    url = f"{os.environ['DOMINO_API_HOST']}/api/datasetrw/v1/datasets/{dataset_id}"
    response = requests.get(url, headers={"Authorization": auth_header}, timeout=30)
    if not response.ok:
        return flask.Response(f"Failed to fetch dataset: {response.status_code}", status=response.status_code)
    dataset = response.json().get("dataset", {})
    return flask.render_template("dataset.html", dataset=dataset)
```

`GET /api/datasetrw/v1/datasets/{datasetId}` exists in both public specs; the same pattern works for any `/api/...` route the viewer is allowed to call.

## Move an Extension to a new App version

Publishing a new version of the App does not update the Extension.

```python
requests.patch(f"{base_url}/api/extensions/beta/extensions/{extension_id}",
               headers=headers, json={"appVersionId": "<newAppVersionId>"}, timeout=30).raise_for_status()
```

Disable without deleting with `{"enabled": false}`.

## Official installs

The Admin panel's **Manage Domino-official Extensions** tab drives these routes: read the catalog from `official-install-menu`, `POST official-installs` with the chosen Extension and version, poll `GET official-installs/{id}` for step status and logs, and use `retry`, `cancel` or `uninstall` as the UI does. The installer creates the Project, Compute Environment, App and Extension itself; do not create them by hand for an official Extension.

## Apps API pointers

The backing App is created, versioned, started and stopped through `/api/apps/v1` (create requires `name`, `projectId`, `visibility`; `content.extendedIdentityPropagationToAppsEnabled` is the identity flag an Extension needs). The chain, bodies and the beta-only instance log routes are in [domino-apps/API-APPS.md](../domino-apps/API-APPS.md).
