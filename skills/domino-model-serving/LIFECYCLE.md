# Model serving lifecycle: worked requests

Request and response shapes: spec schemas `ModelApiCreationRequest`, `ModelApiVersionCreationRequest`, `ModelApiUpdateRequest`, `ModelApi`, `NewRegisteredModelV2` ([API-SPECS.md](../domino-api-intro/API-SPECS.md)). Routes that exist only on Domino Cloud are marked.

## Setup

```python
import os
import time
import requests

# base and headers: the Python setup block in domino-api-intro/SKILL.md#authentication
base, headers = os.environ["DOMINO_API_PROXY"], {}        # in a run with the proxy
```

## List and inspect

```python
r = requests.get(f"{base}/api/modelServing/v1/modelApis", headers=headers,
                 params={"projectId": os.environ["DOMINO_PROJECT_ID"], "limit": 25, "offset": 0})
r.raise_for_status()
for api in r.json()["items"]:
    active = api.get("activeVersion", {})
    print(api["id"], api["name"], api["replicas"], api["routingMode"], api["isAsync"],
          active.get("number"), active.get("deployment", {}).get("status"))
total = r.json()["metadata"]["totalCount"]
```

Filters: `projectId`, `environmentId`, `name` (regular expression), `registeredModelName` (+ `registeredModelVersion`), `limit` (default 25), `offset`, `orderBy`. Archived endpoints carry `isArchived: true`.

`GET /api/modelServing/v1/modelApis/{modelApiId}` returns the same object: `id`, `name`, `description`, `environmentId`, `hardwareTierId`, `replicas`, `routingMode` (`Basic` or advanced), `isAsync`, `strictNodeAntiAffinity`, `access{isPublic, accessTokens[]}`, `healthCheck{...}`, `overrideRequestTimeoutSecs`, `collaborators[]`, `volumes[]`, `activeVersion{id, number, dataPlaneId, deployment{status, isPending}}`, `metadata{created, createdBy, lastModified}`. On Domino Cloud `access.isPublic` is a legacy flag independent of the endpoint's visibility (`Public`, `Discoverable`, `Private`), which is read and set through `GET|PUT /api/modelServing/beta/modelApis/{modelApiId}/visibility`; collaborators there carry the roles `Owner`, `Editor`, `Operator`, `Viewer`.

Versions: `GET .../modelApis/{modelApiId}/versions` lists `ModelApiVersion` objects (`id`, `number`, `projectId`, `source`, `commitId`, `environmentRevisionId`, `predictionDatasetResourceId`, `logHttpRequestResponse`, `monitoringEnabled`, `recordInvocation`, `labels`, `metadata`).

## Create from project files

The version is built from the `version.commitId` you pass, or the Project's head commit if you omit it, never from a Workspace's disk. In a DFS Project sync the Workspace first (**File Changes** > **Sync to Domino**); in a Git-based Project commit and push the code and sync the artifacts. Include the model artifacts the function loads. Then pin the commit: the head lags an upload by a few seconds, and a version built from the stale head crash-loops with `FileNotFoundError` (see `domino-model-endpoints`, "Sync or commit first"). Use the `commitId` the MCP upload tool returned, or read `GET /api/projects/beta/projects/{projectId}/commits/latest` (`commitId`) and confirm `GET /api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content` is 200 for each model file.

```python
commit_id = requests.get(f"{base}/api/projects/beta/projects/{os.environ['DOMINO_PROJECT_ID']}/commits/latest",
                         headers=headers).json()["commitId"]
for path in ("model.py", "random_forest.joblib"):
    ok = requests.get(f"{base}/api/projects/v1/projects/{os.environ['DOMINO_PROJECT_ID']}/files/{commit_id}/{path}/content",
                      headers=headers).status_code == 200
    assert ok, f"{path} is not in commit {commit_id}; wait a few seconds and re-read commits/latest"
```

