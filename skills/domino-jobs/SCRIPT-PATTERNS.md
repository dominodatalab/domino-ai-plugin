# Job script patterns

Applies to Domino 6.3 and Domino Cloud. What a script sees inside a Domino Job, where to write outputs, how logs and results are captured, script-side practices, Quartz cron syntax for scheduled Jobs, and troubleshooting. Starting, scheduling and monitoring Jobs: [SKILL.md](./SKILL.md).

## Job commands

The command is run from `DOMINO_WORKING_DIR` with the Project files in place. Domino recognises the file type from the extension:

```bash
python train.py --data /mnt/data/my-dataset/train.csv   # Python script with arguments
train.py --epochs 10                                      # same; interpreter chosen by extension
Rscript analysis.R                                        # R
notebook.ipynb                                            # executes the notebook and saves the result
bash pipeline.sh                                          # shell wrapper (for spark-submit, nbconvert, ...)
```

Any non-zero exit code marks the Job **Failed**. To treat a specific code (here `2`) as success, wrap the command so the wrapper's last status is what Domino sees:

```bash
bash -c 'python train.py "$@"; rc=$?; [ $rc -eq 0 ] || [ $rc -eq 2 ]' _ --epochs 10
```

## Environment variables in a Job

Documented defaults (full glossary: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/manage-compute-environments/manage-environment-variables/5-glossary-default-variables):

```python
import os

os.environ["DOMINO_RUN_ID"], os.environ["DOMINO_RUN_NUMBER"]
os.environ["DOMINO_PROJECT_ID"], os.environ["DOMINO_PROJECT_NAME"], os.environ["DOMINO_PROJECT_OWNER"]
os.environ["DOMINO_USER_NAME"], os.environ["DOMINO_STARTING_USERNAME"]
os.environ["DOMINO_WORKING_DIR"]                 # /mnt (DFS) or /mnt/code (Git-based)
os.environ.get("DOMINO_IS_GIT_BASED")            # "true" / "false"
os.environ["DOMINO_HARDWARE_TIER_ID"]
os.environ["DOMINO_API_HOST"], os.environ["DOMINO_API_PROXY"]
os.environ.get("MY_SETTING")                     # Project, environment or user variable you defined
```

Names starting with `DOMINO_` are reserved; prefix your own variables (`ACME_...`). `DOMINO_USER_API_KEY` is deprecated: call the API through `DOMINO_API_PROXY` instead.

## Where to write outputs

| | DFS Project | Git-based Project |
|---|---|---|
| Working directory | `/mnt` | `/mnt/code` (the repository) |
| Tracked as results | anything changed under `/mnt` | changes under `/mnt/artifacts`; put files in `/mnt/artifacts/results/` for email attachments |
| Datasets | `/domino/datasets/local/<name>` | `/mnt/data/<name>` |
| `email.html`, `dominostats.json`, `.dominoresults` | Project root `/mnt` | `/mnt/artifacts` (`dominostats.json` at the Project root) |

Results are the files added or modified between the Job's input and output commits; use them for models, reports and metrics files. Large or many files belong in a Dataset ([domino-datasets](../domino-datasets/SKILL.md)): by default a Project holds at most 10,000 files and a single file transfer is capped at 8 GB (both admin-configurable), and sync time grows with size. Project files are not mounted on compute-cluster nodes, so a Job with a cluster writes to a Dataset.

```python
import json, os
from pathlib import Path

git_based = os.environ.get("DOMINO_IS_GIT_BASED", "false").lower() == "true"
out = Path("/mnt/artifacts/results") if git_based else Path(os.environ["DOMINO_WORKING_DIR"]) / "results"
out.mkdir(parents=True, exist_ok=True)
joblib.dump(model, out / "model.joblib")
(out / "metrics.json").write_text(json.dumps(metrics))
```

## Dashboard columns and emails

- `dominostats.json` (Project root): a flat JSON object; each key becomes a column on the Jobs dashboard and a series on the Jobs Timeline. Domino deletes the file before each execution, so write it every run.
  ```python
  with open("dominostats.json", "w") as f:
      json.dump({"R^2": 0.99, "sse": 10.49}, f)
  ```
