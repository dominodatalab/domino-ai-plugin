# Model Export API: build an endpoint image and push it to your registry

Product page: https://docs.domino.ai/cloud/platform-capabilities/features/models/integrate-ci-cd-workflows
(same content on the 6.3 page). The API turns a project plus an inference function into the same
container image a Domino endpoint runs (environment, project files, Flask or Plumber harness,
auth and load-balancing layer) and pushes it to a registry you own. The other targets (NVIDIA
Fleet Command, Snowflake, SageMaker) and the Exports page: [EXPORT-TARGETS.md](./EXPORT-TARGETS.md).

**Every `/v4/...` route in this file is Domino Internal API, may change between Domino versions.**
They are not in the Public API spec; each cluster documents them under
`https://<domino-domain>/docs` (`openapi-internal.json`). The routes come from the product page
(Cloud and 6.3 are identical); the field lists and required flags below come from one Domino
Cloud cluster's reference (reporting version 6.4.0). Before relying on them on Domino 6.3, read
that deployment's own `/docs/openapi/openapi-internal.json`.

## Authentication for a pipeline

A CI/CD runner is outside Domino, so use the deployment URL and a Bearer token:

```bash
BASE="$DOMINO_API_HOST"                      # outside Domino: export DOMINO_API_HOST=<deployment URL users open in a browser>
AUTH="Authorization: Bearer $DOMINO_TOKEN"   # Personal Access Token or service-account token from the CI secret store
```

Inside a Domino run use `$DOMINO_API_PROXY` with no header instead. Do not use
`X-Domino-Api-Key` even though the product page still shows it.

## Sequence

### 1. Build the image

```bash
curl -sS -X POST "$BASE/v4/models/buildModelImage" -H "$AUTH" -H "Content-Type: application/json" -d '{
  "projectId": "<project id>",
  "modelName": "credit-risk",
  "inferenceFunctionFile": "model.py",
  "inferenceFunctionToCall": "predict",
  "environmentId": "<environment id>",
  "logHttpRequestResponse": false,
  "description": "built by pipeline run 123"
}'
```

| Field | Required | Meaning |
|---|---|---|
| `projectId` | yes | project whose files and environment are packaged |
| `modelName` | yes | name of the model in Domino |
| `inferenceFunctionFile`, `inferenceFunctionToCall` | yes | file and function Domino calls per request |
| `logHttpRequestResponse` | yes (cluster reference) | log request and response payloads for the model |
| `environmentId` | no | defaults to the project default environment |
| `modelId` | no | build a new version of this existing model instead of creating a model |
| `description` | no | free text |

Response: `202 Accepted` with `modelId` and `modelVersionId` (the build continues in the
background). On the cluster reference the response schema is declared as an array wrapping that
object; python-domino's examples read it as an object. Handle both.

### 2. Poll the build

```bash
curl -sS "$BASE/v4/models/$MODEL_ID/$MODEL_VERSION_ID/getBuildStatus" -H "$AUTH"
# {"modelId": "...", "modelVersionId": "...", "status": "Preparing" | "Building" | "Complete" | "Failed"}
curl -sS "$BASE/v4/models/$MODEL_ID/$MODEL_VERSION_ID/getBuildLogs" -H "$AUTH"   # adds "logs"
```

Stop on `Complete` or `Failed`. Compare status values case-insensitively; the product page
capitalises them, python-domino's example tests lowercase `complete` and `failed`.

### 3. Export to your registry

Encode the body with a JSON encoder that reads the credentials from the environment, and send
it on stdin. Splicing `$REGISTRY_PASSWORD` into a JSON string literal breaks the payload on a
`"` and silently alters it on a `\`; the encoder also keeps the secrets out of `ps` output and
shell traces.

```bash
python3 -c 'import json, os, sys
json.dump({"registryUrl": "quay.io", "repository": "acme/credit-risk", "tag": "1.4.0",
           "username": os.environ["REGISTRY_USER"], "password": os.environ["REGISTRY_PASSWORD"]}, sys.stdout)' \
| curl -sS -X POST "$BASE/v4/models/$MODEL_ID/$MODEL_VERSION_ID/exportImageToRegistry" \
    -H "$AUTH" -H "Content-Type: application/json" --data-binary @-