```python
body = {
    "name": "churn-scorer",
    "description": "GBM churn model",
    "environmentId": ENVIRONMENT_ID,              # GET /api/environments/beta/environments
    "hardwareTierId": TIER_ID,                    # optional; an endpoint tier, GET /api/hardwaretiers/v1/hardwaretiers
    "replicas": 2,                                # optional
    "isAsync": False,
    "strictNodeAntiAffinity": False,
    "environmentVariables": [{"key": "MODEL_PATH", "value": "models/gbm.pkl"}],
    "version": {
        "projectId": os.environ["DOMINO_PROJECT_ID"],
        "commitId": commit_id,                    # the commit you synced; omitting it takes the head, which can be stale
        "source": {"type": "File", "file": "model.py", "function": "predict", "excludeFiles": ["data/"]},
        "logHttpRequestResponse": False,
        "monitoringEnabled": False,
        # optional: "environmentId": "...", "shouldDeploy": True
    },
}
r = requests.post(f"{base}/api/modelServing/v1/modelApis", headers=headers, json=body)
r.raise_for_status()                              # spec says 201, Cloud returns 200; accept any 2xx
model_api_id = r.json()["id"]
versions = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions", headers=headers).json()
version_id = max(versions, key=lambda v: v["number"])["id"]
wait_version_running(model_api_id, version_id)
```

Pass `hardwareTierId` explicitly ([SCALING.md](../domino-model-endpoints/SCALING.md)). The create response never carries the auto-created access token; read it under **Settings** > **Invocation**.

## Create from a registered model

Same body with `"source": {"type": "Registry", "registeredModelName": "churn-gbm", "registeredModelVersion": 3}`. The `requirements.txt` MLflow inferred when the model was logged is installed into the image.

## Wait until a version is Running

Poll the **version**, not only the Model API: under Basic routing the previous version keeps serving (and stays `activeVersion`) until the new one is up, so `activeVersion.deployment.status` can read `Running` for the old version right after you create a new one.

```python
def wait_version_running(model_api_id, version_id, timeout_s=1800):
    """Poll one version until it is deployed and serving, then confirm it became the active version."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        v = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions/{version_id}",
                         headers=headers).json()
        deployment = v.get("deployment") or {}                 # absent until a deployment exists
        status, pending = deployment.get("status", "Pending"), deployment.get("isPending", True)
        if status != last:
            print(f"version {v.get('number')}: {status} (pending={pending})")
            last = status
        if status == "Running" and not pending:
            api = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).json()
            if api.get("activeVersion", {}).get("id") == version_id:
                return v
        time.sleep(15)
    raise TimeoutError(f"version {version_id} not Running after {timeout_s}s (last status: {last}); "
                       "read its build and instance logs")
```

`Running` is the documented ready state. The spec types `deployment.status` as a free string and does not enumerate the other values, so the helper prints them and keeps polling until the deadline; a status that stops changing is the cue to read the build and instance logs (below).

`Running` is not a health check: a crash-looping container reports `Running` between restarts and the status later flips to `Starting` with `isPending: true`. After the helper returns, read the instance logs **without** `tail` (`maxResults=3000`), keep the model container's lines (tag `kubernetes.container_name` starting with `model-`), and accept the version only on `WSGI app 0 (mountpoint='') ready`; `no app loaded. GAME OVER` after a `Traceback` is a crash loop and the exception line is the cause. The filtering snippet is under "Health check after publishing" in [DEPLOY-ENDPOINT.md](../domino-model-endpoints/DEPLOY-ENDPOINT.md#health-check-after-publishing). Then make one test prediction (200 with your result shape; 503 means no healthy instance).

## Prediction URL

```python
deployment_url = os.environ["DOMINO_URL"]          # not injected by Domino: set it yourself to the deployment URL shown on the endpoint Overview tab
sync_url = f"{deployment_url}/models/{model_api_id}/latest/model"
async_url = f"{deployment_url}/api/modelApis/async/v1/{model_api_id}"
```

