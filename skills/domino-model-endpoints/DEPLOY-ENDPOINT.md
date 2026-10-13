# Publishing and calling Domino endpoints

Applies to Domino 6.3 and Domino Cloud. Management routes below exist in both public API specs
(`https://docs.domino.ai/api-specs/6.3/public-api.json`, `https://docs.domino.ai/api-specs/cloud/public-api.json`).
Product behaviour: https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/index.

## The prediction function

Domino runs your script once when a version starts, keeps every module-level object in memory, and calls the configured function for each request. Load models at module level, not inside the function.

Contract:

- The file is a `.py` (or `.R`) file in the project; the function can have any name (set in the publish form).
- Arguments map from the request JSON (see "Request JSON"). Return a literal, list or dict that is JSON-serializable. NumPy scalars and arrays are not; convert with `.item()` / `.tolist()`, and cast `Decimal` to `float`.
- Anything the function needs (model files, lookup tables) must be in the **committed** project files or in the environment image. The build takes the Project's latest commit (the version records it as `commitId`), never the Workspace disk; see "Sync or commit first" below.

### Scikit-learn

```python
# model.py
import joblib
import numpy as np

_model = joblib.load("random_forest.joblib")    # once, when the version starts

def predict(features):
    """Request: {"data": {"features": [[5.1, 3.5, 1.4, 0.2]]}}"""
    X = np.asarray(features, dtype=float)
    preds = _model.predict(X)
    confidence = _model.predict_proba(X).max(axis=1)
    return {"predictions": preds.tolist(), "confidence": confidence.tolist()}
```

### PyTorch

```python
# model.py
import torch

_device = "cuda" if torch.cuda.is_available() else "cpu"   # GPU only if the endpoint hardware tier has one
_model = torch.jit.load("model_scripted.pt", map_location=_device).eval()

def predict(inputs):
    """Request: {"data": {"inputs": [[0.1, 0.2, 0.3]]}}"""
    with torch.no_grad():
        out = _model(torch.tensor(inputs, dtype=torch.float32, device=_device))
    return {"predictions": out.argmax(dim=1).cpu().tolist()}
```

### Validation and errors

Return a structured error instead of raising when the input is wrong; an unhandled exception becomes a 500 and the detail is only in the instance logs.

```python
def predict(features):
    if not isinstance(features, list) or not features:
        return {"error": "features must be a non-empty list", "code": "INVALID_INPUT"}
    try:
        return {"predictions": _model.predict(features).tolist()}
    except Exception as exc:          # log the detail, return a stable shape
        print(f"prediction error: {exc}")
        return {"error": "prediction failed", "code": "PREDICTION_ERROR"}
```

`print` output goes to the version's instance logs.

## Sync or commit first

The endpoint image is built from the Project's files at a commit, not from the Workspace file system. A file that exists only on the Workspace disk is absent from the image: the build succeeds, the version reaches `Running`, and the container then crash-loops with `FileNotFoundError: [Errno 2] No such file or directory: '/mnt/<username>/<project>/model.py'` followed by `*** no app loaded. GAME OVER ***` every 30 seconds or so, while the status alternates between `Running` and `Starting` and predictions return 503. Before publishing:

- **DFS Project**: in the Workspace, **File Changes** > **Sync to Domino** (every file the function loads: the `.py`, model artifacts such as `.pkl` or `.joblib`, lookup files). From code, `python-domino` `files_upload(path, fileobj)` uploads one file (it uses the legacy `PUT /v1/projects/{owner}/{project}/{path}` route, Domino Internal API, may change between Domino versions; it takes a binary file object), and the bundled MCP server uploads any file type: `upload_file_to_domino_project` with `file_content` (text) or `content_base64` (binary, base64-encoded), or `sync_local_file_to_domino` for a file already on the Workspace disk (its bytes are uploaded unchanged, so `.joblib` and `.pkl` artifacts work). Then **pin the commit** rather than taking the head: the head can lag a few seconds behind an upload, and a version created six seconds after a sync was built from the previous commit and crash-looped. Use the `commitId` the MCP upload tool returned (the newest, if you uploaded several files), or read `GET /api/projects/beta/projects/{projectId}/commits/latest` (field `commitId`) and confirm `GET /api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content` returns 200 for `model.py` and every artifact. Pass that id as `version.commitId` on create or `commitId` on `POST .../versions`; in the UI, publish only after that file check passes.
- **Git-based Project**: commit and push the code; sync artifacts under `/mnt/artifacts` with **File Changes** > **Artifacts** > **Sync to Domino**. The version records the artifacts commit as `commitId` and pulls the repository at build time.

