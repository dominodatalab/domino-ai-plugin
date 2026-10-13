# Domino Model Registry

Domino's registry stores MLflow registered models with Domino additions: project-scoped access control, model cards with lineage, discoverability across projects, and deployment to Domino endpoints. Use the MLflow client for versions, aliases and tags, and Domino's `/api/registeredmodels/...` routes for Domino-only attributes. R models are not supported.

## Register

### From a training run (code)

```python
import mlflow
from mlflow.models import infer_signature

with mlflow.start_run(run_name="rf-candidate") as run:
    model.fit(X_train, y_train)
    signature = infer_signature(X_test, model.predict(X_test))
    mlflow.sklearn.log_model(
        model, "model",
        signature=signature, input_example=X_test[:5],
        registered_model_name="churn-rf",        # creates the registered model if missing, adds version N
    )
```

Or register an existing run's model: `mlflow.register_model("runs:/<run_id>/model", "churn-rf")`. Log a signature and input example; MLflow uses them to infer the `requirements.txt` and input schema that an endpoint built from the registry relies on. MLflow 3 renames the positional `artifact_path` to `name=` (`log_model(model, name="model", ...)`); the positional form still works in 2.x and 3.x, with a deprecation warning in 3.x.

### From the UI

**Experiments** > experiment > run > **Register model from run**. Tick **Model Discoverability** to make the model visible to users outside the project (the default is set by the admin configuration `com.cerebro.domino.registeredmodels.newModelDiscoverability.default`).

### By REST (Domino)

`POST /api/registeredmodels/v2` registers from an MLflow run or a Hugging Face model (`modelName`, `modelSource{sourceType, mlflowSource{experimentRunId, loggedModelId|artifactPath}|huggingFaceSource{modelId}}`, `create`, optional `projectId`, `description`, `discoverable`). With an MLflow 3 client pass `loggedModelId` (`m-<id>`): a version registered with `artifactPath: "model"` points at a run artifact that MLflow 3 never wrote and does not load. `POST /api/registeredmodels/v1/{modelName}/versions` is deprecated. Worked example: [LIFECYCLE.md](../domino-model-serving/LIFECYCLE.md).

## Versions, aliases and tags

MLflow stages (`Staging`, `Production`, `transition_model_version_stage`) are deprecated upstream since MLflow 2.9. Domino's registry still shows `current_stage` for compatibility, but promotion should use **aliases** (one version per alias name) and **tags**. On Domino Cloud aliases work through the client (`set_registered_model_alias`, `get_model_version_by_alias`, `get_registered_model(name).aliases`, `mlflow.pyfunc.load_model("models:/<name>@champion")`) and through `/api/2.0/mlflow/registered-models/alias` on the deployment URL with a bearer token (`GET ?name=...&alias=...` returns the version; `POST` with `{"name": ..., "alias": ..., "version": ...}` sets one). On Domino 6.3 run that GET first; a 404 means the server predates aliases, so use tags instead.

```python
import mlflow
from mlflow import MlflowClient

client = MlflowClient()
name = "churn-rf"

versions = client.search_model_versions(f"name='{name}'")          # all versions
latest = str(max(int(v.version) for v in versions))

client.set_model_version_tag(name, latest, "validated", "true")
client.set_registered_model_tag(name, "team", "risk")

client.set_registered_model_alias(name, "champion", latest)        # promote
client.set_registered_model_alias(name, "challenger", "2")         # a second pointer

champion = client.get_model_version_by_alias(name, "champion")
model = mlflow.sklearn.load_model(f"models:/{name}@champion")      # load by alias
client.delete_registered_model_alias(name, "challenger")           # demote
```

Load a specific version with `models:/churn-rf/3`. Search: `client.search_registered_models(filter_string="name LIKE 'churn%'")`, `client.search_model_versions("name='churn-rf' and tags.validated='true'")`. Raw REST instead of the client: `DELETE /api/2.0/mlflow/registered-models/alias` needs a JSON body `{"name": ..., "alias": ...}`; with query parameters only it returns `403 cannot parse POST body as JSON` (the Python client sends the body itself). Descriptions: `client.update_model_version(name, version, description=...)`. Deleting (`client.delete_model_version`, `client.delete_registered_model`) removes lineage; prefer removing the alias and tagging `status=retired`.

## Model cards and lineage

Every registered model has a model card. Domino fills in the code commit, environment, workspace settings, datasets and data sources of the training run and links each version to its run; you add Markdown:

```python
with open("model_card.md") as f:
    client.update_registered_model(name, f.read())   # the description is the model card body
```

Or edit it under **Models** > model > **Overview**. From a version you can walk back to the run: `run = mlflow.get_run(client.get_model_version(name, "3").run_id)`.

## Access, discoverability and Domino routes

- Who can view, edit or deploy follows the **project** roles: https://docs.domino.ai/cloud/admin/identity-and-access/manage-users/roles#model-registry-actions.
- **Global Models** lists models marked discoverable (anyone can read a limited model card and request access); **Collaborating Models** lists what you can use. Toggle discoverability on the model card (System Admin or project owner) or by API.

| Task | Route |
|------|-------|
| List registered models | `GET /api/registeredmodels/v2?projectId=&searchPattern=&maxResults=25` (token-paginated with `pageToken`) |
| Names only | `GET /api/registeredmodels/v1/names` |
| Get a model | `GET /api/registeredmodels/v1/{modelName}` (`name`, `description`, `latestVersion`, `project`, `tags`, `ownerUsername`, `requestingUserAccess`; it returns neither `discoverable` nor aliases, which only MLflow's API shows) |
| Update description or discoverability | `PATCH /api/registeredmodels/v1/{modelName}` with `{"description": "...", "discoverable": true}` (200; the description persists, `discoverable` is not echoed back by `GET`) |
| Versions | `GET /api/registeredmodels/v1/{modelName}/versions`, `GET .../versions/{version}` |
| Endpoints serving a model or version | `GET /api/registeredmodels/v1/{modelName}/modelapis`, `GET .../versions/{version}/modelapis` |
| Unregistered models in an experiment | `GET /api/registeredmodels/v1/experiments/{experimentId}/unregistered-models` |

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)   # outside a run: PAT or service-account token
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$DOMINO_API_HOST/api/registeredmodels/v1/churn-rf" -d '{"discoverable": true}'
```

`modelName` in these paths is the registry name, not an id. With `DOMINO_API_PROXY` set, call `$DOMINO_API_PROXY/api/...` with no header. The MLflow REST API is also reachable on the deployment URL under `/api/2.0/mlflow/...` with the same bearer token.

## Deploy a registered version

Create a Domino endpoint whose source is the registry entry: in the **Create Domino Endpoint** form choose the registered model and version as the source, or `POST /api/modelServing/v1/modelApis` with `version.source = {"type": "Registry", "registeredModelName": "churn-rf", "registeredModelVersion": 3}`. The `requirements.txt` MLflow inferred when the model was logged is installed into the endpoint image. See `domino-model-endpoints` and `domino-model-serving`.

## Large models

Set `MLFLOW_ENABLE_PROXY_MULTIPART_UPLOAD=true` before `log_model` on AWS and GCP deployments: [MLFLOW-BASICS.md](./MLFLOW-BASICS.md#large-artifact-upload).

## Documentation

- https://docs.domino.ai/cloud/platform-capabilities/features/models/register-and-govern/model-registry
- MLflow registry, aliases and tags: https://mlflow.org/docs/latest/ml/model-registry/
