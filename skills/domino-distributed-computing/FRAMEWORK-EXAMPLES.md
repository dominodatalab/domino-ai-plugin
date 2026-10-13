# Framework examples

Worked code for Spark, Ray and Dask on Domino on-demand clusters. Connecting to each cluster, environments and cluster settings: [SKILL.md](./SKILL.md). Every example assumes the connection snippet from SKILL.md has run.

Dataset paths: `/mnt/data/<dataset>` in a Git-based Project, `/domino/datasets/local/<dataset>` in a DFS Project; both are mounted on the cluster nodes at the same path. Project files (`/mnt`, `/mnt/code`, `/mnt/artifacts`) exist only on the execution container, never on cluster nodes. The sensible default for output is a Dataset, a NetApp Volume (`/domino/netapp-volumes/<name>` in DFS Projects, `/mnt/netapp-volumes/<name>` in Git-based Projects) or an External Data Volume (`/domino/edv/<name>`); the docs document only Dataset mounts on cluster nodes, so for the other two confirm the path exists on the workers or write from the driver. Object storage (`s3a://`, `s3://`) is fine where it is enabled for the cluster: it needs the connector libraries in both environments and credentials (AWS credential propagation, when enabled, puts a profile on every node; never paste keys into code). A Data Source cannot be used from executors.

## Apache Spark

### Read, transform, write

Spark tasks run on the executors, so read and write Dataset paths (with the `file:///` prefix the docs use) or object storage where it is enabled for the cluster. Anything that must become a Job result is collected to the driver first.

```python
import os
from pathlib import Path
from pyspark.sql import functions as F

ds = "file:///mnt/data/my-dataset"           # DFS Project: file:///domino/datasets/local/my-dataset
df = spark.read.csv(f"{ds}/data.csv", header=True, inferSchema=True)
df = spark.read.parquet(f"{ds}/parquet/")
df = spark.read.json("s3a://bucket/prefix/people.json")          # object storage: hadoop-aws in the cluster environment, propagated credentials

result = (df.filter(F.col("value") > 100)
            .groupBy("category")
            .agg(F.mean("value").alias("avg_value"))
            .orderBy("avg_value", ascending=False))
result.show()

result.write.mode("overwrite").parquet(f"{ds}/output/")          # executors write; the Dataset is on every node

# Small result for the Job results view: collect on the driver, then write to the Project files
git_based = os.environ.get("DOMINO_IS_GIT_BASED", "false").lower() == "true"
results_dir = Path("/mnt/artifacts/results") if git_based else Path(os.environ["DOMINO_WORKING_DIR"]) / "results"
results_dir.mkdir(parents=True, exist_ok=True)
result.limit(1000).toPandas().to_csv(results_dir / "summary.csv", index=False)
```

A DataFrame `.write` to `/mnt/...` lands on an executor's ephemeral disk (or fails) and never reaches the Job results; `coalesce(1)` does not change that.

### MLlib pipeline

```python
from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.feature import VectorAssembler

train_df, test_df = df.randomSplit([0.8, 0.2], seed=42)
assembler = VectorAssembler(inputCols=["feature1", "feature2", "feature3"], outputCol="features")
rf = RandomForestClassifier(featuresCol="features", labelCol="label", numTrees=100)
model = Pipeline(stages=[assembler, rf]).fit(train_df)
predictions = model.transform(test_df)
model.write().overwrite().save(f"{ds}/models/rf")                 # Dataset path, visible to all nodes
```

### Tune the context

```python
spark = (SparkSession.builder.appName("etl")
         .config("spark.sql.shuffle.partitions", "400")
         .config("spark.executor.memoryOverhead", "1g")
         .getOrCreate())
conf = spark.sparkContext.getConf()
print(sorted(k for k, _ in conf.getAll()))                      # keys only: see what Domino set
print(conf.get("spark.executor.instances"), conf.get("spark.executor.cores"), conf.get("spark.executor.memory"))
```

Never print `conf.getAll()` values, `spark.hadoop.*` settings or `os.environ` wholesale: storage credentials such as `spark.hadoop.fs.s3a.secret.key`, `fs.s3a.session.token` and propagated cloud credentials live there and would land in the Job logs and the transcript. Read the specific non-secret keys you need, as above. Never override `spark.master` or `spark.driver.host`. Executor cores and memory follow the worker hardware tier; pick a larger tier rather than overriding them unless you understand the worker overhead.

### Project-wide Spark settings

Settings that should apply to every on-demand cluster in a Project live in **Settings > Integrations > Domino managed on-demand cluster**, or in the Project's Spark config over the Internal API (internal API, may change between Domino versions; on 6.3 confirm in your deployment's `/docs`). `onDemandFreeFormConfig` is the free-form box: one `key value` per line.

