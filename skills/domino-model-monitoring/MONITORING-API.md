# Model Monitoring API

Routes: the Model Monitor service under `/model-monitor/...` and custom metrics under `/api/metricValues/v1` and `/api/metricAlerts/v1`. Response shapes are in the public API spec ([API-SPECS.md](../domino-api-intro/API-SPECS.md)); your deployment's `/docs` has the Model Monitor document.

## Authentication

[domino-api-intro](../domino-api-intro/SKILL.md#authentication). The examples use `$TOKEN`:

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)   # in a run; outside Domino a PAT or service-account token
```

## Routes

| Task | Route | Notes |
|------|-------|-------|
| List monitored models | `GET /model-monitor/v2/api/models?pageNumber=1&pageSize=25&numberOfLastChecksToFetch=1` | All three query params are required; optional `searchQuery`, `tagsQuery`, `modelType`, `sortOn`, `sortOrder` |
| Get one model | `GET /model-monitor/v2/api/model?model_id=<dmmModelId>` or `?workbench_model_version_id=<modelApiVersionId>` | The second form maps an endpoint version to its Model Monitor model |
| Register a model (Model Monitor workflow) | `PUT /model-monitor/v2/api/model` | Body: Monitoring Config JSON with `variables`, `datasetDetails`, `modelMetadata` |
| Register prediction or ground-truth data | `PUT /model-monitor/v2/api/model/{model_id}/register-dataset/{dataset_type}` | `dataset_type` is `prediction` or `ground_truth`; body `datasetDetails` plus optional `variables` |
| Update or unregister | `PATCH` and `DELETE /model-monitor/v2/api/model?model_id=` | |
| Ingest history | `POST /model-monitor/v2/api/{model_id}/dataset-jobs` | Body `start`, `end`, `pagination` |
| Prediction traffic | `GET /model-monitor/v2/api/model/get-prediction-traffic?model_ids=&start_date=&end_date=` | All three required; returns `[{modelId, traffic: [{date, queries}]}]` |
| Ad-hoc drift analysis | `POST /model-monitor/v2/api/model/{model_id}/analyse-drift` | Returns `calculatedOn`, `start`, `end`, `records`, `features`, `totalCount`, `pagination` |
| Ad-hoc quality analysis | `POST /model-monitor/v2/api/model/{model_id}/analyze-model-quality` | Body differs for classification and regression (`metricCheckConfigs`) |
| Trends | `GET .../model/{model_id}/{column_id}/drift-trend`, `GET .../model/{model_id}/model-quality-trend` | |
| Scheduled-check history | `GET .../model/{model_id}/drift-schedule-checks-history`, `.../model-quality-scheduled-checks-history` | |
| Scheduled-check data | `GET .../model/{model_id}/{scheduler_id}/scheduled-check-drift-data`, `GET .../model/{scheduled_check_id}/model-quality-scheduled-check-data` | |
| Create a drift schedule | `POST /model-monitor/api/scheduler/create_drift_schedule_check` | Body `name`, `modelId`, `cronExpression`, `dataSinceLastCheck` (bool), `dataSince` (int), `calendarType`, `timezone`, optional `datasetId` |
| Create a quality schedule | `POST /model-monitor/api/scheduler/create_quality_schedule_check` | Same shape |
| Read or remove schedules | `GET .../scheduler/{modelId}/get_drift_schedule_check`, `.../get_quality_schedule_check`, `POST .../scheduler/{schedulerJobId}/unschedule_scheduler_job` | |
| Alert recipients per model | `GET` and `POST /model-monitor/v2/api/notification/model-config/{model_id}` | |
| Global test defaults | `GET` and `PUT /model-monitor/v2/api/setting/default/drift`, `.../default/metric` | |
| Data sources | `GET /model-monitor/v2/api/datasources`; `PUT`, `DELETE /model-monitor/v2/api/datasource` | `datasourceType`: `s3`, `generic_s3`, `azure_blob`, `azure_data_lake_gen_2`, `google_cloud_storage`, `azure_data_lake_gen_1`, `hdfs`, `nfs`, `snowflake` |
| Tags, collaborators, visibility | `.../model/{model_id}/tags`, `.../collaborators`, `.../visibility` | |

## Examples

Find the Model Monitor record for an endpoint version:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$DOMINO_API_HOST/model-monitor/v2/api/model?workbench_model_version_id=$MODEL_API_VERSION_ID"
curl -s -H "Authorization: Bearer $TOKEN" \
  "$DOMINO_API_HOST/model-monitor/v2/api/models?pageNumber=1&pageSize=25&numberOfLastChecksToFetch=1"
```

The list response carries `modelDashboardItems[]` with `id` (the DMM model id), `name`, `version`, `modelType`, `modelStatus`, `sourceType` (`domino_workbench` or `standalone`), `dataDriftChecks`, `modelQualityChecks`, `isDataDriftCheckScheduled`, `isModelQualityCheckScheduled`, plus `classificationModelCount`, `regressionModelCount`, `pagination`.

Register an external model with a Monitoring Config JSON:

```bash
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$DOMINO_API_HOST/model-monitor/v2/api/model" -d '{
  "variables": [
    {"name": "age", "valueType": "numerical", "variableType": "feature", "featureImportance": 0.9},
    {"name": "y", "valueType": "categorical", "variableType": "prediction"},
    {"name": "date", "valueType": "datetime", "variableType": "timestamp"},
    {"name": "RowId", "valueType": "string", "variableType": "row_identifier"}
  ],
  "datasetDetails": {
    "name": "TrainingData.csv", "datasetType": "file",
    "datasetConfig": {"path": "TrainingData.csv", "fileFormat": "csv"},
    "datasourceName": "monitoring-bucket", "datasourceType": "s3"
  },
  "modelMetadata": {"name": "churn", "modelType": "classification", "version": "2", "author": "ml-team"}
}'
```

Keep the returned `id` for every later call. `variableType` values: `feature`, `prediction`, `row_identifier`, `timestamp`, `ground_truth`, `sample_weight`, `prediction_probability`; `valueType`: `categorical`, `numerical`, `string`, `datetime`; `fileFormat`: `csv`, `parquet` or `snowflake` (for a Snowflake data source `path` is the table name). Features must be numerical or categorical and present in every dataset; one `prediction`, one `timestamp` (ISO 8601) and one `row_identifier` at most. Binning options (`binsNum`, `binsEdges`, `binsCategories`) are documented at https://docs.domino.ai/cloud/platform-capabilities/features/monitoring/8-json/1-supported-binning.

Register a new batch of predictions or labels:

```bash
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$DOMINO_API_HOST/model-monitor/v2/api/model/$DMM_MODEL_ID/register-dataset/prediction" -d '{
  "datasetDetails": {"name": "predictions-2026-10-11.parquet", "datasetType": "file",
    "datasetConfig": {"path": "predictions/2026-10-11.parquet", "fileFormat": "parquet"},
    "datasourceName": "monitoring-bucket", "datasourceType": "s3"}}'
```

Use `ground_truth` as the dataset type for labels (with a `variables` entry of `variableType: ground_truth` and `forPredictionOutput`).

Schedules: `cronExpression`, `calendarType` and `timezone` take the values the UI generates. Create one check in the UI, read it back with `GET /model-monitor/api/scheduler/{modelId}/get_drift_schedule_check`, and reuse that format in `create_drift_schedule_check` for other models.

## Custom metrics

Custom metrics attach your own time series (business accuracy, latency SLO, fairness scores) to a monitored model and can raise alerts through the same notification channels.

```bash
# Log values (RegisterMonitoringDataset permission); referenceTimestamp is ISO 8601 UTC
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$DOMINO_API_HOST/api/metricValues/v1" -d '{"newMetricValues": [
    {"modelMonitoringId": "'"$DMM_MODEL_ID"'", "metric": "business_accuracy", "value": 0.93,
     "referenceTimestamp": "2026-10-11T00:00:00Z"}]}'

# Read values (UpdateMonitoringSettings permission); both bounds are required
curl -s -H "Authorization: Bearer $TOKEN" \
  "$DOMINO_API_HOST/api/metricValues/v1/$DMM_MODEL_ID/business_accuracy?startingReferenceTimestampInclusive=2026-10-01T00:00:00Z&endingReferenceTimestampInclusive=2026-10-12T00:00:00Z"

# Raise an alert (ViewMonitoringResults permission)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$DOMINO_API_HOST/api/metricAlerts/v1" -d '{"modelMonitoringId": "'"$DMM_MODEL_ID"'",
    "metric": "business_accuracy", "value": 0.81,
    "targetRange": {"condition": "greaterThan", "lowerLimit": 0.9},
    "description": "Business accuracy below 0.9"}'
```

`condition` is one of `lessThan`, `lessThanEqual`, `greaterThan`, `greaterThanEqual`, `between` (with `lowerLimit` and `upperLimit`). Each metric value may also carry `tags`. The same operations exist in `python-domino` as `Domino("owner/project").custom_metrics_client()` with `log_metric`, `log_metrics`, `read_metrics` and `trigger_alert`: https://docs.domino.ai/cloud/platform-capabilities/features/monitoring/5-use-monitoring/2-custom-metrics.

## Automating retraining on drift

```python
import os
import requests

# base and headers: the Python setup block in domino-api-intro/SKILL.md#authentication
base, headers = os.environ["DOMINO_API_PROXY"], {}        # in a run with the proxy

dmm_model_id = os.environ["DMM_MODEL_ID"]       # the Model Monitor model id (set it as a project or job variable)

# Each entry is {"id", "time" (epoch), "columnsDrifted", "columnsNotDrifted"} (spec: dmm-plier_driftHistoryTimeline)
history = requests.get(f"{base}/model-monitor/v2/api/model/{dmm_model_id}/drift-schedule-checks-history",
                       headers=headers).json()
latest = max(history, key=lambda check: check["time"]) if history else None

if latest and latest["columnsDrifted"] > 0:
    job = requests.post(f"{base}/api/jobs/v1/jobs", headers=headers, json={
        "projectId": os.environ["DOMINO_PROJECT_ID"],
        "runCommand": "python retrain.py --since-days 30",
    })
    job.raise_for_status()
    print("retraining job", job.json()["job"]["id"], "started; drifted columns:", latest["columnsDrifted"])
```

`POST /api/jobs/v1/jobs` requires only `projectId` and `runCommand`; optional `hardwareTier`, `environmentId`, `title` and others are documented in `domino-jobs`. Run this script as a scheduled Job after the daily check. Where the Model Monitor and the retraining project differ, give the service account access to both.
