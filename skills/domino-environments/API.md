# Environments REST API

Authentication and hosts: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Which path applies

Read `GET $DOMINO_API_HOST/version` (`{"version": "6.3.x"}` or a later version; Domino Cloud reports 6.4 or later). On `6.3.x` use only the "6.3" column; on 6.4 and later use the "6.4+" routes. When unsure, call the route: a `404` means it is absent on that deployment.

| Route | 6.3 | 6.4+ (including Domino Cloud) |
|---|---|---|
| `GET /api/environments/beta/environments` (list) | yes | yes |
| `GET /api/environments/v1/environments/{environmentId}` | yes | yes |
| `DELETE /api/environments/v1/environments/{environmentId}` (archive) | yes | yes |
| `POST /api/environments/beta/environments` (create) | yes | yes, deprecated |
| `POST /api/environments/beta/environments/{environmentId}/revisions` | yes | yes, deprecated |
| `PATCH /api/environments/beta/environments/{environmentId}/revisions/{revisionId}` body `{"isRestricted": true}` (mark the restricted revision; needs ClassifyEnvironments) | yes | yes |
| `POST /api/environments/v2/environments` | no | yes |
| `POST /api/environments/v2/environments/{environmentId}/revisions` | no | yes |
| `PUT /api/environments/v1/environments/{environmentId}/name`, `/description` | no | yes |

Use v2 on 6.4+ (it adds `architectures` and nests build fields under `buildConfiguration`); use beta on 6.3. The beta list and get routes return `metadata.notices: ["Beta endpoint with known limitations"]`.

## List and inspect

```python
import os, requests

base = os.environ["DOMINO_API_PROXY"]
envs = requests.get(f"{base}/api/environments/beta/environments", params={"limit": 50, "offset": 0}).json()
for e in envs["environments"]:
    rev = e.get("latestRevision") or {}                 # optional; status is optional too
    print(e["id"], e["name"], e["visibility"], e["supportedClusters"], rev.get("number"), rev.get("status"))
# metadata.totalCount is the total number of environments; page with offset/limit

env = requests.get(f"{base}/api/environments/v1/environments/{env_id}").json()["environment"]
# env: id, name, archived, visibility (global|private|organization), owner, rebuildOnBaseChanges (never|followActive),
#      supportedClusters [dask|mpi|ray|slurm|spark], latestRevision / selectedRevision / restrictedRevision
#      {id, number, status (queued|starting|pulling|building|pushing|succeeded|failed|killed), availableTools[],
#       architectures[] (6.4+ only)}
```

`selectedRevision` is the Active revision; `restrictedRevision` applies in restricted Projects. Use a revision `id` in `environmentRevisionSpec: "SomeRevision(<id>)"` when starting a Job.

## Create an environment

### 6.4+ (including Domino Cloud): `POST /api/environments/v2/environments`

```python
body = {
    "name": "team-ml-env",
    "description": "DSE plus team packages",
    "visibility": "private",                 # global | private ("organization" via orgOwnerId)
    "addBaseDependencies": True,             # make a non-Domino image Domino-compatible
    "rebuildOnBaseChanges": "never",         # or followActive
    "initialRevision": {
        "image": "quay.io/domino/domino-standard-environment:<tag>",
        "architectures": ["amd64"],          # optional: amd64, arm64
        "buildConfiguration": {
            "dockerfileInstructions": "USER root\nRUN pip install --no-cache-dir pandas==2.3.2\nUSER ubuntu",   # the DSE's own pandas version
            "preSetupScript": "", "postSetupScript": "", "preRunScript": "", "postRunScript": "",
        },
        "environmentVariables": [{"key": "ACME_MODE", "value": "prod"}],
        "supportedClusters": [],             # e.g. ["ray"] for a cluster-node environment
        "workspaceTools": [...],             # see below
        "summary": "initial build",
    },
}
r = requests.post(f"{base}/api/environments/v2/environments", json=body)
env = r.json()["environment"]
```

Add a revision: `POST /api/environments/v2/environments/{environmentId}/revisions` with the `initialRevision` fields at the top level. Send `{"duplicateFromEnvironmentId": "<id>"}` alone to clone an environment.