```python
import os, requests

base = os.environ["DOMINO_API_PROXY"]
project_id = os.environ["DOMINO_PROJECT_ID"]
cfg = requests.get(f"{base}/v4/projects/{project_id}/sparkConfig").json()      # {"sparkMode": "OnDemand", "masterPort": 7077, ...}
r = requests.patch(f"{base}/v4/projects/{project_id}/sparkConfig", json={
    "sparkMode": cfg["sparkMode"],                                              # required; "OnDemand" for Domino-managed clusters
    "onDemandFreeFormConfig": "spark.sql.shuffle.partitions 200\nspark.executor.memoryOverhead 1g",
})
r.raise_for_status()
print(r.json()["onDemandFreeFormConfig"])
```

Other fields (`freeFormConfig`, `yarnFreeFormConfig`, `masterHost`, `masterPort`, `hadoopUserName`, `hostnameMappings`) belong to the external Hadoop and Spark modes; leave them alone for on-demand clusters.

## Ray

### Parallel tasks and actors

```python
import ray

@ray.remote
def process(item):
    return item * 2

print(ray.get([process.remote(i) for i in range(10)]))

@ray.remote(num_cpus=1)
class Counter:
    def __init__(self):
        self.n = 0
    def incr(self):
        self.n += 1
        return self.n

c = Counter.remote()
print(ray.get([c.incr.remote() for _ in range(3)]))
```

### Distributed training with Ray Train (PyTorch)

```python
import torch
import torch.nn as nn
import ray.train
import ray.train.torch
from ray.train import ScalingConfig
from ray.train.torch import TorchTrainer

def train_loop(config):
    model = ray.train.torch.prepare_model(nn.Linear(10, 1))
    opt = torch.optim.SGD(model.parameters(), lr=config["lr"])
    for epoch in range(config["epochs"]):
        x, y = torch.randn(64, 10), torch.randn(64, 1)      # replace with your data loader
        loss = nn.functional.mse_loss(model(x), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        ray.train.report({"epoch": epoch, "loss": loss.item()})

trainer = TorchTrainer(
    train_loop,
    train_loop_config={"lr": 0.01, "epochs": 5},
    scaling_config=ScalingConfig(num_workers=2, use_gpu=False),   # use_gpu=True on a GPU worker tier
)
result = trainer.fit()
print(result.metrics)
```

`num_workers` must not exceed the cluster's worker count (or max workers with autoscaling). Checkpoints and outputs go to a Dataset, not the worker's `/tmp`; log the final model to the experiment ([domino-experiment-tracking](../domino-experiment-tracking/SKILL.md)).

### Hyperparameter tuning with Ray Tune

```python
from ray import tune

def objective(config):
    score = (config["lr"] * 100 - 1) ** 2 + config["batch_size"] / 1000   # replace with training + eval
    tune.report({"score": score})

tuner = tune.Tuner(
    objective,
    param_space={"lr": tune.loguniform(1e-4, 1e-1), "batch_size": tune.choice([32, 64, 128])},
    tune_config=tune.TuneConfig(num_samples=20, metric="score", mode="min"),
)
results = tuner.fit()
print(results.get_best_result().config)
```

`tune.report` is exported by recent Ray releases (Domino's validated 2.55.x has it); on older cluster images such as the Ray 2.36 tags use `from ray import train` and `train.report({...})` instead. Log trials to MLflow with `mlflow.get_tracking_uri()` (preconfigured in Domino) to compare them in Experiments; see https://docs.domino.ai/cloud/platform-capabilities/features/development/ray-tune and [domino-experiment-tracking](../domino-experiment-tracking/SKILL.md).

## Dask

### DataFrames and arrays

```python
import dask.dataframe as dd
import dask.array as da

df = dd.read_csv("/mnt/data/my-dataset/*.csv")
df = dd.read_parquet("s3://bucket/path/data-*.parquet", storage_options={"profile": "my-role"})   # object storage: s3fs on all nodes, profile from AWS credential propagation
means = df.groupby("category")["value"].mean().compute()

x = da.random.random((100_000, 10_000), chunks=(1_000, 1_000))
print(x.mean().compute())
```

### Dask-ML

```python
from dask_ml.model_selection import GridSearchCV
from sklearn.ensemble import RandomForestClassifier

search = GridSearchCV(RandomForestClassifier(),
                      {"n_estimators": [100, 200], "max_depth": [10, 20]}, cv=3)
search.fit(X_train, y_train)          # X_train, y_train: pandas/NumPy or Dask collections
print(search.best_params_)
```

`dask_ml` must be installed in both the execution and the cluster environment. Prefer `client.persist(df)` for data reused across steps; call `client.close()` at the end, not `client.shutdown()`.

## GPUs

- Pick a GPU hardware tier for the workers (and the Ray GPU cluster image). Check allocation with `nvidia-smi` on the execution; `ray.cluster_resources()["GPU"]` on Ray.
- Ray: `@ray.remote(num_gpus=1)` tasks or `ScalingConfig(num_workers=N, use_gpu=True)` in Ray Train.
- Spark: GPU-accelerated workers are possible with the RAPIDS Accelerator for Apache Spark; the plugin jars and configuration must be added to the cluster environment (https://docs.domino.ai/cloud/platform-capabilities/features/development/distributed-training).
- MPI: Domino sets slots from the worker tier's CPU/GPU requests; `mpirun python train.py` with Horovod or `torch.distributed` launched per rank.
