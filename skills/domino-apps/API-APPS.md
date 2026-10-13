# Apps REST API (automation)

Management routes for Domino Apps, verified against the 6.3 and Cloud public API specs (`https://docs.domino.ai/api-specs/6.3/public-api.json`, `https://docs.domino.ai/api-specs/cloud/public-api.json`). Runtime configuration (`app.sh`, ports, prefixes) is in [SKILL.md](./SKILL.md).

## Base URL and authentication

| Context | Base | Authorization |
|---|---|---|
| In a run, `DOMINO_API_PROXY` set | `$DOMINO_API_PROXY` | none; the proxy adds the token |
| In a run, no proxy | `$DOMINO_API_HOST` | `Bearer` from `GET http://localhost:8899/access-token` |
| Outside Domino (laptop, CI) | the deployment's public URL | `Bearer` Personal Access Token (you) or service account token (automation) |

Legacy API keys are deprecated; never send `X-Domino-Api-Key`. Details: https://docs.domino.ai/cloud/reference/api/domino-api-authentication and the `domino-api-intro` skill.

Smoke test before a longer workflow:

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
curl -s -H "Authorization: Bearer $TOKEN" "$DOMINO_API_HOST/api/apps/v1/apps?limit=1"
```

## v1 vs beta

| Use | Prefix | Routes |
|---|---|---|
| Writes and lifecycle | `/api/apps/v1` | `GET/POST /apps`, `POST /apps/drafts`, `GET/PATCH/DELETE /apps/{appId}`, `POST /apps/{appId}/publish`, `GET/POST /apps/{appId}/versions`, `POST .../versions/createAndStart`, `GET/PATCH .../versions/{versionId}`, `POST .../versions/{versionId}/start`, `.../stop`, `.../liveSync` |
| Instance reads only | `/api/apps/beta` | `GET /apps/{appId}/versions/{versionId}/instances`, `GET .../instances/{instanceId}/logs`, `GET .../realTimeLogs`, `POST .../instances/{instanceId}/views`, `DELETE .../instances/{instanceId}` |

Beta remains the only surface for instance reads, thumbnails (`/apps/{appId}/thumbnail`), access requests (`/apps/{appId}/access/requests`), vanity URL lookup (`/apps/vanityUrls/{vanityUrl}`), the project and publisher filter options, and (Cloud only) `GET`/`PUT /apps/{appId}/roles`. On 6.3, where that roles route does not exist, the same sharing controls are on the Domino Internal API (`/v4`, may change between Domino versions): `POST /v4/modelProducts/{appId}/visibility` with `{"visibility": "AUTHENTICATED"}` (or `GRANT_BASED`, `GRANT_BASED_STRICT`, `PUBLIC`), `POST .../grantAccess` and `POST .../denyAccess` with `{"userId": "..."}`, `POST .../invite` with `{"emails": [...]}` and `POST .../uninvite` with `{"email": "..."}`; each answers 200 with the App id, and the result shows in `GET /api/apps/v1/apps/{appId}` under `accessControl`. Verified on Cloud 6.4 only, by the App's owner; `python-domino` wraps the same family, so it is long-lived, but it is not part of the Public API. For create, versions, start and stop use v1; the beta write routes still work but gain nothing. The `python-domino` SDK's `app_publish`, `app_unpublish` and `app_get_status` wrap the Domino Internal API (`/v4/modelProducts/{appId}/start`, `.../stop`, `GET /v4/modelProducts/{appId}`, which may change between Domino versions); prefer the v1 routes below.

## Publish chain (App created directly, no workspace)

1. **Create the App with its first version**: `POST /api/apps/v1/apps`. Required: `name`, `projectId`, `visibility`. A version is always created; nothing is started.

```json
{
  "projectId": "<projectId>",
  "name": "sales-dashboard",
  "description": "Sales dashboard",
  "entryPoint": "app.sh",
  "visibility": "AUTHENTICATED",
  "discoverable": true,
  "initialVersion": {
    "content": {
      "environmentId": "<environmentId>",
      "gitRef": { "type": "branches", "value": "main" }
    },
    "deployment": { "hardwareTierId": "small-k8s" }
  }
}
```

   - `visibility` enum: `AUTHENTICATED`, `GRANT_BASED`, `GRANT_BASED_STRICT`, `PUBLIC`. The spec carries no descriptions; the docs name two sharing modes, "Anyone in Domino" (any Domino account) and "Restricted" (listed users plus project collaborators), which the live records show as `AUTHENTICATED` and `GRANT_BASED`. `GRANT_BASED_STRICT` is undocumented; `PUBLIC` (anonymous viewers) also needs the admin setting described on the app-configuration-settings page. `discoverable` is the "Make globally discoverable" switch.
   - `gitRef.type`: `head`, `commitId`, `branches`, `tags`, `custom`. DFS projects use `content.dfsCommitId` instead (the field sits inside `content` on `initialVersion`, `versions` and `createAndStart` in both specs). Either way the App runs the project's **committed** files, so sync first: in a DFS Workspace **File Changes > Sync to Domino** (or the bundled MCP server's upload tool); in a Git-based project commit and push. **Right after syncing or uploading, pin `dfsCommitId`; do not leave it out to take the head**, because the head the Apps service resolves can lag the upload by a few seconds and the version then runs the previous commit without your file. Use the `commitId` the upload tool returned (the newest, if several), or read `GET /api/projects/beta/projects/{projectId}/commits/latest` (`{"commitId": ...}`) and confirm `GET /api/projects/v1/projects/{projectId}/files/{commitId}/app.sh/content` returns 200 before passing it. `entryPoint` is a path relative to the project root; a missing file fails the start with `entry script 'app.sh' not found in the root directory of your project`.
   - `content` also accepts `environmentRevisionId`, `dataPlaneId` (must match the hardware tier's data plane or the call returns 422), `externalVolumeMountIds`, `netAppVolumeIds`, `mountDatasets`, `extendedIdentityPropagationToAppsEnabled`. `deployment` also accepts `autoscalingSpecification`, `vanityUrl`, `renderIFrame`.
   - IDs: `GET /api/environments/beta/environments` and `GET /api/hardwaretiers/v1/hardwaretiers` (both paginated with `limit`/`offset`).
   - The response (`AppResponseV1`) carries `id`, `url` and `currentVersion` (the most recently started version; right after creation it is the new version), so `currentVersion.id` is the version to start. The Cloud spec also returns `latestVersion` (most recently created version, started or not); the 6.3 spec does not, so code that must find the newest version on both targets lists `GET /api/apps/v1/apps/{appId}/versions` (`items[]` newest first, each with `id`, `versionNumber`, `createdAt`) and takes the highest `versionNumber`. Verified on Cloud 6.4.0: `environmentRevisionId` and the commit may be omitted (the server resolves the environment's selected revision and the DFS head), and a DFS App's `url` looks like `https://apps.<domain>/u/<owner>/<project>/app/?appId=<id>` until a vanity URL is set.