# -> {"modelId", "modelVersionId", "exportId", "status"}
```

With `jq` instead of Python: `jq -n '{registryUrl: "quay.io", repository: "acme/credit-risk", tag: "1.4.0", username: env.REGISTRY_USER, password: env.REGISTRY_PASSWORD}'`
piped into the same `curl ... --data-binary @-` (`env.NAME` reads the variable without putting
it on the command line, unlike `--arg`).

`registryUrl` and `repository` are required; `tag`, `username`, `password` are optional on the
cluster reference but a private registry needs the credentials. Derive the tag from the model
version or the pipeline run so re-runs never collide (the product page documents a collision
failure for the NVIDIA export; do not count on other registries overwriting silently either).

### 4. Poll the export, then read its logs

```bash
curl -sS "$BASE/v4/models/$EXPORT_ID/getExportImageStatus" -H "$AUTH"
# {"modelId", "modelVersionId", "exportId", "status", "errorMessage"?}
curl -sS "$BASE/v4/models/$EXPORT_ID/getExportLogs" -H "$AUTH"
# {"modelId", "modelVersionId", "exportId", "status", "logs"}
```

Public API alternative for the logs, present in both published specs and keyed by the Model API
ids you can list with `GET /api/modelServing/v1/modelApis?projectId=...` and
`GET /api/modelServing/v1/modelApis/{modelApiId}/versions`:

```text
GET /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/exportLogs[?sinceTimeNano=...]
-> {"modelId", "modelVersionId", "status", "logs": [{"timestamp", "timeNano", "log", "streamType", "tags"}]}
```

## Pipeline script (bash, any CI system)

```bash
#!/usr/bin/env bash
# scripts/export-model.sh. Needs: DOMINO_API_HOST, DOMINO_TOKEN, PROJECT_ID, ENVIRONMENT_ID, REGISTRY_USER, REGISTRY_PASSWORD, TAG
set -euo pipefail
BASE="$DOMINO_API_HOST"
AUTH="Authorization: Bearer $DOMINO_TOKEN"
# field <key>: print one key from a JSON object (or from the first element if the server wraps it in an array)
field() { python3 -c 'import json,sys; d=json.load(sys.stdin); d=d[0] if isinstance(d,list) else d; print(d[sys.argv[1]])' "$1"; }
lower() { tr "[:upper:]" "[:lower:]"; }
# export_body: the exportImageToRegistry payload, JSON-encoded from the environment so the credentials are never spliced into a string or echoed
export_body() { python3 -c 'import json, os, sys; json.dump({"registryUrl": "quay.io", "repository": "acme/credit-risk", "tag": os.environ["TAG"], "username": os.environ["REGISTRY_USER"], "password": os.environ["REGISTRY_PASSWORD"]}, sys.stdout)'; }

build=$(curl -sSf -X POST "$BASE/v4/models/buildModelImage" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"projectId\":\"$PROJECT_ID\",\"modelName\":\"credit-risk\",\"inferenceFunctionFile\":\"model.py\",\"inferenceFunctionToCall\":\"predict\",\"environmentId\":\"$ENVIRONMENT_ID\",\"logHttpRequestResponse\":false}")
model_id=$(echo "$build" | field modelId); version_id=$(echo "$build" | field modelVersionId)

until status=$(curl -sSf "$BASE/v4/models/$model_id/$version_id/getBuildStatus" -H "$AUTH" | field status | lower); \
      [ "$status" = complete ] || [ "$status" = failed ]; do sleep 20; done
[ "$status" = complete ] || { curl -sS "$BASE/v4/models/$model_id/$version_id/getBuildLogs" -H "$AUTH"; exit 1; }

export_id=$(export_body | curl -sSf -X POST "$BASE/v4/models/$model_id/$version_id/exportImageToRegistry" \
  -H "$AUTH" -H "Content-Type: application/json" --data-binary @- | field exportId)

until status=$(curl -sSf "$BASE/v4/models/$export_id/getExportImageStatus" -H "$AUTH" | field status | lower); \
      [ "$status" = complete ] || [ "$status" = failed ]; do sleep 20; done
