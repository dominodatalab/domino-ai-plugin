# Domino Models API

Model APIs (hosted prediction endpoints), Model Deployments, the Registered Models
registry, and how to invoke an endpoint. Routes marked **Cloud** exist only on Domino
Cloud. Lifecycle guidance and the v1/v2 registry split:
[API-MODEL-SERVING.md](./API-MODEL-SERVING.md) and
[domino-model-serving](../domino-model-serving/SKILL.md); deployment workflow and
monitoring: [domino-model-endpoints](../domino-model-endpoints/SKILL.md).

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication). Invoking an endpoint
uses that endpoint's own access token instead (below); to create one, see
[Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens) in `domino-model-endpoints`.

## Model APIs

### List

```
GET /api/modelServing/v1/modelApis
```

Filters: `projectId`, `environmentId`, `name` (regular expression),
`registeredModelName`, `registeredModelVersion`, `limit` (default 25), `offset`,
`orderBy` (`<field> ASC|DESC`). Response: `{"items": [...], "metadata": {...}}`. Each item
has `id`, `name`, `description`, `isArchived`, `environmentId`, `hardwareTierId`,
`replicas`, `isAsync`, `routingMode`, `access` (`isPublic`, `accessTokens[]`),
`activeVersion` (`id`, `number`, `dataPlaneId`, `deployment.status`, `deployment.isPending`),
`collaborators`, `healthCheck`, `metadata`.

```python
items = requests.get(f"{base_url}/api/modelServing/v1/modelApis", headers=headers,
                     params={"projectId": project_id}).json()["items"]
```

### Create

```
POST /api/modelServing/v1/modelApis        -> the Model API record (spec says 201; Domino returns 200)
```

Required: `name`, `description`, `environmentId`, `isAsync`, `strictNodeAntiAffinity`,
`environmentVariables` (array of `{"key", "value"}`, may be empty), `version`. Optional:
`hardwareTierId`, `replicas`, `resourceQuotaId`, `bundleId` (governance).

`version` (required fields `projectId`, `source`, `logHttpRequestResponse`,
`monitoringEnabled`): `source.type` is `File` (`file`, `function`, optional
`excludeFiles`) or `Registry` (`registeredModelName`, `registeredModelVersion`); optional
`description`, `commitId`, `environmentId`, `shouldDeploy`, `recordInvocation`,
`predictionDatasetResourceId`, `provenanceCheckpointId`.

```python
model_api = requests.post(f"{base_url}/api/modelServing/v1/modelApis", headers=headers, json={
    "name": "customer-churn",
    "description": "Predicts customer churn probability",
    "environmentId": env_id,
    "hardwareTierId": "small-k8s",
    "isAsync": False,
    "strictNodeAntiAffinity": False,
    "environmentVariables": [],
    "version": {
        "projectId": project_id,
        "description": "initial version",
        "source": {"type": "File", "file": "serve.py", "function": "predict"},
        "logHttpRequestResponse": False,
        "monitoringEnabled": False,
        "shouldDeploy": True,
    },
}).json()
model_api_id = model_api["id"]
```

Omitting `hardwareTierId` uses the project default tier (not the deployment's
`isDefaultForModelApi` tier). An access token is created automatically (id only in the
response; its value is in the UI or in the fragment returned by the token create route,
[Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens)).
`activeVersion.deployment` is absent until the build finishes; poll until it is
`{"status": "Running", "isPending": false}`.

```python
import time
deadline = time.time() + 1800
while time.time() < deadline:
    api = requests.get(f"{base_url}/api/modelServing/v1/modelApis/{model_api_id}", headers=headers).json()
    deployment = (api.get("activeVersion") or {}).get("deployment")   # absent until deployed
    if deployment and not deployment["isPending"]:
        print("status:", deployment["status"]); break
    time.sleep(15)
```

### Get, update, delete

```
GET    /api/modelServing/v1/modelApis/{modelApiId}
PUT    /api/modelServing/v1/modelApis/{modelApiId}
DELETE /api/modelServing/v1/modelApis/{modelApiId}
```

The GET response carries `access.accessTokens[]` (token ids and metadata, not the secret
values) and, once deployed, `activeVersion.deployment.status`. It does not include the
invocation URL, and no other route does: the URL is the deployment's external URL (the one
you sign in at) plus `/models/{modelApiId}/latest/model`, as shown on the Model API's page.

