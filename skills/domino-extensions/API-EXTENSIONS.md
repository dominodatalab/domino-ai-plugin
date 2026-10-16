# Extensions REST surface

Routes under `/api/extensions/beta/`. Auth and base URL: [domino-api-intro](../domino-api-intro/SKILL.md#authentication). Create, patch and delete need admin-panel system-operations permission (not necessarily SysAdmin); a 403 means it is missing.

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
import requests
# base_url and headers: the Python setup block in domino-api-intro/SKILL.md#authentication

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

Mount config shapes: every config has `enabled` (required) and `urlConfig` (`contextualQueryParams`, optional `route`); `projectSidebar` adds `allProjects` and `mountPoints[{enabled, projectId}]`; `datasetFileContext` and `netAppVolumeFileContext` add `allProjects`, `mountPoints` and `fileTypes`; `dataset`, `modelDetails`, `adminPanel` and `netAppVolume` take only `enabled` and `urlConfig`. `contextualQueryParams` values come from the enum `projectId`, `datasetId`, `datasetSnapshotId`, `filePath`, `modelId`, `modelVersionId`, `netAppVolumeId`, `netAppVolumeSnapshotId`; the server stores and returns them capitalized (`ProjectId`), so compare case-insensitively when reading them back. `DELETE` is a soft delete: `GET` still returns the record with `deletedAt`, the default list omits it, and `?deleted=true` lists it.

## Handle the context in the App

The parameters an App receives are the ones its `urlConfig.contextualQueryParams` lists ([SKILL.md](./SKILL.md#mount-points-and-context)). Domino's own clinical-data-explorer reads `filePath` and a `mountPointType` parameter to learn where it was opened from. Validate what you need and fail clearly, because a user can open the App URL without any parameters.

```python
# Flask App mounted on Datasets: read the context, call Domino as the viewer
import base64
import json
import os

import flask
import requests

app = flask.Flask(__name__)
API_HOST = os.environ["DOMINO_API_HOST"]                 # API calls only, never browser links
PREFIX = os.environ.get("DOMINO_RUN_HOST_PATH", "/")     # current URL prefix, trailing slash


def viewer_token():
    header = flask.request.headers.get("Authorization", "")
    token = header[len("Bearer "):].strip() if header.startswith("Bearer ") else ""
    return token or None


def viewer_name(token):
    # Display only. Before granting access on a claim, verify the token (see below).
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return claims.get("preferred_username")


@app.route("/")
def index():
    dataset_id = flask.request.args.get("datasetId")
    if not dataset_id:
        return flask.Response("Missing required query parameter: datasetId", status=400)
    token = viewer_token()
    if token is None:   # never call without it: DOMINO_API_HOST would run the call as the publisher
        return flask.Response("No viewer token: open the App through Domino", status=401)
    response = requests.get(f"{API_HOST}/api/datasetrw/v1/datasets/{dataset_id}",
                            headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if not response.ok:
        return flask.Response(f"Failed to fetch dataset: {response.status_code}", status=response.status_code)
    dataset = response.json().get("dataset", {})
    return flask.render_template("dataset.html", dataset=dataset, viewer=viewer_name(token), base=PREFIX)
```

`dataset.html` starts its `<head>` with `<base href="{{ base }}">` and uses only relative URLs (`static/app.css`, `fetch("api/files")`).

The same pattern works for any `/api/...` route the viewer is allowed to call.

## Identity, URLs and scripts

An Extension App always runs with extended identity propagation, so:

- **Token.** `Authorization: Bearer` carries the viewer's own credential (the browser session token, or the Personal Access Token a script sent) with the viewer's full permissions. Never log it, return it, store it, or reuse it for another request or viewer; keep the App stateless.
- **Viewer.** Read `preferred_username` from the token (`sub` is the Domino user id). Domino does not send `domino-username` to these Apps, and a client can send its own. To trust a claim without calling Domino, verify the RS256 signature against the Domino realm's JWKS (`<issuer>/protocol/openid-connect/certs`) and pin the issuer `https://<domino-domain>/auth/realms/DominoRealm`; do not require audience `apps`, which the viewer's credential does not carry.
- **Calls.** `$DOMINO_API_HOST` can be an API gateway in the App's pod. It accepts browser-session, service-account and Personal Access Token credentials, rejects Domino CLI login tokens (403), and runs a request without `Authorization` as the publisher. Forward the viewer's token on every viewer call and answer 401 when it is missing.
- **URLs.** Domino opens the App at its URL prefix with the context in the query string. `<prefix>` and `<prefix>/` both reach the App as `/`, so a page opened without the slash resolves relative URLs one level up. Emit `<base href>` from `DOMINO_RUN_HOST_PATH` (the current prefix, with a trailing slash; it differs between App Preview and the published App) in every server-rendered page, which also covers a `urlConfig.route` below the root. A single-page frontend can add the slash in the browser instead, keeping `location.search`, which carries the context: `if (!location.pathname.endsWith('/')) location.replace(location.pathname + '/' + location.search + location.hash)`. Domino never sends `X-Script-Name`.
- **Scripts.** Send a Personal Access Token as the bearer. The script's user must have consented once in a browser: until then every request, JSON included, gets a 302 to `/app-consent?appId=<id>&callback=<url>`, and a request without credentials gets a 302 to the sign-in page. In the App's own pages, treat a redirected or `text/html` response to `fetch` as expired consent and reload the page.
- **Shared origin.** Every App on the deployment shares one origin, so another App's scripts can read `localStorage` and unscoped cookies. Keep viewer data out of `localStorage`; give cookies App-specific names and `Path` set to the prefix.
- **400 on the App URL.** Some deployments allow Apps only inside Domino's page; there, opening the App URL directly answers 400. If an Extension's tab shows 400 when opened on its own, open it from Domino instead.

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
