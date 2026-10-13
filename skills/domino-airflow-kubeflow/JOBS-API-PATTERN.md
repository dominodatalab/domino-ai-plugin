# Start, wait, collect: the Jobs API pattern behind every orchestrator step

Every external orchestrator step is the same three Public API calls. Routes and fields below are
in both published specs (`https://docs.domino.ai/api-specs/6.3/public-api.json`,
`https://docs.domino.ai/api-specs/cloud/public-api.json`). Field semantics:
[domino-jobs](../domino-jobs/SKILL.md).

## Base URL and token outside Domino

```bash
BASE="$DOMINO_API_HOST"                        # export DOMINO_API_HOST=<the deployment URL users open in a browser>
AUTH="Authorization: Bearer $DOMINO_TOKEN"     # Personal Access Token or service-account token
```

Nothing injected into Domino runs is available here: no `DOMINO_API_PROXY`, no
`localhost:8899/access-token`, no `127.0.0.1:8763`. Legacy API keys are deprecated.

## 1. Start

```bash
curl -sS -X POST "$BASE/api/jobs/v1/jobs" -H "$AUTH" -H "Content-Type: application/json" -d '{
  "projectId": "<project id>",
  "runCommand": "python train.py --as-of 2026-10-01",
  "title": "airflow churn_pipeline 2026-10-01",
  "environmentId": "<environment id>",
  "hardwareTier": "<hardware tier id, e.g. small-k8s>"
}'
```

| Field | Required | Note |
|---|---|---|
| `projectId`, `runCommand` | yes | the only required fields |
| `title` | no | shows in the Jobs dashboard; put the orchestrator run id in it |
| `environmentId`, `environmentRevisionSpec` | no | default: project environment, `ActiveRevision` |
| `hardwareTier` | no | hardware tier **id** |
| `commitId` | no | DFS commit to run from; not a git SHA |
| `mainRepoGitRef` | no | `{"refType": "head" \| "commitId" \| "tags" \| "branches", "value": ...}` for Git-based projects; `value` only where the type needs one |
| `computeCluster` | no | `{"clusterType": "spark" \| "ray" \| "dask" \| "mpi" \| "slurm", "computeEnvironmentId", "workerCount", "workerHardwareTier", "masterHardwareTierId"?, "maxWorkerCount"?, "workerStorageMB"?}`; cluster environments (Spark, Ray, Dask, MPI): [domino-distributed-computing](../domino-distributed-computing/SKILL.md) |
| `externalVolumeMountIds`, `netAppVolumeIds` | no | volumes to mount |
| `snapshotDatasetsOnCompletion`, `snapshotNetAppVolumesOnCompletion` | no | snapshot mounted storage when the Job ends |

Response: `{"job": {"id": ..., "status": {...}, ...}}`. Keep `job.id`.

## 2. Wait

```bash
until job=$(curl -sS "$BASE/api/jobs/beta/jobs/$JOB_ID" -H "$AUTH") && \
      [[ $(echo "$job" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job"]["status"]["isCompleted"])') == True ]]; do
  sleep 30
done
echo "$job" | python3 -c 'import json,sys; s=json.load(sys.stdin)["job"]["status"]; print(s["executionStatus"])'
```

`status.isCompleted` is the terminal flag; `status.executionStatus` is a string whose success
value is `Succeeded` (the spec's example). Treat anything else at completion as failure. The
endpoint is marked beta in the spec; it is the only Public route for Job details.

Other status fields: `isArchived`, `isScheduled`; `stageTimes` (`submissionTime`, `startTime`,
`completedTime`) for duration metrics; `queuedJobStatusDetails` (`expectedWait`, `explanation`)
while the Job waits for capacity.

## 3. Collect

Logs (paginated, `latestTimeNano` continues a page):

```bash
curl -sS "$BASE/api/jobs/beta/jobs/$JOB_ID/logs?logType=stdErr&limit=500" -H "$AUTH"
# {"logs": {"logContent": [{"timestamp", "logType", "log", "size"}], "isComplete"}, "metadata": {"pagination": {"latestTimeNano", "limit"}}}
```

`logType`: `stdOut`, `stdErr`, `prepareOutput` (setup), `complete`.

Result files, by the Job's output commit:

```bash
COMMIT=$(echo "$job" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job"]["commitDetails"]["outputCommitId"])')
curl -sS -o metrics.json "$BASE/api/projects/v1/projects/$PROJECT_ID/files/$COMMIT/results%2Fmetrics.json/content" -H "$AUTH"
```

`{path}` is the project-relative path, URL-encoded (`results%2Fmetrics.json`).

## Passing data between steps

| Hand-off | Mechanism |
|---|---|
| Small values (metrics, a model version) | read a result file as above and store it in the orchestrator (XCom, KFP output) |
| Files for the next Job in the same project | the next Job starts from the latest commit, so it sees them; pin with `commitId` (DFS) |
| Large data | write to a Dataset or Data Source in step 1, read it in step 2 ([domino-datasets](../domino-datasets/SKILL.md)) |
| A model for serving | register it (MLflow) and let the next step call the model serving API ([domino-model-serving](../domino-model-serving/SKILL.md)) |

## Failure handling

- HTTP 401/403 on start: token expired or wrong deployment; `GET $BASE/api/pat/v1/tokens` lists
  your PATs if you need to confirm one is still valid.
- HTTP 404 on `/api/jobs/beta/jobs/{jobId}`: wrong id, or the Job was archived.
- `executionStatus` not `Succeeded`: pull `stdErr` and `prepareOutput`, attach them to the
  orchestrator task log, and fail the task; do not retry blindly, since a retry starts a new Job.
- Orchestrator timeout while the Job runs: the Job continues in Domino. Record the Job id so a
  manual stop is possible from the UI **Stop** button. Neither Public spec has a Job stop
  route; python-domino's `job_stop` posts to `/v4/jobs/stop` (non-public route; may change in a future Domino version).
- Rate limits and 5xx: back off and retry the poll, never the start.
  [ERRORS.md](../domino-api-intro/ERRORS.md).
