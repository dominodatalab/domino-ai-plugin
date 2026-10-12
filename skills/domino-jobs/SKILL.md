---
name: domino-jobs
description: Create, run, and manage Domino Jobs - batch executions for scripts, training, and data processing. Covers starting a Job from the UI, CLI or REST API, hardware tiers and environments, scheduled Jobs with Quartz cron, checking status and logs through the Jobs API, stopping Jobs, results and notifications. Use when running batch workloads, scheduling recurring tasks, or automating training pipelines. For the CLI itself use domino-cli; for multi-step pipelines domino-flows; for an existing Airflow or Kubeflow domino-airflow-kubeflow; for batch scoring with a model use domino-model-delivery.
compatibility: Domino 6.3 and Domino Cloud. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a Personal Access Token.
---

# Domino Jobs

Applies to Domino 6.3 and Domino Cloud.

A Job runs one command to completion in its own container on a hardware tier, recording the Project files, environment revision, data mounts and inputs. Interactive work: [domino-workspaces](../domino-workspaces/SKILL.md); web forms that start Jobs: [domino-launchers](../domino-launchers/SKILL.md); batch scoring with a trained model: [domino-model-delivery](../domino-model-delivery/SKILL.md).

Authentication ([domino-api-intro](../domino-api-intro/SKILL.md)): in a run `$DOMINO_API_PROXY` with no `Authorization` header; outside, `$DOMINO_API_HOST` with a PAT or service-account bearer token.

## Start a Job

A Job runs the Project's committed files, not the Workspace disk: in a DFS Project upload or sync new or changed scripts first (MCP `sync_local_file_to_domino` or **File Changes > Sync to Domino**); Git-based Projects: commit and push.

**UI**: **Jobs > Run**. Enter the **Command or File Name** with arguments (`train.py --epochs 100`), pick environment, revision and volume size, **Next**, pick the hardware tier, optionally a compute cluster ([domino-distributed-computing](../domino-distributed-computing/SKILL.md)) and per-asset snapshot pins, then start.

**CLI**: `domino run <file> [args]` (`--wait` blocks, `--direct "<shell command>"`) from a logged-in CLI Project directory; install, sign-in, commands: [domino-cli](../domino-cli/SKILL.md).

**REST**: `POST /api/jobs/v1/jobs` (both specs). Only `projectId` and `runCommand` are required; the rest defaults from the Project. A misspelt field (`hardwareTierId`) or an unknown `hardwareTier` id still returns 200 and the Job silently runs on the default tier; verify below.