Publish only after that. If a version is already crash-looping, sync the missing files and publish a new version; the running one never sees later file changes.

## Publish from the UI

1. **Deployments** > **Endpoints** > **Create Domino Endpoint**.
2. Name, description, file and function.
3. Compute environment to build the image from (packaging rules in [SKILL.md](./SKILL.md)).
4. Scaling: number of instances and endpoint hardware tier ([SCALING.md](./SCALING.md)); a GPU tier exists only if your administrator configured one.
5. **Request Type**: **Sync** or **Async**.
6. Publish. The status moves through building and starting to **Running**.

Endpoint environment variables: on the endpoint, **Settings** > **Environment variables** (values up to 64 K). Only endpoint owners and editors can set them; restart running versions to pick up changes. Project and user variables are not injected into endpoints.

## Publish with the API

`POST /api/modelServing/v1/modelApis` creates the endpoint and its first version in one call. Required: `name`, `description`, `environmentId`, `isAsync`, `strictNodeAntiAffinity`, `environmentVariables` (may be `[]`) and `version` with `projectId`, `source`, `logHttpRequestResponse`, `monitoringEnabled`. Optional: `hardwareTierId`, `replicas`, `resourceQuotaId`, `bundleId`. Pass `hardwareTierId` anyway: on Domino Cloud 6.4 a create without it lands on `small-k8s` rather than the deployment's default endpoint tier. With the body below the endpoint reaches **Running** in about 2.5 minutes.

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)   # in a run; outside Domino use a PAT or service-account token
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$DOMINO_API_HOST/api/modelServing/v1/modelApis" -d '{
    "name": "iris-classifier",
    "description": "RandomForest on iris",
    "environmentId": "'"$ENVIRONMENT_ID"'",
    "isAsync": false,
    "strictNodeAntiAffinity": false,
    "environmentVariables": [],
    "replicas": 2,
    "version": {
      "projectId": "'"$DOMINO_PROJECT_ID"'",
      "commitId": "'"$COMMIT_ID"'",
      "source": {"type": "File", "file": "model.py", "function": "predict", "excludeFiles": []},
      "logHttpRequestResponse": false,
      "monitoringEnabled": false
    }
  }'
```

`version.commitId` is the Project commit the image is built from: set it to the commit you verified after syncing ("Sync or commit first"); omitting it takes the head, which lags an upload by a few seconds.

When `DOMINO_API_PROXY` is set, send the same request to `$DOMINO_API_PROXY/api/...` with no `Authorization` header. `source.type` is `File` (`file` + `function`) or `Registry` (`registeredModelName` + `registeredModelVersion`). The response is the `ModelApi` object; its `id` is the model ID used in prediction URLs. Poll `GET /api/modelServing/v1/modelApis/{id}` until `activeVersion.deployment.status` is `Running` and `isPending` is false (the `deployment` key is absent until a deployment exists), then run the health check below; `Running` alone is not proof that the endpoint works. The full REST lifecycle (new versions, stop and delete, logs, list filters) is in `domino-model-serving`. `python-domino` offers `model_publish(file, function, environment_id, name, description)` and `model_version_publish(model_id, file, function, environment_id, description)` on a client built with `Domino("owner/project")`; see `domino-python-sdk`.

## Health check after publishing

`Running` means a container started; a crash-looping container reports `Running` between restarts. Treat a version as healthy only when all of these hold:

1. **The model container reported ready.** Fetch the instance logs **without** `tail` and with a large window, `GET /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/instanceLogs?maxResults=3000` (the version id is `activeVersion.id`), and keep only entries whose `tags` contain `kubernetes.container_name` with a value starting with `model-`. The `istio-proxy` sidecar writes hundreds of lines, so `tail=true` with a small `maxResults` returns sidecar lines only and a crash looks clean (`tail=true&maxResults=200` gives no model-container lines; `maxResults=3000` without `tail` gives the full traceback). Healthy: a model-container line `WSGI app 0 (mountpoint='') ready`. Crash loop: `no app loaded. GAME OVER` after a `Traceback`, and the exception line (`FileNotFoundError`, `ModuleNotFoundError`, ...) is the cause. No model-container lines at all means the container has not logged yet: wait and refetch; that is never "clean". The route also accepts `containerName`; filter on the tag rather than relying on it.
2. **The status holds.** Re-read the status a minute later: `Running` with `isPending: false` both times. Alternating `Running` / `Starting` or `isPending: true` after a `Running` reading is a restart loop.
3. **One real prediction succeeds.** The **Tester** tab needs no token; a client call needs the URL and token from the user (next section). HTTP 200 with your result shape is the pass; 503 means no healthy instance behind the route, 401 means the wrong credential or auth mode, 400 means the request shape does not match the function signature.

```python
import os
import requests

