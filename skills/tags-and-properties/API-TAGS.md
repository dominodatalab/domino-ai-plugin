# Tags API reference

Endpoint-by-endpoint reference for the tag side of `/api/taxonomy/v1`: concepts, the
endpoint table, curl examples for namespaces, tags, entity tags, the taxonomy tree and
config limits, and troubleshooting. Properties: [PROPERTIES.md](./PROPERTIES.md) and
[PROPERTY-VALUES.md](./PROPERTY-VALUES.md). Entity types differ per target:
[SKILL.md](./SKILL.md#which-path-applies).

All examples assume `BASE` and `H` from [SKILL.md](./SKILL.md#configuration).

## Key concepts

| Concept | Description |
|---------|-------------|
| **Namespace** | The key of a tag pair (`Indication`, `Analysis`). Fields: `label`, `allowMultipleAssignments`, `status` (`active`, `deprecated`), `tagCount`, `entityCount`. |
| **Tag** | A value inside a namespace, optionally nested with `parentId`. Fields: `id`, `label`, `description`, `namespaceId`, `namespaceLabel`, `parentId`, `status`, `children`, `entityCount`. |
| **Entity** | A taggable Domino object identified by `entityType` + `entityId`. Types: [SKILL.md](./SKILL.md#which-path-applies). |
| **Property / property value** | Typed field and its per-entity value; see the property files. |
| **`allowMultipleAssignments`** | `true`: an entity can carry several tags from the namespace. `false` (default): a new tag from the namespace replaces the existing one. |
| **Taxonomy tree** | Namespaces with nested tags, from `GET /taxonomy`. |
| **Limits** | `GET /config`: `maxDepth`, `maxLabelLength`, `maxSelectAllowedValuesCount`, `maxSelectAllowedValueLength`. |

## Endpoint table

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/config` | GET | Limits |
| `/taxonomy` | GET | Full tree |
| `/namespaces` | GET, POST | List (`search`, `label`, `sort`, `order`, `limit`, `offset`) / create |
| `/namespaces/{namespaceId}` | GET, PUT, DELETE | Get / update / delete (removes its tags; fails while any tag has entity assignments) |
| `/namespaces/bulk-delete` | POST | [BULK-OPS.md](./BULK-OPS.md) |
| `/tags` | GET, POST | List / create |
| `/tags/{tagId}` | GET, PUT, DELETE | Get / update (re-parent, deprecate) / delete |
| `/tags/{tagId}/entities` | GET | Entities carrying a tag |
| `/tags/autocomplete` | GET | Typeahead (`q` required, `namespaceId`, `limit`) |
| `/tags/bulk-delete` | POST | [BULK-OPS.md](./BULK-OPS.md) |
| `/rpc/merge-tags` | POST | [BULK-OPS.md](./BULK-OPS.md) |
| `/entities` | GET | Entities by one or more tag ids |
| `/entity-tags` | GET, DELETE | Tags on entities / remove all tags from one entity |
| `/rpc/tag-entity`, `/rpc/untag-entity` | POST | Add / remove tags on an entity |
| `/rpc/copy-entity-tags`, `/rpc/copy-property-values` | POST | "Internal, service-account only" per the spec; replaces the target's tags or values. Not a user workflow; see [BULK-OPS.md](./BULK-OPS.md) |
| `/rpc/export-to-file`, `/rpc/validate-file`, `/rpc/import-from-file` | POST | [IMPORT-EXPORT.md](./IMPORT-EXPORT.md) |
| `/properties`, `/properties/{propertyId}`, `/property-groups` | GET, POST, PUT, DELETE | [PROPERTIES.md](./PROPERTIES.md) |
| `/property-values/{entityType}/{entityId}` | GET, PATCH, DELETE | [PROPERTY-VALUES.md](./PROPERTY-VALUES.md) |

## Namespaces

```bash
# List
curl -s -H "$H" "$BASE/namespaces?limit=50&offset=0"
# {"data":[{"id","label","description","allowMultipleAssignments","tagCount","entityCount":{...},"status"}],
#  "meta":{"pagination":{"total","limit","offset"},"sort"}}

# Create (label required; description and allowMultipleAssignments optional, default false)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Indication","description":"Therapeutic area","allowMultipleAssignments":true}' "$BASE/namespaces"
# 201 -> the namespace record (id, label, description, status "active", tagCount, entityCount, timestamps)

# Get one
curl -s -H "$H" "$BASE/namespaces/<id>"

# Update (label and status required; description and allowMultipleAssignments optional; status is active or deprecated)
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Indication","description":"updated","status":"active","allowMultipleAssignments":true}' "$BASE/namespaces/<id>"

# Delete: removes the namespace and all its tags; fails while any of its tags is still
# assigned (see Troubleshooting). No confirmation.
curl -s -X DELETE -H "$H" "$BASE/namespaces/<id>"
# 204
```

Namespace labels are alphanumeric with hyphens and underscores.

## Tags

```bash
# List with filters: namespaceId, search, status, parentId, rootOnly, entityId, entityType, sort, order, limit, offset
curl -s -H "$H" "$BASE/tags?namespaceId=<ns>&rootOnly=true&limit=50"
# {"data":[{"id","label","namespaceId","namespaceLabel","parentId","status","children":[...],"entityCount":{...}}],"meta":{...}}

# Create (label and namespaceId required; description optional; parentId nests under a tag in the same namespace)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"SDTM","namespaceId":"<ns>","description":"Study Data Tabulation Model","parentId":"<parent-tag>"}' "$BASE/tags"
# 201 -> tag record (id, label, description, namespaceId, parentId, status, entityCount, ...).
#        The optional fullPath in the schema is absent from tag responses: build the path
#        from parentId or use /tags/autocomplete.

# Get one
curl -s -H "$H" "$BASE/tags/<id>"

# Update (label required; description, parentId (re-parent) and status (active or deprecated) optional)
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"SDTMv2","description":"new desc","status":"active","parentId":"<new-parent>"}' "$BASE/tags/<id>"

# Deprecate: keeps existing assignments, blocks new ones
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"SDTM","status":"deprecated"}' "$BASE/tags/<id>"

# Delete
curl -s -X DELETE -H "$H" "$BASE/tags/<id>"
# 204
```

## Entity tags

```bash
# Tag an entity (entityType, entityId, tagIds all required)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"entityType":"project","entityId":"<project-id>","tagIds":["<tag-1>","<tag-2>"]}' \
  "$BASE/rpc/tag-entity"
# 201 -> {"entityId","entityType","entityName","tags":[{"id","label"}]}
# Several tags from one namespace in a single call need allowMultipleAssignments=true on
# that namespace; otherwise send one request per tag and the newest replaces the previous.

# Remove specific tags
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"entityType":"project","entityId":"<project-id>","tagIds":["<tag-1>"]}' \
  "$BASE/rpc/untag-entity"
