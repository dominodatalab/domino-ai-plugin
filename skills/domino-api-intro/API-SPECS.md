# OpenAPI specs and route discovery

Verify every route and body against these before writing an example. Do not guess
routes from memory.

## Published Public API specs

One per supported target. A route must exist in the spec for every Domino version a skill
claims.

| Target | OpenAPI JSON | Reference UI |
|--------|--------------|--------------|
| Domino 6.3 | https://docs.domino.ai/api-specs/6.3/public-api.json | https://docs.domino.ai/6.3/reference/api/domino-open-api |
| Domino Cloud | https://docs.domino.ai/api-specs/cloud/public-api.json | https://docs.domino.ai/cloud/reference/api/domino-open-api |

```bash
# List paths in the Cloud spec (swap cloud for 6.3)
curl -s https://docs.domino.ai/api-specs/cloud/public-api.json | jq -r '.paths | keys[]' | grep taxonomy
# Request body for one operation
curl -s https://docs.domino.ai/api-specs/cloud/public-api.json \
  | jq '.paths["/api/jobs/v1/jobs"].post.requestBody.content["application/json"].schema'
```

Differences between the two (October 2026): the Cloud spec adds
`POST /api/jobs/v1/projects/{projectId}/job-defaults`, `/api/environments/v2/environments`,
environment name/description `PUT`s, Model API collaborators/visibility under
`/api/modelServing/beta`, app roles, and repository default-ref/readme routes. The 6.3 spec
alone has `/api/aigateway/v1/*`.

## A deployment's own reference

Every Domino deployment from 6.3 serves an unauthenticated API reference at
`https://<domino-domain>/docs`, with one OpenAPI document per service:

```bash
curl -s https://<domino-domain>/docs/configuration.json | jq '.sources[] | {title, url}'
```

| Document | Contents |
|----------|----------|
| `/docs/openapi/openapi-public.json` | That deployment's full Public API |
| `/docs/openapi/openapi-internal.json` | The internal API (the `/v4/*` routes; non-public, may change in a future Domino version) |
| `/docs/openapi/data_taxonomy_service-swagger.json` | Tags and properties service |
| `/docs/openapi/data_remotefs_service-swagger.json` | NetApp Volumes service |
| `/docs/openapi/rai_guardrails_service-swagger.json` | Governance service |

`$DOMINO_API_HOST/assets/public-api.json` is only a subset of the Public API and omits
governance, taxonomy, model monitoring, NetApp volumes and dataset-file routes; do not
treat it as complete.

## Internal routes (`/v4/*`)

`/v4/*` routes are the Domino Internal API. They are not in the Public API spec and are
not versioned for external use. Prefer the `/api/...` equivalent; where none exists,
label the call **non-public route; may change in a future Domino version** at the point of use ([route types](./SKILL.md#route-types)).

## Product docs

- https://docs.domino.ai/llms.txt indexes every page; any page is Markdown with `.md`
  appended (for example
  https://docs.domino.ai/cloud/reference/api/domino-api-authentication.md).
- Service entry pages: [Tags API](https://docs.domino.ai/cloud/reference/api/tags-api),
  [NetApp Volumes API](https://docs.domino.ai/cloud/reference/api/domino-volumes-api),
  [Governance API](https://docs.domino.ai/cloud/reference/api/governance-api).