Sync calls use `auth=(token, token)`; async calls use `Authorization: Bearer <token>`; the token is an endpoint access token, not your API token (a user bearer token or PAT gets 401 even on a Public endpoint). The deployment URL is external only: no API field returns it, `DOMINO_API_HOST` and `DOMINO_API_PROXY` return 404 for `/models/...` inside a run, and no run variable holds it, so outside Domino use the URL you sign in at, and inside a run read a stored variable or ask the user. The token: the user's, or create one and store it as an environment variable without printing it ([Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens) in `domino-model-endpoints`). Request formats are in `domino-model-endpoints`.

## New version

```python
r = requests.post(f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions", headers=headers, json={
    "projectId": os.environ["DOMINO_PROJECT_ID"],
    "source": {"type": "File", "file": "model.py", "function": "predict"},
    "logHttpRequestResponse": False,
    "monitoringEnabled": False,
    "shouldDeploy": True,                        # optional in the spec with no stated default; set it explicitly
    "description": "retrained 2026-10",
})
r.raise_for_status()
version_id = r.json()["id"]
wait_version_running(model_api_id, version_id)
```

With Basic routing, `latest` switches to the new version once it runs and the previous version shuts down. With Advanced routing, `labels/prod` stays on the promoted version until you promote in the UI.

## Update replicas, tier, environment

```python
api = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).json()
r = requests.put(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers, json={
    "name": api["name"], "description": api["description"],      # required even when unchanged
    "environmentId": api["environmentId"],
    "replicas": 4,
    "hardwareTierId": api.get("hardwareTierId"),
    "resourceQuotaId": api.get("resourceQuotaId"),               # keep the deployment target of remote-data-plane endpoints
})
r.raise_for_status()
```

The PUT returns 200 at once, but a scale change takes effect only when the version restarts. The public API has no restart route: restart from the endpoint page in the UI, or stop and start the active version with the Domino Internal API (non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types); on 6.3 confirm the routes in your deployment's `/docs`):

```python
v = f"{base}/v4/models/{model_api_id}/{api['activeVersion']['id']}"       # non-public route; may change in a future Domino version
requests.post(f"{v}/stopModelDeployment", headers=headers, json={}).raise_for_status()    # -> {"status": "not_running"}
for _ in range(6):
    r = requests.post(f"{v}/startModelDeployment", headers=headers)         # no body; -> {"status": "starting"}
    if r.status_code != 400:                                                # 400: the stop has not settled yet
        break
    time.sleep(5)
r.raise_for_status()
for _ in range(30):
    if requests.get(f"{v}/getModelDeploymentStatus", headers=headers).json()["status"] == "running":
        break
    time.sleep(10)
```

`getModelDeploymentStatus` returns `{modelId, modelVersionId, status}`; `status` is `not_running`, `starting` or `running`, and a restarted version is usually `running` within a minute. Then confirm the change with `GET` on the Model API (`replicas`, `hardwareTierId`) and run the health check from "Wait until a version is Running".

## Stop and delete

The spec describes `DELETE /api/modelServing/v1/modelApis/{modelApiId}` as "archives a Model API"; what it does:

- `DELETE` while a version is running returns `500 "Model API with id <id> is running"`. Stop the running version first.
- The public API has no stop route. Stop from the UI (**Versions** > **Actions**), or with the Domino Internal API route `POST /v4/models/{modelApiId}/{modelApiVersionId}/stopModelDeployment` with body `{}` (non-public route; may change in a future Domino version; on 6.3 confirm it in `/docs`); it returns `{"status": "not_running"}` and `activeVersion.deployment` disappears from the public view. `startModelDeployment` brings the version back (restart snippet above).
- After a successful `DELETE` (200, empty body) the endpoint is gone from the caller's view: `GET` returns `404 No model API found` and it no longer appears in list results, with or without filters. Do not expect to read it back with `isArchived: true`; export the logs and settings you need before deleting.

```python
api = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).json()
version_id = api["activeVersion"]["id"]
requests.post(f"{base}/v4/models/{model_api_id}/{version_id}/stopModelDeployment",   # non-public route; may change in a future Domino version
              headers=headers, json={}).raise_for_status()
requests.delete(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).raise_for_status()
assert requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).status_code == 404
```