if os.environ.get("DOMINO_API_PROXY"):
    base, headers = os.environ["DOMINO_API_PROXY"], {}
else:
    base = os.environ["DOMINO_API_HOST"]
    headers = {"Authorization": "Bearer " + requests.get("http://localhost:8899/access-token").text.strip()}

r = requests.get(f"{base}/api/modelServing/v1/modelApis/{MODEL_ID}/versions/{VERSION_ID}/instanceLogs",
                 headers=headers, params={"maxResults": 3000})          # no tail: the sidecar would crowd out the model container
r.raise_for_status()
model_lines = [e["log"] for e in r.json().get("logs", [])
               if any(t["key"] == "kubernetes.container_name" and t["value"].startswith("model-")
                      for t in e.get("tags", []))]
text = "\n".join(model_lines)
if not model_lines:
    print("no model-container log lines yet: wait and refetch")
elif "no app loaded. GAME OVER" in text:
    errors = [line for line in model_lines if "Error" in line or "Exception" in line]
    print("CRASH LOOP, cause:", errors[-1] if errors else "see the traceback below")
    print(text[-3000:])
elif "WSGI app 0 (mountpoint='') ready" in text:
    print("model container ready")
else:
    print("model container still starting: refetch")
```

A missing file means the Project commit predates it: sync or commit, pin the commit, then publish a new version. A missing module means the package is not in the environment Dockerfile (endpoint hosts ignore `requirements.txt`).

## Request JSON

| Function signature | Request body |
|--------------------|--------------|
| `predict(x, y, z)` | `{"data": {"x": 1, "y": 2, "z": 3}}` or `{"parameters": [1, 2, 3]}` |
| `predict(d)` using `d["x"]` | `{"parameters": [{"x": 1, "y": 2, "z": 3}]}` |
| `predict(x, **kwargs)` | `{"data": {"x": 1, "y": 2, "z": 3}}` |

JSON to Python: object to dict, array to list, string to str, integer to int, real to float, true/false to True/False, null to None. The return value is serialized back to JSON.

## Call a synchronous endpoint

Two inputs only the user can supply; do not try to derive them:

- **The prediction URL.** It is the deployment's external URL plus `/models/{modelId}/latest/model`, shown on the endpoint's **Overview** tab under "Calling your endpoint". Inside a run, `DOMINO_API_HOST` and `DOMINO_API_PROXY` do not route `/models/...` (they return 404), and no injected variable holds the external URL, so the agent must be given it.
- **The endpoint access token.** It is created and displayed only in the UI (**Settings** > **Invocation** > **Add Model Access Token**). No public or internal route creates or returns a token value: the API exposes token ids and timestamps only (`access.accessTokens[]`), and your own Domino bearer token or Personal Access Token is rejected with 401 even on a Public endpoint, because visibility (who can see it) and prediction authorization (who can call it) are separate settings.

Ask the user for both before promising a prediction, and suggest they store them as project or user environment variables (`DOMINO_URL`, `MODEL_ID`, `MODEL_ACCESS_TOKEN`) so later runs can read them. Alternatives: the user runs the call from the **Tester** tab, or sets the endpoint to **Unrestricted** under **Settings** > **Invocation**, after which only the URL is needed.

Restricted endpoints: HTTP Basic with the endpoint access token as **both** username and password (not a Bearer header). Unrestricted endpoints: no credentials.

```python
import os
import requests

DOMINO_URL = os.environ["DOMINO_URL"]        # external deployment URL, supplied by the user (Overview tab); not injected by Domino
MODEL_ID = os.environ["MODEL_ID"]            # from the Overview tab or the create response
TOKEN = os.environ["MODEL_ACCESS_TOKEN"]      # supplied by the user from Settings > Invocation; keep it out of source and browser bundles