2. **Start it**: `POST /api/apps/v1/apps/{appId}/versions/{versionId}/start` with the JSON body `{}` (`Content-Type: application/json`), or `{"deployment": {"hardwareTierId": "..."}}` to override the tier or autoscaling for this launch. The v1 route returns `415 Expecting text/json or application/json body` when the body is empty, so always send `{}`; only the beta `start` route accepts no body. Starting a version while another version of the same App runs stops the running one (verified live), so this is also the rollback call.
3. **Ship a new build later**: `POST /api/apps/v1/apps/{appId}/versions/createAndStart` with the same `content` and `deployment` shape creates a version and starts it, stopping the running version first. The response has `version` and `instance`; a `warnings` array appears only when the version was saved but the start failed, in which case retry with the `start` route.
4. **Stop**: `POST /api/apps/v1/apps/{appId}/versions/{versionId}/stop` (no body; empty 200 response). `DELETE /api/apps/v1/apps/{appId}` removes a stopped App (empty 200, then `GET` returns 404).
5. **Find the App again**: `GET /api/apps/v1/apps?projectId=<id>&name=<name>`. `name` is a substring match, so compare `items[].name` exactly. Other filters: `ownerId`, `status`, `publisherId`, `tagIds`, `entryPoint`, `draftsOnly`, `includeTemplateApps`; sort with `sortField` (`name`, `lastUpdated`, `status`, `views`, `lastViewed`) and `sortOrder`.

