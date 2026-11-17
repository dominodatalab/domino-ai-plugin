# Domino REST API reference

Route index for the Domino 6.1 Public API, as published in the Domino 6.1 Platform API
reference (https://docs.dominodatalab.com/en/6.1/api_guide/8c929e/domino-platform-api-reference/).
Your deployment's own `/docs` page is authoritative
([API-SPECS.md](../domino-api-intro/API-SPECS.md)). Request bodies with their required
fields live in the per-area files; this file is the map.

## Authentication and base URL

Rules and the shared `base_url` / `headers` setup block:
[domino-api-intro](../domino-api-intro/SKILL.md#authentication).

```python
response = requests.get(f"{base_url}/api/projects/beta/projects", headers=headers,
                        params={"limit": 20})
projects = response.json()["projects"]
```

## Route index

### Users, auth, admin ([API-ADMIN.md](./API-ADMIN.md))

| Method | Route | Notes |
|--------|-------|-------|
| GET | `/api/users/v1/self` | Current user: `{"user": {...}, "metadata": {...}}` |
| GET | `/api/users/v1/users` | `offset`, `limit` |
| GET | `/api/users/beta/credentials/{userId}` | Git credentials |
| POST | `/v4/serviceAccounts`; GET, POST `/v4/serviceAccounts/{serviceAccountIdpId}/tokens` | Service accounts (non-public route; may change in a future Domino version): [API-ADMIN.md](./API-ADMIN.md#service-accounts) |
| GET, POST | `/api/organizations/v1/organizations`; `/all`; PUT, DELETE `/{organizationId}/user` | |
| GET, POST, PUT | `/api/hardwaretiers/v1/hardwaretiers`; GET, DELETE `/{hardwareTierId}` | |
| GET, POST | `/api/datasource/v1/datasources`; GET, PATCH, DELETE `/{dataSourceId}`; GET `/api/datasource/v1/audit` | |
| GET | `/api/audittrail/v1/auditevents` | Platform audit trail |
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
| GET, POST, PATCH, DELETE | `/api/projects/v1/projects/{projectId}/goals[/{goalId}]` |
| GET, POST, DELETE | `/api/projects/v1/projects/{projectId}/shared-datasets[/{datasetId}]` |
| GET | `/api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content` (also under `/beta/`) |
| GET, PUT | `/api/projects/beta/projects/{projectId}/results-settings` |
| POST | `/api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions` |

### Jobs ([API-JOBS.md](./API-JOBS.md))

| Method | Route |
|--------|-------|
| POST | `/api/jobs/v1/jobs` |
| GET | `/api/jobs/beta/jobs`, `/api/jobs/beta/jobs/{jobId}`, `/api/jobs/beta/jobs/{jobId}/logs` |
| POST, DELETE | `/api/jobs/v1/jobs/{jobId}/tags[/{tagId}]` |
| GET, POST, DELETE | `/api/jobs/v1/goals[/{goalId}]` (`jobId` query) |

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
| GET, POST | `/api/environments/beta/environments` |
| GET, DELETE | `/api/environments/v1/environments/{environmentId}` |
| POST | `/api/environments/beta/environments/{environmentId}/revisions`; PATCH `.../revisions/{revisionId}` |

### Model APIs, deployments, registry ([API-MODELS.md](./API-MODELS.md))

| Method | Route |
|--------|-------|
| GET, POST | `/api/modelServing/v1/modelApis`; GET, PUT, DELETE `/{modelApiId}` |
| GET, POST | `/api/modelServing/v1/modelApis/{modelApiId}/versions`; GET `/{modelApiVersionId}`, `/buildLogs`, `/exportLogs`, `/instanceLogs` |
| GET, POST | `/api/modelServing/v1/modelDeployments`; GET, PATCH, DELETE `/{modelDeploymentId}`; `/start`, `/stop`, `/versions`, `/logs/{logSuffix}`, `/credentials` |
| POST, GET | `/api/modelApis/async/v1/{asyncModelId}[/{asyncPredictionId}]` (async predictions) |
| GET, POST | `/api/registeredmodels/v1` (list; register from an experiment run) |
| GET, PATCH | `/api/registeredmodels/v1/{modelName}`; GET, POST `/versions`; GET `/versions/{version}`, `/modelapis`, build logs |

### Apps

| Method | Route | Where |
|--------|-------|-------|
| GET, POST, PATCH, DELETE | `/api/apps/beta/apps...` | [API-APPS.md](./API-APPS.md), [domino-apps](../domino-apps/API-APPS.md) |

### Other services

| Prefix | Skill |
|--------|-------|
| `/remotefs/v1` | [netapp-volumes](../netapp-volumes/SKILL.md) |
| `/model-monitor/v2/api`, `/api/metricValues/v1`, `/api/metricAlerts/v1` | [domino-model-monitoring](../domino-model-monitoring/SKILL.md) |
| `/api/aigateway/v1` (AI Gateway) | [domino-llm-access](../domino-llm-access/SKILL.md) |

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
| 204 | No content (remotefs `delete-volume`, `delete-snapshot`). The remotefs attach, detach, mark, restore-volume and restore-snapshot RPCs are specified as 204 but return 200 with a record. |
| 400, 401, 403, 404, 409, 500 | See [ERRORS.md](../domino-api-intro/ERRORS.md). |

### Error body

Read whichever of `errors`, `error` and `message` is present: the specs declare
`{"error"}` for most Nucleus 4xx/5xx, `{"code", "message"}` for 401/403 and
`{"errors", "requestId"}` for a few routes;
NetApp returns `{"message"}`. Details: [ERRORS.md](../domino-api-intro/ERRORS.md#error-bodies).

### Pagination

`offset` / `limit` on most list routes. Nucleus responses wrap items under a resource key
with `metadata.offset`, `metadata.limit` and (usually) `metadata.totalCount`; NetApp,
model serving and apps use `items`. The registry (`/api/registeredmodels/v1`) pages with `pageToken` / `maxResults` and
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

- https://docs.dominodatalab.com/en/6.1/api_guide/8c929e/domino-platform-api-reference/
- https://docs.dominodatalab.com/en/6.1/user_guide/40b91f/domino-api-authentication/
- [API-SPECS.md](../domino-api-intro/API-SPECS.md) for the spec files and per-deployment `/docs`
