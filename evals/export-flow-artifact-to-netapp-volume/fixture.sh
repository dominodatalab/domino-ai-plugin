#!/usr/bin/env bash
set -euo pipefail
mkdir -p stages
cat > flow.py <<'EOF'
from typing import TypeVar
from flytekit import workflow
from flytekit.types.file import FlyteFile
from flytekitplugins.domino.task import DominoJobConfig, DominoJobTask

CSV = FlyteFile[TypeVar("csv")]

clean_task = DominoJobTask(
    name="Clean data",
    domino_job_config=DominoJobConfig(Command="python stages/clean.py"),
    inputs={"raw_path": str},
    outputs={"cleaned": CSV},
    use_latest=True,
)


@workflow
def clean_flow(raw_path: str = "/mnt/data/raw/orders.csv") -> CSV:
    return clean_task(raw_path=raw_path)
EOF
cat > stages/clean.py <<'EOF'
from pathlib import Path
import pandas as pd

raw_path = Path("/workflow/inputs/raw_path").read_text().strip()
df = pd.read_csv(raw_path).dropna()
Path("/workflow/outputs").mkdir(parents=True, exist_ok=True)
df.to_csv("/workflow/outputs/cleaned", index=False)
EOF
