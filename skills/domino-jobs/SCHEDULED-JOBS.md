# Scheduled Jobs over the API

Applies to Domino 6.3 and Domino Cloud. Scheduled Jobs are created in the UI (**Jobs > Schedules > Schedule a Job**) or through the routes below. The Public API has no scheduled-Job route and python-domino has no scheduled-Job method, so the API path is the Domino Internal API that the UI itself calls: **internal API, may change between Domino versions**. Every call here was run live on Domino 6.4 (create, list, fire, update, pause, delete); Domino's own public tooling uses the same routes on earlier lines, but confirm the bodies in your deployment's `https://<domino-domain>/docs` (`openapi-internal.json`) before relying on them on 6.3.

Authentication: [domino-api-intro](../domino-api-intro/SKILL.md). Inside a run call `$DOMINO_API_PROXY/v4/...` with no `Authorization` header; outside a run call `$DOMINO_API_HOST/v4/...` with a Personal Access Token or service-account bearer token.

## Routes

| Action | Route (all internal API) |
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
    # "mainRepoGitRef": {"type": "branch", "value": "main"},   # Git-based Projects; not live-tested here
    # "computeClusterProperties": {"clusterType": "Ray", "computeEnvironmentId": "<id>", "workerCount": 2,
    #                              "workerHardwareTierId": {"value": "small-k8s"}, "masterHardwareTierId": {"value": "small-k8s"}},
    # "snapshotDatasetsOnCompletion": True, "netAppVolumeIds": [], "externalVolumeMounts": [],
}
r = requests.post(f"{base}/v4/projects/{project_id}/scheduledjobs", json=body)   # internal API, may change between Domino versions
r.raise_for_status()
sched = r.json()
key = sched["id"]
print(key, sched["schedule"]["humanReadableCronString"], sched["hardwareTierName"])
```

Response (the schedule object, also returned by GET and PUT): `id`, `created`, `projectId`, `title`, `command`, `schedule.{cronString, isCustom, humanReadableCronString}`, `timezoneId`, `isPaused`, `allowConcurrentExecution`, `hardwareTierIdentifier`, `hardwareTierName`, `environmentRevisionSpec`, `overrideEnvironmentId`, `publishModelId`, `scheduledByUserId`, `scheduledByUserName`, `notifyOnCompleteEmailAddresses`, `dataConfig.{datasetConfig, snapshotDatasetsOnCompletion, snapshotNetAppVolumesOnCompletion, externalVolumeMounts, netAppVolumeIds, snapshotSelection}`, `computeClusterProperties`, `mainRepoGitRef`.

The `command` is what the Jobs UI calls **File Name** with arguments; it runs from the Project working directory with the same rules as `runCommand` ([SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#job-commands)). On a DFS Project the schedule runs the Project's committed files at fire time, so upload or sync the script first.

## The schedule and its timezone

`schedule.cronString` is a Quartz CronTrigger expression (six fields plus an optional year, seconds first, `?` in exactly one of day-of-month and day-of-week), evaluated in `timezoneId` (an IANA name such as `UTC`, `Europe/London`, `America/New_York`). `isCustom: true` marks a hand-written expression; the UI's **Repeat every** presets also arrive as a cron string. Layout and special characters: [SCRIPT-PATTERNS.md](./SCRIPT-PATTERNS.md#quartz-cron-expressions). Examples:

| Meaning | `cronString` |
|---|---|
| Every minute (testing) | `0 * * * * ?` |
| Daily at 02:00 in `timezoneId` | `0 0 2 * * ?` |
| Weekdays at 09:30 | `0 30 9 ? * MON-FRI` |
| First of the month at 06:00 | `0 0 6 1 * ?` |
| Never (parked schedule) | `0 0 0 1 1 ? 2099` |

## Verify that it fires

Each firing is an ordinary Job whose `status.isScheduled` is `true` and whose `runCommand` is the schedule's `command`. Within the first minute after an every-minute schedule was created, the Job appeared here:

```python
jobs = requests.get(f"{base}/api/jobs/beta/jobs", params={"projectId": project_id, "limit": 10}).json()["jobs"]
fired = [j for j in jobs if j["status"]["isScheduled"]]
```

Stop a run you do not want with `POST /v4/jobs/stop` `{"projectId", "jobId", "commitResults": false}` (internal API, may change between Domino versions); logs and status come from the public `/api/jobs/beta/jobs/{jobId}` routes ([SKILL.md](./SKILL.md#monitor-a-job)).

## Update, pause, resume

`PUT` takes the same body as create (all required fields again), so read the schedule, change what you need, and send it back. Changing `isPaused` is how the UI and Domino's own tooling pause and resume a schedule; the UI has no separate pause control.

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

Afterwards `GET .../scheduledjobs/{key}` returns `404` with `{"message": "Cannot find scheduled job with job id ...", "success": false}`, the Project list no longer includes it, and no new runs start. Jobs it already started stay in the Jobs dashboard.

## Permissions

Creating, editing and deleting schedules needs the Create / Edit / Delete Scheduled Job permissions, granted to Project Owners and Contributors. `forRequestingUser` reports `canEdit` per schedule for the caller.

## Docs

- https://docs.domino.ai/cloud/platform-capabilities/core-concepts/jobs/schedule-a-job (UI wizard; same path under `/6.3/`)
- https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html
