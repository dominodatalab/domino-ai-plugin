# HPC Jobs and Slurm discovery over the API

Applies to Domino 6.3 and Domino Cloud. Authentication and hosts: [domino-api-intro](../domino-api-intro/SKILL.md). The `/api/hpc/v1/...`, `/api/environments/...` and `/api/hardwaretiers/...` routes are Public API; every `/v4/...` route below is the Domino Internal API (non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types)).

All snippets assume:

```python
# base and headers: the Python setup block in domino-api-intro/SKILL.md#authentication
import os, time, requests
project_id = os.environ["DOMINO_PROJECT_ID"]
```

## Find the data plane, environments and tiers

Slurm is a property of a data plane, so the three questions are: which data plane has Slurm, which environments are the Slurm client and worker, and which tiers sit on that plane.

```python
# 1. Data planes (non-public route; may change in a future Domino version): status.supportsSlurm says whether Slurm is installed.
planes = requests.get(f"{base}/v4/dataplanes/dataplanes", headers=headers).json()
slurm_planes = [p for p in planes if p["status"].get("supportsSlurm")]
#    Each entry: id, name, isLocal, isHealthy, status.state. The Local data plane's id is 000000000000000000000000.

# 2. Environments visible to you (paginated; the default page is 10).
def all_pages(path, key, **params):
    offset, out = 0, []
    while True:
        page = requests.get(f"{base}{path}", params={**params, "offset": offset, "limit": 100}, headers=headers).json()
        out += page[key]
        if len(page[key]) < 100:
            return out
        offset += 100

envs = all_pages("/api/environments/beta/environments", "environments")
worker_envs = [e for e in envs if "slurm" in [c.lower() for c in e.get("supportedClusters", [])]]
#    The worker (cluster) environment carries supportedClusters ["Slurm"] (the value is capitalised; compare
#    case-insensitively). The Workspace (client) environment has supportedClusters [] and workspace tools in
#    latestRevision.availableTools; tell it apart by name, there is no flag for it.

# 3. Hardware tiers: dataPlaneName, dataPlaneId and the per-cluster-type restriction.
tiers = all_pages("/api/hardwaretiers/v1/hardwaretiers", "hardwareTiers")
on_plane = [t for t in tiers if t["dataPlaneName"] == slurm_planes[0]["name"]]
slurm_only = [t for t in tiers if t["computeClusterRestrictions"]["restrictToSlurm"]]
#    dataPlaneId is empty for tiers on the Local data plane; match on dataPlaneName or use the id from step 1.

# 4. Can this project submit HPC Jobs to that plane through the API?
ok = requests.get(f"{base}/api/hpc/v1/jobs/submit-supported",
                  params={"projectId": project_id, "dataPlaneId": slurm_planes[0]["id"]}, headers=headers).json()
#    {"supported": true|false}; optional partition= checks one partition. Both projectId and dataPlaneId are required
#    (400 without). false means the plane cannot take an API submission from this user and project (no Slurm on the
#    plane is one cause): stop and report it, do not start. An unknown dataPlaneId is a 500.
```

`GET /api/hardwaretiers/v1/hardwaretiers` takes `offset`, `limit` and `includeArchived`; `GET /api/environments/beta/environments` takes `offset` and `limit`. `GET /v4/hardwareTier/withCapacity/{hardwareTierId}?projectId=` (non-public route; may change in a future Domino version) returns the tier together with its `dataPlane` object and current capacity.

## Start, poll, read logs, cancel

