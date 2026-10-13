# Scheduled Jobs over the API

Scheduled Jobs are created in the UI (**Jobs > Schedules > Schedule a Job**) or through the routes below. The Public API has no scheduled-Job route and python-domino has no scheduled-Job method, so the API path is the Domino Internal API that the UI itself calls: **non-public route; may change in a future Domino version**. On 6.3 confirm the bodies in your deployment's `/docs` (`openapi-internal.json`).

Authentication: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Routes

| Action | Route (all non-public; may change in a future Domino version) |
|---|---|
| Create | `POST /v4/projects/{projectId}/scheduledjobs` |
| List in a Project | `GET /v4/projects/{projectId}/scheduledjobs` -> array of schedule objects |
| List with the caller's rights | `GET /v4/projects/{projectId}/scheduledjobs/forRequestingUser` -> array of `{"canEdit", "scheduledJob"}` |
| Read | `GET /v4/projects/{projectId}/scheduledjobs/{scheduledJobKey}` |
| Update or pause | `PUT /v4/projects/{projectId}/scheduledjobs/{scheduledJobKey}` with the full body |
| Delete | `DELETE /v4/projects/{projectId}/scheduledjobs/{scheduledJobKey}` -> 200; a later GET is 404 |
| All schedules of a user | `GET /v4/scheduledruns?userId=<user id>` |
| Schedules that republish an endpoint | `GET /v4/scheduledruns/publishedModelApis/{modelApiId}/count` |

`scheduledJobKey` is the `id` in the create response.

## Create

Every field below is required; the server rejects a body without them with a `400` that names the missing ones.

```python
import os, requests

base = os.environ["DOMINO_API_PROXY"]                 # outside a run: DOMINO_API_HOST + Bearer token
project_id = os.environ["DOMINO_PROJECT_ID"]
me = requests.get(f"{base}/api/users/v1/self").json()["user"]["id"]      # Public API, both specs

body = {
    "title": "nightly-train",
    "command": "train.py --epochs 5",                 # file plus arguments, as in the Jobs UI
    "schedule": {"cronString": "0 0 2 * * ?", "isCustom": True},   # Quartz, seconds first
    "timezoneId": "UTC",                              # IANA zone the cron is evaluated in
    "isPaused": False,
    "allowConcurrentExecution": False,                # False = "Run sequentially"
    "hardwareTierIdentifier": "small-k8s",            # tier id from GET /api/hardwaretiers/v1/hardwaretiers
    "environmentRevisionSpec": "ActiveRevision",      # or LatestRevision, RestrictedRevision, {"revisionId": "<id>"}
    "scheduledByUserId": me,
    "notifyOnCompleteEmailAddresses": [],             # "Notify emails"
    # optional:
    # "overrideEnvironmentId": "<environment id>",    # default: the Project's environment
    # "publishModelId": "<Domino endpoint id>",       # "Update Domino endpoint" after success
    # "capacityType": "on-demand",                    # or "spot"
    # "mainRepoGitRef": {"type": "branch", "value": "main"},   # Git-based Projects
    # "computeClusterProperties": {"clusterType": "Ray", "computeEnvironmentId": "<id>", "workerCount": 2,
    #                              "workerHardwareTierId": {"value": "small-k8s"}, "masterHardwareTierId": {"value": "small-k8s"}},
    # "snapshotDatasetsOnCompletion": True, "netAppVolumeIds": [], "externalVolumeMounts": [],
}
r = requests.post(f"{base}/v4/projects/{project_id}/scheduledjobs", json=body)   # non-public route; may change in a future Domino version
r.raise_for_status()
sched = r.json()
key = sched["id"]
print(key, sched["schedule"]["humanReadableCronString"], sched["hardwareTierName"])
```

Response (the schedule object, also returned by GET and PUT): `id`, `created`, `projectId`, `title`, `command`, `schedule.{cronString, isCustom, humanReadableCronString}`, `timezoneId`, `isPaused`, `allowConcurrentExecution`, `hardwareTierIdentifier`, `hardwareTierName`, `environmentRevisionSpec`, `overrideEnvironmentId`, `publishModelId`, `scheduledByUserId`, `scheduledByUserName`, `notifyOnCompleteEmailAddresses`, `dataConfig.{datasetConfig, snapshotDatasetsOnCompletion, snapshotNetAppVolumesOnCompletion, externalVolumeMounts, netAppVolumeIds, snapshotSelection}`, `computeClusterProperties`, `mainRepoGitRef`.

The `command` is what the Jobs UI calls **File Name** with arguments; it runs from the Project working directory with the same rules as `runCommand` ([SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#job-commands)). On a DFS Project the schedule runs the Project's committed files at fire time, so upload or sync the script first.

## The schedule and its timezone

`schedule.cronString` is a Quartz CronTrigger expression evaluated in `timezoneId` (an IANA name such as `UTC` or `Europe/London`); `isCustom: true` marks a hand-written expression, and the UI's **Repeat every** presets also arrive as a cron string. Layout, examples and special characters: [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#quartz-cron-expressions). `0 * * * * ?` fires every minute (for testing); `0 0 0 1 1 ? 2099` parks a schedule.

## Verify that it fires

Each firing is an ordinary Job whose `status.isScheduled` is `true` and whose `runCommand` is the schedule's `command`. An every-minute schedule fires within a minute; find its Jobs with:

```python
jobs = requests.get(f"{base}/api/jobs/beta/jobs", params={"projectId": project_id, "limit": 10}).json()["jobs"]
fired = [j for j in jobs if j["status"]["isScheduled"]]
```

Stop a run you do not want with `POST /v4/jobs/stop` `{"projectId", "jobId", "commitResults": false}` (non-public route; may change in a future Domino version); logs and status come from the public `/api/jobs/beta/jobs/{jobId}` routes ([SKILL.md](./SKILL.md#monitor-a-job)).

## Update, pause, resume

`PUT` takes the same body as create (all required fields again), so read the schedule, change what you need, and send it back. `isPaused` pauses and resumes.

```python
sched = requests.get(f"{base}/v4/projects/{project_id}/scheduledjobs/{key}").json()
update = {k: sched[k] for k in ("title", "command", "timezoneId", "isPaused", "allowConcurrentExecution",
                                 "hardwareTierIdentifier", "environmentRevisionSpec", "scheduledByUserId",
                                 "notifyOnCompleteEmailAddresses", "overrideEnvironmentId", "publishModelId")}
update["schedule"] = {"cronString": sched["schedule"]["cronString"], "isCustom": True}
update["isPaused"] = True                              # pause; False resumes
update["schedule"]["cronString"] = "0 0 3 * * ?"       # or change the time, the command, the tier ...
r = requests.put(f"{base}/v4/projects/{project_id}/scheduledjobs/{key}", json=update)
r.raise_for_status()
```

`hardwareTierName`, `scheduledByUserName`, `humanReadableCronString`, `created` and `dataConfig` are read-only response fields; do not send them back.

## Delete

```python
requests.delete(f"{base}/v4/projects/{project_id}/scheduledjobs/{key}").raise_for_status()   # 200
```

Afterwards `GET .../scheduledjobs/{key}` returns `404` and no new runs start; Jobs it already started remain.

## Permissions

Creating, editing and deleting schedules needs the Create / Edit / Delete Scheduled Job permissions, granted to Project Owners and Contributors. `forRequestingUser` reports `canEdit` per schedule for the caller.

## Docs

- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/jobs/schedule-a-job (UI wizard; same path under `/6.3/`)
- https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html
