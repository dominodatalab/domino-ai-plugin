# TrainingSets

A TrainingSet is a named, versioned collection of training DataFrames with column roles (key,
target, excluded, categorical, timestamp, ordinal) and free-form metadata. Versions are what
Model Monitoring uses as the training baseline. Each version is stored as Parquet under
`DOMINO_TRAINING_SET_PATH` (default `/var/opt/domino/trainingset/project`), a volume Domino
mounts into executions, so creating and loading versions only works inside a Domino execution
in the owning Project (`DOMINO_PROJECT_ID`).

Docs: https://docs.domino.ai/cloud/reference/api/data_api/trainingsets_usecases (create,
retrieve, update, delete, custom authentication). Source:
`domino_data/training_sets/client.py` and `model.py`.

## Import

`domino_data.training_sets` is a package with an empty `__init__`; import the modules:

```python
from domino_data.training_sets import client as ts, model
# or, through python-domino: from domino.training_sets import TrainingSetClient as ts, model
```

The functions below live in `client`; the dataclasses in `model`.

## Create a version

```python
import pandas as pd

version = ts.create_training_set_version(
    training_set_name="customer-churn",          # ^[-A-Za-z0-9_]+$ ; created on first use
    df=df,                                        # pandas DataFrame
    description="Q3 2026 features",
    key_columns=["customer_id"],                  # row identifiers; dropped from training data
    target_columns=["churned"],                   # prediction targets
    exclude_columns=["notes"],                    # dropped from training data
    monitoring_meta=model.MonitoringMeta(
        timestamp_columns=["event_ts"],
        categorical_columns=["churned", "plan"],  # a classification target must be listed here
        ordinal_columns=["tier"],                 # not used by Model Monitoring
    ),
    meta={"source": "warehouse", "quarter": "2026Q3"},
)
print(version.number)
```

Every column not named in `key_columns`, `exclude_columns` or `monitoring_meta` is treated as
numerical. Naming a column the DataFrame lacks raises `SchemaMismatchException`. Versions in a
TrainingSet must come from the same Project. A TrainingSet without `monitoring_meta` cannot be
selected as a monitoring baseline for a classification model.

## Retrieve

```python
t = ts.get_training_set("customer-churn")        # model.TrainingSet
print(t.name, t.project_id, t.description, t.meta)

v = ts.get_training_set_version("customer-churn", 2)   # model.TrainingSetVersion
print(v.number, v.description, v.key_columns, v.target_columns, v.all_columns, v.meta)
raw_df = v.load_raw_pandas()            # every column
train_df = v.load_training_pandas()     # without key_columns and exclude_columns
```

`TrainingSet` fields: `name`, `project_id`, `description`, `meta`. `TrainingSetVersion` fields:
`training_set_name`, `number`, `description`, `key_columns`, `target_columns`,
`exclude_columns`, `all_columns`, `monitoring_meta`, `meta`, `path`, `container_path`,
`pending`, plus the `absolute_container_path` property. There is no `created_at`,
`version_count` or `row_count`; compute row counts from the loaded DataFrame.

## List and search

```python
sets = ts.list_training_sets(meta={"source": "warehouse"}, asc=True, offset=0, limit=10000)
versions = ts.list_training_set_versions(
    training_set_name="customer-churn",
    meta={"quarter": "2026Q3"},              # version metadata, all keys must match
    training_set_meta={"source": "warehouse"},
    asc=False, offset=0, limit=50,
)
latest = versions[0].number if versions else None
```

Results are scoped to the current Project.

## Update

```python
t = ts.get_training_set("customer-churn")
t.description = "widget transactions"
t.meta = {**t.meta, "region": "west"}
t = ts.update_training_set(t)

v = ts.get_training_set_version("customer-churn", 2)
v.description = "2026 transactions"
v.meta = {**v.meta, "status": "final"}
v = ts.update_training_set_version(v)
```

The attribute is `meta`, not `metadata`.

## Delete

```python
ts.delete_training_set_version("customer-churn", 2)    # True on success
ts.delete_training_set("customer-churn")               # only when no versions remain

for v in ts.list_training_set_versions(training_set_name="old-set"):
    ts.delete_training_set_version(v.training_set_name, v.number)
ts.delete_training_set("old-set")
```

## Authentication

The client reads `DOMINO_API_HOST` (or `DOMINO_USER_HOST`) for the host and authenticates with
`DOMINO_API_PROXY`, then `DOMINO_TOKEN_FILE`, then `DOMINO_USER_API_KEY` (deprecated); all are
injected in executions. It has no `token=` parameter. Domino endpoints receive none of these,
so load training data for an endpoint at build time or from a Dataset instead.

## Errors

```python
from domino_data.training_sets.client import ServerException, SchemaMismatchException

try:
    ts.create_training_set_version(training_set_name="my-set", df=df, key_columns=["id"])
except SchemaMismatchException as e:
    print(e)                       # "DataFrame missing columns: {...}"
except ServerException as e:
    print(e.message, e.server_msg) # message and the server's errors list
```

`ValueError` is raised for a name outside `[-A-Za-z0-9_]`.

## Patterns

Tie a version to an experiment run (domino-experiment-tracking skill):

```python
import mlflow

version = ts.create_training_set_version(
    training_set_name="model-training-data", df=train_df, key_columns=["id"],
    target_columns=["label"], description=f"run {mlflow.active_run().info.run_id}",
)
mlflow.log_param("training_set_version", version.number)
```

Validate before versioning:

```python
assert not df.isnull().any().any(), "nulls present"
assert len(df) >= 100, "too few rows"
```