Check first, then start. `GET /api/hpc/v1/jobs/submit-supported?projectId=&dataPlaneId=` answering `{"supported": false}` means HPC submission is unavailable on that data plane for this user and project (prerequisites in [SKILL.md](./SKILL.md#prerequisites)): stop and report it. A start on such a plane fails with a 500 whose message begins `(503) Unexpected response code`, creates nothing and fails the same way on retry.

`POST /api/hpc/v1/jobs` needs `projectId`, `filePath` and `dataPlaneId`; `title`, `mainRepoGitRef` and `config` are optional. The response is 202 with no body.

```python
plane_id = slurm_planes[0]["id"]                  # from the discovery step
ok = requests.get(f"{base}/api/hpc/v1/jobs/submit-supported",
                  params={"projectId": project_id, "dataPlaneId": plane_id}, headers=headers).json()["supported"]
if not ok:
    raise SystemExit(f"HPC submission is unavailable on data plane {plane_id}")   # do not retry the start

body = {
    "projectId": project_id,
    "filePath": "hpc/sweep.sh",                  # relative to the Project root; runs from the latest commit
    "dataPlaneId": plane_id,
    "title": "parameter sweep",
    # "mainRepoGitRef": {"refType": "branches", "value": "main"},   # Git-based Projects: which ref to run from
    "config": {                                   # all optional; Slurm-native units
        "cpu": 4,                                 # number of cores (number)
        "gpu": 0,                                 # integer
        "memory": "8Gi",                          # string
        "nodes": 1,                               # default 1
        "ntasks": 1,                              # default 1
        "walltime": "02:00:00",                   # HH:MM:SS
    },
}
r = requests.post(f"{base}/api/hpc/v1/jobs", json=body, headers=headers)
r.raise_for_status()                              # 202

# The new Job's id comes from the list, highest number first.
job = requests.get(f"{base}/api/hpc/v1/jobs", headers=headers,
                   params={"projectId": project_id, "sortBy": "number", "ascending": "false", "limit": 1}).json()["jobs"][0]
job_id = job["id"]

# Poll: status is Submitted, Running, Completed, Failed, Cancelled or TimedOut.
while True:
    job = requests.get(f"{base}/api/hpc/v1/jobs/{job_id}", headers=headers).json()
    if job["status"] in ("Completed", "Failed", "Cancelled", "TimedOut"):
        break
    time.sleep(30)
print(job["status"], job["requestedResources"], job.get("usage"), job["stageTime"])

# Logs: page with latestTimeNano until logset.isComplete; logType filters stdout or stderr.
since = None
while True:
    params = {"limit": 1000, **({"latestTimeNano": since} if since else {})}
    logs = requests.get(f"{base}/api/hpc/v1/jobs/{job_id}/logs", params=params, headers=headers).json()["logset"]
    for line in logs["logContent"]:
        print(line["timestamp"], line["logType"], line["log"])
    if logs["isComplete"] or not logs.get("pagination", {}).get("latestTimeNano"):
        break
    since = logs["pagination"]["latestTimeNano"]

# Cancel a queued or running Job: 204.
requests.post(f"{base}/api/hpc/v1/jobs/cancel", json={"jobId": job_id}, headers=headers).raise_for_status()
```

The list route returns `{"jobs": [...], "totalCount", "pagination": {"offset", "limit"}}`. Each Job carries `id`, `number`, `title`, `status`, `jobRunCommand`, `script` (the script contents that ran), `dataPlaneId` (`{"id", "name"}`), `startedBy`, `tags`, `requestedResources` (`cpus`, `gpus`, `memory` in bytes, `nodes`, `timeLimit` in minutes, 0 = unset), `usage` (`cpu`, `memory` maxima) and `stageTime` (`submissionTime`, `runStartTime`, `completedTime`, epoch milliseconds). `statusFilter` is case-insensitive; `sortBy` accepts `number`, `title`, `command`, `startedTime`, `duration`, `status`, `user`, `commentCount`.

Permissions: `ViewJobs` to list, read and fetch logs; `StartJob` and `UseGlobalCompute` to start and to call `submit-supported`; `StartJob` to cancel.

## Errors

Errors come back as `{"requestId", "errors": ["..."]}`.

| Call | Response |
|---|---|
| Start with a `filePath` that is not in the Project's latest commit (or the given `mainRepoGitRef`) | 403, `Not authorized: File <path>, commitId ..., projectId: ... are not valid`. Upload or commit the script first, as for a standard Job ([domino-jobs](../domino-jobs/SKILL.md#troubleshooting)). Nothing is created. |
| Details, logs or cancel with an unknown `jobId` | an error envelope whose message says `(404) ... Could not find HPC job with id: ...`; the outer HTTP status may be 500, so check the message. |
| Start on a data plane without Slurm (`submit-supported` is `false` there) | 500, `(503) Unexpected response code. Content : HttpEntity.Strict(application/json, ...)`. Not transient; nothing is created. Use a Slurm-enabled plane. |
| `submit-supported` without `dataPlaneId` | 400, `Missing required query string parameter dataPlaneId`. |
| `submit-supported` with an unknown `dataPlaneId` | 500, `Unable to process request`. |
| Start or `submit-supported` without `StartJob` and `UseGlobalCompute` | 403. |

## Attach a Slurm cluster to a Workspace

The Workspace create and update bodies take `computeClusterConfig` ([domino-workspaces API.md](../domino-workspaces/API.md#attach-a-cluster); `POST /v4/workspace/project/{projectId}/workspace`, non-public route; may change in a future Domino version).

The create route does not check the data plane. With `clusterType` `"Slurm"` and a tier on a plane that has no Slurm it still answers 200 with state `Created` and `configTemplate.computeClusterResponseProps.clusterType` `"Slurm"`, and the session then never starts: it stays `Pending` or `Initializing` while the execution events repeat `FailedMount: MountVolume.SetUp failed for volume "slurm-jwt-secret-vol": secret "execution-<id>-slurm-jwt-secret" not found`. The UI disables the Slurm option in that case; by API, check the tier's data plane first and never create the Workspace on a plane without Slurm:

```python
tier_id = on_plane[0]["id"]                        # a tier on the Slurm-enabled plane, from the discovery step
t = requests.get(f"{base}/v4/hardwareTier/withCapacity/{tier_id}", params={"projectId": project_id}, headers=headers).json()
#   non-public route; may change in a future Domino version. Returns hardwareTier, capacity and the tier's dataPlane.
if not t["dataPlane"]["status"].get("supportsSlurm"):
    raise SystemExit(f"data plane {t['dataPlane']['name']} has no Slurm; pick a tier on a Slurm-enabled plane")
# Equivalent: the plane from GET /v4/dataplanes/dataplanes (status.supportsSlurm), or, for API submission,
# GET /api/hpc/v1/jobs/submit-supported?projectId=&dataPlaneId= returning {"supported": true}.
```

Then the cluster body, with the Workspace's own `hardwareTierId` on the same data plane:

```python
body["computeClusterConfig"] = {
    "clusterType": "Slurm",
    "computeEnvironmentId": worker_envs[0]["id"],          # the Slurm worker environment
    "computeEnvironmentRevisionSpec": "ActiveRevision",
    "workerCount": 1,
    "maxWorkerCount": 8,                                   # the UI's Max Number of Workers: the partition scales up to it
    "workerHardwareTierId": {"value": tier_id},             # the tier checked above
}
```

There is no master tier for Slurm. `GET /v4/workspace/{projectId}/Slurm/defaultComputeClusterSettings` (non-public route; may change in a future Domino version) returns the defaults the UI would use (`clusterType`, `workerCount`, `workerHardwareTierId`, `maxUserExecutionSlots`). The Workspace's own `environmentId` is the Slurm client environment and its `hardwareTierId` a tier on the same Slurm-enabled data plane as `workerHardwareTierId`. A Workspace already stuck as described above: stop it if `isStoppable` is true, then delete it ([domino-workspaces API.md](../domino-workspaces/API.md#update-stop-resume-delete)) and recreate it on a Slurm-enabled plane.

The `slurm` value in `ClusterTypeV1`, the enum behind `computeCluster.clusterType` on `POST /api/jobs/v1/jobs`, is not a supported path: a standard Job cannot carry a Slurm cluster. Submit through `/api/hpc/v1/jobs` instead.
