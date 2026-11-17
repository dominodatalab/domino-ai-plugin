# Domino Admin API

Users, organizations, service accounts, hardware tiers, data sources, cost and the
platform audit trail. Admin-only routes return `403` for other callers.

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication). Service-account
administration: https://docs.dominodatalab.com/en/6.1/admin_guide/6921e5/manage-domino-service-accounts/.

## Users

```
GET /api/users/v1/self
GET /api/users/v1/users?offset=0&limit=50
```

`self` returns `{"user": {"id", "idpId", "userName", "fullName", "firstName", "lastName", "email", "avatarUrl", "roles"}, "metadata": {...}}`.
`users` returns `{"users": [...], "metadata": {"offset", "limit", ...}}` and includes
organization pseudo-users and service accounts; there is no server-side filter, so
filter client-side.

```python
me = requests.get(f"{base_url}/api/users/v1/self", headers=headers).json()["user"]
print(me["userName"], me["id"])
```

### Roles

The Domino 6.1 Public API has no role routes. Administrators assign roles in the Admin panel. A service account inherits the roles of the administrator who
created it.

### Git credentials

```
GET /api/users/beta/credentials/{userId}
```

### Deactivation

Users have no Public API deactivate route. For a service account, invalidate its tokens
([Service accounts](#service-accounts)). Administrators do it in the admin UI or
with the Domino Internal API `PATCH /v4/admin/user-management/users/{targetUserIdpId}`,
body `{"enabled": false}` (`UpdateUserRequest`: optional `roles`, `enabled`,
`isDominoEmployee`; `idpId` from `GET /api/users/v1/users`). non-public route; may change in a future Domino version; admin-only. Confirm it in your
deployment's `/docs` first.

## Organizations

```
GET  /api/organizations/v1/organizations            organizations the caller belongs to
GET  /api/organizations/v1/organizations/all        admin only
GET  /api/organizations/v1/organizations/{organizationId}
POST /api/organizations/v1/organizations            body: {"name": "...", "members": [{"userId": "...", "organizationRole": "member" | "admin"}]}
PUT  /api/organizations/v1/organizations/{organizationId}/user      body: {"userId": "...", "organizationRole": "member" | "admin"}
DELETE /api/organizations/v1/organizations/{organizationId}/user?memberToRemoveId=<userId>
```

`name` and `members` are required on create; the response is `{"org": {"id", "name", "members", "defaultEnvironmentId"}, "metadata"}`.
List responses use `{"orgs": [...], "metadata": {...}}`.

## Service accounts

On Domino 6.1 service accounts are managed with the Domino Internal API (non-public route; may
change in a future Domino version). Administrators only; expect `403` for anyone else.
Reference: https://docs.dominodatalab.com/en/6.1/admin_guide/6921e5/manage-domino-service-accounts/

```
POST   /v4/serviceAccounts                                             body: {"username": "...", "email": "..."}
POST   /v4/serviceAccounts/{serviceAccountIdpId}/tokens                body: {"name": "..."}
GET    /v4/serviceAccounts/{serviceAccountIdpId}/tokens
POST   /v4/serviceAccounts/{serviceAccountIdpId}/tokens/{tokenName}/invalidate
DELETE /v4/serviceAccounts/{serviceAccountIdpId}/tokens/{tokenName}
```

Create returns `{"id", "userName", "email", "idpId"}`; the email must be valid and unique.
Token routes are keyed by **`idpId`**, not `id`. `POST .../tokens` returns `name`,
`serviceAccountIdpId`, `isValid`, `createdAt`, `expiresAt` and `token` (the value). The list
returns the same fields without `token`, so store the value when it is created. Tokens
inherit the service account's roles at creation and expire after four months by default; after
a role change, create a new token. Give the value to its consumer once: a Project or user
environment variable for Domino executions, or the CI system's own secret for a runner
outside Domino, where Domino variables are not readable. Invalidate or delete a token that
leaked.

```python
sa = requests.post(f"{base_url}/v4/serviceAccounts", headers=headers,
                   json={"username": "github-actions", "email": "mlops@example.com"}).json()
token = requests.post(f"{base_url}/v4/serviceAccounts/{sa['idpId']}/tokens",
                      headers=headers, json={"name": "ci-token"}).json()
secret = token["token"]   # hand to the consumer once: a Project or user environment variable in Domino, or the CI system's own secret outside
```

## Hardware tiers

```
GET    /api/hardwaretiers/v1/hardwaretiers?offset=&limit=&includeArchived=
GET    /api/hardwaretiers/v1/hardwaretiers/{hardwareTierId}
POST   /api/hardwaretiers/v1/hardwaretiers        admin; required id, name, resources, nodePool
PUT    /api/hardwaretiers/v1/hardwaretiers        admin; full object
DELETE /api/hardwaretiers/v1/hardwaretiers/{hardwareTierId}   archive
```

Response: `{"hardwareTiers": [{"id", "name", "resources": {"cores", "coresLimit", "memory": {"value", "units"}, ...}, "flags": {"isDefault", "isVisible", "isGlobal", "isArchived", ...}, "gpuConfiguration": {"numberOfGpus", "gpuKey"}, "centsPerMinute", "nodePool", "computeClusterRestrictions", "capacity", ...}], "metadata": {...}}`
(`limit` defaults to 10; `architecture` `amd64`/`arm64` is **Cloud** only). The `id` (for
example `small-k8s`) is what `POST /api/jobs/v1/jobs` takes as `hardwareTier`. Listing
needs the ViewHardwareTiers permission; python-domino `hardware_tiers_list()` lists the
tiers usable by a project without it.

```python
tiers = requests.get(f"{base_url}/api/hardwaretiers/v1/hardwaretiers", headers=headers).json()["hardwareTiers"]
for t in tiers:
    print(t["id"], t["name"], t["resources"]["cores"], t["resources"]["memory"])
```

## Data sources

```
GET    /api/datasource/v1/datasources?dataSourceNames=&offset=&limit=
POST   /api/datasource/v1/datasources
GET, PATCH, DELETE /api/datasource/v1/datasources/{dataSourceId}
GET    /api/datasource/v1/audit?startTime=&endTime=&dataSourceIds=&dataSourceNames=&eventKinds=
```

List returns `{"dataSources": [{"id", "name", "dataSourceType", "authType", "credentialType", "config", "permissions", "ownerId", ...}]}`.
Create requires `name`, `dataSourceType`, `authType`, `credentialType`
(`Individual` or `Shared`), `credentials` (`visibleCredentials`, `secretCredentials`
maps), `config` (map) and `permissions` (`isEveryone`, `userAndOrganizationIds`);
`description` is optional. `config`, `visibleCredentials` and `secretCredentials` are
free-form string maps whose keys depend on `dataSourceType`: copy them from an existing
data source of the same type (`GET` one) or create the first one in the UI. `PATCH` by a
non-admin updates only that user's individual credentials; an admin's `PATCH` updates the
shared credentials. `DELETE` needs ownership. Audit `eventKinds`: `AccessDataSource`, `CreateDataSource`,
`DataSourceAssociatedToProject`, `DataSourceDissociatedFromProject`,
`DataSourceChangeOfOwnership`, `DataSourceChangeOfPermissions`, `DeleteDataSource`
(https://docs.dominodatalab.com/en/6.1/admin_guide/f5934f/monitor-data-source-logs/).

## Deployment targets (model deployments)

```
GET /api/admin/v1/deploymentTargetTypes[/{deploymentTargetTypeId}]
GET, POST /api/admin/v1/deploymentTargets;  GET /api/admin/v1/deploymentTargets/selectable
GET, PATCH, DELETE /api/admin/v1/deploymentTargets/{deploymentTargetId}
GET, POST /api/admin/v1/deploymentTargets/{deploymentTargetId}/resourceConfigurations
GET, PATCH, DELETE .../resourceConfigurations/{resourceConfigurationId};  GET .../effectiveModelDeploymentSchema
```

## Cost

```
GET /api/cost/v1/allocation?window=<required>&aggregate=&start=&end=&accumulate=&filter=&shareIdle=...
GET /api/cost/v1/allocation/summary;  GET /api/cost/v1/asset;  GET /api/cost/v1/cloudCost
GET /api/cost/v2/allocation[/accumulated], /allocation/summary[/accumulated], /asset[/accumulated], /cloudCost[/accumulated]
GET, POST /api/cost/v1/billingtags;  GET, DELETE /api/cost/v1/billingtags/{tag}
GET, PUT /api/cost/v1/billingtagSettings;  /mode;  /notifications
GET /api/cost/v1/costActivationStatus;  PUT /api/cost/v1/licenseKey;  PUT /api/cost/v1/athenaConfigs
```

`window` is the only required allocation parameter. It accepts words
(`today`, `week`, `month`, `yesterday`, `lastweek`, `lastmonth`), durations (`30m`,
`12h`, `7d`) or a time range (`2021-03-10T00:00:00Z,2021-03-11T00:00:00Z`); `start` and
`end` (RFC 3339) must fall inside it. `aggregate` takes the kubecost aggregates
(`cluster`, `namespace`, `pod`, `deployment`, `service`, `daemonset`, `statefulset`, `job`,
`cronjob`, `replicaset`, `node`, `container`, `pv`, `pvc`, `storageclass`); `filter` uses the
same keys. The response is `{"data": [{"name", "totalCost", "cpuCost", "ramCost", "gpuCost", "cpuCoreHours", "gpuHours", "window", ...}]}`.
Permissions vary by deployment; a `403` means the caller lacks the admin or billing role.

```python
costs = requests.get(f"{base_url}/api/cost/v1/allocation", headers=headers,
                     params={"window": "7d", "aggregate": "namespace"}).json()["data"]
```

Budgets and alerts are covered by python-domino's `budget_*` and `billing_tag*` methods
([SDK-EXAMPLES.md](./SDK-EXAMPLES.md)), which call `/v4/cost` routes (non-public route; may change in a future Domino version).

## Audit trail

Feature docs: https://docs.domino.ai/cloud/platform-capabilities/features/governance/audit-trail.

```
GET  /api/audittrail/v1/auditevents
```

`auditevents` query parameters (all optional): `startTimestamp`, `endTimestamp`
(integers, epoch milliseconds), `actorId`, `actorName`, `event`, `targetType`, `targetId`,
`targetName`, `withinProjectId`, `withinProjectName`, `sort` (comma-separated fields with
`+`/`-` prefix: `timestamp`, `actorId`, `actorName`, `withinProjectId`,
`withinProjectName`, `event`, `targetType`, `targetName`), `limit` (default 10),
`offset`, `column` (CSV download only). There is no `startTime`, `endTime` or `eventType`
parameter.

```python
events = requests.get(f"{base_url}/api/audittrail/v1/auditevents", headers=headers, params={
    "startTimestamp": 1735689600000,     # 2025-01-01T00:00:00Z
    "endTimestamp":   1735776000000,
    "event": "Create Dataset",
    "limit": 100, "offset": 0,
}).json()
for e in events["events"]:
    print(e["timestamp"], e["actor"]["name"], e["action"]["eventName"],
          [t["entity"]["name"] for t in e["targets"]])
```

Response: `{"events": [{"timestamp", "actor": {"id", "name"}, "action": {"eventName", "using", "traceId", "electronicallySigned"}, "targets": [{"entity": {"entityType", "id", "name"}, "fieldChanges"}], "affecting", "in", "metadata"}], "estimatedMatches", "total"}`.

## Internal routes you may still meet

These are non-public routes; they may change in a future Domino version, and are not in either
published spec: `/v4/users?listOnlyUsers=true`, `/v4/admin/centralConfigSettings`,
`/v4/auth/principal`, `/v4/datasetrw/dataset-cost`, `/v4/domino-cost/budgets`. Confirm
each in your deployment's `/docs/openapi/openapi-internal.json` before using it, and
prefer the public routes above.
