# Job script patterns

Command lines for running Python, notebooks, R and shell scripts as Domino Jobs; what a script sees inside a job (environment variables, output paths, logs); script-side best practices; and troubleshooting failed jobs.

Starting, scheduling and monitoring jobs: [SKILL.md](./SKILL.md).

## Job Commands

### Run Python Script
```bash
python train.py
```

### Run with Arguments
```bash
python train.py --data /mnt/data/train.csv --output /mnt/artifacts/model.pkl
```

### Run Jupyter Notebook
```bash
jupyter nbconvert --to notebook --execute notebook.ipynb
```

### Run R Script
```bash
Rscript analysis.R
```

### Run Shell Script
```bash
bash pipeline.sh
```

## Environment Variables in Jobs

```python
import os

# Domino-provided
run_id = os.environ.get('DOMINO_RUN_ID')
project_name = os.environ.get('DOMINO_PROJECT_NAME')
username = os.environ.get('DOMINO_USER_NAME')

# Custom (set in project or job settings)
api_key = os.environ.get('MY_API_KEY')
```

## Accessing Job Results

### Output Files
Files written to `/mnt/` directories are available after job completion:
- `/mnt/results/` - Custom outputs
- `/mnt/artifacts/` - Model artifacts

### Job Logs
View logs in Domino UI or via API:
```python
# Get job logs
logs = domino.runs_get_logs(run_id)
print(logs)
```

### Stdout/Stderr
All print statements and errors are captured in job logs.

## Job Best Practices

### 1. Parameterize Scripts
```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--data-path', required=True)
parser.add_argument('--model-output', required=True)
parser.add_argument('--epochs', type=int, default=100)
args = parser.parse_args()
```

### 2. Log Progress
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting training...")
logger.info(f"Epoch {epoch}/{total_epochs}")
logger.info("Training complete!")
```

### 3. Handle Failures Gracefully
```python
try:
    train_model(data)
except Exception as e:
    logger.error(f"Training failed: {e}")
    # Save checkpoint
    save_checkpoint(model, "checkpoint.pt")
    raise
```

### 4. Save Artifacts
```python
import joblib

# Save model
joblib.dump(model, "/mnt/artifacts/model.joblib")

# Save metrics
with open("/mnt/artifacts/metrics.json", "w") as f:
    json.dump(metrics, f)
```

## Troubleshooting

### Job Fails Immediately
- Check script syntax
- Verify file paths exist
- Check environment has required packages

### Job Times Out
- Increase hardware tier resources
- Optimize code performance
- Check for infinite loops

### Out of Memory
- Use larger hardware tier
- Optimize data loading (chunking, generators)
- Clear variables when no longer needed
