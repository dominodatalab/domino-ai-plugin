# Framework examples

Worked code for Spark, Ray and Dask on Domino on-demand clusters: reading, processing and writing data, distributed training and hyperparameter tuning, and GPU use.

Connecting to each cluster from a workspace or job: [Spark](./SKILL.md#apache-spark), [Ray](./SKILL.md#ray), [Dask](./SKILL.md#dask) in SKILL.md.

## Apache Spark

### Reading Data
```python
# Read CSV
df = spark.read.csv("/mnt/data/dataset/data.csv", header=True, inferSchema=True)

# Read Parquet
df = spark.read.parquet("/mnt/data/dataset/")

# Read from database
df = spark.read.jdbc(
    url="jdbc:postgresql://host:5432/db",
    table="schema.table",
    properties={"user": "user", "password": "pass"}
)
```

### Processing Data
```python
from pyspark.sql import functions as F

# Transformations
result = df.filter(F.col("value") > 100) \
    .groupBy("category") \
    .agg(F.mean("value").alias("avg_value")) \
    .orderBy("avg_value", ascending=False)

# Show results
result.show()
```

### Machine Learning with Spark MLlib
```python
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml import Pipeline

# Prepare features
assembler = VectorAssembler(
    inputCols=["feature1", "feature2", "feature3"],
    outputCol="features"
)

# Create model
rf = RandomForestClassifier(
    featuresCol="features",
    labelCol="label",
    numTrees=100
)

# Build pipeline
pipeline = Pipeline(stages=[assembler, rf])
model = pipeline.fit(train_df)
predictions = model.transform(test_df)
```

### Writing Results
```python
# Write Parquet (recommended)
result.write.parquet("/mnt/artifacts/output/", mode="overwrite")

# Write CSV
result.write.csv("/mnt/artifacts/output.csv", header=True)
```

## Ray

### Parallel Tasks
```python
import ray

@ray.remote
def process_item(item):
    # Your processing logic
    return item * 2

# Run in parallel
items = [1, 2, 3, 4, 5]
futures = [process_item.remote(item) for item in items]
results = ray.get(futures)
print(results)  # [2, 4, 6, 8, 10]
```

### Distributed Training with Ray Train
```python
from ray import train
from ray.train import ScalingConfig
from ray.train.torch import TorchTrainer

def train_func():
    # Training logic
    model = create_model()
    for epoch in range(10):
        train_epoch(model)
        train.report({"loss": loss})

trainer = TorchTrainer(
    train_func,
    scaling_config=ScalingConfig(num_workers=4, use_gpu=True)
)
result = trainer.fit()
```

### Hyperparameter Tuning with Ray Tune
```python
from ray import tune
from ray.tune import CLIReporter

def objective(config):
    # Training with hyperparameters
    model = train_model(
        learning_rate=config["lr"],
        batch_size=config["batch_size"]
    )
    return {"accuracy": accuracy}

analysis = tune.run(
    objective,
    config={
        "lr": tune.loguniform(1e-4, 1e-1),
        "batch_size": tune.choice([32, 64, 128])
    },
    num_samples=20,
    progress_reporter=CLIReporter()
)

print(f"Best config: {analysis.best_config}")
```

## Dask

### Dask DataFrames (Parallel pandas)
```python
import dask.dataframe as dd

# Read large CSV files
df = dd.read_csv("/mnt/data/dataset/*.csv")

# Parallel operations (lazy)
result = df.groupby("category")["value"].mean()

# Execute
computed_result = result.compute()
```

### Dask Arrays (Parallel NumPy)
```python
import dask.array as da

# Create large array
x = da.random.random((100000, 100000), chunks=(1000, 1000))

# Operations (lazy)
result = x.mean()

# Compute
value = result.compute()
```

### Dask ML
```python
from dask_ml.model_selection import GridSearchCV
from sklearn.ensemble import RandomForestClassifier

# Distributed hyperparameter search
param_grid = {
    "n_estimators": [100, 200, 300],
    "max_depth": [10, 20, 30]
}

grid_search = GridSearchCV(
    RandomForestClassifier(),
    param_grid,
    cv=3
)

grid_search.fit(X_train, y_train)
print(f"Best params: {grid_search.best_params_}")
```

## GPU Clusters

### Spark RAPIDS
```python
# Use GPU-accelerated Spark
spark = SparkSession.builder \
    .config("spark.rapids.sql.enabled", "true") \
    .getOrCreate()

# Operations automatically use GPU
df = spark.read.parquet("/mnt/data/large_dataset/")
result = df.groupBy("category").agg({"value": "mean"})
```

### Ray with GPUs
```python
@ray.remote(num_gpus=1)
def train_on_gpu():
    import torch
    device = torch.device("cuda")
    # GPU training logic
    return model

# Run on GPU workers
futures = [train_on_gpu.remote() for _ in range(4)]
```