- `email.html`: body of the success email; `<head><title>...</title></head>` sets the subject; inline CSS; image paths relative to the Project root.
- `.dominoresults`: one path or glob per line (`*.pdf`, `results/*.png`, `**/*.txt`) selecting what the results view shows and the email attaches; if you use it, list `email.html` in it. `.dominoignore` patterns are excluded from the new file revision altogether (the files are not saved), so use it for scratch output, never to hide a result you still want.
- MLflow is the recommended place for metrics ([domino-experiment-tracking](../domino-experiment-tracking/SKILL.md)); `dominostats.json` is the lightweight dashboard option.
- Who gets the emails is a per-collaborator preference: Project **Settings > Access and Sharing**, or the Internal API (internal API, may change between Domino versions; live-verified on Domino 6.4, confirm on 6.3 in your deployment's `/docs`). Read the current values with `GET /v4/projects/{projectId}/projectSettingsCollaborators` (`[{collaborator: {id, ...}, role, participantNotificationSettings}]`) and set one with `PATCH /v4/projects/{projectId}/notificationPreference` `{"collaboratorId": "<user id>", "notificationPreference": "AllRuns" | "RunsStartedByUser" | "Never"}`; any other value is rejected with `500 No value found`. Failure emails are always sent.

## Pin the commit after an upload

In a DFS Project the Jobs service can resolve the head commit from before an upload for a few seconds after the files API already shows the file. A Job started in that window without `commitId` runs the previous commit and fails with `can't open file`. Pin the commit:

- MCP: the upload tools (`upload_file_to_domino_project`, `sync_local_file_to_domino`, `smart_sync_file`) return `commitId`, and `run_domino_job` passes the newest commit containing recent uploads by itself (or takes an explicit `commit_id`).
- REST: use the `commitId` the upload returned, or poll the DFS head until it contains your file, then pass it:

```python
import os, time, requests
from urllib.parse import quote

base = os.environ["DOMINO_API_PROXY"]                 # outside a run: DOMINO_API_HOST + Bearer token
project_id = os.environ["DOMINO_PROJECT_ID"]
path = quote("sum_squares.py", safe="")               # path relative to the Project root, URL-encoded

for _ in range(30):
    commit = requests.get(f"{base}/api/projects/beta/projects/{project_id}/commits/latest").json()["commitId"]
    if requests.get(f"{base}/api/projects/v1/projects/{project_id}/files/{commit}/{path}/content").status_code == 200:
        break                                         # the head now contains the uploaded file
    time.sleep(2)
else:
    raise SystemExit("uploaded file is not in the DFS head yet")

job = requests.post(f"{base}/api/jobs/v1/jobs", json={
    "projectId": project_id, "runCommand": "python sum_squares.py", "commitId": commit,
}).json()["job"]
assert job["commitDetails"]["inputCommitId"] == commit
```

Both routes are in the 6.3 and Cloud specs. If the file existed before the upload, the 200 check cannot tell old content from new: compare the returned bytes with what you uploaded, or use the `commitId` the upload returned. Git-based Projects do not take `commitId`; pin code with `mainRepoGitRef` (`{"refType": "commitId", "value": "<sha>"}`) after pushing.

## Logs

Everything written to stdout and stderr is captured. In the UI the Job's **Logs** tab offers Setup Output, User Output, Deployment Logs and a Support Bundle. From code:

```python
import os, requests

base = os.environ["DOMINO_API_PROXY"]                 # outside a run: DOMINO_API_HOST + Bearer token
logs = requests.get(f"{base}/api/jobs/beta/jobs/{job_id}/logs",
                    params={"logType": "stdOut", "limit": 1000}).json()
for line in logs["logs"]["logContent"]:
    print(line["timestamp"], line["log"], end="")
# logs["logs"]["isComplete"]; pass metadata.pagination.latestTimeNano back as latestTimeNano for the next page
```

`logType` is `stdOut`, `stdErr`, `prepareOutput` (setup) or `complete`.

## Script practices

```python
import argparse, logging, sys

parser = argparse.ArgumentParser()
parser.add_argument("--data-path", required=True)
parser.add_argument("--epochs", type=int, default=100)
args = parser.parse_args()

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

try:
    for epoch in range(args.epochs):
        log.info("epoch %d/%d", epoch + 1, args.epochs)
        # ...
except Exception:
    log.exception("training failed")
    save_checkpoint(model, out / "checkpoint.pt")    # keep partial work as a result
    raise                                             # non-zero exit -> Failed, failure email
```

- Parameterize with arguments or environment variables rather than editing the script per run; the Job records the command.
- Flush logs (`print(..., flush=True)` or logging to stdout) so progress is visible while running.
- Pin dependencies in the environment Dockerfile, not `requirements.txt`, for fast repeatable starts ([domino-environments](../domino-environments/SKILL.md)).
- Read inputs from Datasets or data sources; write reproducible outputs to the results directory and large artifacts to a Dataset with a completion snapshot (`snapshotDatasetsOnCompletion`).

## Quartz cron expressions

A scheduled Job's **Schedule** is a repeat interval or a Quartz CronTrigger expression, not five-field crontab: six required fields plus an optional year, seconds first, and `?` in exactly one of day-of-month or day-of-week.

```
sec   min   hour  day-of-month  month         day-of-week                  [year]
0-59  0-59  0-23  1-31 or ?     1-12/JAN-DEC  1-7 or SUN-SAT (1=SUN) or ?
```

| Schedule | Expression |
|---|---|
| Every hour on the hour | `0 0 * * * ?` |
| Daily at 00:00 | `0 0 0 * * ?` |
| Mondays at 09:00 | `0 0 9 ? * MON` |

Special characters (`-`, `/`, `L`, `W`, `#`): https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html

## Troubleshooting failed Jobs

- **Fails at once with `Failed`** (non-zero exit): read `stdErr`; typical causes are a wrong relative path (the working directory is `/mnt` or `/mnt/code`), a missing package in the environment revision, or a missing argument.
- **`Error` state**: platform-side; check `prepareOutput` logs, the environment build status and the hardware tier's capacity, then open the support bundle.
- **Out of memory**: larger hardware tier, chunked loading, or a compute cluster; check **Usage** on the Job.
- **Long queue times**: per-user execution limit, tier capacity, or a cluster waiting for workers. **Building** or **Pulling**: the environment revision is still being built or pulled.
- **Results missing**: files written outside the tracked directories (table above), or matched by `.dominoignore` (they are dropped from the revision, not just hidden).