resp = requests.post(
    f"{DOMINO_URL}/models/{MODEL_ID}/latest/model",
    auth=(TOKEN, TOKEN),
    json={"data": {"features": [[5.1, 3.5, 1.4, 0.2]]}},
)
resp.raise_for_status()
print(resp.json()["result"])
```

```bash
curl -s -u "$MODEL_ACCESS_TOKEN:$MODEL_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"data": {"features": [[5.1, 3.5, 1.4, 0.2]]}}' "$DOMINO_URL/models/$MODEL_ID/latest/model"
```

The JSON body carries the function's return value under `result`.

## Call an asynchronous endpoint

Async endpoints queue the request and you poll for the result. Limits: request and response bodies up to 10 KB, so the payload carries a reference to data in an external store, an `s3://` URI or similar (the docs' own example), or a key the function reads through a Data Source with the domino-data SDK (`domino-data-sdk`); the function writes its result the same way and returns a small reference. A request stays alive for 30 minutes after pickup, a prediction may execute more than once (make the function idempotent) and ordering is not guaranteed. Auth is Bearer with the endpoint access token.

```python
import time
import requests

base = f"{DOMINO_URL}/api/modelApis/async/v1/{MODEL_ID}"
headers = {"Authorization": f"Bearer {TOKEN}"}

created = requests.post(base, headers=headers,
                        json={"parameters": {"input_file": "s3://bucket/batch/2026-10.parquet"}})   # a reference, not the data; or a Data Source key
created.raise_for_status()
prediction_id = created.json()["asyncPredictionId"]

deadline = time.time() + 45 * 60             # Domino keeps a picked-up request alive for 30 minutes
delay = 1
while time.time() < deadline:
    status = requests.get(f"{base}/{prediction_id}", headers=headers)
    if status.status_code >= 500:            # transient; retry with backoff
        time.sleep(delay)
        delay = min(delay * 2, 60)
        continue
    status.raise_for_status()
    body = status.json()
    state = body["status"].lower()           # sources differ on casing; compare case-insensitively
    if state == "succeeded":
        print(body["result"])
        break
    if state == "failed":
        print(body.get("errors"))
        break
    if state not in ("queued", "pending", "processing"):
        raise RuntimeError(f"unexpected prediction status: {body['status']}")
    time.sleep(delay)
    delay = min(delay * 2, 60)
else:
    raise TimeoutError(prediction_id)
```

Status values: the spec documents `Pending`, `Processing`, `Succeeded` and `Failed`; the docs' example client compares lowercase `queued`, `succeeded` and `failed`. Compare case-insensitively and treat anything else as an error. Async endpoints are not available on remote data planes. Full client with retries: https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/async-example-client. Scoring a whole file, table or Dataset with no request/response contract at all is a batch scoring Job, not an endpoint: [domino-model-delivery](../domino-model-delivery/BATCH-SCORING.md).

## Versions

- New version: open the endpoint, **Versions**, publish again with the updated file and function. Project files are re-read at build time; a running version never sees later file changes.
- Routing (**Settings** > **Deployment**): Basic routing points `/models/<modelId>/latest/model` at the newest successful version and stops the previous one; Advanced routing keeps a promoted version at `/models/<modelId>/labels/prod/model` and lets you promote `latest` without downtime.
- Stop or start a version from the **Actions** menu on the Versions tab. Domino recommends stopping the previous version before deploying a retrained one.
- Scheduled retraining: in a scheduled Job, select the endpoint under **Update Domino Endpoint**; the project files after the Job become a new version.
- Via the API: `POST /api/modelServing/v1/modelApis/{modelApiId}/versions` with `projectId`, `source`, `logHttpRequestResponse`, `monitoringEnabled` and `shouldDeploy: true` (optional `environmentId`, `commitId`), then poll that version's `deployment.status`. Details in `domino-model-serving`.

## Access control

- **Settings** > **Access and Sharing**: Public (anyone on the deployment can discover and view) or Private (collaborators only). Endpoint collaborators are Viewers, Editors or Owners; project Contributors can create endpoints and become their owner. On Domino Cloud the API additionally exposes a `Discoverable` visibility (discover but not invoke) and an `Operator` role through `/api/modelServing/beta/modelApis/{modelApiId}/visibility` and `.../collaborators`; the docs pages lag the spec there.
- **Settings** > **Invocation**: Unrestricted (no token) or Restricted (token required). Generate, name, revoke and regenerate access tokens here.

## Remote data planes, volumes, spot instances

- To deploy on a remote data plane, pick a hardware tier belonging to that data plane from the **Deployment Target** list. Async requests and integrated model monitoring are not supported there.
- Sync endpoints can mount Kubernetes `hostPath` volumes: **Settings** > **Advanced** > **Add Volume** (name, mount path, host path, read-only), as configured by your administrator.
- Endpoints can run on spot node pools (preview) by selecting a spot hardware tier; an interruption degrades or stops the endpoint until capacity returns.
