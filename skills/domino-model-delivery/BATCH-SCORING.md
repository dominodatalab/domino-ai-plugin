# Batch scoring with Domino Jobs

Product page: https://docs.domino.ai/cloud/platform-capabilities/features/models/batch-scoring
(the 6.3 page has the same content). A batch scoring Job is an ordinary Domino Job whose command
is a scoring script. Everything about Jobs in general (hardware tiers, environments, logs, script
patterns, Quartz cron syntax) is in [domino-jobs](../domino-jobs/SKILL.md) and its
SCRIPT-PATTERNS.md; this file covers only what is specific to scoring.

## When to choose a Job over an endpoint

| Use a batch scoring Job | Use an endpoint |
|---|---|
| Fire-and-forget scoring of many records, no strict SLA | Interactive or customer-facing predictions |
| Input arrives periodically (nightly file, table refresh) | Each caller needs its own answer now |
| Results are files or table writes | Results are HTTP responses |
| Needs a Spark, Ray or Dask cluster or a large hardware tier | Needs replicas and autoscaling |

Long single predictions that still need request/response semantics belong on an **asynchronous
endpoint** (last section).

## 1. The scoring script

Write it like any Job script ([SCRIPT-PATTERNS.md](../domino-jobs/SCRIPT-PATTERNS.md) covers
arguments, environment variables and output paths). Scoring-specific points:

- **Load the model once** at the top of the script, from a project file, a mounted Dataset or
  the Model Registry (`mlflow` client; see
  [domino-experiment-tracking](../domino-experiment-tracking/SKILL.md)).
- **Read input** from a mounted Dataset ([domino-datasets](../domino-datasets/SKILL.md)), a Data
  Source ([domino-data-sdk](../domino-data-sdk/SKILL.md)) or a file path passed as an argument.
- **Write predictions** to a file in the project's results location or to a Dataset or Data
  Source. Files the Job adds or modifies are captured as its results; a Dataset write is not a
  Job result but survives on the Dataset.
- **Parameterise** the run date or partition on the command line so one scheduled Job handles
  every period: `python score.py --as-of 2026-10-01`.

```python
# score.py
import argparse, pickle
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

with open("model.pkl", "rb") as f:
    model = pickle.load(f)

df = pd.read_csv(args.input)
df["prediction"] = model.predict(df)
df.to_csv(args.output, index=False)
print(f"scored {len(df)} rows -> {args.output}")   # the last lines of stdout go into the result email
```

## 2. Run it once

UI: **Jobs > Run**, file `score.py` with arguments, hardware tier, environment, optional cluster.

API (Public, both specs):

```bash
# In a run: BASE=$DOMINO_API_PROXY and no AUTH header. Outside: export DOMINO_API_HOST=<deployment URL>, BASE=$DOMINO_API_HOST, AUTH="Authorization: Bearer <PAT>".
curl -sS -X POST "$BASE/api/jobs/v1/jobs" -H "$AUTH" -H "Content-Type: application/json" -d '{
  "projectId": "'"$DOMINO_PROJECT_ID"'",
  "runCommand": "python score.py --input /mnt/data/scoring/today.csv --output results/scored.csv",
  "title": "nightly scoring",
  "environmentId": "<environment id>",
  "hardwareTier": "<hardware tier id, e.g. small-k8s>"
}'
```

`projectId` and `runCommand` are the only required fields; `environmentId` and `hardwareTier`
default to the project settings. Add `computeCluster` for Spark, Ray or Dask. The response's
`job.id` is the Job id for polling.

Other ways to start the same Job: `domino run --wait score.py <arguments>` from a laptop with
the Domino CLI (DFS projects; [domino-cli](../domino-cli/SKILL.md)); a Launcher, when business
users should pick the input file or date in a web form
([domino-launchers](../domino-launchers/SKILL.md)).

## 3. Schedule it

**Jobs > Schedules > Schedule a Job**:

| Field | Note |
|---|---|
| File Name | `score.py --as-of ...`; arguments go in the same box |
| Data Plane & Hardware | tier, plus the Datasets and NetApp Volumes the Job mounts (pin a snapshot per asset if the input must be reproducible) |
| Environment | revision defaults to the latest; the UI recommends the project owner's active revision |
| Schedule | Quartz CronTrigger, six fields, seconds first: `0 0 2 * * ?` is 02:00 daily |
| Run sequentially | on, if run N+1 must not start before run N finishes |
| Notify emails | who gets the completion mail |
| Update Domino endpoint | republish an endpoint after the Job; for retraining, not scoring |

There is no Public API route for scheduled Jobs (stated on
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/jobs/schedule-a-job). Create and
edit schedules in the UI. There is no pause: edit the schedule to a far-future start time.

If Apache Airflow or Kubeflow Pipelines already owns the nightly schedule, keep it there: a task
starts this Job over the same `POST /api/jobs/v1/jobs`, waits for it and collects the result file
([domino-airflow-kubeflow](../domino-airflow-kubeflow/SKILL.md)).

## 4. Monitor and collect results

Poll (Public, both specs; beta endpoint):

```bash
curl -sS "$BASE/api/jobs/beta/jobs/$JOB_ID" -H "$AUTH" | python3 -c '
import json,sys; j=json.load(sys.stdin)["job"]
print(j["status"]["isCompleted"], j["status"]["executionStatus"], j.get("commitDetails",{}).get("outputCommitId"))'
```

Terminal when `status.isCompleted` is true; success when `status.executionStatus` is
`Succeeded`. `commitDetails.outputCommitId` is the project commit holding the results.

Fetch a result file (Public, both specs):

```bash
curl -sS -o scored.csv "$BASE/api/projects/v1/projects/$DOMINO_PROJECT_ID/files/$OUTPUT_COMMIT_ID/results%2Fscored.csv/content" -H "$AUTH"
```

The `{path}` segment is the project-relative path, URL-encoded. Logs:
`GET $BASE/api/jobs/beta/jobs/{jobId}/logs?logType=stdOut` (`stdOut`, `stdErr`, `prepareOutput`,
`complete`). In the UI, the **Results** tab of the Job lists the same files, and the completion
email carries the last lines of stdout plus up to ten result files; custom report emails:
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/jobs/customize-job-results

## Troubleshooting

| Symptom | Where to look |
|---|---|
| Fails before the script starts | **Setup Output** (`logType=prepareOutput`): environment, mounts, cluster |
| Script error | **User Output** (`stdOut`, `stdErr`); fix `score.py` |
| Infrastructure or scheduling failure | Deployment logs on the Job page; share with Domino support |
| Runs overlap | turn on **Run sequentially** |
| Output missing from results | the file was written outside the project working directory (for example into a Dataset), or the script exited before writing |

## Alternative: asynchronous endpoint

For predictions that take minutes but still need an HTTP request/response contract, deploy the
model as an **asynchronous Domino endpoint** and call it with the model access token (Public API,
both specs):

```text
POST /api/modelApis/async/v1/{asyncModelId}                       body {"parameters": {...}} -> {"asyncPredictionId"}
GET  /api/modelApis/async/v1/{asyncModelId}/{asyncPredictionId}   -> {"status": "queued" | "succeeded" | "failed", "result", "errors"}
```

Request and response payloads are capped at 10 KB, so pass data by reference (a path or table
name) and read and write it through a Data Source with the domino-data SDK (an endpoint needs a
service-account token, see `domino-data-sdk`) rather than raw cloud credentials; Domino keeps a picked-up request alive for 30
minutes. Python client with retries and polling:
https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/async-example-client
Deploying the endpoint: [domino-model-endpoints](../domino-model-endpoints/SKILL.md).