## Logs

```python
logs = requests.get(
    f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions/{version_id}/instanceLogs",
    headers=headers, params={"maxResults": 3000}).json()["logs"]   # no tail; filter on tags[kubernetes.container_name]
build = requests.get(
    f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions/{version_id}/buildLogs", headers=headers).json()
```

`exportLogs` works the same way. Optional filters: `podName`, `containerName`, `sinceTimeNano` (instance), `buildId`, `sinceTimeNano` (build).

## Registered models by API

```python
# Register the model logged in an MLflow run (POST /api/registeredmodels/v2)
r = requests.post(f"{base}/api/registeredmodels/v2", headers=headers, json={
    "modelName": "churn-gbm",
    "create": True,                                   # create the registered model if it does not exist
    "projectId": os.environ["DOMINO_PROJECT_ID"],
    "description": "GBM churn model",
    "discoverable": False,
    "modelSource": {
        "sourceType": "mlflow",
        "mlflowSource": {"experimentRunId": RUN_ID, "loggedModelId": LOGGED_MODEL_ID},   # "m-..." from mlflow 3; see below
    },
})
r.raise_for_status()
version = r.json()["modelVersion"]["modelVersion"]

# Read, patch, versions
requests.get(f"{base}/api/registeredmodels/v1/churn-gbm", headers=headers).json()
requests.patch(f"{base}/api/registeredmodels/v1/churn-gbm", headers=headers, json={"discoverable": True})
requests.get(f"{base}/api/registeredmodels/v1/churn-gbm/versions/{version}", headers=headers).json()
requests.get(f"{base}/api/registeredmodels/v1/churn-gbm/versions/{version}/modelapis", headers=headers).json()
```

`PATCH` with `description` and `discoverable` returns 200 and the description persists, but `GET /api/registeredmodels/v1/{modelName}` returns neither `discoverable` nor aliases; its keys are `name`, `description`, `latestVersion`, `project`, `tags`, `ownerUsername`, `createdAt`, `updatedAt`, `requestingUserAccess`. Aliases live in MLflow: read them with `GET /api/2.0/mlflow/registered-models/get?name=...` (`aliases`) on the deployment URL with the same bearer token, or with the MLflow client (see `domino-experiment-tracking`).

`mlflowSource` takes `experimentRunId` (required) plus `artifactPath` or `loggedModelId`. With an MLflow 3 client, `log_model` stores the model as a LoggedModel (`m-<id>`, `mlflow.last_logged_model()` or the `model_id` on the returned model info) rather than as a run artifact, so pass `loggedModelId`: with an MLflow 3 client, `artifactPath` also returns 200 but the version does not load; the `loggedModelId` version does. Use `artifactPath` only for models logged as run artifacts by MLflow 2 clients. `huggingFaceSource` takes `modelId` (required), `modelRevision`, `huggingFaceToken`. `sourceType` is `mlflow` or `huggingface` and names which of the two you filled in. List with `GET /api/registeredmodels/v2?projectId=...&maxResults=25`; the response's `metadata.nextPageToken` goes into the next request's `pageToken` query parameter until it is absent. `POST /api/registeredmodels/v1/{modelName}/versions` (`description`, `experimentRunId`, `artifact`) is deprecated.

## python-domino equivalents

`Domino("owner/project")` (the project argument is required) exposes `models_list()`, `model_publish(file, function, environment_id, name, description, files_to_exclude=None)`, `model_versions_get(model_id)`, `model_version_publish(model_id, file, function, environment_id, description, files_to_exclude=None)` and the export helpers `model_version_export`, `model_version_sagemaker_export`, `model_version_export_status`, `model_version_export_logs`. They call the older `/v1/models` and `/v4` routes (non-public route; may change in a future Domino version) and know nothing about replicas, hardware tiers, async endpoints or registry sources; use the public REST routes above for those. See `domino-python-sdk`.
