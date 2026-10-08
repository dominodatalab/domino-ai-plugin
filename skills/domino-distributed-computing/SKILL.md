---
name: domino-distributed-computing
description: Work with distributed computing frameworks in Domino including Apache Spark, Ray, and Dask clusters. Covers cluster configuration, on-demand clusters, choosing between frameworks, PySpark usage, and scaling workloads. Use when processing large datasets, parallel ML training, or running distributed compute jobs.
---

# Domino Distributed Computing Skill

## Description
This skill helps users work with distributed computing frameworks in Domino - Spark, Ray, and Dask clusters for scaling compute-intensive workloads.

## Activation
Activate this skill when users want to:
- Run Spark, Ray, or Dask clusters in Domino
- Scale data processing or ML training
- Configure distributed cluster settings
- Understand when to use each framework

## Supported Frameworks

| Framework | Best For |
|-----------|----------|
| **Apache Spark** | Large-scale data processing, SQL, ETL |
| **Ray** | Distributed ML, hyperparameter tuning, RL |
| **Dask** | Parallel pandas, NumPy at scale |
| **MPI** | Scientific computing, HPC workloads |

## When to Use Each Framework

### Spark
- Processing terabyte-scale data
- SQL analytics on big data
- ETL pipelines
- Structured data processing

### Ray
- Distributed model training
- Hyperparameter optimization
- Reinforcement learning
- Generic Python parallelization

### Dask
- Scaling pandas workflows
- Parallel NumPy operations
- Lazy evaluation needed
- Familiar pandas/NumPy API preferred

## Launching On-Demand Clusters

### Via Domino UI
1. Start a workspace or job
2. Check **Attach compute cluster**
3. Select:
   - **Cluster Type**: Spark, Ray, or Dask
   - **Worker Count**: Number of workers
   - **Hardware Tier**: Resources per worker
   - **Auto-scaling**: Enable/disable
4. Launch

### Via Python SDK
```python
from domino import Domino

domino = Domino("project-owner/project-name")

# Start workspace with Spark cluster
workspace = domino.workspace_start(
    hardware_tier_name="medium",
    cluster_config={
        "clusterType": "Spark",
        "workerCount": 4,
        "workerHardwareTier": "medium",
        "masterHardwareTier": "medium"
    }
)
```

## Apache Spark

### Connecting to Spark
```python
from pyspark.sql import SparkSession

# Domino auto-configures Spark
spark = SparkSession.builder.getOrCreate()

# Check configuration
print(f"Spark version: {spark.version}")
print(f"Executors: {spark.sparkContext.defaultParallelism}")
```

Reading data, transformations, MLlib pipelines, writing results and Spark RAPIDS on GPUs: [FRAMEWORK-EXAMPLES.md](./FRAMEWORK-EXAMPLES.md#apache-spark).

## Ray

### Connecting to Ray
```python
import ray

# Domino auto-initializes Ray
# Or manually connect
ray.init(address="auto")

print(f"Cluster resources: {ray.cluster_resources()}")
```

Parallel tasks, Ray Train, Ray Tune and GPU workers: [FRAMEWORK-EXAMPLES.md](./FRAMEWORK-EXAMPLES.md#ray).

## Dask

### Connecting to Dask
```python
from dask.distributed import Client

# Domino auto-configures Dask
client = Client()

print(f"Dashboard: {client.dashboard_link}")
print(f"Workers: {len(client.scheduler_info()['workers'])}")
```

Dask DataFrames, Dask Arrays and Dask-ML grid search: [FRAMEWORK-EXAMPLES.md](./FRAMEWORK-EXAMPLES.md#dask).

## Autoscaling

### Enable Autoscaling
Configure clusters to scale based on workload:
```python
cluster_config = {
    "clusterType": "Spark",
    "workerCount": 2,
    "maxWorkerCount": 10,  # Scale up to 10
    "autoScaling": True
}
```

### Monitor Scaling
View cluster status in Domino UI or via dashboard URLs.

## Best Practices

### 1. Choose Right Framework
- SQL/ETL: Spark
- ML/Parallel Python: Ray
- Pandas at scale: Dask

### 2. Right-size Clusters
- Start small, scale up
- Monitor resource usage
- Use autoscaling when unsure

### 3. Data Locality
```python
# Keep data close to compute
# Use Domino Datasets or cloud storage in same region
df = spark.read.parquet("/mnt/data/dataset/")
```

### 4. Persist Intermediate Results
```python
# Cache frequently used DataFrames
df.cache()
df.persist()
```

## Troubleshooting

### Cluster Won't Start
- Check hardware tier availability
- Verify cluster environment builds
- Review cluster logs

### Out of Memory
- Increase worker memory
- Add more workers
- Optimize code (reduce shuffles)

### Slow Performance
- Check data locality
- Review partition sizes
- Monitor cluster dashboard

## Reference files

- [FRAMEWORK-EXAMPLES.md](./FRAMEWORK-EXAMPLES.md) - Read when writing Spark, Ray or Dask code beyond connecting: data I/O, processing, distributed training and tuning, GPU clusters

## Documentation Reference
- [On-demand distributed computing](https://docs.dominodatalab.com/en/latest/user_guide/8b4418/on-demand-distributed-computing/)
- [Spark, Dask, Ray comparison](https://domino.ai/blog/spark-dask-ray-choosing-the-right-framework)
- [Access data with Dask](https://docs.dominodatalab.com/en/latest/user_guide/0919a6/access-data-with-dask/)