# 200 -> {"entityId","entityType","entityName","removedTagIds":[...]}

# Tags on one or more entities (entityIds is an array parameter: repeat it)
curl -s -H "$H" "$BASE/entity-tags?entityType=project&entityIds=<id-1>&entityIds=<id-2>"
# 200 -> {"data":{"<id-1>":[Tag,...],"<id-2>":[Tag,...]}}

# Remove all tags from an entity
curl -s -X DELETE -H "$H" "$BASE/entity-tags?entityType=project&entityId=<id>"
# 200 -> {"removedCount":N}
```

## Find entities by tag

```bash
# One tag
curl -s -H "$H" "$BASE/tags/<tag-id>/entities?entityTypes=project&includeDescendants=true&limit=50"

# Several tags (tagIds is an array parameter: repeat it). AND semantics: only entities
# that carry ALL of the given tags are returned.
curl -s -H "$H" "$BASE/entities?tagIds=<tag-1>&tagIds=<tag-2>&entityTypes=project&entityTypes=app"
# 200 -> {"data":[{"entityId","entityName","ownerUsername","taggedAt","tags":[{"id","label","namespace"}], ...}],
#         "meta":{"pagination":{"total","limit","offset"}}}
```

`includeDescendants=true` also matches entities tagged with child tags.

## Taxonomy tree

```bash
curl -s -H "$H" "$BASE/taxonomy"
```

Returns an array of namespaces, each with `tags` nested as `children`:

```json
[{"id":"...","label":"Indication","status":"active","allowMultipleAssignments":false,
  "tags":[{"id":"...","label":"Oncology","status":"active",
           "children":[{"id":"...","label":"Breast_Cancer","status":"active","children":[]}]}]}]
```

## Config

```bash
curl -s -H "$H" "$BASE/config"
# {"maxDepth":5,"maxLabelLength":128,"maxSelectAllowedValuesCount":100,"maxSelectAllowedValueLength":2048}
```

Limits differ per deployment; read them at startup.

## Troubleshooting

### 404 on every route

Check the base: `/api/taxonomy/v1` on `$DOMINO_API_PROXY` or `$DOMINO_API_HOST` in a run,
the deployment URL outside. A 404 with the right base means the taxonomy service is not
enabled on the deployment; ask the administrator.

### `400` on `POST /rpc/tag-entity`

`entityType` must be one of the values for your target
([SKILL.md](./SKILL.md#which-path-applies)), lowercase. `tagIds` must exist and belong to
namespaces that allow the assignment (see the multiple-assignment rule above).

### `400` on `POST /tags`

`namespaceId` must exist, `label` must be non-empty and at most `maxLabelLength`, and
`parentId` must be a tag in the same namespace within `maxDepth` levels.

### Namespace delete fails

`DELETE /namespaces/{id}` removes the namespace and its tags but is refused while any
of those tags is still assigned to an entity. Either untag the entities first (`DELETE /tags/{id}` or
`POST /tags/bulk-delete` do unassign; `DELETE /entity-tags` clears one entity) or set the
namespace to `status: deprecated` and leave it. Prefer deprecating over deleting on
shared deployments.