curl -sS "$BASE/v4/models/$export_id/getExportLogs" -H "$AUTH"
[ "$status" = complete ]
echo "quay.io/acme/credit-risk:$TAG"
```

### GitHub Actions job that runs it

Secrets hold the Domino token (a Personal Access Token, or a service-account token for a
pipeline that acts as nobody in particular) and the registry credentials; repository variables
hold the ids. No API key anywhere.

```yaml
name: export-model
on:
  workflow_dispatch:
jobs:
  export:
    runs-on: ubuntu-latest
    env:
      DOMINO_API_HOST: ${{ vars.DOMINO_API_HOST }}        # https://<deployment URL>
      DOMINO_TOKEN: ${{ secrets.DOMINO_TOKEN }}           # PAT or service-account token, sent as Bearer
      PROJECT_ID: ${{ vars.DOMINO_PROJECT_ID }}
      ENVIRONMENT_ID: ${{ vars.DOMINO_ENVIRONMENT_ID }}
      REGISTRY_USER: ${{ secrets.REGISTRY_USER }}
      REGISTRY_PASSWORD: ${{ secrets.REGISTRY_PASSWORD }}
      TAG: ${{ github.sha }}
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/export-model.sh
```

Jenkins: the same script with `withCredentials` binding `DOMINO_TOKEN`, `REGISTRY_USER` and
`REGISTRY_PASSWORD`.

## python-domino methods (reference only)

python-domino wraps the export calls but not the build call. Use the REST calls above in
examples; the mapping is here so you can read existing code. Usage of the client itself:
[domino-python-sdk](../domino-python-sdk/SKILL.md). Routes from `domino/routes.py`:

| Method | Calls | API |
|---|---|---|
| `models_list()` | `GET /v1/projects/{owner}/{project}/models` | legacy v1, not in the Public API, may change between Domino versions |
| `model_versions_get(model_id)` | `GET /v1/models/{modelId}/versions` (versions carry `_id`, `metadata.number`) | legacy v1, as above |
| `model_version_export(model_id, model_version_id, registry_host, registry_username, registry_password, repository_name, image_tag)` | `POST /v4/models/{modelId}/{modelVersionId}/exportImageToRegistry` | internal API |
| `model_version_sagemaker_export(...)` (same arguments) | `POST /v4/models/{modelId}/{modelVersionId}/exportImageForSagemaker` | internal API; see [EXPORT-TARGETS.md](./EXPORT-TARGETS.md#amazon-sagemaker) |
| `model_version_export_status(model_export_id)` | `GET /v4/models/{exportId}/getExportImageStatus` | internal API |
| `model_version_export_logs(model_export_id)` | `GET /v4/models/{exportId}/getExportLogs` | internal API |

Public API replacements for the two listing calls: `GET /api/modelServing/v1/modelApis?projectId=...`
and `GET /api/modelServing/v1/modelApis/{modelApiId}/versions`.

## Run the exported image in staging

The image listens on **8888** and serves predictions at `/model`. Sample manifests from the
product page (image, names and ports are yours to change):

```yaml
# my-model-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: mymodel, labels: {app: mymodel}}
spec:
  replicas: 1
  selector: {matchLabels: {app: mymodel}}
  template:
    metadata: {labels: {app: mymodel}}
    spec:
      containers:
        - name: mymodel
          image: quay.io/acme/credit-risk:1.4.0
          ports: [{name: mymodel, containerPort: 8888}]
---
# my-model-service.yaml
apiVersion: v1
kind: Service
metadata: {name: mymodel-service}
spec:
  type: NodePort
  selector: {app: mymodel}
  ports: [{nodePort: 31440, name: mymodel-port, port: 90, targetPort: 8888}]
```

```bash
kubectl apply -f my-model-deployment.yaml -f my-model-service.yaml   # add an imagePullSecret for a private registry
PORT=$(kubectl get service/mymodel-service -o jsonpath='{.spec.ports[?(@.name=="mymodel-port")].nodePort}')
curl -sS -X POST "http://<node ip>:$PORT/model" -H "Content-Type: application/json" -d '{"data": {"start": 1, "stop": 100}}'
```

The `data` object is passed to your inference function as its arguments, exactly as a Domino
endpoint would. Promote the same image to production once staging tests pass.

## `.modelignore`

By default every project file is copied into the image. Put file names, folder names or UNIX
shell patterns in `.modelignore` at the project root to leave them out (training data, notebooks,
large artifacts the model does not load).
