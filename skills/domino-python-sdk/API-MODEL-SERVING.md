# Model serving REST (agent reference)

Orientation for `/api/modelServing/v1` and the registered-models routes. Route details
and bodies: [API-MODELS.md](./API-MODELS.md). Pitfalls and workflow:
[domino-model-serving](../domino-model-serving/SKILL.md).

Authentication: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Registered models

| Operation | Path | Notes |
|-----------|------|--------|
| List, register from an experiment run | `/api/registeredmodels/v1` | `pageToken` / `maxResults` pagination |
| Get, update, read versions, model APIs for a version | `/api/registeredmodels/v1/{modelName}/...` | Path key is the **model name**, not an id |
| Add a version from an experiment run | `POST /api/registeredmodels/v1/{modelName}/versions` | |

Domino 6.1 has only the v1 registry routes. Bodies: [API-MODELS.md](./API-MODELS.md#registered-models-registry).

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
finishes. The Model API record does not contain the invocation URL and no route returns
it: it is the deployment's external URL plus `/models/{modelApiId}/latest/model`, as shown
on the Model API's page. Async batch prediction uses
`/api/modelApis/async/v1/{asyncModelId}` ([API-MODELS.md](./API-MODELS.md#invoking-a-model-api)).

## Model Deployments vs Model APIs

`/api/modelServing/v1/modelDeployments` deploys registered models to a deployment target
(`/api/admin/v1/deploymentTargets`) with a `SYNC_ENDPOINT` or `ASYNC_ENDPOINT`
configuration and has explicit `start` / `stop` routes. `modelApis` are the classic
file-or-registry Model APIs whose versions deploy on create (`shouldDeploy`). They are
separate resources with separate lifecycles; do not mix their ids.

## Lifecycle

- A running Model API cannot be deleted (`500 ... is running`): stop it first, then
  `DELETE` ([API-MODELS.md](./API-MODELS.md#get-update-delete); worked requests in
  [LIFECYCLE.md](../domino-model-serving/LIFECYCLE.md#stop-and-delete)).
- A Model Deployment has `start` and `stop`; after `stop` or `DELETE`, `GET` the resource
  to confirm the state before issuing the next call.

## MLflow vs REST

| Need | Use |
|------|-----|
| Experiment tracking, run artifacts | `MLFLOW_TRACKING_URI` and the MLflow client ([domino-experiment-tracking](../domino-experiment-tracking/SKILL.md)) |
| Registry record | `/api/registeredmodels/v1/...` |
| Hosted prediction endpoint | `/api/modelServing/v1/modelApis` plus the endpoint's invocation URL |

## Discovery

OpenAPI and route discovery: [API-SPECS.md](../domino-api-intro/API-SPECS.md).