`DELETE` on a running Model API returns `500 Model API with id <id> is running`. The
Public API has no stop route; stop it first with
`POST /v4/models/{modelApiId}/{modelApiVersionId}/stopModelDeployment` (body `{}`;
non-public route; may change in a future Domino version) or from the UI, then `DELETE`. After
deletion `GET` returns 404 and the list no longer includes the record.

**Cloud only:** `PUT /api/modelServing/beta/modelApis/{modelApiId}/access` saves
`visibility` (`Public`/`Discoverable`/`Private`) and the **complete** collaborator list
(`collaborators[]` with `id`, `isOrganization`, `role` `Owner`/`Editor`/`Operator`/`Viewer`)
in one request: anyone omitted loses the assigned role, including the caller, and the
last Owner cannot be omitted, so load the current list from
`GET .../collaborators` and send it back with your change. `POST .../collaborators`
adds one principal (fails if the id is already assigned; only Owners can add);
`PUT .../collaborators/{collaboratorId}` changes a role; `GET/PUT .../visibility`
reads or sets visibility alone (the v1 record's `access.isPublic` is a separate legacy
flag); `GET .../consumer/access` reports the caller's access.

### Versions and logs

```
GET  /api/modelServing/v1/modelApis/{modelApiId}/versions
POST /api/modelServing/v1/modelApis/{modelApiId}/versions        -> the version record (spec says 201; Domino returns 200)
GET  /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}
GET  /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/buildLogs
GET  /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/exportLogs
GET  /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/instanceLogs
```

New-version body is the `version` object above (`projectId`, `source`,
`logHttpRequestResponse`, `monitoringEnabled` required; `description` optional). The
response includes `environmentRevisionId` and `number`, and `deployment.status` /
`deployment.isPending` once deployed. `shouldDeploy: false` still builds the image (the
build logs complete) but creates no deployment.

## Model Deployments

```
GET, POST          /api/modelServing/v1/modelDeployments
GET, PATCH, DELETE /api/modelServing/v1/modelDeployments/{modelDeploymentId}
POST               /api/modelServing/v1/modelDeployments/{modelDeploymentId}/start | /stop
GET                /api/modelServing/v1/modelDeployments/{modelDeploymentId}/versions[/{version}]
GET                /api/modelServing/v1/modelDeployments/{modelDeploymentId}/logs/{logSuffix}
GET                /api/modelServing/v1/modelDeployments/{modelDeploymentId}/credentials[/{operationType}]
```

Create body, required fields: `name`, `deploymentTargetId`, `resourceConfigurationId`,
`configuration` (`deploymentType` with `type` `SYNC_ENDPOINT` or `ASYNC_ENDPOINT`,
`sharedConfig`, `modelConfigs`; plus top-level `sharedConfig` and `modelConfigs`), and
`models[]`, each with `name`, `environmentId` and `source`
(`registeredModelName`, `registeredModelVersion`, `registeredModelType: "MODELREGISTRY"`).
Optional: `description`, `collaborators[]` (`id`, `role` `OWNER`/`CONSUMER`),
`isGloballyAccessible`. Deployment targets and resource configurations come from
`GET /api/admin/v1/deploymentTargets/selectable` and
`.../{deploymentTargetId}/resourceConfigurations`; the `sharedConfig` / `modelConfigs`
shape follows the target type's `effectiveModelDeploymentSchema`. The record's
`status.state` is one of `STARTING`, `RUNNING`, `UPDATING`, `STOPPING`, `STOPPED`,
`FAILED`, `DELETING`, `DELETED`.

## Registered models (registry)

List and register use v2; per-model reads use v1 keyed by **model name**. Version
creation goes through `POST /api/registeredmodels/v2` as well: the v1 route
`POST /api/registeredmodels/v1/{modelName}/versions` is deprecated.

```
GET  /api/registeredmodels/v2            params: projectId, searchPattern, modelCategory (genai|ml), pageToken, maxResults (default 25), orderBy
POST /api/registeredmodels/v2            register a model or add a version
GET  /api/registeredmodels/v1            ML models only; v2 returns all categories by default
GET  /api/registeredmodels/v1/{modelName};  PATCH /api/registeredmodels/v1/{modelName}
GET  /api/registeredmodels/v1/{modelName}/versions;  GET .../versions/{version};  GET .../versions/{version}/modelapis
GET  /api/registeredmodels/v2/{modelName}/versions[/{version}]
```

