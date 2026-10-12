# Host an LLM: REST API reference

Applies to Domino 6.3 and Domino Cloud. Every route below is present, with the same bodies, in both public specs (6.3.1 and 6.4.0) under the `/api/gen-ai/beta` prefix: 14 paths, 17 operations. The prefix is `beta`; re-check the deployment's own reference (`https://<domino-domain>/docs`; `$DOMINO_API_HOST/assets/public-api.json` is an incomplete subset that does include these routes) before generating client code. The write operations below (create, patch, start, stop, delete) are taken from the spec and have not been exercised against a live deployment; confirm the first call's response before building on it.

## Authentication and base URL

```python
import os
import requests

if os.environ.get("DOMINO_API_PROXY"):                       # in-run, JWT credential propagation
    base_url, headers = os.environ["DOMINO_API_PROXY"].rstrip("/"), {}
else:                                                        # in-run, access-token sidecar
    base_url = os.environ["DOMINO_API_HOST"].rstrip("/")
    token = requests.get("http://localhost:8899/access-token").text.strip()
    headers = {"Authorization": f"Bearer {token}"}
# Outside a run: base_url = the deployment's HTTPS URL, headers = Bearer <Personal Access Token>
```

In a run without `DOMINO_API_PROXY`, `DOMINO_API_HOST` may point at a legacy sidecar that lacks some `/api/*` routes (see HOSTS.md in the `domino-api-intro` skill). A 404 from it is not proof the route is absent: retry against the deployment's public HTTPS URL with a Personal Access Token before concluding anything. Legacy user API keys (`X-Domino-Api-Key`, `DOMINO_USER_API_KEY`) are deprecated; do not use them.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/gen-ai/beta/default-endpoint-environment` | The default environment for endpoints (the Domino vLLM Environment): `{id, name, revisionId?}` |
| GET | `/api/gen-ai/beta/endpoints?projectId=&registeredModelName=` | List endpoints, optionally filtered; returns `{"items": [...]}` |
| POST | `/api/gen-ai/beta/endpoints` | Create an endpoint with its first version |
| GET | `/api/gen-ai/beta/endpoints/{endpointId}` | Endpoint detail, including `url` and `currentVersion.status` |
| DELETE | `/api/gen-ai/beta/endpoints/{endpointId}` | Delete the endpoint |
| GET | `/api/gen-ai/beta/endpoints/{endpointId}/collaborators` | Who has access |
| GET | `/api/gen-ai/beta/endpoints/{endpointId}/versions` | Versions of the endpoint |
| GET | `/api/gen-ai/beta/endpoints/{endpointId}/versions/{versionNumber}` | One version |
| PATCH | `/api/gen-ai/beta/endpoints/{endpointId}/versions/{versionNumber}` | Patch labels, description, access or instructions in place; a change to `vanityUrl`, `modelSource`, `environment`, `hardwareTierId` or `configuration` stops the version and starts a new one (see below) |
| POST | `.../versions/{versionNumber}/start` | Start a version |
| POST | `.../versions/{versionNumber}/stop` | Stop a version |
| GET | `.../versions/{versionNumber}/request-metrics` | Request metrics |
| GET | `.../versions/{versionNumber}/vllm-token-metrics` | Token metrics from vLLM |
| GET | `.../versions/{versionNumber}/vllm-latency-metrics` | Latency metrics from vLLM |
| GET | `.../versions/{versionNumber}/pod-resource-metrics` | CPU, memory and GPU usage of the serving pod |
| GET | `.../versions/{versionNumber}/realTimeLogs?logType=&limit=&offset=&latestTime=` | Live logs of the serving execution |
| GET | `/api/gen-ai/beta/vanity-url-availability/{vanityUrl}` | Whether a vanity URL is free |

All four metrics routes take the same query parameters: `startTime`, `endTime`, `aggregationWindow` (`hourly` or `daily`), `maxHistoricalExecutions`. `logType` is one of `complete`, `prepareoutput`, `stdout`, `stderr`.

