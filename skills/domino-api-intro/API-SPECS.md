# OpenAPI specs and route discovery

Check that a route and its body exist in the reference for Domino 6.1 before calling it; do
not guess routes from memory.

## Published Public API reference

Domino 6.1 Platform API reference:
https://docs.dominodatalab.com/en/6.1/api_guide/8c929e/domino-platform-api-reference/

Your deployment's own `/docs` page (below) is authoritative for the routes and bodies it
serves. The specs at `https://docs.domino.ai/api-specs/` describe Domino 6.3 and Domino Cloud
and list routes that Domino 6.1 does not have; do not take a route from them without
confirming it on your deployment.

## A deployment's own reference

A Domino deployment serves an unauthenticated API reference at
`https://<domino-domain>/docs`, with one OpenAPI document per service:

```bash
curl -s https://<domino-domain>/docs/configuration.json | jq '.sources[] | {title, url}'
# List paths in the deployment's Public API
curl -s https://<domino-domain>/docs/openapi/openapi-public.json | jq -r '.paths | keys[]'
# Request body for one operation
curl -s https://<domino-domain>/docs/openapi/openapi-public.json \
  | jq '.paths["/api/jobs/v1/jobs"].post.requestBody.content["application/json"].schema'
```

If `/docs/configuration.json` returns 404, open `https://<domino-domain>/docs` in a browser
or use the 6.1 Platform API reference above.

| Document | Contents |
|----------|----------|
| `/docs/openapi/openapi-public.json` | That deployment's full Public API |
| `/docs/openapi/openapi-internal.json` | The internal API (the `/v4/*` routes; non-public, may change in a future Domino version) |
| `/docs/openapi/data_remotefs_service-swagger.json` | NetApp Volumes service |

`$DOMINO_API_HOST/assets/public-api.json` is only a subset of the Public API and omits
model monitoring, NetApp volumes and dataset-file routes; do not treat it as complete.

## Internal routes (`/v4/*`)

`/v4/*` routes are the Domino Internal API. They are not in the Public API spec and are
not versioned for external use. Prefer the `/api/...` equivalent; where none exists,
label the call **non-public route; may change in a future Domino version** at the point of use ([route types](./SKILL.md#route-types)).

## Product docs

- Domino 6.1 user, admin and API guides: https://docs.dominodatalab.com/en/6.1/user_guide/1a73c8/user-guide/
- https://docs.domino.ai/llms.txt indexes the Domino 6.3 and Cloud docs; any page is Markdown
  with `.md` appended. Those pages can describe features Domino 6.1 does not have.
- [NetApp Volumes API](https://docs.domino.ai/cloud/reference/api/domino-volumes-api).
