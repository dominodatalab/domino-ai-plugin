# Domino Admin API

Users, organizations, service accounts, Personal Access Tokens, hardware tiers, data
sources, cost and the platform audit trail. Routes and bodies are from both published
specs unless marked **Cloud**. Admin-only routes return `403` for other callers.

## Authentication

Use the shared setup block (`base_url`, `headers`) from
[domino-api-intro](../domino-api-intro/SKILL.md#authentication). Service-account and PAT
administration pages: https://docs.domino.ai/cloud/admin/identity-and-access/manage-users/service-accounts
and https://docs.domino.ai/cloud/admin/identity-and-access/manage-users/personal-access-tokens.

## Users

```
GET /api/users/v1/self
GET /api/users/v1/users?offset=0&limit=50
GET /api/users/v1/user/{userId}
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

```
GET  /api/users/v1/user/{userId}/roles                    -> {"roles": [...], "metadata"}
POST /api/users/v1/user/{userId}/roles      body: {"roles": ["..."]}   REPLACES the user's roles
```

Needs the `SetUserSystemRoles` permission. There is no `PUT`, and `POST` is not additive:
the spec says it sets "the complete list of roles for a user, replacing any previously
assigned roles" and "any roles not listed will be revoked". To add a role, send the
existing list plus the new one:

```python
roles = requests.get(f"{base_url}/api/users/v1/user/{user_id}/roles", headers=headers).json()["roles"]
if "Librarian" not in roles:
    requests.post(f"{base_url}/api/users/v1/user/{user_id}/roles", headers=headers,
                  json={"roles": roles + ["Librarian"]})
```

Posting `{"roles": ["Librarian"]}` alone would strip every other role, including admin
roles. Role names are deployment-defined; read them from the user's current list or the
admin UI.

### Git credentials

```
GET /api/users/beta/credentials/{userId}
PUT /api/users/v1/user/{userId}/tokenCredentials/{credentialId}      GitHub and GitHub Enterprise PATs only (spec note)
```

### Deactivation

Service accounts: `POST /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/deactivate`.
Human users have no Public API deactivate route; use the admin UI.

## Personal Access Tokens

```
GET, POST, DELETE /api/pat/v1/tokens                      your own tokens; POST body {"name": "...", "expiresIn": <seconds>, "description": "...", "scopes": [...]}
POST /api/pat/v1/tokens/{patId}/invalidate;  DELETE /api/pat/v1/tokens/{patId}
POST /api/pat/v1/tokens/invalidate | /invalidate/bulk | /delete/bulk
GET  /api/pat/v1/tokens/expiration-policy;  GET /api/pat/v1/tokens/grantable-scopes (Cloud)
GET  /api/pat/v1/users/tokens                              admin: all users' tokens
GET, DELETE /api/pat/v1/users/{userId}/tokens;  POST .../invalidate;  DELETE .../{patId};  POST .../{patId}/invalidate
```

`name` and `expiresIn` are required on create; `description` is optional; `scopes`
(**Cloud** only, values from `grantable-scopes`; omitted means none) restricts the token.
The response includes `token` once.

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

```
GET, POST /api/serviceAccounts/v1/serviceAccounts                       POST body: {"username": "...", "email": "..."}
POST /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/activate | /deactivate | /resetpassword
GET, POST /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/tokens      POST body: {"name": "..."}
GET, DELETE /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/tokens/{tokenName};  POST .../invalidate
GET /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/gitcredentials;  POST .../passwordgitcredentials | /sshgitcredentials | /tokengitcredentials
```

Create returns `{"serviceAccount": {"id", "idpId", "username", "email"}, "metadata": {...}}`.
Token routes are keyed by **`idpId`**, not `id`. `POST .../tokens` returns a
`ServiceAccountToken` (`name`, `serviceAccountIdpId`, `isValid`, `createdAt`, `expiresAt`,
`token`) with the token value. Unlike a Personal Access Token, the value is not
shown only once: in both specs `GET .../tokens/{tokenName}` ("Get the token with the
provided name") returns the same object, including `token`, as `{"token": {...}, "metadata"}`,
so an authorized caller can read a value again by name (spec-verified, not live-tested).
The list route `GET .../tokens` returns `{"tokens": [...], "metadata"}` with the metadata
fields only, never `token`. Neither spec describes the permission beyond `401`/`403`;
the docs restrict service-account management to Administrators, so expect `403` for
anyone else. Tokens inherit the service account's roles at creation and expire after
four months by default (docs). Give the value to its consumer once rather than re-reading
it: a Project or user environment variable for Domino executions, or the CI system's own
secret for a runner outside Domino, where Domino variables are not readable. Invalidate or
delete a token that leaked.

```python
sa = requests.post(f"{base_url}/api/serviceAccounts/v1/serviceAccounts", headers=headers,
                   json={"username": "github-actions", "email": "mlops@example.com"}).json()["serviceAccount"]
token = requests.post(f"{base_url}/api/serviceAccounts/v1/serviceAccounts/{sa['idpId']}/tokens",
                      headers=headers, json={"name": "ci-token"}).json()
secret = token["token"]   # hand to the consumer once: a Project or user environment variable in Domino, or the CI system's own secret outside

# Later, an administrator can read it again by name:
secret = requests.get(f"{base_url}/api/serviceAccounts/v1/serviceAccounts/{sa['idpId']}/tokens/ci-token",
                      headers=headers).json()["token"]["token"]
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
`description` is optional. The spec
types `config`, `visibleCredentials` and `secretCredentials` as free-form string maps
("a map of configuration name -> value"), so the keys depend on `dataSourceType`: copy them
from an existing data source of the same type (`GET` one) or create the first one in the
UI. `PATCH` by a non-admin updates only that user's individual credentials; an admin's
`PATCH` updates the shared credentials (spec). `DELETE` needs ownership. Audit `eventKinds`: `AccessDataSource`, `CreateDataSource`,
`DataSourceAssociatedToProject`, `DataSourceDissociatedFromProject`,
`DataSourceChangeOfOwnership`, `DataSourceChangeOfPermissions`, `DeleteDataSource`
(https://docs.domino.ai/cloud/admin/operations/audit-logs/monitor-data-source-logs).

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

`window` is the only required allocation parameter. Per the spec it accepts words
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
([SDK-EXAMPLES.md](./SDK-EXAMPLES.md)), which call `/v4/cost` routes (internal API, may
change between Domino versions).

## Audit trail

Feature docs: https://docs.domino.ai/cloud/platform-capabilities/features/governance/audit-trail.

```
GET  /api/audittrail/v1/auditevents
POST /api/audittrail/v1/search
GET  /api/audittrail/v1/fieldValues?field=<required>&search=
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

`search` takes a JSON filter: `{"filter": {"type": "group", "operator": "AND" | "OR", "rules": [...]}, "limit": 50, "offset": 0}` with `limit` 1 to 1000.
`fieldValues` lists distinct values for one field (`field` required) for building filters.

## Internal routes you may still meet

These are Domino Internal API, may change between Domino versions, and are not in either
published spec: `/v4/users?listOnlyUsers=true`, `/v4/admin/centralConfigSettings`,
`/v4/auth/principal`, `/v4/datasetrw/dataset-cost`, `/v4/domino-cost/budgets`. Confirm
each in your deployment's `/docs/openapi/openapi-internal.json` before using it, and
prefer the public routes above.
