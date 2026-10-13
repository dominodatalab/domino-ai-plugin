# Domino Environments API

Create, revise and inspect Compute Environments. Routes marked **Cloud** exist only on
Domino Cloud. Product docs:
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments.

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Which path applies

Read `GET $DOMINO_API_HOST/version`.

| Target | Create environments and revisions with |
|--------|----------------------------------------|
| Domino Cloud (`6.4.0` and later) | `POST /api/environments/v2/environments` and `POST /api/environments/v2/environments/{environmentId}/revisions`. On Cloud the beta create routes are **deprecated**: they cannot set a CPU architecture and gain no new capabilities. |
| Domino 6.3 | `POST /api/environments/beta/environments` and `.../beta/environments/{environmentId}/revisions` (v2 does not exist on 6.3) |

List (`GET /api/environments/beta/environments`), get and archive
(`/api/environments/v1/environments/{environmentId}`) and the revision `PATCH` are the same
on both.

## List environments

```
GET /api/environments/beta/environments?offset=0&limit=50
```

Only `offset` and `limit` (default 10). Response: `{"environments": [...], "metadata": {...}}`.
Each environment has `id`, `name`, `visibility` (`global`, `private`, `organization`),
`owner` (`id`, `username`, `ownerType`), `supportedClusters`, `archived`, `isCurated`,
`rebuildOnBaseChanges` (`never`, `followActive`) and `latestRevision` (`id`, `number`,
`status`, `availableTools`; `architectures` on **Cloud**).

```python
envs = requests.get(f"{base_url}/api/environments/beta/environments", headers=headers,
                    params={"limit": 100}).json()["environments"]
for env in envs:
    print(env["name"], env["id"], env["latestRevision"]["status"])
```

## Create an environment

Required: `name`, `visibility` (`global` or `private`), `image` and `addBaseDependencies`.
`duplicateFromEnvironmentId` is the alternative, sent with no other field in the body.
There is no `baseEnvironmentId`.

Build fields (shared by create and revision bodies): `image` (base image URI),
`dockerfileInstructions`, `preSetupScript`, `postSetupScript`, `preRunScript`,
`postRunScript`, `environmentVariables` (`[{"key", "value"}]`), `workspaceTools`,
`supportedClusters` (`dask`, `mpi`, `ray`, `slurm`, `spark`), `skipCache`, `summary`,
`useVpn`. Environment-level fields: `name`, `description`, `visibility`, `addBaseDependencies`,
`isRestricted` (needs the ClassifyEnvironments permission), `isCurated`, `orgOwnerId`
(private environments owned by an organization), `rebuildOnBaseChanges`. `tags` is deprecated
in favour of taxonomy tags.

**Cloud** (`POST /api/environments/v2/environments`): the build fields sit under
`initialRevision` (`image`, `buildConfiguration` with the Dockerfile and scripts,
`environmentVariables`, `workspaceTools`, `supportedClusters`, `architectures`
`amd64`/`arm64`, ...); environment-level fields stay at the top.

```python
env = requests.post(f"{base_url}/api/environments/v2/environments", headers=headers, json={
    "name": "pytorch-gpu-env",
    "description": "PyTorch with GPU support",
    "visibility": "private",
    "addBaseDependencies": True,
    "initialRevision": {
        "image": "<base-image-uri>",                       # for example a Domino Standard Environment image
        "architectures": ["amd64"],
        "buildConfiguration": {
            "dockerfileInstructions": "USER root\nRUN pip install --no-cache-dir torch==2.14.1\nUSER ubuntu",
        },
    },
}).json()["environment"]
```