## Create an endpoint

Required fields: `name`, `projectId`, `modelSource`, `environment`, `hardwareTierId`, `configuration`, `generalAccess`, `collaborators`. Exactly one of the two `modelSource` shapes is used.

```python
env = requests.get(f"{base_url}/api/gen-ai/beta/default-endpoint-environment", headers=headers).json()

body = {
    "name": "llama-3-8b-chat",
    "description": "Chat model for the support assistant",
    "projectId": os.environ["DOMINO_PROJECT_ID"],
    "modelSource": {
        # From Hugging Face:
        "huggingFace": {
            "path": "meta-llama/Meta-Llama-3-8B-Instruct",   # repo path on Hugging Face
            "commit": "main",                                 # revision; required
            "apiToken": os.environ.get("HF_TOKEN", ""),       # needed for gated models
            "modelType": "LLM",                               # LLM | Embedding | OtherGenAI; required
        },
        # Or from the Domino Model Registry instead:
        # "registeredModel": {"modelName": "support-llm", "modelVersion": 3},
    },
    "environment": {"environmentId": env["id"]},              # "revisionId" is optional; pins a revision
    "hardwareTierId": "<a GPU hardware tier id on the deployment>",
    "configuration": {
        "servedModelName": "support-llm",                     # the `model` value callers pass
        "maxNumberOfSequences": 8,                            # requests processed in parallel
        "tensorParallelism": 1,                               # GPUs the model is split across
        "vllmArguments": "--enable-auto-tool-choice --tool-call-parser hermes",
    },
    "generalAccess": "Restricted",                            # Restricted | Viewer | Consumer
    "collaborators": [{"userId": "<user id>", "name": "<username>"}],   # or {"organizationId": ..., "name": ...}
    "versionLabel": "v1",
}
endpoint = requests.post(f"{base_url}/api/gen-ai/beta/endpoints", headers=headers, json=body).json()
endpoint_id = endpoint["id"]
```

Field notes, from the spec:

- `configuration.servedModelName` is the name callers use as `model` in OpenAI-style requests. `maxNumberOfSequences` is the number of requests processed in parallel; `tensorParallelism` is the number of GPUs the model is split across; `vllmArguments` is the string passed to the vLLM binary (tool calling with agent frameworks needs `--enable-auto-tool-choice --tool-call-parser hermes` for some models).
- `modelSource.huggingFace` requires `path`, `commit` and `modelType` (`LLM`, `Embedding`, `OtherGenAI`); `registeredModel` requires `modelName` and `modelVersion` (integer).
- `generalAccess` is one of `Restricted`, `Viewer`, `Consumer`; `collaborators` entries carry either a `userId` or an `organizationId` plus `name`.
- `vanityUrl` is optional; check availability first with the vanity-url route. The response carries both `vanityUrl` and `url`.
- `GET /api/gen-ai/beta/default-endpoint-environment` returns `{"id", "name"}` and optionally `"revisionId"`. Pass `id` as `environment.environmentId`; a live Cloud deployment returned no `revisionId` (checked 2026-10-12), so do not require it.
- Hardware tier ids are deployment-specific; list them with the hardware-tier routes of the Public API or read one from an existing endpoint's `currentVersion.hardwareTier.id`.

## Wait for it to run, then get the URL

```python
import time

TERMINAL = {"Running", "Stopped", "Failed", "BuildFailed", "Unknown"}
status = None
for _ in range(120):
    ep = requests.get(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}", headers=headers).json()
    version = ep.get("currentVersion")            # not guaranteed by the spec; absent while nothing is deployed
    status = version["status"] if version else None
    if status in TERMINAL:
        break
    time.sleep(10)

print(status, ep["url"])   # ep["url"] is the base_url for OpenAI-style clients, valid once status is Running
```