Deploy status: `GET /api/apps/v1/apps/{appId}/versions/{versionId}` and read `currentInstance.status` (spec values include `Queued`, `Pending`, `Preparing`, `Building`, `Pulling`, `Running`, `Stopping`, `Stopped`, `Succeeded`, `Failed`, `Error`; a live start went `Queued`, `Pending`, `Preparing`, `Running` in about 25 seconds; `Running` is the serving state, `Succeeded` means the entry point exited). `GET /api/apps/v1/apps/{appId}` gives the viewer `url`.

## Draft Apps (workspace flow)

Drafts, App Preview and versioning depend on the `EnableAppsSDLC` feature flag (on by default; an admin who disables it gets the legacy one-step Publish flow). `POST /api/apps/v1/apps/drafts` (`workspaceId` required) creates or returns the Draft App bound to a workspace; App Preview instances run from it. `POST /api/apps/v1/apps/{draftAppId}/publish` promotes the draft's last-run version: omit `targetAppId` to publish as a new App (`appOverrides` sets name, visibility, vanity URL and so on), or set `targetAppId` to add a version to an existing App (entry point and configuration type must match or the call returns 422). `start: true` deploys in the same call; `startOverrides.deployment` carries hardware tier, autoscaling, vanity URL and iframe overrides. `publish` applies to drafts only; Apps created with step 1 get new versions through `versions` or `createAndStart`.

## Logs

Instance logs are beta-only:

```bash
# instances of a version (newest first is not guaranteed; read createdAt)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$DOMINO_API_HOST/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances"
# logs for one instance; logType: complete (default) | prepareoutput | stdout | stderr
curl -s -H "Authorization: Bearer $TOKEN" \
  "$DOMINO_API_HOST/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances/$INSTANCE_ID/logs?logType=stdout&limit=200"
```

The response is `{"logContent": [{"timestamp", "logType", "log", "size"}], "isComplete", "pagination"}`; `realTimeLogs` streams the same data. The App details page shows the same logs with an instance selector and offers a support bundle download.

## Management URL vs App URL

Management calls go to the platform API base above. Viewers open the `url` field of the App record (an `apps` hostname or a `/apps/<vanity>/` path, depending on the deployment). Do not call `/api/apps/...` on the App's own hostname, and do not build the viewer URL by hand.

## When a call fails

| Response | Likely cause |
|---|---|
| 401 | Missing or expired token, or an in-run call that bypassed the proxy and sent no bearer |
| 403 | No edit permission on the project |
| 415 on v1 `start` | Empty request body; send `{}` as JSON |
| 422 on create or `versions` | `visibility`, `name` or `projectId` missing; `hardwareTierId or dataPlaneId is required` when `deployment.hardwareTierId` is omitted and the App has no started version to inherit from (verified live); unknown environment or hardware tier; `dataPlaneId` not matching the tier |
| 422 on publish or start | Entry point or configuration type differs from `targetAppId`; `vanityUrl` or `renderIFrame` override on a draft start |
| Deploy blocked | A governance policy gates **Deploy** until approvals are complete; see the `domino-governance` skill |

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/apps/publish-and-deploy-app-versions (same content under `/6.3/`).
