# Limits, pagination, and credential patterns to avoid

Authentication: [SKILL.md](./SKILL.md#authentication) and
https://docs.dominodatalab.com/en/6.1/user_guide/40b91f/domino-api-authentication/. Error handling:
[ERRORS.md](./ERRORS.md).

## Credential patterns to avoid

Do not use these in new examples or agent steps:

| Pattern | Status |
|---------|--------|
| `DOMINO_TOKEN_FILE` / JWT file propagation | Not set in executions; the `EnableLegacyJwtTooling` feature flag can re-enable it; do not build on it |
| Deriving the deployment URL from the JWT `iss` claim | Unsupported; for API calls read `DOMINO_API_HOST`; for links users open, see [HOSTS.md](./HOSTS.md) |
| A user API key where a service account token is available | Use the service account token for unattended automation; the user API key is the fallback ([SKILL.md](./SKILL.md#authentication)) |

## Pagination

Most list routes in the Public API spec take `offset` and `limit` query parameters
(`limit` usually defaults to 10). The envelope differs by service:

| Service | Response shape |
|---------|----------------|
| Platform `/api/...` lists (projects, jobs, users, environments, datasets, hardware tiers) | `{"<items-key>": [...], "metadata": {"requestId", "notices", "offset", "limit", "totalCount"}}`. The items key is the resource name (`projects`, `jobs`, `users`, `environments`, `datasets`, `hardwareTiers`). `totalCount` is optional in the schema. |
| NetApp `/remotefs/v1` lists | `{"items": [...], "totalCount": N}`; confirm the shape in your deployment's `/docs` |
| Model serving, apps | `{"items": [...], "metadata": {...}}` with `offset` / `limit` (apps: `limit` defaults to no limit) |
| Registered models `/api/registeredmodels/v1` | `{"items": [...], "metadata": {"nextPageToken"}}`; page with `pageToken` / `maxResults` (default 25), not offset |

Rules for agents:

- Page until a page returns fewer rows than `limit` (or `offset` reaches `totalCount`).
  Never treat the first page as complete.
- Beta routes return `metadata.notices: ["Beta endpoint with known limitations"]`;
  surface that notice when results look truncated.
- Prefer server-side filters that exist in the spec (for example `GET /api/datasetrw/v2/datasets`
  takes `projectIdsToInclude`, `projectIdsToExclude`, `minimumPermission`); filter client-side
  only for fields the route does not accept.

## Asynchronous starts

`POST /api/jobs/v1/jobs` returns `200` with `{"job": {...}, "metadata": {...}}`; the id is
`job.id`. Poll `GET /api/jobs/beta/jobs/{jobId}` and read `job.status.executionStatus` and
`job.status.isCompleted`. Details and terminal values: [ERRORS.md](./ERRORS.md#jobs-and-execution-status)
and [API-JOBS.md](../domino-python-sdk/API-JOBS.md).
