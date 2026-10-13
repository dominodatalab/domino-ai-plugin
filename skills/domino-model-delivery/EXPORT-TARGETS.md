# Export targets: NVIDIA Fleet Command, Snowflake, SageMaker, the Exports page

**Every `/v4/...` route in this file is Domino Internal API, may change between Domino versions.**
They are documented on the product pages cited below and on each cluster's reference
(`https://<domino-domain>/docs`, `openapi-internal.json`); they are not in the Public API spec.
Authentication as in [SKILL.md](./SKILL.md#authentication): Bearer token, never `X-Domino-Api-Key`.

## NVIDIA Fleet Command (edge)

Product page: https://docs.domino.ai/cloud/platform-capabilities/features/models/export-nvidia
(same on 6.3). Domino pushes the endpoint container image and a Helm chart to private
repositories in NVIDIA NGC; Fleet Command then deploys them to edge systems. The cluster
reference labels the route **BETA**.

Prerequisites: a Domino endpoint deployed from the project and in **Ready to Run** state, so a
model id and a built model version id exist (list them with
`GET /api/modelServing/v1/modelApis?projectId=...` and `.../{modelApiId}/versions`, Public API).

```bash
# JSON-encode the body from the environment and send it on stdin: never splice $NGC_API_KEY into a quoted string
python3 -c 'import json, os, sys
json.dump({"containerRepository": "<org>/<team>/<container-repo>", "tag": "1.4.0",
           "helmRepository": "<org>/<team>/<helm-repo>", "helmVersion": "1.4.0",
           "ngcApiKey": os.environ["NGC_API_KEY"]}, sys.stdout)' \
| curl -sS -X POST "$BASE/v4/models/$MODEL_ID/$MODEL_VERSION_ID/exportImageForNvidia" \
    -H "$AUTH" -H "Content-Type: application/json" --data-binary @-
# -> export id; poll GET $BASE/v4/models/<export-id>/getExportImageStatus
```

| Field | Required | Rule |
|---|---|---|
| `containerRepository` | yes | existing private NGC container repository; lowercase alphanumerics, dashes, slashes, no spaces |
| `tag` | no (cluster reference) | alphanumerics, underscores, periods, dashes |
| `helmRepository` | yes | existing private NGC Helm repository, same character rules |
| `helmVersion` | yes | semver |
| `ngcApiKey` | yes | NGC API key; generate it in NGC, keep it in a Project or user environment variable and read it by name (`os.environ["NGC_API_KEY"]`); a CI runner outside Domino holds its own copy |

Constraints from the product page:

- The endpoint port on the edge device is hardcoded to **30008**; a second Domino model on the
  same device fails unless you override the port in `values.yaml` in the Fleet Command UI.
- The model cannot use Domino-specific assets (Datasets, prediction sets).
- The export fails if the image tag or Helm chart version already exists in NGC.
- Different versions of the same NVIDIA application cannot share one edge device.

## Snowflake (Snowpark UDF)

Product page: https://docs.domino.ai/cloud/platform-capabilities/features/models/snowflake-queries
(same on 6.3). Domino uploads the model artifact, the file holding the predict function and its
dependent modules to a Snowflake stage and registers the function as a Snowpark Python UDF, so
scoring runs where the data lives. The documented path is the UI publish flow.

Requirements for the model:

- Python 3.8.
- `requirements.txt` at the root of the project (or of the imported repository or project), listing
  only packages available on the Snowflake Anaconda channel
  (https://repo.anaconda.com/pkgs/snowflake/); the Snowflake account must allow Anaconda packages.
- Type hints on the predict function's inputs and return value (Snowpark derives the UDF
  signature from them). The function typically accepts and returns a DataFrame.
- Files the predict function reads (a pickle, for example) sit at a different path inside
  Snowflake than in Domino; follow Snowflake's "reading files from a UDF" guidance.

Publish (UI):

1. Train the model and write the UDF-style predict function in the project.
2. Start the Domino publish flow for Snowflake and fill in the Snowflake session:
   account URL `https://<account-id>.snowflakecomputing.com`, username, password, user role,
   warehouse, database, schema, stage, and the UDF name.
3. Domino runs a Job that uploads the artifacts and registers the UDF. Its logs are on the
   project's Jobs dashboard and behind **view export logs** on the export; the `SNOWFLAKE`
   password shown in the Job command is an environment variable name, not the secret.
4. New code: **Exports > model > Actions > Push new version**, choose the predict file, function
   and environment, then **Authenticate & Export**. The current project HEAD becomes the next
   version and Snowflake overwrites the UDF.

The same operation exists as an internal API call with the fields the dialog asks for:

```text
POST /v4/models/{modelId}/{modelVersionId}/exportImageForSnowflake   (also /v4/modelManager/exportImageForSnowflake/{modelId}/{modelVersionId})
body: snowflakeUdfName, snowflakeUrl, snowflakeUsername, snowflakePassword, snowflakeUserRole,
      snowflakeWarehouseName, snowflakeDatabaseName, snowflakeSchemaName, snowflakeStageName   (all required)
```

Monitoring: on the **Exports** page open the model, **Grafana Monitoring > Configure Monitoring >
Data**, pick the Training Set and version, model type (classification or regression), then add
prediction and ground-truth data once ingested. The prediction table needs a `timestamp` column;
Domino ingests rows with new timestamps in batches. Thresholds, schedules and alerts:
[domino-model-monitoring](../domino-model-monitoring/SKILL.md).

Troubleshooting: authentication and networking failures surface in the export Job's User Output;
code failures mean fixing the model and pushing a new version (the version number increments on
the next export).

## Amazon SageMaker

Two mechanisms exist; prefer the first.

**Deployment targets (current, Public API in both specs).** An admin registers an external
deployment target (`GET/POST /api/admin/v1/deploymentTargets`, types from
`/api/admin/v1/deploymentTargetTypes`, resource configurations under
`.../{deploymentTargetId}/resourceConfigurations`). A user then deploys a **registered model**
from **Endpoints > External > Create external endpoint** (model, environment, target, resources,
min/max instances with CPU-based autoscaling at 80%, streaming, visibility) or with
`POST /api/modelServing/v1/modelDeployments`; lifecycle via `.../{modelDeploymentId}/start|stop`
and `.../versions`. Only supported when the Domino control plane runs on AWS EKS. Product page:
https://docs.domino.ai/cloud/platform-capabilities/features/models/deploy-sagemaker. REST
details: [domino-python-sdk API-MODELS.md](../domino-python-sdk/API-MODELS.md).

**Legacy image export (internal API).** `POST /v4/models/{modelId}/{modelVersionId}/exportImageForSagemaker`
with the same body as `exportImageToRegistry` (`registryUrl`, `repository`, `tag`, `username`,
`password`) pushes a SageMaker-compatible image to ECR; python-domino's
`model_version_sagemaker_export(...)` wraps it and
`examples/export_model_to_sagemaker.py` in the python-domino repository shows the ECR
credential dance with `boto3`. You then create the SageMaker model and endpoint yourself.

## The Exports page and catalog

**Exports** in the project navigation lists every exported model with its target, latest
version and, for Snowflake and other monitored exports, drift and model-quality columns (green
check healthy, red number of alerts, grey no data). Internal API behind it:

```text
GET /v4/modelManager/getModelExports/{projectId}?startIndex=0&count=50&sort=created&sortDirection=desc
-> {currentItemCount, itemsPerPage, startIndex, totalItems, items: [{id, modelId, registryUrlHostName,
    target: "Sagemaker" | "NvidiaFleetcommand" | "Snowflake" | "Domino", projectId, modelName, modelDescription,
    latestSuccessfulVersionId, isArchived, created}]}
GET /v4/modelManager/getModelExport/{exportId}
GET /v4/modelManager/getModelExportVersions/{exportId}
GET /v4/modelManager/getExportVersionLogs/{exportVersionId}
DELETE /v4/modelManager/archiveModelExport/{exportId}
```

On a project with no exports the list route returns HTTP 200 with an empty list.
