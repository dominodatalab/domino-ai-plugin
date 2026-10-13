# Domino Flows examples

Applies to Domino 6.3 and Domino Cloud. Every API used here is documented at https://docs.domino.ai/cloud/platform-capabilities/features/flows/define-flows and `.../define-flow-artifacts`. Paths assume a Git-based project (`/mnt/code`, `/mnt/data/<dataset>`); in a DFS project use `/mnt` and `/domino/datasets/local/<dataset>`. Hardware tier and environment ids are placeholders; look yours up as described in [FLOW-BASICS.md](./FLOW-BASICS.md).

## Example 1: data pipeline (load, clean, features)

`flows/data_pipeline.py`:

```python
from typing import TypeVar
from flytekit import workflow
from flytekit.types.file import FlyteFile
from flytekitplugins.domino.task import DominoJobConfig, DominoJobTask

CSV = FlyteFile[TypeVar("csv")]

load_task = DominoJobTask(
    name="Load data",
    domino_job_config=DominoJobConfig(Command="python flows/stages/load.py"),
    inputs={"source_path": str},
    outputs={"raw": CSV},
    use_latest=True,
)
clean_task = DominoJobTask(
    name="Clean data",
    domino_job_config=DominoJobConfig(Command="python flows/stages/clean.py"),
    inputs={"raw": CSV, "max_missing": float},
    outputs={"clean": CSV},
    use_latest=True,
)
feature_task = DominoJobTask(
    name="Build features",
    domino_job_config=DominoJobConfig(Command="python flows/stages/features.py"),
    inputs={"clean": CSV},
    outputs={"features": CSV, "row_count": int},
    use_latest=True,
)

@workflow
def data_pipeline(source_path: str = "/mnt/data/raw/transactions.csv", max_missing: float = 0.2) -> CSV:
    raw = load_task(source_path=source_path)                       # one output: a single promise
    clean = clean_task(raw=raw, max_missing=max_missing)           # pass it as is
    features = feature_task(clean=clean)
    return features.features                                       # two outputs: a namedtuple, select by attribute
```

A task with one declared output returns the promise itself; one with several returns a namedtuple (`features.features`, `features.row_count`, or `features_file, row_count = feature_task(...)`). `features["features"]` does not compile for multi-output tasks (`TypeError: tuple indices must be integers or slices, not str`), and `raw["raw"]` on a single-output task binds a lookup inside the file rather than the output.

`flows/stages/load.py`:

```python
from pathlib import Path
import pandas as pd

source_path = Path("/workflow/inputs/source_path").read_text().strip()
df = pd.read_csv(source_path)
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
df.to_csv("/workflow/outputs/raw", index=False)
print(f"loaded {len(df)} rows from {source_path}")
```

`flows/stages/clean.py`:

```python
from pathlib import Path
import pandas as pd

df = pd.read_csv("/workflow/inputs/raw")
max_missing = float(Path("/workflow/inputs/max_missing").read_text())
keep = df.columns[df.isna().mean() <= max_missing]
df = df[keep].dropna()
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
df.to_csv("/workflow/outputs/clean", index=False)
```

`flows/stages/features.py`:

```python
from pathlib import Path
import numpy as np
import pandas as pd

df = pd.read_csv("/workflow/inputs/clean")
df["amount_log"] = np.log1p(df["amount"].clip(lower=0))
out = Path("/workflow/outputs")
out.mkdir(parents=True, exist_ok=True)
df.to_csv(out / "features", index=False)
(out / "row_count").write_text(str(len(df)))
```

Launch:

```bash
git add flows && git commit -m "data pipeline" && git push
pyflyte run --remote --name data-pipeline-1 flows/data_pipeline.py data_pipeline \
  --source_path /mnt/data/raw/transactions.csv --max_missing 0.1
```

## Example 2: training pipeline with Flow Artifacts, MLflow and parallel evaluation

`flows/training_pipeline.py`:

```python
from typing import TypeVar
from flytekit import workflow
from flytekit.types.file import FlyteFile
from flytekitplugins.domino.helpers import Input, Output, run_domino_job_task
from flytekitplugins.domino.artifact import (
    Artifact, DATA, MODEL, REPORT, ExportArtifactToDatasetsSpec, run_launch_export_artifacts_task,
)

CSV = FlyteFile[TypeVar("csv")]
PKL = FlyteFile[TypeVar("pkl")]
DataArtifact = Artifact(name="Training splits", type=DATA)
ModelArtifact = Artifact(name="Churn model", type=MODEL)
ReportArtifact = Artifact(name="Evaluation", type=REPORT)

@workflow
def training_pipeline(features_path: str, test_size: float = 0.2) -> ModelArtifact.File(name="model.pkl"):
    split = run_domino_job_task(
        flyte_task_name="Split",
        command="python flows/stages/split.py",
        inputs=[Input(name="features_path", type=str, value=features_path),
                Input(name="test_size", type=float, value=test_size)],
        output_specs=[Output(name="train", type=DataArtifact.File(name="train.csv")),
                      Output(name="test", type=DataArtifact.File(name="test.csv"))],
        use_project_defaults_for_omitted=True,
        cache=True, cache_version="1.0",          # same inputs and code => reuse the split
    )
    train = run_domino_job_task(
        flyte_task_name="Train",
        command="python flows/stages/train.py",
        inputs=[Input(name="train", type=CSV, value=split.train)],    # two outputs: attribute access
        output_specs=[Output(name="model", type=PKL)],
        hardware_tier_id="large-k8s",             # id from GET /api/hardwaretiers/v1/hardwaretiers
        use_project_defaults_for_omitted=True,
    )
    # Both evaluations depend only on train and split, so they run in parallel
    run_domino_job_task(
        flyte_task_name="Evaluate metrics",
        command="python flows/stages/evaluate.py",
        inputs=[Input(name="model", type=PKL, value=train),            # one output: the promise itself
                Input(name="test", type=CSV, value=split.test)],
        output_specs=[Output(name="metrics", type=ReportArtifact.File(name="metrics.json"))],
        use_project_defaults_for_omitted=True,
    )
    run_domino_job_task(
        flyte_task_name="Plot ROC",
        command="python flows/stages/plot.py",
        inputs=[Input(name="model", type=PKL, value=train),
                Input(name="test", type=CSV, value=split.test)],
        output_specs=[Output(name="roc", type=ReportArtifact.File(name="roc.png"))],
        use_project_defaults_for_omitted=True,
    )
    # Copy the split files into a Domino Dataset once the run finishes (separate export execution)
    run_launch_export_artifacts_task(
        spec_list=[ExportArtifactToDatasetsSpec(artifact=DataArtifact, dataset_id="681d3030ae3a706ef9c7f08b")],
        environment_name="Domino Standard Environment",
        hardware_tier_id="small-k8s",
        use_project_defaults_for_omitted=True,
    )
    return train
```

`flows/stages/split.py`:

```python
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split

features_path = Path("/workflow/inputs/features_path").read_text().strip()
test_size = float(Path("/workflow/inputs/test_size").read_text())
df = pd.read_csv(features_path)
train, test = train_test_split(df, test_size=test_size, random_state=42, stratify=df["churned"])
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
train.to_csv("/workflow/outputs/train", index=False)
test.to_csv("/workflow/outputs/test", index=False)
```

`flows/stages/train.py` (logs to the Experiment Manager; see `domino-experiment-tracking` for naming rules):

```python
import os
import pickle
from pathlib import Path
import mlflow
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

df = pd.read_csv("/workflow/inputs/train")
X, y = df.drop(columns=["churned"]), df["churned"]

mlflow.set_experiment(f"churn-{os.environ['DOMINO_PROJECT_NAME']}-{os.environ['DOMINO_STARTING_USERNAME']}")
with mlflow.start_run(run_name=f"flow-job-{os.environ.get('DOMINO_RUN_NUMBER', '')}"):
    model = GradientBoostingClassifier().fit(X, y)
    mlflow.log_metric("train_accuracy", model.score(X, y))
    mlflow.sklearn.log_model(model, "model")

Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
with open("/workflow/outputs/model", "wb") as f:
    pickle.dump(model, f)
```

`flows/stages/evaluate.py`:

```python
import json
import pickle
from pathlib import Path
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

model = pickle.load(open("/workflow/inputs/model", "rb"))
df = pd.read_csv("/workflow/inputs/test")
X, y = df.drop(columns=["churned"]), df["churned"]
metrics = {"accuracy": accuracy_score(y, model.predict(X)),
           "roc_auc": roc_auc_score(y, model.predict_proba(X)[:, 1])}
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
Path("/workflow/outputs/metrics").write_text(json.dumps(metrics))
```

`flows/stages/plot.py`:

```python
import pickle
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import RocCurveDisplay

model = pickle.load(open("/workflow/inputs/model", "rb"))
df = pd.read_csv("/workflow/inputs/test")
X, y = df.drop(columns=["churned"]), df["churned"]
RocCurveDisplay.from_estimator(model, X, y)
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
with open("/workflow/outputs/roc", "wb") as f:      # output name has no extension; the Artifact file name carries it
    plt.savefig(f, format="png")
```

Launch:

```bash
pyflyte run --remote flows/training_pipeline.py training_pipeline --features_path /mnt/data/features/latest.csv
```

Flow Artifacts show up under the run with lineage; DATA artifacts can also be assigned to a Dataset from the UI (**Examine Flow Artifacts** in the docs). Behind that UI action is the internal `POST /v4/datasetrw/dataset/{datasetId}/snapshotFromFlowsArtifacts` (non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types)), whose body needs presigned blob URLs, a signature and the artifact id that the Flows backend supplies, so there is no one-call recipe; use the UI or the `run_launch_export_artifacts_task` export above. The export task launches a separate execution that waits for the run to finish, so its node may appear early in the graph.

## Example 3: production pinning and an approval gate