The response has `latestRevision.status: "Queued"` and `selectedRevision: null`; poll
[Build status](#build-status) below. The Public API does not expose a base image
URI; copy one from an existing environment's details page (the DSE image) or your
registry. `PUT .../description` works, but the description is not returned by the
Public `GET`.

**6.3** (`POST /api/environments/beta/environments`): the same fields flat.

```python
env = requests.post(f"{base_url}/api/environments/beta/environments", headers=headers, json={
    "name": "pytorch-gpu-env",
    "description": "PyTorch with GPU support",
    "visibility": "private",
    "addBaseDependencies": True,
    "image": "<base-image-uri>",
    "dockerfileInstructions": "USER root\nRUN pip install --no-cache-dir torch==2.14.1\nUSER ubuntu",
}).json()["environment"]
```

Duplicate an existing environment instead (either target; nothing else in the body).
The copy is named "Duplicate of <name>" and reuses the source's built
revision, so no new build runs.

```python
env = requests.post(f"{base_url}/api/environments/beta/environments", headers=headers,
                    json={"duplicateFromEnvironmentId": "<environment-id>"}).json()["environment"]
```

**Cloud only:** `PUT /api/environments/v1/environments/{environmentId}/name` (`{"name"}`)
and `.../description` (`{"description"}`).

## Get an environment

```
GET /api/environments/v1/environments/{environmentId}
```

Returns `{"environment": {...}, "metadata": {...}}` with the fields listed under List.

## Archive an environment

```
DELETE /api/environments/v1/environments/{environmentId}
```

A soft archive: the response is the environment with `archived: true`, and `GET` still
returns it.

## Revisions

```
POST  /api/environments/v2/environments/{environmentId}/revisions     Cloud: {"image", "buildConfiguration": {...}, "environmentVariables", "architectures", ...}
POST  /api/environments/beta/environments/{environmentId}/revisions   6.3: the flat build fields (deprecated on Cloud)
PATCH /api/environments/beta/environments/{environmentId}/revisions/{revisionId}   body: {"isRestricted": true}
```

**`image` is required on both revision routes**: without it the server returns
`400 image is required` on both routes, even though the schema marks it
optional. Pass the base image URI the environment already uses. The body is a complete
definition, not a delta: no field inherits from the previous revision, so send the full
`dockerfileInstructions`, the scripts and `workspaceTools` you want to keep (copy
`selectedRevision.availableTools` from the environment `GET`, renaming `start` to
`startScripts`; an environment created without `workspaceTools` has
`availableTools: []`). The Public API does not return the base image or the
Dockerfile; [SDK-EXAMPLES.md](./SDK-EXAMPLES.md#environments) shows how to read them
through the Domino Internal API (non-public routes; may change in a future Domino version). The create responses are
`{"environmentRevision": {"id", "number", "availableTools"}, "metadata"}` (plus
`architectures` on v2); neither carries `status`, so poll the environment (below) for the
build state. `isRestricted` is required on `PATCH`.

```python
rev = requests.post(f"{base_url}/api/environments/beta/environments/{env_id}/revisions",
                    headers=headers, json={
    "image": "<base-image-uri>",
    "dockerfileInstructions": "USER root\nRUN pip install --no-cache-dir pandas==2.3.2 scikit-learn==1.7.2\nUSER ubuntu",
    "summary": "pin pandas and scikit-learn",
}).json()["environmentRevision"]
```

On Cloud, the same fields go under `buildConfiguration` on the v2 route:

```python
rev = requests.post(f"{base_url}/api/environments/v2/environments/{env_id}/revisions",
                    headers=headers, json={
    "image": "<base-image-uri>",
    "architectures": ["amd64"],
    "buildConfiguration": {"dockerfileInstructions": "USER root\nRUN pip install --no-cache-dir pandas==2.3.2\nUSER ubuntu"},
    "environmentVariables": [{"key": "MODEL_PATH", "value": "/mnt/artifacts/model.pkl"}],
    "summary": "pin pandas",
}).json()["environmentRevision"]
```

## Build status

Poll `GET /api/environments/v1/environments/{environmentId}` and read
`environment.latestRevision.status`. The spec enum is lowercase (`queued`, `starting`,
`pulling`, `building`, `pushing`, `succeeded`, `failed`, `killed`) but Domino 6.4
returns capitalized values (`Succeeded`, `Failed`, `Killed`), so compare
case-insensitively. `latestRevision` is the newest build; `selectedRevision` is the one
executions use, and the two differ when the newest build failed or was killed.

```python
import time
deadline = time.time() + 3600
while time.time() < deadline:
    env = requests.get(f"{base_url}/api/environments/v1/environments/{env_id}",
                       headers=headers).json()["environment"]
    status = env["latestRevision"]["status"].lower()
    if status in ("succeeded", "failed", "killed"):
        break
    print("building...", status)
    time.sleep(30)
```

## Use the environment in a job

```python
requests.post(f"{base_url}/api/jobs/v1/jobs", headers=headers, json={
    "projectId": project_id,
    "runCommand": "python train.py",
    "environmentId": env_id,
    "hardwareTier": "small-k8s",
})
```

Body reference: [API-JOBS.md](./API-JOBS.md#start-a-job).

## Dockerfile instructions

`dockerfileInstructions` is a Dockerfile fragment appended to the base image. Domino
images must run as the `ubuntu` user, and the docs recommend installing packages as
`root`: add `USER root` before the install commands and `USER ubuntu` after them
(https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/add-packages-to-environments/preload-environment-packages).

```dockerfile
USER root
RUN pip install --no-cache-dir pandas==2.3.2 "numpy<=2.5.2" scikit-learn==1.7.2
RUN apt-get update && apt-get install -y libpq-dev graphviz && rm -rf /var/lib/apt/lists/*
RUN R -e "install.packages(c('tidyverse', 'caret'), repos='https://cloud.r-project.org')"
ENV MODEL_PATH=/mnt/artifacts/model.pkl
USER ubuntu
```

Quote version specifiers that contain `>` or `<`; unquoted, the shell treats them as
redirections. For a package the Domino Standard Environment already ships, pin at or below the
DSE's own version (`pip show <pkg>` in a Workspace on that environment): a newer release can
break the ranges its MLflow and other preinstalled packages declare (for example `pandas<3`
and `scikit-learn<2`). Packages the DSE does not ship, such as torch, take their newest release.

## python-domino

`environments_list()`, `get_environment(environment_id)`, `get_default_environment()`,
`create_environment(name, visibility, ...)`, `create_environment_revision(environment_id, ...)`,
`restrict_environment_revision(environment_id, revision_id)`, `archive_environment(environment_id)`.
`create_environment` and `create_environment_revision` call the beta routes above (current on
6.3, deprecated on Cloud, where they still work but cannot set `architectures`).
`create_environment_revision` posts a complete definition and fills omitted fields with
defaults, not with the environment's current values: [SDK-EXAMPLES.md](./SDK-EXAMPLES.md#environments).
Signatures: [SDK-EXAMPLES.md](./SDK-EXAMPLES.md#environments-and-hardware-tiers). There is
no `environment_get` method.

## Best practices

1. Start from a Domino Standard Environment image or `duplicateFromEnvironmentId`.
2. Pin package versions and wrap installs in `USER root` / `USER ubuntu`.
3. Combine `RUN` lines to reduce layers and clean package caches.
4. Create a revision rather than a new environment for dependency changes; Workspaces and
   Jobs pick the active revision.
