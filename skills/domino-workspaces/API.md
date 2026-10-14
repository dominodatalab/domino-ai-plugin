# Workspaces over the API

The Public API has one Workspace route, `POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions` (resume a stopped Workspace; both specs). Everything else below is the Domino Internal API that the UI calls: **non-public route; may change in a future Domino version**. On 6.3 confirm the bodies in your deployment's `/docs` (`openapi-internal.json`). python-domino has no Workspace methods.

Authentication: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Routes

| Action | Route | Notes |
|---|---|---|
| Tools an environment offers | `GET /v4/workspaces/project/{projectId}/environment/{environmentId}/availableTools` | `workspaceTools[].id` such as `jupyter`, `jupyterlab`, `vscode` |
| Create and start | `POST /v4/workspace/project/{projectId}/workspace` | body below; returns the Workspace object |
| List in a Project | `GET /v4/workspace/project/{projectId}/workspace?offset=0&limit=20` | `offset` and `limit` are required (400 without them); `{workspaces[], totalWorkspaceCount, offset, limit}` |
| List across Projects (yours) | `GET /v4/workspace?pageSize=20&pageNumber=1` | |
| Read | `GET /v4/workspace/project/{projectId}/workspace/{workspaceId}` | `state`, `configTemplate.{environment, hardwareTier, tools}`, `mostRecentSession.sessionStatusInfo` |
| Update settings | `POST /v4/workspace/project/{projectId}/workspace/{workspaceId}` | full body (below); takes effect on the next session |
| Stop the session | `POST /v4/workspace/project/{projectId}/workspace/{workspaceId}/stop` | no body |
| Resume | `POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions` | **Public API**, body `{"externalVolumeMounts": [], "netAppVolumeMounts": []}` |
| Sessions | `GET /v4/workspace/project/{projectId}/workspace/{workspaceId}/sessions` | `[{id, executionId, config, ...}]` |
| Session logs | `GET /v4/workspace/{projectId}/{workspaceSessionId}/logs` (also `.../realTimeLogs`) | `{logContent[{timestamp, logType, log, size}]}` |
| Delete | `DELETE /v4/workspace/project/{projectId}/workspace/{workspaceId}` | only after the session has stopped; returns the object with `deleted: true` |
| Cluster defaults | `GET /v4/workspace/{projectId}/{Spark\|Ray\|Dask\|MPI}/defaultComputeClusterSettings` | tiers and worker count the UI would prefill |

## Create

```python
import os, requests

base = os.environ["DOMINO_API_PROXY"]                 # outside a run: DOMINO_API_HOST + Bearer token
project_id = os.environ["DOMINO_PROJECT_ID"]
env_id = "<environment id>"                           # GET /api/environments/beta/environments
tools = requests.get(f"{base}/v4/workspaces/project/{project_id}/environment/{env_id}/availableTools").json()["workspaceTools"]

body = {
    "name": "analysis",
    "environmentId": env_id,
    "environmentRevisionSpec": "ActiveRevision",      # or LatestRevision, RestrictedRevision, {"revisionId": "<id>"}
    "hardwareTierId": {"value": "small-k8s"},          # tier id from GET /api/hardwaretiers/v1/hardwaretiers
    "tools": ["jupyterlab"],                           # one of tools[].id above
    "externalVolumeMounts": [],                        # required, may be empty
    "ssh": {"enabled": False},
    "persistence": {"persistPackages": False, "persistHomeDirectory": False},
    # optional: "capacityType": "on-demand" | "spot", "overrideVolumeSizeGiB": 20, "netAppVolumeIds": [],
    #           "datasetMountSelection": [{"datasetId": "<id>", "snapshotVersion": 3}],
    #           "overrideMainGitRepoRef": {"type": "branch", "value": "main"},
    #           "computeClusterConfig": {...}            # see "Attach a cluster"
}
ws = requests.post(f"{base}/v4/workspace/project/{project_id}/workspace", json=body)   # non-public route; may change in a future Domino version
ws.raise_for_status()
ws_id = ws.json()["id"]
print(ws.json()["state"], ws.json()["configTemplate"]["hardwareTier"]["name"])
```

The Workspace is created and its first session starts at once (`state` goes `Created`, `Initializing`, then running; `mostRecentSession.sessionStatusInfo.isStoppable` becomes true). Open it from the UI as usual; the URL carries the `workspaceId`.

## Update, stop, resume, delete

```python
w = f"{base}/v4/workspace/project/{project_id}/workspace/{ws_id}"
update = {"name": "analysis", "environmentId": env_id, "environmentRevisionSpec": "ActiveRevision",
          "hardwareTierId": {"value": "medium-k8s"}, "tools": ["jupyterlab"],
          "ssh": {"enabled": False}, "persistence": {"persistPackages": True, "persistHomeDirectory": True}}
requests.post(w, json=update).raise_for_status()           # same as Settings > Edit Settings; applies at the next session
requests.post(f"{w}/stop").raise_for_status()               # Stop; wait until sessionStatusInfo.isCompleted
requests.post(f"{base}/api/projects/v1/projects/{project_id}/workspaces/{ws_id}/sessions",
              json={"externalVolumeMounts": [], "netAppVolumeMounts": []}).raise_for_status()   # Start (Public API); runs on medium-k8s now
requests.post(f"{w}/stop").raise_for_status()
requests.delete(w).raise_for_status()                       # Delete; 200 with "deleted": true once the volume is detached (retry after a short wait if not)
```

Poll `GET {w}` between steps: stop is accepted once `isStoppable` is true, delete once the session reports `isCompleted`. Deleting discards the persistent volume, so sync first ([SKILL.md](./SKILL.md#paths-and-what-persists)).

## Attach a cluster

Add `computeClusterConfig` to the create or update body; the cluster environment must list the cluster type under **Supported Clusters** ([domino-distributed-computing](../domino-distributed-computing/SKILL.md)):

```python
body["computeClusterConfig"] = {
    "clusterType": "Ray",                                  # Spark | Ray | Dask | MPI | Slurm
    "computeEnvironmentId": "<cluster environment id>",
    "computeEnvironmentRevisionSpec": "ActiveRevision",
    "workerCount": 1,                                      # "maxWorkerCount": 4 enables autoscaling
    "workerHardwareTierId": {"value": "small-k8s"},
    "masterHardwareTierId": {"value": "small-k8s"},       # omit for MPI and Slurm
    # "workerStorage": {"value": 10, "unit": "GiB"},
}
```

The response's `configTemplate.computeClusterResponseProps` echoes the cluster; `GET .../{clusterType}/defaultComputeClusterSettings` returns the defaults the UI would use. For `Slurm` the cluster environment is the Slurm worker environment, `maxWorkerCount` is the partition ceiling and the Workspace itself runs the Slurm client environment on a tier of the Slurm-enabled data plane. The route accepts a tier on a plane without Slurm and the session then never starts, so check `status.supportsSlurm` first ([domino-hpc-slurm API.md](../domino-hpc-slurm/API.md#attach-a-slurm-cluster-to-a-workspace)).

## Not in any API

The per-user auto-shutdown period (**Account Settings > Workspace Settings**) has no API route; `GET /v4/workspace/getGlobalSettings` only reads the deployment-wide values.
