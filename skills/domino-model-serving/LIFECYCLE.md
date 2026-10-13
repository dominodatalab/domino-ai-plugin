# Model serving lifecycle: worked requests

Applies to Domino 6.3 and Domino Cloud. Every route here is in both public API specs unless marked (Cloud). Field names come from the spec schemas (`ModelApiCreationRequest`, `ModelApiVersionCreationRequest`, `ModelApiUpdateRequest`, `ModelApi`, `NewRegisteredModelV2`).

## Setup

```python
import os
import time
import requests

if os.environ.get("DOMINO_API_PROXY"):                 # in a run, proxy available
    base, headers = os.environ["DOMINO_API_PROXY"], {}
else:                                                  # in a run without the proxy
    base = os.environ["DOMINO_API_HOST"]
    token = requests.get("http://localhost:8899/access-token").text.strip()
    headers = {"Authorization": f"Bearer {token}"}
# Outside Domino: base = deployment URL; headers = {"Authorization": "Bearer <PAT or service-account token>"}
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

The version is built from the `version.commitId` you pass, or the Project's head commit if you omit it, never from a Workspace's disk. In a DFS Project sync the Workspace first (**File Changes** > **Sync to Domino**); in a Git-based Project commit and push the code and sync the artifacts. Include the model artifacts the function loads. Then pin the commit: the head lags an upload by a few seconds, and a version created right after a sync was built from the previous commit and crash-looped with `FileNotFoundError` (see `domino-model-endpoints`, "Sync or commit first"). Use the `commitId` the MCP upload tool returned, or read `GET /api/projects/beta/projects/{projectId}/commits/latest` (`commitId`) and confirm `GET /api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content` is 200 for each model file.

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
r.raise_for_status()                              # spec says 201; Domino Cloud 6.4 returned 200. Check for 2xx
model_api_id = r.json()["id"]
versions = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions", headers=headers).json()
version_id = max(versions, key=lambda v: v["number"])["id"]
wait_version_running(model_api_id, version_id)
```

On Domino Cloud 6.4 this body (with `replicas: 1` and no `hardwareTierId`) creates the endpoint, which reaches `Running` in about 2.5 minutes. Two things to know: without `hardwareTierId` the response carries `hardwareTierId: "small-k8s"` rather than the tier flagged `isDefaultForModelApi`, so pass `hardwareTierId` explicitly; and an access token is created automatically but its value is not in the response (read it under **Settings** > **Invocation**).

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

`Running` is not a health check: a crash-looping container reports `Running` between restarts and the status later flips to `Starting` with `isPending: true`. After the helper returns, read the instance logs **without** `tail` and with a large window, keep the model container's lines (tag `kubernetes.container_name` starting with `model-`; the `istio-proxy` sidecar's hundreds of lines otherwise crowd them out and a small `tail` window shows no crash at all), and accept the version only on `WSGI app 0 (mountpoint='') ready`; `no app loaded. GAME OVER` after a `Traceback` is a crash loop and the exception line is the cause. Then make one test prediction (200 with your result shape; 503 means no healthy instance).

```python
def model_container_health(model_api_id, version_id):
    """'ready', 'crash' (with the cause), or 'pending' when the model container has not logged yet."""
    r = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}/versions/{version_id}/instanceLogs",
                     headers=headers, params={"maxResults": 3000})      # no tail
    r.raise_for_status()
    lines = [e["log"] for e in r.json().get("logs", [])
             if any(t["key"] == "kubernetes.container_name" and t["value"].startswith("model-")
                    for t in e.get("tags", []))]
    text = "\n".join(lines)
    if not lines:
        return "pending", None                                           # never treat an empty result as healthy
    if "no app loaded. GAME OVER" in text:
        errors = [line for line in lines if "Error" in line or "Exception" in line]
        return "crash", (errors[-1] if errors else text[-2000:])
    if "WSGI app 0 (mountpoint='') ready" in text:
        return "ready", None
    return "pending", None

state, cause = model_container_health(model_api_id, version_id)
if state == "crash":
    raise RuntimeError(f"version {version_id} is crash-looping: {cause}")
```