### 6.3 (deprecated but present on 6.4+): `POST /api/environments/beta/environments`

Same fields, flat: `name`, `description`, `visibility`, `addBaseDependencies`, `rebuildOnBaseChanges`, `isRestricted`, `isCurated`, `orgOwnerId`, `image`, `dockerfileInstructions`, `preSetupScript`, `postSetupScript`, `preRunScript`, `postRunScript`, `environmentVariables`, `supportedClusters`, `workspaceTools`, `useVpn`, `skipCache`, `summary`. Revisions: `POST /api/environments/beta/environments/{environmentId}/revisions` with the revision fields. No `architectures`.

### `workspaceTools[]`

```json
{"name": "jupyterlab", "title": "JupyterLab", "iconUrl": "/assets/images/workspace-logos/jupyterlab.svg",
 "startScripts": ["/opt/domino/workspaces/jupyterlab/start"], "supportedFileExtensions": [],
 "proxyConfig": {"port": 8888, "internalPath": "/{{ownerUsername}}/{{projectName}}/{{sessionPathComponent}}/{{runId}}/{{#if pathToOpen}}tree/{{pathToOpen}}{{/if}}", "rewrite": false, "requireSubdomain": false}}
```

The UI's YAML form of the same data is in [WORKSPACE-TOOLS.md](./WORKSPACE-TOOLS.md).

## Rename, describe, archive

- 6.4+: `PUT /api/environments/v1/environments/{environmentId}/name` and `/description`.
- Both: `DELETE /api/environments/v1/environments/{environmentId}` archives (not while it is a Project's default). Archived environments still run existing executions but are not rebuilt.

## Hardware tiers (for pairing)

`GET /api/hardwaretiers/v1/hardwaretiers?limit=50` (both specs) lists tiers with `id` (the value Jobs take as `hardwareTier`), `name`, `resources`, `gpuConfiguration`, `computeClusterRestrictions` and `capacity`; `architecture` (`amd64`/`arm64`) appears on 6.4+ only.

## Project default environment and tier

A Project's defaults are set under Project **Settings > Hardware & Environment** or with the Internal API (non-public route; may change in a future Domino version; on 6.3 confirm in your deployment's `/docs`). Every field is optional and a partial body changes only what it names:

```python
base = os.environ["DOMINO_API_PROXY"]
project_id = os.environ["DOMINO_PROJECT_ID"]
cur = requests.get(f"{base}/v4/projects/{project_id}/settings").json()
# {"defaultEnvironmentId", "defaultEnvironmentRevisionSpec", "defaultHardwareTierId", "defaultVolumeSizeGiB", "sparkClusterMode", ...}
r = requests.put(f"{base}/v4/projects/{project_id}/settings", json={
    "defaultEnvironmentId": env_id,
    "defaultEnvironmentRevisionSpec": "ActiveRevision",   # or LatestRevision, RestrictedRevision, {"revisionId": "<id>"}
    "defaultHardwareTierId": "small-k8s",
    "defaultVolumeSizeGiB": 12,
})
r.raise_for_status()                                        # 200 with an empty body; read it back with GET
```

## Not in the Public API

Build logs have no route anywhere (environment **Revisions** tab only). The rest of the revision lifecycle is Internal API (non-public route; may change in a future Domino version): set the Active revision with `POST /v4/environments/{environmentId}/setactive?revisionId=<revision id>` or `PATCH /v4/environments/{environmentId}` with `{"assignLatestRevisionAsActive": true|false}`; cancel a running build with `POST /v4/environments/{environmentId}/environmentRevision/{revisionId}/cancel`; set the deployment-wide default (admin) with `POST /v4/environments/setDefaultEnvironment` `{"environmentId": "<id>"}` and read it with `GET /v4/environments/defaultEnvironment`. python-domino offers `environments_list`, `get_environment`, `create_environment`, `create_environment_revision`, `archive_environment` and `restrict_environment_revision` over the public and internal routes; see [domino-python-sdk](../domino-python-sdk/SKILL.md).
