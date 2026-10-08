# python-domino SDK examples

Common python-domino operations (projects, jobs, workspaces, files, datasets, environments, Model APIs), the separate Domino Data API client, automation examples, error handling, and retry/logging helpers.

Authentication and client setup: [SKILL.md](./SKILL.md#authentication). Never pass `api_key=`.

## Common Operations

### Projects

```python
from domino import Domino

domino = Domino()

# Create project
project = domino.project_create(
    project_name="my-new-project",
    owner_name="username"
)

# Get project info
info = domino.project_info()
print(f"Project: {info['name']}")
print(f"ID: {info['id']}")
```

### Jobs (Runs)

```python
# Start a job
run = domino.runs_start(
    command="python train.py --epochs 100",
    hardware_tier_name="medium",
    environment_id="env-id"
)
print(f"Run ID: {run['runId']}")

# Start job with different commit
run = domino.runs_start(
    command="python train.py",
    commit_id="abc123"
)

# Check status
status = domino.runs_status(run['runId'])
print(f"Status: {status['status']}")

# Wait for completion
domino.runs_wait(run['runId'])

# Get logs
logs = domino.runs_get_logs(run['runId'])
print(logs)

# Stop a run
domino.runs_stop(run['runId'])
```

### Workspaces

```python
# Start workspace
workspace = domino.workspace_start(
    hardware_tier_name="medium",
    environment_id="env-id",
    workspace_type="JupyterLab"
)
print(f"Workspace ID: {workspace['workspaceId']}")

# Stop workspace
domino.workspace_stop(workspace['workspaceId'])
```

### Files

```python
# Upload file
domino.files_upload(
    path="local/file.csv",
    dest_path="/mnt/code/data/"
)

# Download file
domino.files_download(
    path="/mnt/code/results/output.csv",
    dest_path="local/output.csv"
)

# List files
files = domino.files_list("/mnt/code/")
for f in files:
    print(f['path'])
```

### Datasets

```python
# Create dataset
dataset = domino.datasets_create(
    name="training-data",
    description="Training dataset"
)

# List datasets
datasets = domino.datasets_list()

# Create snapshot
snapshot = domino.datasets_snapshot(
    dataset_name="training-data",
    tag="v1.0"
)
```

### Environments

```python
# List environments
environments = domino.environments_list()
for env in environments:
    print(f"{env['name']}: {env['id']}")

# Get environment details
env = domino.environment_get("env-id")
```

### Model APIs

```python
# Publish model
model = domino.model_publish(
    file="model.py",
    function="predict",
    environment_id="env-id",
    name="my-classifier",
    description="Classification model"
)
print(f"Model ID: {model['id']}")

# List models
models = domino.models_list()

# Get model info
model_info = domino.model_get("model-id")
```

## Domino Data API

Separate SDK for data access:

```python
from domino_data.data_sources import DataSourceClient

# Initialize client
client = DataSourceClient()

# List data sources
sources = client.list_data_sources()

# Query data source
df = client.get_datasource("my-datasource").query(
    "SELECT * FROM customers WHERE region = 'US'"
)
```

## Automation Examples

### CI/CD Integration
```python
# trigger_training.py - Call from CI/CD pipeline
from domino import Domino
import sys

domino = Domino("team/ml-project")

# Start training job
run = domino.runs_start(
    command="python train.py",
    hardware_tier_name="gpu-large"
)

# Wait for completion
result = domino.runs_wait(run['runId'])

if result['status'] != 'Succeeded':
    print(f"Training failed: {result['status']}")
    sys.exit(1)

print("Training completed successfully!")
```

### Batch Job Scheduler
```python
# Run multiple experiments
from domino import Domino
import itertools

domino = Domino("team/experiments")

# Parameter grid
params = {
    "learning_rate": [0.01, 0.001, 0.0001],
    "batch_size": [32, 64, 128]
}

# Generate combinations
combinations = list(itertools.product(*params.values()))
param_names = list(params.keys())

# Submit all experiments
runs = []
for combo in combinations:
    param_str = " ".join(
        f"--{name}={value}"
        for name, value in zip(param_names, combo)
    )
    run = domino.runs_start(
        command=f"python experiment.py {param_str}",
        hardware_tier_name="gpu-small"
    )
    runs.append(run['runId'])
    print(f"Started run {run['runId']} with {param_str}")

# Wait for all to complete
for run_id in runs:
    result = domino.runs_wait(run_id)
    print(f"Run {run_id}: {result['status']}")
```

### Model Deployment Pipeline
```python
from domino import Domino

domino = Domino("team/model-deployment")

# 1. Train model
train_run = domino.runs_start(command="python train.py")
domino.runs_wait(train_run['runId'])

# 2. Evaluate model
eval_run = domino.runs_start(command="python evaluate.py")
domino.runs_wait(eval_run['runId'])

# 3. Deploy if evaluation passes
# (Check evaluation results first)
model = domino.model_publish(
    file="serve.py",
    function="predict",
    name="production-model"
)

print(f"Model deployed: {model['id']}")
```

## Error Handling

```python
from domino import Domino
from domino.exceptions import DominoException

try:
    domino = Domino("team/project")
    run = domino.runs_start(command="python train.py")
except DominoException as e:
    print(f"Domino error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Best Practices

Item 1, follow [Authentication](./SKILL.md#authentication), stays in SKILL.md.

### 2. Handle Rate Limits
```python
import time
from domino.exceptions import DominoException

def api_call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except DominoException as e:
            if "rate limit" in str(e).lower():
                time.sleep(2 ** attempt)
            else:
                raise
    raise Exception("Max retries exceeded")
```

### 3. Log API Calls
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_run(command):
    logger.info(f"Starting run: {command}")
    run = domino.runs_start(command=command)
    logger.info(f"Run ID: {run['runId']}")
    return run
```
