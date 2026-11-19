# Apps REST API (automation)

Management routes for Domino Apps on Domino 6.1. Runtime configuration (`app.sh`, ports, prefixes) is in [SKILL.md](./SKILL.md).

## Base URL and authentication

Base URL and auth: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

Connectivity check:

```bash
# in a Domino run: the proxy adds the credential
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps?limit=1"
# outside a run: DOMINO_API_HOST is the deployment URL; DOMINO_TOKEN a service account token
curl -s -H "Authorization: Bearer $DOMINO_TOKEN" "$DOMINO_API_HOST/api/apps/beta/apps?limit=1"
# or a user API key
curl -s -H "X-Domino-Api-Key: $DOMINO_USER_API_KEY" "$DOMINO_API_HOST/api/apps/beta/apps?limit=1"
```

The examples below use the in-run form; outside a run add the credential header and use the deployment URL.

## Routes

The Apps API on Domino 6.1 is `/api/apps/beta`. It has no draft or publish routes and no start route on a version: creating a version starts it. Request and response bodies are in the [6.1 Platform API reference](https://docs.dominodatalab.com/en/6.1/api_guide/8c929e/domino-platform-api-reference/) (Apps, AppVersions, AppInstances).

| Use | Route |
|---|---|
| List Apps | `GET /api/apps/beta/apps` (`projectId`, `name`, `includeTemplateApps`, `sortField`, `sortOrder`, `limit`, `offset`; no status or owner filter, so read `currentVersion.currentInstance.status` from each item) |
| Create an App | `POST /api/apps/beta/apps`; this **also starts the App** on its first version, so poll `currentVersion.id` from the response instead of creating a version |
| Read, update, delete an App | `GET`, `PATCH`, `DELETE /api/apps/beta/apps/{appId}` |
| Versions | `GET /api/apps/beta/apps/{appId}/versions`; `POST` the same path **creates a version and starts the App on it** (see [Start and stop](#start-and-stop)); `GET`, `PATCH .../versions/{versionId}` (`PATCH` takes only `vanityUrl`) |
| Instances of a version | `GET /api/apps/beta/apps/{appId}/versions/{versionId}/instances`; `GET .../instances/{instanceId}` |
| Stop a running instance | `DELETE /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}` |
| Logs | `GET .../instances/{instanceId}/logs`, `GET .../instances/{instanceId}/realTimeLogs` |
| Views | `GET /api/apps/beta/apps/{appId}/views` |
| Other | access requests (`/apps/{appId}/access/requests`), vanity URL lookup (`/apps/vanityUrls/{vanityUrl}`) |

- `name` is a substring match, so compare `items[].name` exactly. List responses are `{"items": [...], "metadata": {...}}`.
- `visibility` values: `AUTHENTICATED` ("Anyone in Domino"), `GRANT_BASED` ("Restricted": listed users plus project collaborators), `GRANT_BASED_STRICT`, `PUBLIC` (anonymous viewers; also needs the admin setting on the app-configuration-settings page).
- IDs: `GET /api/environments/beta/environments` and `GET /api/hardwaretiers/v1/hardwaretiers` (both paginated with `limit`/`offset`).
- The App runs the project's **committed** files, so sync first: in a DFS Workspace **File Changes > Sync to Domino** (or the bundled MCP server's upload tool); in a Git-based project commit and push. A missing entry point fails the start with `entry script 'app.sh' not found in the root directory of your project`.
- A version has no description or notes field on Domino 6.1; record a build label in the App log and `/healthz` ([FRAMEWORKS.md](./FRAMEWORKS.md#build-once-and-version-builds)).

## Start and stop

- **Start**: creating the App (`POST /api/apps/beta/apps`, or **Deployments > Apps > Publish Domino App**) starts it on its first version; poll `currentVersion.id` from the response. In a DFS Project the create body's `version.dfsCommitId` picks the commit.
- **Restart an existing App**: the App's page in the UI, or `POST /api/apps/beta/apps/{appId}/versions`. That call creates a version and starts an instance of it, so never create a version only to record one. Body fields (all optional): `hardwareTierId`, `environmentId`, `environmentRevisionId`, `gitRef` (`{"type": "head" | "commitId" | "branches" | "tags" | "custom", "value": "..."}`), `netAppVolumeIds`, `externalVolumeMountIds`. Set a vanity URL with `PATCH .../versions/{versionId}`, not here. In a Git-based Project, `gitRef` picks the code. In a DFS Project the version runs the Project's latest commit, and `dfsCommitId` is ignored, so sync before you call it. Stop the running instance first (below) so two do not serve at once:

```bash
# in a run; outside, add the credential header and use the deployment URL
curl -s -X POST "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions" \
  -H "Content-Type: application/json" \
  -d "{\"hardwareTierId\": \"$TIER_ID\", \"environmentId\": \"$ENV_ID\", \"gitRef\": {\"type\": \"commitId\", \"value\": \"$GIT_SHA\"}}"
# the response is the new version: read its id, then poll it for currentInstance.status
```

- **Stop**: list the instances of the running version and `DELETE` the running one:

```bash
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances"
curl -s -X DELETE "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances/$INSTANCE_ID"
```

- **Status**: `GET /api/apps/beta/apps/{appId}/versions/{versionId}` and read `currentInstance.status` (`Running` is the serving state; `Succeeded` means the entry point exited; `Failed` and `Error` mean the start failed).
- python-domino's `app_publish` calls the Domino Internal API (non-public route; may change in a future Domino version), and its arguments differ between releases (the `dominodatalab` 1.4.4 in the Domino 6.1 image takes no App or commit). Use the versions route above instead.
- Rolling back to an earlier version is not available on Domino 6.1: revert the code and publish again.

## Logs

```bash
# instances of a version (newest first is not guaranteed; read createdAt)
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances"
# logs for one instance; logType: complete (default) | prepareoutput | stdout | stderr
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances/$INSTANCE_ID/logs?logType=stdout&limit=200"
```

The response is `{"logContent": [{"timestamp", "logType", "log", "size"}], "isComplete", "pagination"}`; `realTimeLogs` streams the same data. `APP_ID` comes from `GET /api/apps/beta/apps?projectId=<id>&name=<name>` (`items[].id`) and `VERSION_ID` from `GET /api/apps/beta/apps/{appId}` (`currentVersion.id`). The App details page shows the same logs.

## Management URL vs App URL

Management calls go to the platform API base above. Viewers open the `url` field of the App record (an `apps` hostname or a `/apps/<vanity>/` path, depending on the deployment). Do not call `/api/apps/...` on the App's own hostname, and do not build the viewer URL by hand, least of all from `DOMINO_API_HOST` or `DOMINO_USER_HOST` (in-cluster addresses). A request to the App without browser credentials gets a 302 to sign-in.

## When a call fails

| Response | Likely cause |
|---|---|
| 401 | Missing or expired credential. In a run, call `$DOMINO_API_PROXY` with no header instead of sending your own |
| 403 | No edit permission on the project |
| 404 | The route or the ID does not exist on this deployment; check the route in the 6.1 Platform API reference |
| 422 on create or `versions` | A required field is missing or an environment or hardware tier ID is unknown; compare the body with `AppCreationRequest` or `AppVersionCreationRequest` in the 6.1 Platform API reference |

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/apps/publish
