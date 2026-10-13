# Model serving REST (agent reference)

Orientation for `/api/modelServing/v1` and the registered-models routes. Route details
and bodies: [API-MODELS.md](./API-MODELS.md). Pitfalls and workflow:
[domino-model-serving](../domino-model-serving/SKILL.md).

Authentication: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Registered models v1 vs v2

| Operation | Path | Notes |
|-----------|------|--------|
| List, register, add a version | `/api/registeredmodels/v2` | `pageToken` / `maxResults` pagination; `modelCategory` filter; `create: false` adds a version to an existing model |
| Get, update, read versions, model APIs for a version | `/api/registeredmodels/v1/{modelName}/...` | Path key is the **model name**, not an id |
| Versions (v2 read) | `/api/registeredmodels/v2/{modelName}/versions[/{version}]` | |

Both families are in both specs; use v2 for discovery and writes, v1 for per-model reads.
`POST /api/registeredmodels/v1/{modelName}/versions` is marked deprecated in both specs
(since 6.2.1); do not use it for new automation.

## Model Serving (`/api/modelServing/v1`)

Common flow:

```
POST /api/modelServing/v1/modelApis                                    create (body includes the first version)
GET  /api/modelServing/v1/modelApis/{modelApiId}                       poll activeVersion.deployment.status
POST /api/modelServing/v1/modelApis/{modelApiId}/versions              new version from a file or registry entry
GET  /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/buildLogs
```

Read `activeVersion.deployment.status` and `activeVersion.deployment.isPending` to know
when a version is serving; `deployment` is absent from the record until the first build
finishes. The Model API record does not contain the invocation URL; copy it from the
Model API's page in Domino. Async batch prediction uses
`/api/modelApis/async/v1/{asyncModelId}` ([API-MODELS.md](./API-MODELS.md#invoking-a-model-api)).

## Model Deployments vs Model APIs

`/api/modelServing/v1/modelDeployments` deploys registered models to a deployment target
(`/api/admin/v1/deploymentTargets`) with a `SYNC_ENDPOINT` or `ASYNC_ENDPOINT`
configuration and has explicit `start` / `stop` routes. `modelApis` are the classic
file-or-registry Model APIs whose versions deploy on create (`shouldDeploy`). They are
separate resources with separate lifecycles; do not mix their ids.

## Lifecycle

- A running Model API cannot be deleted (`500 ... is running`). Stop it first (`POST /v4/models/{modelApiId}/{modelApiVersionId}/stopModelDeployment`,
  internal API, may change between Domino versions, or the UI), then `DELETE`; afterwards
  `GET` returns 404 and the record is gone from the list.
- A Model Deployment has `start` and `stop`; after `stop` or `DELETE`, `GET` the resource
  to confirm the state before issuing the next call.
- Collaborator and visibility routes under `/api/modelServing/beta` exist only in the
  Cloud spec.

## MLflow vs REST

| Need | Use |
|------|-----|
| Experiment tracking, run artifacts | `MLFLOW_TRACKING_URI` and the MLflow client ([domino-experiment-tracking](../domino-experiment-tracking/SKILL.md)) |
| Registry record, governance attachments | `/api/registeredmodels/...` |
| Hosted prediction endpoint | `/api/modelServing/v1/modelApis` plus the endpoint's invocation URL |

## GenAI endpoints

`GET/POST /api/gen-ai/beta/endpoints`, `GET/DELETE .../{endpointId}`,
`GET/PATCH .../versions/{versionNumber}`, `.../start`, `.../stop`, `.../realTimeLogs`,
`.../request-metrics`, `.../pod-resource-metrics`, `.../vllm-*-metrics`,
`GET /api/gen-ai/beta/default-endpoint-environment`,
`GET /api/gen-ai/beta/vanity-url-availability/{vanityUrl}` are in both specs. Invoke a
GenAI endpoint at the URL the endpoint's page shows, not at a management route. These
are Domino-hosted LLM endpoints; the routes, bodies and calling pattern are in
[domino-llm-access/HOST-AN-LLM-API.md](../domino-llm-access/HOST-AN-LLM-API.md).

## Discovery

OpenAPI and route discovery: [API-SPECS.md](../domino-api-intro/API-SPECS.md).
