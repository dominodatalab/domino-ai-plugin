# Limits, pagination, and deprecated patterns

Authentication: [SKILL.md](./SKILL.md#authentication) and
https://docs.domino.ai/cloud/reference/api/domino-api-authentication. Error handling:
[ERRORS.md](./ERRORS.md).

## Deprecated credentials and variables

Do not use these in new examples or agent steps:

| Pattern | Status |
|---------|--------|
| `X-Domino-Api-Key` header, `DOMINO_USER_API_KEY`, `api_key=` in python-domino | Deprecated; never use, not even as a fallback |
| `DOMINO_TOKEN_FILE` / JWT file propagation | Not set in executions; on Domino 6.3 the `EnableLegacyJwtTooling` feature flag can re-enable it; do not build on it |
| Deriving the deployment URL from the JWT `iss` claim | Unsupported; for API calls read `DOMINO_API_HOST`; for links users open, see [HOSTS.md](./HOSTS.md) |

Legacy API key section (migration only):
https://docs.domino.ai/cloud/reference/api/domino-api-authentication#authenticate-with-an-api-key-legacy

## Pagination

Most list routes in the Public API spec take `offset` and `limit` query parameters
(`limit` usually defaults to 10). The envelope differs by service:

| Service | Response shape |
|---------|----------------|
| Platform `/api/...` lists (projects, jobs, users, environments, datasets, hardware tiers) | `{"<items-key>": [...], "metadata": {"requestId", "notices", "offset", "limit", "totalCount"}}`. The items key is the resource name (`projects`, `jobs`, `users`, `environments`, `datasets`, `hardwareTiers`). `totalCount` is optional in the schema. |
| Taxonomy `/api/taxonomy/v1` and NetApp `/remotefs/v1` lists | `{"data": [...], "meta": {"pagination": {"total" or "totalCount", "limit", "offset"}}}` |
| Model serving, apps | `{"items": [...], "metadata": {...}}` with `offset` / `limit` (apps: `limit` defaults to no limit) |
| Registered models `/api/registeredmodels/v1` and `/v2` | `{"items": [...], "metadata": {"nextPageToken"}}`; page with `pageToken` / `maxResults` (default 25), not offset |
| Audit trail `POST /api/audittrail/v1/search` | `limit` 1 to 1000 (default 50), `offset` >= 0 |

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
