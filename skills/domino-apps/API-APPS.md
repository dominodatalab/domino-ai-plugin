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

The Apps API on Domino 6.1 is `/api/apps/beta`. It has no draft, publish or start routes. Request and response bodies are in your deployment's API reference at `https://<domino-domain>/docs`; check them there before sending a create or version body. If a route returns 404, confirm it in the same reference.

| Use | Route |
|---|---|
| List Apps | `GET /api/apps/beta/apps` (filters `projectId`, `name`, `ownerId`, `status`, `publisherId`; `limit`, `offset`, `sortField`, `sortOrder`) |
| Create an App | `POST /api/apps/beta/apps` |
| Read, update, delete an App | `GET`, `PATCH`, `DELETE /api/apps/beta/apps/{appId}` |
| Versions | `GET`, `POST /api/apps/beta/apps/{appId}/versions`; `GET`, `PATCH .../versions/{versionId}` |
| Instances of a version | `GET /api/apps/beta/apps/{appId}/versions/{versionId}/instances`; `GET .../instances/{instanceId}` |
| Stop a running instance | `DELETE /api/apps/beta/apps/{appId}/versions/{versionId}/instances/{instanceId}` |
| Logs | `GET .../instances/{instanceId}/logs`, `GET .../instances/{instanceId}/realTimeLogs` |
| Views | `GET /api/apps/beta/apps/{appId}/views` |
| Other | thumbnail (`/apps/{appId}/thumbnail`), access requests (`/apps/{appId}/access/requests`), vanity URL lookup (`/apps/vanityUrls/{vanityUrl}`) |

- `name` is a substring match, so compare `items[].name` exactly. List responses are `{"items": [...], "metadata": {...}}`.
- `visibility` values: `AUTHENTICATED` ("Anyone in Domino"), `GRANT_BASED` ("Restricted": listed users plus project collaborators), `GRANT_BASED_STRICT`, `PUBLIC` (anonymous viewers; also needs the admin setting on the app-configuration-settings page).
- IDs: `GET /api/environments/beta/environments` and `GET /api/hardwaretiers/v1/hardwaretiers` (both paginated with `limit`/`offset`).
- The App runs the project's **committed** files, so sync first: in a DFS Workspace **File Changes > Sync to Domino** (or the bundled MCP server's upload tool); in a Git-based project commit and push. A missing entry point fails the start with `entry script 'app.sh' not found in the root directory of your project`.
- A version's `description` is what the App page shows as Version Notes. For an App that starts a prebuilt build, put the build label there ([FRAMEWORKS.md](./FRAMEWORKS.md#build-once-and-version-builds)).

## Start and stop

- **Start**: publish from the UI (**Deployments > Apps > Publish Domino App**, or the App's page), or call python-domino `app_publish`. It wraps the Domino Internal API (`POST /v4/modelProducts/{appId}/start`; non-public route; may change in a future Domino version) and by default stops a running App first:

```python
from domino import Domino

d = Domino("<owner>/<project>")   # in a run it reads the run's credentials; outside: auth_token= or api_key=, host=
d.app_publish(app_id="<appId>", hardware_tier_id="<tierId>", environment_id="<environmentId>",
              commit_id="<git commit sha>")   # or branch="main"; omit both for the default
print(d.app_get_status("<appId>"))   # Running, Stopped, Failed, ...
```

  Without `app_id`, `app_publish` uses the project's first App and creates one when the project has none. `app_unpublish(app_id=...)` stops it.
- **Stop over the public API**: list the instances of the running version and `DELETE` the running one:

```bash
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances"
curl -s -X DELETE "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances/$INSTANCE_ID"
```

- **Status**: `GET /api/apps/beta/apps/{appId}/versions/{versionId}` and read `currentInstance.status` (`Running` is the serving state; `Succeeded` means the entry point exited; `Failed` and `Error` mean the start failed), or `app_get_status`.
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
| 404 | The route or the ID does not exist on this deployment; confirm the route in `https://<domino-domain>/docs` |
| 422 on create or `versions` | A required field is missing or an environment or hardware tier ID is unknown; compare the body with the schema in `/docs` |

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/apps/publish