`currentVersion.status` is one of `Building`, `BuildFailed`, `Starting`, `Running`, `Stopping`, `Stopped`, `Failed`, `Unknown`; only `Running` means the endpoint serves requests. On `Failed` or `BuildFailed`, read `realTimeLogs` for the version before retrying. The endpoint detail also carries `requestCount`, `instructions`, `generalAccess`, `project`, `currentVersion.number`, `currentVersion.configuration` and `currentVersion.hardwareTier` (`id`, `dataPlaneId`, `dataPlaneName`). On a live Cloud deployment `url` is served from the apps host (`https://apps.<domain>/endpoints/<vanityUrl>/`), not from `DOMINO_API_HOST`; always read it from the response.

## Call the running endpoint

Use `ep["url"]` as `base_url` and `configuration.servedModelName` as `model`; the bearer is the in-run access token (or a PAT outside a run). See [HOST-AN-LLM.md](./HOST-AN-LLM.md). Predictions go to the endpoint URL, not to `/api/gen-ai/beta/...`, which is management only.

## Stop, start, update, delete

```python
v = ep["currentVersion"]["number"]
requests.post(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}/versions/{v}/stop", headers=headers)
requests.post(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}/versions/{v}/start", headers=headers)

# Patch in place: versionLabel, versionDescription, name, description, generalAccess, collaborators, instructions
requests.patch(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}/versions/{v}", headers=headers,
               json={"versionLabel": "v1-reviewed", "instructions": "Use servedModelName support-llm"})

# Change the serving setup: the spec says a change to vanityUrl, modelSource, environment, hardwareTierId or
# configuration STOPS this version and STARTS A NEW ONE with the patched values. Send the complete
# configuration object (copy it from currentVersion and change the field): the spec does not say whether a
# partial object is merged or replaces the whole configuration, and a replacement would drop servedModelName.
new_configuration = dict(ep["currentVersion"]["configuration"])
new_configuration["vllmArguments"] = "--enable-auto-tool-choice --tool-call-parser hermes --max-model-len 8192"
requests.patch(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}/versions/{v}", headers=headers,
               json={"hardwareTierId": "<a larger GPU tier id>", "configuration": new_configuration})

ep = requests.get(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}", headers=headers).json()
v = ep["currentVersion"]["number"]      # the new version; poll its status as above before calling the endpoint

requests.delete(f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}", headers=headers)
```

After any of these, `GET` the endpoint again and read `currentVersion.number`, `currentVersion.status` and `url` before assuming the operation completed or telling callers what to use.

## Metrics and logs

```python
params = {"startTime": "2026-10-01T00:00:00Z", "endTime": "2026-10-12T00:00:00Z", "aggregationWindow": "hourly"}
base = f"{base_url}/api/gen-ai/beta/endpoints/{endpoint_id}/versions/{v}"
requests.get(f"{base}/request-metrics", headers=headers, params=params).json()
requests.get(f"{base}/vllm-token-metrics", headers=headers, params=params).json()
requests.get(f"{base}/vllm-latency-metrics", headers=headers, params=params).json()
requests.get(f"{base}/pod-resource-metrics", headers=headers, params=params).json()
requests.get(f"{base}/realTimeLogs", headers=headers, params={"logType": "stderr", "limit": 200}).json()
```

## Verified

- Routes, required fields, enums and the PATCH stop-and-restart rule above: both published specs (6.3.1 and 6.4.0), 2026-10-12. The write operations were not executed against a live deployment.
- Read-only against a live Domino Cloud deployment (`GET /version` returned `6.4.0`), 2026-10-12: `GET /api/gen-ai/beta/default-endpoint-environment` returned `{id, name}` with no `revisionId`; `GET /api/gen-ai/beta/endpoints` returned `{"items": [...]}` with the documented keys, `generalAccess` values `Viewer` and `Consumer`, `currentVersion.status` `Stopped`, `currentVersion.configuration` carrying `vllmArguments`, `maxNumberOfSequences` and `tensorParallelism`, and `url` on the apps host; `GET /api/aigateway/v1/endpoints` returned 404 (legacy gateway absent on Cloud).