Replace `use_latest` / `use_project_defaults_for_omitted` with a complete config before putting a flow on a schedule, and gate deployment on a human check. With `use_latest=False` (the default) `DominoJobTask` raises unless every field below is set, so the config is written once and shared. The ids are placeholders; look yours up as in [FLOW-BASICS.md](./FLOW-BASICS.md) "Finding ids", or print the project defaults with `DominoJobConfig(Command="...").resolve_job_properties()` in a Workspace. This example reuses `split.py` and `train.py` from Example 2.

`flows/release_pipeline.py`:

```python
from datetime import timedelta
from typing import TypeVar
from flytekit import approve, workflow
from flytekit.types.file import FlyteFile
from flytekitplugins.domino.task import (
    DatasetSnapshot,
    DominoJobConfig,
    DominoJobTask,
    EnvironmentRevisionSpecification,
    EnvironmentRevisionType,
    GitRef,
)

CSV = FlyteFile[TypeVar("csv")]
PKL = FlyteFile[TypeVar("pkl")]

PINNED = dict(
    CommitId="4e6f2ee71e3bd64eaa90ce826c7d523b29f179cd",        # Git-based: artifacts commit; DFS: code commit
    MainRepoGitRef=GitRef(Type="commitId", Value="2f1cb9bf696921f0858e4a1c0b3d7f2a9c5e8d41"),  # Git-based only; must be commit-pinned
    EnvironmentId="66b5324c495c6c124cfb0a28",
    EnvironmentRevisionSpec=EnvironmentRevisionSpecification(
        EnvironmentRevisionType.SomeRevision, "6659daf5fc8de1a2b3c4d5e6"   # revision id, not the revision number
    ),
    HardwareTierId="large-k8s",
    VolumeSizeGiB=20,
    DatasetSnapshots=[DatasetSnapshot(Id="6615af2820a4b1c2d3e4f5a6", Version=3)],
    NetAppVolumeSnapshots=[],                                     # required even when unused
    ExternalVolumeMountIds=[],                                    # required even when unused
)


def pinned_task(name, script, inputs, outputs, **task_kwargs):
    return DominoJobTask(
        name=name,
        domino_job_config=DominoJobConfig(Command=f"python {script}", **PINNED),
        inputs=inputs,
        outputs=outputs,
        **task_kwargs,
    )


@workflow
def release_pipeline(features_path: str, test_size: float = 0.2) -> PKL:
    split = pinned_task("Split (pinned)", "flows/stages/split.py",
                        {"features_path": str, "test_size": float}, {"train": CSV, "test": CSV})
    splits = split(features_path=features_path, test_size=test_size)   # two outputs: namedtuple

    train = pinned_task("Train (pinned)", "flows/stages/train.py",
                        {"train": CSV}, {"model": PKL}, retries=1, timeout=timedelta(hours=2))
    trained = train(train=splits.train)                                  # one output: a single promise

    # The run pauses here until someone clicks Resume and approves in the Flows UI; rejecting stops it
    approved_model = approve(trained, "Release approval", timeout=timedelta(hours=24))

    package = pinned_task("Package for deployment", "flows/stages/package.py", {"model": PKL}, {"bundle": PKL})
    return package(model=approved_model)
```

`flows/stages/package.py`:

```python
import pickle
import shutil
from pathlib import Path

model = pickle.load(open("/workflow/inputs/model", "rb"))
assert hasattr(model, "predict"), "not a fitted estimator"
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
shutil.copyfile("/workflow/inputs/model", "/workflow/outputs/bundle")
```

In a DFS project drop `MainRepoGitRef` (it is only checked for Git-based projects). To run the flow nightly, create a scheduled Job in the project with this command (the Flows docs document `pyflyte run` "as the start command for a Job"; a scheduled Job is the pattern that follows, not a separate documented scheduler):

```bash
pyflyte run --remote flows/release_pipeline.py release_pipeline --features_path /mnt/data/features/latest.csv
```

Each scheduled run registers the current definition (a new version only if the code changed) and starts an execution; monitor it under **Flows**, and the individual Jobs under **Jobs**.

## Example 4: iterate on one node

```bash
# Launch once
pyflyte run --remote --name exp-7 flows/training_pipeline.py training_pipeline --features_path /mnt/data/features/latest.csv
```

Then in the Flows UI open run `exp-7`, click the **Train** node and **Rerun Node** with a different input, or **Re-run** the whole flow with a task override (different hardware tier or environment) without touching the code. When a transient failure (spot pre-emption, timeout) kills a node, **Recover** continues from the failed node and reuses the finished outputs; from a Workspace terminal or a Job the same recovery is one call:

```bash
curl -s -X POST "$FLYTE_PLATFORM_URL_HTTP/api/v1/executions/recover" -H 'Content-Type: application/json' \
  -d "{\"id\": {\"project\": \"$DOMINO_PROJECT_ID\", \"domain\": \"development\", \"name\": \"exp-7\"}}"
```

The other calls (re-launch, re-run with new inputs, stop, archive) and why they work only from inside Domino are in [FLOW-BASICS.md](./FLOW-BASICS.md#re-run-recover-stop-and-archive). Once the code changes, launch from the CLI again so a new version is registered.