## Prediction URL

```python
deployment_url = os.environ["DOMINO_URL"]          # not injected by Domino: set it yourself to the deployment URL shown on the endpoint Overview tab
sync_url = f"{deployment_url}/models/{model_api_id}/latest/model"
async_url = f"{deployment_url}/api/modelApis/async/v1/{model_api_id}"
```

Sync calls use `auth=(token, token)`; async calls use `Authorization: Bearer <token>`; the token is an endpoint access token, not your API token. Neither value can be fetched by an agent: the deployment URL is external only (`DOMINO_API_HOST` and `DOMINO_API_PROXY` return 404 for `/models/...`, and no run variable holds it), and the access token is created and shown only in the UI (**Settings** > **Invocation**; the API returns token ids, never values, and a user bearer token or PAT gets 401 even on a Public endpoint). Ask the user for both, or have them use the **Tester** tab or set the endpoint to **Unrestricted**. Request formats are in `domino-model-endpoints`.

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

The PUT is accepted immediately (200; `replicas` reads back as the new value while the running version stays `Running`), but a scale change takes effect only when the version restarts. The public API has no restart route: restart from the endpoint page in the UI, or stop and start the active version with the Domino Internal API (internal API, may change between Domino versions; on 6.3 confirm the routes in your deployment's `/docs`):

```python
v = f"{base}/v4/models/{model_api_id}/{api['activeVersion']['id']}"       # internal API, may change between Domino versions
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
- The public API has no stop route. Stop from the UI (**Versions** > **Actions**), or with the Domino Internal API route `POST /v4/models/{modelApiId}/{modelApiVersionId}/stopModelDeployment` with body `{}` (internal API, may change between Domino versions; on 6.3 confirm it in `/docs`); it returns `{"status": "not_running"}` and `activeVersion.deployment` disappears from the public view. `startModelDeployment` brings the version back (restart snippet above).
- After a successful `DELETE` (200, empty body) the endpoint is gone from the caller's view: `GET` returns `404 No model API found` and it no longer appears in list results, with or without filters. Do not expect to read it back with `isArchived: true`; export the logs and settings you need before deleting.

```python
api = requests.get(f"{base}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).json()
version_id = api["activeVersion"]["id"]
requests.post(f"{base}/v4/models/{model_api_id}/{version_id}/stopModelDeployment",   # internal API, may change between Domino versions
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

`mlflowSource` takes `experimentRunId` (required) plus `artifactPath` or `loggedModelId`. With an MLflow 3 client, `log_model` stores the model as a LoggedModel (`m-<id>`, `mlflow.last_logged_model()` or the `model_id` on the returned model info) rather than as a run artifact, so pass `loggedModelId`: with MLflow 3.3.2, `artifactPath: "model"` also returns 200 but the version points at a nonexistent run artifact and `mlflow.pyfunc.load_model` fails, while the `loggedModelId` version loads. Use `artifactPath` only for models logged as run artifacts by MLflow 2 clients. `huggingFaceSource` takes `modelId` (required), `modelRevision`, `huggingFaceToken`. `sourceType` is `mlflow` or `huggingface` and names which of the two you filled in. List with `GET /api/registeredmodels/v2?projectId=...&maxResults=25`; the response's `metadata.nextPageToken` goes into the next request's `pageToken` query parameter until it is absent. `POST /api/registeredmodels/v1/{modelName}/versions` (`description`, `experimentRunId`, `artifact`) still exists but is deprecated since 6.2.1.

## python-domino equivalents

`Domino("owner/project")` (the project argument is required) exposes `models_list()`, `model_publish(file, function, environment_id, name, description, files_to_exclude=None)`, `model_versions_get(model_id)`, `model_version_publish(model_id, file, function, environment_id, description, files_to_exclude=None)` and the export helpers `model_version_export`, `model_version_sagemaker_export`, `model_version_export_status`, `model_version_export_logs`. They call the older `/v1/models` and `/v4` routes (Domino Internal API, may change between Domino versions) and know nothing about replicas, hardware tiers, async endpoints or registry sources; use the public REST routes above for those. See `domino-python-sdk`.