**Right after an upload** (DFS): the head can lag by seconds, and a Job without `commitId` may run the previous commit. The MCP `run_domino_job` pins the commit by itself; over REST pin `commitId` per [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#pin-the-commit-after-an-upload); Git-based: `mainRepoGitRef`.

```python
import os, requests

r = requests.post(f"{os.environ['DOMINO_API_PROXY']}/api/jobs/v1/jobs", json={
    "projectId": os.environ["DOMINO_PROJECT_ID"],
    "runCommand": "python train.py --epochs 100",
    "title": "Training run",
    # "hardwareTier": "small-k8s",   # tier id from GET /api/hardwaretiers/v1/hardwaretiers
    # "environmentId": "<id>", "environmentRevisionSpec": "ActiveRevision",
    # "mainRepoGitRef": {"refType": "branches", "value": "main"},   # Git-based; refType: head | commitId | tags | branches (not "branch")
    # "commitId": "<DFS commit>",   # pin after an upload; DFS history only, never a Git commit
    # also: computeCluster, netAppVolumeIds, externalVolumeMountIds, snapshotDatasetsOnCompletion
})
r.raise_for_status()
job = r.json()["job"]   # response: {"job": {...}, "metadata": {...}}
print(job["id"], job["number"], job["status"]["executionStatus"])
```

Tags: `POST /api/jobs/v1/jobs/{jobId}/tags` `{"projectId", "tagName"}`; `DELETE .../tags/{tagId}?projectId=...` (required).

### Which path applies

Read `GET $DOMINO_API_HOST/version`. On `6.3.x` use only the routes above. On 6.4 and later (Domino Cloud today) `POST /api/jobs/v1/projects/{projectId}/job-defaults` also exists: send `{}` or start-Job field overrides to see what a Job would run with, without starting one (`404` = absent).

## Monitor a Job

Both specs (beta).

- List: `GET /api/jobs/beta/jobs?projectId=...&statusFilter=all|queued|running|completed|archived|active&limit=&offset=` -> `{"jobs": [...], "metadata": {..., "totalCount"}}`.
- Details: `GET /api/jobs/beta/jobs/{jobId}` -> `job.status.executionStatus` (`Queued` ... `Running`, `Succeeded`, `Stopped`, `Failed`, `Error`; see job-states), `status.isCompleted`, `stageTimes.{submissionTime,startTime,completedTime}`, `commitDetails.{inputCommitId,outputCommitId}`, `usage`, `computeCluster`, `runLauncherId`.
- Logs: `GET /api/jobs/beta/jobs/{jobId}/logs?logType=stdOut|stdErr|prepareOutput|complete&limit=1000&latestTimeNano=...` -> `logs.logContent[].{timestamp,logType,log}`, `logs.isComplete`, `metadata.pagination.latestTimeNano` (next page). Code: [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#logs).
- Verify what a Job ran on: the Job object omits tier and environment; use the **Details** tab or `GET /v4/jobs/{jobId}/runtimeExecutionDetails` -> `hardwareTier.id`, `environment.environmentId` (internal API, may change between Domino versions; python-domino `job_runtime_execution_details(job_id)` wraps it).

## Stop, re-run, archive

- Stop: **Jobs > Active**, select, **Stop**. No public stop route; the Internal API has `POST /v4/jobs/stop` with `{"projectId", "jobId", "commitResults"}` (internal API, may change between Domino versions; python-domino `job_stop(job_id, commit_results=True)`, [domino-python-sdk](../domino-python-sdk/SKILL.md)).
- Re-run: select a Job > **Re-Run with Original Version** or **Re-Run with Current Version** (Git refs refresh only if the original ran from a branch).
- Archive hides Jobs (`showArchived=true` lists them).

## Scheduled Jobs

Configured only in the UI: **Jobs > Schedules > Schedule a Job**. The Public API has no scheduled-Job routes; `/v4/projects/{projectId}/scheduledjobs` exists (internal API, may change between Domino versions). Fields: the Job fields plus a schedule, **Run sequentially** (no overlapping runs), **Notify emails**, **Update Domino endpoint**. No pause: set a far-future start to suspend.

**Schedule** is a repeat interval or a **Quartz CronTrigger** expression, not crontab: six fields plus an optional year, seconds first, `?` in exactly one day field (`0 0 0 * * ?` daily at 00:00, `0 0 9 ? * MON` Mondays at 09:00). Field layout and special characters: [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#quartz-cron-expressions).

Multi-step pipelines: [domino-flows](../domino-flows/SKILL.md); an existing Airflow or Kubeflow: [domino-airflow-kubeflow](../domino-airflow-kubeflow/SKILL.md).

## Results and notifications

Files changed under the Project files during the run are results. Write `dominostats.json` at the Project root for dashboard columns, `email.html` for a custom success email, `.dominoresults` to choose what is shown and attached; `.dominoignore` drops files from the revision. Success emails: Project **Settings > Access and Sharing**.

## Troubleshooting

- `can't open file`: the file is not in the commit the Job ran. Never uploaded or synced: do that first. Uploaded seconds before starting: pin `commitId`.
- `400` from `POST /api/jobs/v1/jobs`: a `commitId` not in the Project's DFS history (use `mainRepoGitRef` for Git) or an environment the Project cannot use. A wrong tier id gives no error; see the runtime details.
- Queued or Building, Failed vs Error, missing results: [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#troubleshooting-failed-jobs).

## Reference files and docs

- [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md): commands, env vars, outputs, logs, Quartz cron, troubleshooting.
- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/jobs/create-and-run-jobs, `.../schedule-a-job`, `.../monitor-jobs`, `.../job-states` (same paths under `/6.3/`).