Register (`POST /api/registeredmodels/v2`) requires `modelName`, `modelSource` and
`create` (true to create the registered model; false to add a version to an existing
one, and `true` on an existing name is a 400). `modelSource` is
`{"sourceType": "mlflow", "mlflowSource": {"experimentRunId": "...", "loggedModelId": "m-..."}}`
(or `"artifactPath": "..."` instead of `loggedModelId`), or
`{"sourceType": "huggingface", "huggingFaceSource": {"modelId": "org/model", "modelRevision": "...", "huggingFaceToken": "..."}}`.
Optional: `description`, `discoverable`, `modelCategory` (`genai`, `ml`), `modelType`,
`projectId` (required for Hugging Face sources only; MLflow sources take the project from
the run). Response: `{"registeredModel": {...}, "modelVersion": {...}}`.

**Use `loggedModelId` for models logged with MLflow 3.** MLflow 3 clients store
`log_model` output as a LoggedModel (`m-<id>`) rather than as a run artifact, so a
version registered with `artifactPath: "model"` points at a path that does not exist and
`mlflow.pyfunc.load_model("models:/<name>/<version>")` fails. Get the id from the run
(`mlflow.last_logged_model()`, or the `model_id` on the logged model info).

```python
result = requests.post(f"{base_url}/api/registeredmodels/v2", headers=headers, json={
    "modelName": "fraud-classifier",
    "description": "Random forest fraud classifier",
    "create": True,
    "modelSource": {"sourceType": "mlflow",
                    "mlflowSource": {"experimentRunId": run_id, "loggedModelId": logged_model_id}},
}).json()
print(result["modelVersion"]["modelVersion"])
```

List responses use `{"items": [...], "metadata": {"nextPageToken", ...}}`; page with
`pageToken` / `maxResults` (both v1 and v2), not `offset` / `limit`.

## Invoking a Model API

Use the invocation URL shown on the Model API's page (the deployment's external URL plus
`/models/{modelApiId}/latest/model`; not the in-run `$DOMINO_API_HOST`), with the
endpoint's access token: the user's, or one you create and store
([Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens)). Per
https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/domino-endpoint-authorization:

- Restricted **synchronous** endpoint: HTTP Basic, username and password both the token.
- Restricted **asynchronous** endpoint: `Authorization: Bearer <token>`.
- Unrestricted endpoint: no credentials.

```python
# Synchronous (URL copied from the Model API page in Domino)
response = requests.post(
    model_api_url,
    auth=(model_access_token, model_access_token),
    json={"data": {"features": [1.0, 2.0, 3.0, 4.0]}},
)
prediction = response.json()
```

Asynchronous endpoints use the Public API routes with the endpoint's own access token.
Call them on the deployment URL (the same base the Model API page shows), not through
`$DOMINO_API_PROXY`, which would inject a platform token. From outside Domino that is the
URL you sign in at; from inside a run, prefer the deployment URL as well, since the
in-run `DOMINO_API_HOST` base may reject an endpoint token.

```python
import time
async_base = "https://<deployment-url>"      # the host the Model API page shows
auth = {"Authorization": f"Bearer {model_access_token}"}

submitted = requests.post(f"{async_base}/api/modelApis/async/v1/{model_api_id}", headers=auth,
                          json={"parameters": {"input_file": "s3://bucket/data.csv"}}).json()
prediction_id = submitted["asyncPredictionId"]

deadline = time.time() + 1800
while time.time() < deadline:
    result = requests.get(f"{async_base}/api/modelApis/async/v1/{model_api_id}/{prediction_id}",
                          headers=auth).json()
    if result["status"] in ("Succeeded", "Failed"):
        break
    time.sleep(5)                                   # Pending or Processing
print(result["status"], result.get("result"), result.get("errors"))
```

`parameters` is required on submit. The poll response has `asyncPredictionId`, `status`
(`Pending`, `Processing`, `Succeeded`, `Failed`), `result` and `errors[]`.

## python-domino

`models_list()`, `model_publish(file, function, environment_id, name, description, files_to_exclude=None)`,
`model_versions_get(model_id)`, `model_version_publish(model_id, file, function, environment_id, description, files_to_exclude=None)`
and the `model_version_export*` methods call `/v1/models` and `/v4/models`, which are
non-public routes; they may change in a future Domino version. Signatures and a publish example:
[SDK-EXAMPLES.md](./SDK-EXAMPLES.md#model-apis-and-apps); the export routes and the build call
the SDK lacks: [EXPORT-API.md](../domino-model-delivery/EXPORT-API.md); the NVIDIA Fleet Command,
Snowflake and SageMaker targets: [EXPORT-TARGETS.md](../domino-model-delivery/EXPORT-TARGETS.md).
There is no `model_get` or `runs_wait`.
