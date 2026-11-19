# OpenAPI specs and route discovery

Check that a route and its body exist in the reference for Domino 6.1 before calling it; do
not guess routes from memory.

## Published Public API reference

Domino 6.1 Platform API reference (every public route, with request and response schemas):
https://docs.dominodatalab.com/en/6.1/api_guide/8c929e/domino-platform-api-reference/

Domino 6.1 does not serve a per-deployment API reference: the `https://<domino-domain>/docs`
page and its `/docs/openapi/*.json` documents arrive in Domino 6.3. On 6.1, use the reference
above. The specs at `https://docs.domino.ai/api-specs/` describe Domino 6.3 and Domino Cloud
and list routes and fields that Domino 6.1 does not have; do not take a route from them.

`$DOMINO_API_HOST/assets/public-api.json` is only a subset of the Public API and omits
model monitoring, NetApp volumes and dataset-file routes; do not treat it as complete.

## Internal routes (`/v4/*`)

`/v4/*` routes are the Domino Internal API. They are not in the Public API reference, Domino
6.1 publishes no reference for them, and they are not versioned for external use. Prefer the
`/api/...` equivalent; where none exists, label the call **non-public route; may change in a
future Domino version** at the point of use ([route types](./SKILL.md#route-types)). If a
`/v4` call returns 404, or 400 for a body the skill gives, use the UI steps the skill names
instead.

## Product docs

- Domino 6.1 user, admin and API guides: https://docs.dominodatalab.com/en/6.1/user_guide/1a73c8/user-guide/
- https://docs.domino.ai/llms.txt indexes the Domino 6.3 and Cloud docs; any page is Markdown
  with `.md` appended. Those pages can describe features Domino 6.1 does not have.
- [NetApp Volumes API](https://docs.dominodatalab.com/en/6.1/api_guide/b3b2a1/domino-netapp-volumes-api/)
  (its base path and shapes differ from the service; use
  [API-NETAPP-VOLUMES.md](../netapp-volumes/API-NETAPP-VOLUMES.md)).
