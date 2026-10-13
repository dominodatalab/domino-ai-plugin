# Domino REST API reference

Route index for the Domino Public API as published at
https://docs.domino.ai/api-specs/6.3/public-api.json and
https://docs.domino.ai/api-specs/cloud/public-api.json. Request bodies with
their required fields live in the per-area files; this file is the map.

## Authentication and base URL

Rules and the shared `base_url` / `headers` setup block:
[domino-api-intro](../domino-api-intro/SKILL.md#authentication).

```python
response = requests.get(f"{base_url}/api/projects/beta/projects", headers=headers,
                        params={"limit": 20})
projects = response.json()["projects"]
```

## Route index

Routes marked **Cloud** exist only on Domino Cloud (6.4.0 and later); routes marked
**6.3** only on Domino 6.3.

### Users, auth, admin ([API-ADMIN.md](./API-ADMIN.md))

| Method | Route | Notes |
|--------|-------|-------|
| GET | `/api/users/v1/self` | Current user: `{"user": {...}, "metadata": {...}}` |
| GET | `/api/users/v1/users` | `offset`, `limit` |
| GET | `/api/users/v1/user/{userId}` | |
| GET, POST | `/api/users/v1/user/{userId}/roles` | POST body `{"roles": [...]}` **replaces** the user's roles (unlisted roles are revoked); no PUT |
| GET | `/api/users/beta/credentials/{userId}` | Git credentials |
| PUT | `/api/users/v1/user/{userId}/tokenCredentials/{credentialId}` | |
| GET, POST, DELETE | `/api/pat/v1/tokens` and sub-routes | Personal Access Tokens (self); `/api/pat/v1/users/...` for admins |
| GET, POST | `/api/serviceAccounts/v1/serviceAccounts` and `/{serviceAccountIdpId}/tokens` | Service accounts |
| GET, POST | `/api/organizations/v1/organizations`; `/all`; PUT, DELETE `/{organizationId}/user` | |
| GET, POST, PUT | `/api/hardwaretiers/v1/hardwaretiers`; GET, DELETE `/{hardwareTierId}` | |
| GET, POST | `/api/datasource/v1/datasources`; GET, PATCH, DELETE `/{dataSourceId}`; GET `/api/datasource/v1/audit` | |
| GET | `/api/audittrail/v1/auditevents`, `/fieldValues`; POST `/search` | Platform audit trail |
| GET | `/api/cost/v1/allocation`, `/allocation/summary`, `/asset`, `/cloudCost`; `/api/cost/v2/...`; billing tags | Cost |
| GET, POST, PATCH, DELETE | `/api/admin/v1/deploymentTargets...` | Model deployment targets |

### Projects ([API-PROJECTS.md](./API-PROJECTS.md))

| Method | Route |
|--------|-------|
| GET, POST | `/api/projects/beta/projects` |
| POST | `/api/projects/v2/projects` |
| DELETE | `/api/projects/beta/projects/{projectId}` |
| GET | `/api/projects/v1/projects/{projectId}` |
| PUT | `/api/projects/v1/projects/{projectId}/status` |
| POST | `/api/projects/v1/projects/{projectId}/copy-project` |
| POST, DELETE | `/api/projects/v1/projects/{projectId}/collaborators[/{collaboratorId}]` |
| GET, POST, DELETE | `/api/projects/v1/projects/{projectId}/repositories[/{repositoryId}]` |
| PUT, GET | `/api/projects/v1/projects/{projectId}/repositories/{repositoryId}/default-ref`, `/file-metadata`, `/readme`, `/rendered-file` (**Cloud**) |
| GET, POST, PATCH, DELETE | `/api/projects/v1/projects/{projectId}/goals[/{goalId}]` |
| GET, POST, DELETE | `/api/projects/v1/projects/{projectId}/shared-datasets[/{datasetId}]` |
| GET | `/api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content` (also under `/beta/`) |
| GET, POST | `/api/projects/beta/projects/{projectId}/commits/latest`, `/commits/resolveGitRef` |
| GET, PUT | `/api/projects/beta/projects/{projectId}/results-settings` |
| POST | `/api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions` |
| GET | `/api/workspace/v1/workspace/{workspaceId}/writable-project-mounts` (**Cloud**) |

### Jobs ([API-JOBS.md](./API-JOBS.md))

| Method | Route |
|--------|-------|
| POST | `/api/jobs/v1/jobs` |
| GET | `/api/jobs/beta/jobs`, `/api/jobs/beta/jobs/{jobId}`, `/api/jobs/beta/jobs/{jobId}/logs` |
| POST, DELETE | `/api/jobs/v1/jobs/{jobId}/tags[/{tagId}]` |
| GET, POST, DELETE | `/api/jobs/v1/goals[/{goalId}]` (`jobId` query) |
| POST | `/api/jobs/v1/projects/{projectId}/job-defaults` (**Cloud**) |
| GET, POST | `/api/hpc/v1/jobs`, `/submit-supported`, `/cancel`, `/{jobId}`, `/{jobId}/logs` (Slurm HPC jobs) |

### Datasets ([API-DATASETS.md](./API-DATASETS.md))

| Method | Route |
|--------|-------|
| GET, POST | `/api/datasetrw/v1/datasets`; GET `/api/datasetrw/v2/datasets` |
| GET, PATCH, DELETE | `/api/datasetrw/v1/datasets/{datasetId}` |
| GET, POST | `/api/datasetrw/v1/datasets/{datasetId}/snapshots`; GET `/api/datasetrw/v1/snapshots/{snapshotId}` |
| POST, DELETE | `/api/datasetrw/v1/datasets/{datasetId}/tags[/{tagName}]` |
| GET, POST, DELETE | `/api/datasetrw/v1/datasets/{datasetId}/grants` |
| various | `/datasetrw/...` file upload and download routes (dataset files service) |

### Environments ([API-ENVIRONMENTS.md](./API-ENVIRONMENTS.md))

| Method | Route |
|--------|-------|
| GET, POST | `/api/environments/beta/environments` (POST is deprecated on Cloud in favour of v2) |
| GET, DELETE | `/api/environments/v1/environments/{environmentId}` |
| POST | `/api/environments/beta/environments/{environmentId}/revisions` (deprecated on Cloud); PATCH `.../revisions/{revisionId}` |
| POST | `/api/environments/v2/environments`, `.../{environmentId}/revisions` (**Cloud**; the current create routes there) |
| PUT | `/api/environments/v1/environments/{environmentId}/name`, `/description` (**Cloud**) |

### Model APIs, deployments, registry ([API-MODELS.md](./API-MODELS.md))

| Method | Route |
|--------|-------|
| GET, POST | `/api/modelServing/v1/modelApis`; GET, PUT, DELETE `/{modelApiId}` |
| GET, POST | `/api/modelServing/v1/modelApis/{modelApiId}/versions`; GET `/{modelApiVersionId}`, `/buildLogs`, `/exportLogs`, `/instanceLogs` |
| PUT | `/api/modelServing/beta/modelApis/{modelApiId}/access` (**Cloud**) |
| GET, PUT | `/api/modelServing/beta/modelApis/{modelApiId}/visibility` (**Cloud**) |
| GET, POST; GET, PUT, DELETE | `/api/modelServing/beta/modelApis/{modelApiId}/collaborators[/{collaboratorId}]` (**Cloud**); GET `.../consumer/access` (**Cloud**) |
| GET, POST | `/api/modelServing/v1/modelDeployments`; GET, PATCH, DELETE `/{modelDeploymentId}`; `/start`, `/stop`, `/versions`, `/logs/{logSuffix}`, `/credentials` |
| POST, GET | `/api/modelApis/async/v1/{asyncModelId}[/{asyncPredictionId}]` (async predictions) |
| GET, POST | `/api/registeredmodels/v2` (register and add versions); GET `/api/registeredmodels/v2/{modelName}/versions[/{version}]` |
| GET, PATCH | `/api/registeredmodels/v1/{modelName}`; GET `/versions`, `/versions/{version}`, `/modelapis`, build logs; POST `/versions` is deprecated (use v2) |
| GET, POST | `/api/gen-ai/beta/endpoints` and version/start/stop/metrics sub-routes (Domino-hosted LLM endpoints): [domino-llm-access](../domino-llm-access/HOST-AN-LLM-API.md) |

### Apps and extensions

| Method | Route | Where |
|--------|-------|-------|
| GET, POST | `/api/apps/v1/apps`; `/drafts`; `/{appId}/publish`; `/{appId}/versions[/createAndStart]`; `/versions/{versionId}/start`, `/stop`, `/liveSync` | [domino-apps](../domino-apps/API-APPS.md) |
| GET, POST, PATCH, DELETE | `/api/apps/beta/apps...` | [API-APPS.md](./API-APPS.md) |
| GET, POST, PATCH, DELETE | `/api/extensions/beta/extensions...` | [domino-extensions](../domino-extensions/SKILL.md) |

### Other services

| Prefix | Skill |
|--------|-------|
| `/api/governance/v1` | [domino-governance](../domino-governance/SKILL.md) |
| `/api/taxonomy/v1` | [tags-and-properties](../tags-and-properties/SKILL.md) |
| `/remotefs/v1` | [netapp-volumes](../netapp-volumes/SKILL.md) |
| `/model-monitor/v2/api`, `/api/metricValues/v1`, `/api/metricAlerts/v1` | [domino-model-monitoring](../domino-model-monitoring/SKILL.md) |
| `/api/aigateway/v1` (**6.3**; removed on Cloud) | [domino-llm-access](../domino-llm-access/SKILL.md); LLM Gateway 2.0 is [domino-llm-gateway](../domino-llm-gateway/SKILL.md) |

## Workspace sessions

```
POST /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions
```

Body: `{"externalVolumeMounts": ["<edv-id>", ...], "netAppVolumeMounts": ["<volume-id>", ...]}`.
`externalVolumeMounts` is required (send `[]` when none). Response:
`{"workspaceSession": {"id", "executionId"}, "metadata": {...}}`. There is no hardware
tier, environment or workspace type in this body; those belong to the workspace, which has
no create route in the Public API. See [domino-workspaces](../domino-workspaces/SKILL.md).

## Conventions

### Response codes

| Code | Meaning |
|------|---------|
| 200 | Success. Job start, project create and most creates return 200 with the object. |
| 201 | Created (taxonomy creates). |
| 204 | No content (taxonomy deletes; remotefs `delete-volume`, `delete-snapshot` and tag delete). The remotefs attach, detach, mark, restore-volume and restore-snapshot RPCs are specified as 204 but return 200 with a record. |
| 400, 401, 403, 404, 409, 500 | See [ERRORS.md](../domino-api-intro/ERRORS.md). |

### Error body

Read whichever of `errors`, `error` and `message` is present: the specs declare
`{"error"}` for most Nucleus 4xx/5xx, `{"code", "message"}` for 401/403 and
`{"errors", "requestId"}` for a few routes;
taxonomy and NetApp return `{"message"}`. Details: [ERRORS.md](../domino-api-intro/ERRORS.md#error-bodies).

### Pagination

`offset` / `limit` on most list routes. Nucleus responses wrap items under a resource key
with `metadata.offset`, `metadata.limit` and (usually) `metadata.totalCount`; taxonomy and
NetApp use `data` plus `meta.pagination`; model serving and apps use `items`. The
registry (`/api/registeredmodels/v1` and `/v2`) pages with `pageToken` / `maxResults` and
returns `metadata.nextPageToken`. Details: [LIMITS.md](../domino-api-intro/LIMITS.md#pagination).

### Path conventions

| Prefix | Meaning |
|--------|---------|
| `/api/<service>/v1`, `/v2` | Stable Public API |
| `/api/<service>/beta` | Public API, beta: responses carry `metadata.notices` and fields may change |
| `/remotefs/v1`, `/datasetrw`, `/model-monitor` | Public API served by separate services |
| `/v4/...`, `/v1/projects/...` | Domino Internal API. Not in the published specs; documented per deployment under `https://<domino-domain>/docs/openapi/openapi-internal.json`. Label any use `(non-public route; may change in a future Domino version)`; see [domino-api-intro](../domino-api-intro/SKILL.md#route-types). |

Field names differ between surfaces: `POST /api/jobs/v1/jobs` takes `runCommand` and
`hardwareTier`; python-domino `job_start` takes `command` and `hardware_tier_id`; the
internal scheduled-jobs route takes `command`. Always confirm the body for the exact route
in [API-SPECS.md](../domino-api-intro/API-SPECS.md).

## Documentation

- https://docs.domino.ai/cloud/reference/api/domino-open-api (reference UI; `/6.3/` for 6.3)
- https://docs.domino.ai/cloud/reference/api/domino-api-authentication
- [API-SPECS.md](../domino-api-intro/API-SPECS.md) for the spec files and per-deployment `/docs`
