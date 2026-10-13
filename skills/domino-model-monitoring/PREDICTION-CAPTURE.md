# Prediction capture for Domino endpoints

Applies to Domino 6.3 and Domino Cloud. Source: https://docs.domino.ai/cloud/platform-capabilities/features/monitoring/3-set-up-domino-endpoints/1-set-up-prediction-capture.

When you can choose how to serve a model, serve it as a Domino endpoint: integrated monitoring then captures predictions into the project Dataset `prediction_data` automatically, with no external data source to connect. The Model Monitor data-source path (S3, generic S3, Azure Blob or Data Lake, GCS, HDFS, NFS, Snowflake) is the documented exception, for models served as an App, Launcher or Job or outside Domino, and for ground-truth files.

Integrated monitoring only works when the endpoint code records each prediction with Domino's data-capture library. Domino converts the records to Parquet in a project Dataset and the Model Monitor reads them from there; the Model Monitoring API cannot ingest endpoint predictions from any other source.

## Install

Domino Standard Environments include the client. For other environments add it to the Dockerfile instructions and rebuild:

```dockerfile
USER root
RUN pip install domino-data-capture
USER ubuntu
```

R: `RUN R --no-save -e "install.packages(c('DominoDataCapture'))"`.

## Instrument the predict function

```python
# model.py
import datetime
import pickle
import uuid

from domino_data_capture.data_capture_client import DataCaptureClient

feature_names = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
predict_names = ["variety"]
metadata_names = ["cohort"]                      # optional extra columns

capture = DataCaptureClient(feature_names, predict_names, metadata_names)
model = pickle.load(open("model.pkl", "rb"))

def predict(sepal_length, sepal_width, petal_length, petal_width, event_id=None, cohort="default"):
    feature_values = [sepal_length, sepal_width, petal_length, petal_width]
    prediction = model.predict([feature_values])
    probabilities = model.predict_proba([feature_values])[0].tolist()

    event_id = event_id or str(uuid.uuid4())      # the row identifier ground truth is matched on
    event_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

    capture.capturePrediction(
        feature_values,
        [str(prediction[0])],
        metadata_values=[cohort],
        event_id=event_id,
        timestamp=event_time,
        prediction_probability=probabilities,
    )
    return {"variety": str(prediction[0]), "event_id": event_id}
```

Constructor:

| Parameter | Type | Meaning |
|-----------|------|---------|
| `feature_names` | list of str | Input feature names, in the order you pass values |
| `predict_names` | list of str | Prediction column names (always a list) |
| `metadata_names` | list of str, optional | Extra columns stored with each prediction |

`capturePrediction`:

| Parameter | Type | Meaning |
|-----------|------|---------|
| `feature_values` | list of float or str | Values in `feature_names` order |
| `predict_values` | list of float or str | Prediction values (always a list) |
| `metadata_values` | list, optional | Values in `metadata_names` order |
| `event_id` | str, optional | Unique id per prediction; generated if omitted. Supply your own and return it to the caller so labels can be joined later |
| `timestamp` | optional | Event time; generated if omitted. Use ISO 8601 UTC |
| `prediction_probability` | list of float, optional | Class probabilities; required for AUC-ROC, log loss and Gini |
| `sample_weight` | list of float, optional | Weights used by the normalized Gini metric |

Keep the capture call inside the function so one row is written per request. Capture is sized for 8 GB per endpoint per 24 hours; bursts up to about five times that work; beyond that the endpoint log shows errors or warnings.

## Test before publishing

Developer mode lets you call the function in a Workspace to check the library calls without capturing data: import the module in a notebook, call `predict(...)`, and read the library's output to confirm the column shapes. Then publish and send a few requests from the endpoint's **Tester** tab; after the hourly batch, **Configure Monitoring** > **Target Ranges** on the endpoint populates.

## Where the data goes

Domino creates a Dataset named `prediction_data` in the project. Files are Parquet, written hourly when there was traffic, partitioned by model version id, UTC date and hour:

| Project type | Path |
|--------------|------|
| Git-based | `/mnt/data/prediction_data/<model_version_id>/$$date$$=<yyyy-mm-dd>/$$hour$$=<hh>/predictions_<uuid>.parquet` |
| DFS | `/domino/datasets/local/prediction_data/<model_version_id>/$$date$$=<yyyy-mm-dd>/$$hour$$=<hh>/predictions_<uuid>.parquet` |

```python
import pandas as pd
df = pd.read_parquet("/mnt/data/prediction_data/<model_version_id>")   # whole dataset, all partitions
```

Do not rename files or directories. A daily job deletes data older than 30 days by default; your administrator sets the retention policy. The model version id is the `id` of the version in `GET /api/modelServing/v1/modelApis/{modelApiId}/versions`.

## Ground truth for endpoint predictions

Model quality needs a row identifier present in both the prediction data and the ground-truth file. For endpoint capture that is the `event_id` you pass (check the column name in the captured Parquet before writing the config). Build a ground-truth file with that identifier plus the label column, store it on a data source connected to the Model Monitor, and register it with a config whose only variable is the label:

```json
{
  "variables": [
    {"name": "variety_actual", "variableType": "ground_truth", "valueType": "categorical",
     "forPredictionOutput": "variety"}
  ],
  "datasetDetails": {
    "name": "labels-2026-10.csv",
    "datasetType": "file",
    "datasetConfig": {"path": "labels/labels-2026-10.csv", "fileFormat": "csv"},
    "datasourceName": "monitoring-bucket",
    "datasourceType": "s3"
  }
}
```

Register it under **Model Monitor** > model > **Model Quality** > **Register Ground Truth**, or with `PUT /model-monitor/v2/api/model/{model_id}/register-dataset/ground_truth` ([MONITORING-API.md](./MONITORING-API.md)). Labels are matched to predictions made in the last 90 days.

## Remediate from captured data

1. On the endpoint, **Open in Workspace**: Domino opens a Workspace on a new branch at the published commit (Git-based projects need the model published on Domino 5.0 or later).
2. Read `prediction_data` for the affected period, join your labels on the identifier, and retrain.
3. Merge the branch (Git-based) or **Revert Project** to the branch's commit (DFS), then publish a new endpoint version.
