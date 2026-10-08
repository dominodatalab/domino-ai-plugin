# Tags API reference

Endpoint-by-endpoint reference for the tag side of the Domino Taxonomy API: key concepts, the full endpoint table, curl examples for namespaces, tags, entity tags, the taxonomy tree and config limits, and troubleshooting for those calls. Property endpoints are in [PROPERTIES.md](./PROPERTIES.md) and [PROPERTY-VALUES.md](./PROPERTY-VALUES.md).

All examples assume the configuration block from [SKILL.md](./SKILL.md#configuration):

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
BASE="$DOMINO_API_HOST/api/taxonomy/v1"
H="Authorization: Bearer $TOKEN"
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Namespace** | Top-level group for **tags** (e.g. `Indication`, `Analysis`). Has `label`, optional `description`, and `allowMultipleAssignments` flag. |
| **Tag** | A label inside a namespace. Can be hierarchical via `parentId` (e.g. `Clinical_Data / SDTM`). Has `label`, `namespaceId`, optional `description` and `parentId`, and `status` (`active` / `inactive`). |
| **Property** | A typed metadata *field* — has a `label`, a `type` (`text`, `number`, `date`, `boolean`, `url`, `user`, `organization`, `user_or_org`, `select`, `multi_select`), a set of `allowedEntities`, an optional `groupName`, and (for select types) `allowedValues`. See [PROPERTIES.md](./PROPERTIES.md). |
| **Property value** | The typed value a property holds for one specific entity, set via `PATCH /property-values`. See [PROPERTY-VALUES.md](./PROPERTY-VALUES.md). |
| **Property group** | Free-form `groupName` string that buckets properties in the values view; ungrouped properties fall under `Miscellaneous`. |
| **EntityType** | Enum over entities. Tags apply to `dataset`, `project`, `project_template`, `model`, `app`, `netapp_volume`. Properties additionally support the *versioned* types `model_version` and `app_version`. |
| **`allowMultipleAssignments`** | (Tags) When `true`, an entity can hold multiple tags from the same namespace. When `false`, applying a new tag from the namespace replaces any existing one. |
| **Taxonomy tree** | The full nested view: namespaces → root tags → child tags. Returned by `GET /taxonomy`. |
| **Limits** | `GET /config` returns `maxDepth` (max tag nesting), `maxLabelLength` (max characters per label), `maxSelectAllowedValuesCount` (max options on a select property), and `maxSelectAllowedValueLength` (max length of one option). |

## Taxonomy API Reference

All endpoints are under `$BASE` (`/api/taxonomy/v1`). Authenticate every
request with `Authorization: Bearer $TOKEN`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/config` | GET | Get configuration limits |
| `/taxonomy` | GET | Get full taxonomy tree (nested namespaces + tags) |
| `/namespaces` | GET / POST | List / create namespaces |
| `/namespaces/{namespaceId}` | GET / PUT / DELETE | Get / update / delete a namespace |
| `/namespaces/bulk-delete` | POST | Bulk delete namespaces — see [BULK-OPS.md](./BULK-OPS.md) |
| `/tags` | GET / POST | List / create tags |
| `/tags/{tagId}` | GET / PUT / DELETE | Get / update / delete a tag |
| `/tags/{tagId}/entities` | GET | List entities tagged with a tag |
| `/tags/autocomplete` | GET | Autocomplete tag suggestions for a query |
| `/tags/bulk-delete` | POST | Bulk delete tags — see [BULK-OPS.md](./BULK-OPS.md) |
| `/rpc/merge-tags` | POST | Merge tags — see [BULK-OPS.md](./BULK-OPS.md) |
| `/entities` | GET | Get entities by one or more tag IDs |
| `/entity-tags` | GET / DELETE | Get tags for entities / delete all tags for an entity |
| `/rpc/tag-entity` | POST | Tag an entity |
| `/rpc/untag-entity` | POST | Remove specific tags from an entity |
| `/rpc/export-to-file` | POST | Export taxonomy as CSV — see [IMPORT-EXPORT.md](./IMPORT-EXPORT.md) |
| `/rpc/import-from-file` | POST | Import taxonomy from CSV — see [IMPORT-EXPORT.md](./IMPORT-EXPORT.md) |
| `/rpc/validate-file` | POST | Validate a CSV before import — see [IMPORT-EXPORT.md](./IMPORT-EXPORT.md) |
| `/properties` | GET / POST | List / create property definitions — see [PROPERTIES.md](./PROPERTIES.md) |
| `/properties/{propertyId}` | GET / PUT / DELETE | Get / update / soft-delete a property — see [PROPERTIES.md](./PROPERTIES.md) |
| `/property-groups` | GET | List distinct property group names — see [PROPERTIES.md](./PROPERTIES.md) |
| `/property-values/{entityType}/{entityId}` | GET / PATCH / DELETE | Get / set-clear / delete-all property values for an entity — see [PROPERTY-VALUES.md](./PROPERTY-VALUES.md) |

## Namespaces

```bash
# List
curl -s -H "$H" "$BASE/namespaces?limit=50&offset=0"

# Create (label required)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Indication","description":"Therapeutic area","allowMultipleAssignments":true}' \
  "$BASE/namespaces"
# 201 → returns full Namespace including id, status, timestamps

# Get one
curl -s -H "$H" "$BASE/namespaces/<id>"

# Update (label and status both required)
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Indication","description":"updated","status":"active","allowMultipleAssignments":true}' \
  "$BASE/namespaces/<id>"

# Delete — cascades through the namespace's tags and entity-tag bindings.
# Returns 204 even on a non-empty namespace. There is no "are you sure" prompt.
# Reach for `namespaces/bulk-delete` when removing several at once.
curl -s -X DELETE -H "$H" "$BASE/namespaces/<id>"
# 204 No Content
```

## Tags

```bash
# List with optional filters
curl -s -H "$H" "$BASE/tags?namespaceId=<ns>&limit=50"

# Create (label and namespaceId required, parentId optional for hierarchy)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"SDTM","namespaceId":"<ns>","description":"Study Data Tabulation Model","parentId":"<parent-tag>"}' \
  "$BASE/tags"

# Get one — includes entityCount broken down by EntityType
curl -s -H "$H" "$BASE/tags/<id>"

# Update (label required; you can change parentId to re-parent within the same namespace)
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"SDTMv2","description":"new desc","status":"active","parentId":"<new-parent>"}' \
  "$BASE/tags/<id>"

# Delete (single)
curl -s -X DELETE -H "$H" "$BASE/tags/<id>"
# 204 No Content
```

## Entity Tags

```bash
# Tag an entity (entityType, entityId, tagIds[] all required)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"entityType":"project","entityId":"<project-id>","tagIds":["<tag-1>","<tag-2>"]}' \
  "$BASE/rpc/tag-entity"
# 201 → {"entityId":"...","entityType":"project","entityName":"...","tags":[...]}
#
# Constraint: if `tagIds` contains more than one tag from the SAME namespace,
# that namespace must have `allowMultipleAssignments=true`. Otherwise:
# 400 → {"message":"namespace does not allow multiple tag assignments per entity"}
# To replace a tag in a single-assign namespace, send a separate request — the
# new tag overwrites the prior one for that namespace.

# Remove specific tags from an entity
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"entityType":"project","entityId":"<project-id>","tagIds":["<tag-1>"]}' \
  "$BASE/rpc/untag-entity"
# 200 → {"entityId":"...","entityType":"project","entityName":"...","removedTagIds":[...]}

# Get tags for one or more entities (entityIds is comma-separated)
curl -s -H "$H" "$BASE/entity-tags?entityType=project&entityIds=<id-1>,<id-2>"
# 200 → {"data":{"<id-1>":[Tag,...], "<id-2>":[Tag,...]}}

# Remove ALL tags from an entity
curl -s -X DELETE -H "$H" "$BASE/entity-tags?entityType=project&entityId=<id>"
# 200 → {"removedCount":N}
```

`entityType` must be one of: `dataset`, `project`, `project_template`,
`model`, `app`, `netapp_volume`. Other values return 400.

## Taxonomy Tree

```bash
curl -s -H "$H" "$BASE/taxonomy" | python3 -m json.tool
```

Returns an array of `TreeNamespace` objects, each with nested `tags` of type
`TreeTag`:

```json
[{
  "id":"821e1455-...",
  "label":"Indication",
  "description":"Therapeutic area",
  "status":"active",
  "allowMultipleAssignments":false,
  "tags":[
    {"id":"...", "label":"Oncology", "status":"active", "children":[
      {"id":"...", "label":"Breast_Cancer", "status":"active", "children":[]}
    ]}
  ]
}]
```

Use this to render the full taxonomy in a UI in one call.

## Config

```bash
curl -s -H "$H" "$BASE/config"
# {"maxDepth":5,"maxLabelLength":128,"maxSelectAllowedValuesCount":100,"maxSelectAllowedValueLength":2048}
```

| Field | Applies to |
|-------|-----------|
| `maxDepth` | Max tag nesting depth |
| `maxLabelLength` | Max characters for a namespace/tag/property label (and property group name) |
| `maxSelectAllowedValuesCount` | Max options on a `select`/`multi_select` property |
| `maxSelectAllowedValueLength` | Max length of a single select option |

Surface these limits in any UI that lets users create tags, namespaces, or
properties so the user gets immediate validation feedback.

## Troubleshooting

### `Public api endpoint not found` (404)

The taxonomy service is not registered on the gateway you are calling. Two
common causes:

1. **Wrong base URL.** Taxonomy is served through the Domino API host gateway.
   Ensure `BASE` is set to `$DOMINO_API_HOST/api/taxonomy/v1` and that
   `$DOMINO_API_HOST` is populated (it is set automatically in Domino
   workspaces, jobs, and apps).
2. **Taxonomy not enabled on this deployment.** Older or stripped-down
   deployments may not include the taxonomy microservice. Confirm with
   your Domino administrator before working around this.

### `400 Bad Request` on `POST /rpc/tag-entity`

Ensure `entityType` is exactly one of:
`dataset | project | project_template | model | app | netapp_volume`.
Casing matters — `Project` and `PROJECT` will be rejected.

### `400` on `POST /tags`

`namespaceId` must reference an existing namespace, and the `label` must be
non-empty and ≤ `maxLabelLength` (from `/config`). If you intend to nest the
tag, `parentId` must reference a tag in the same namespace.

### Deleting a namespace removes its tags too

`DELETE /namespaces/{id}` is a cascading delete: it removes the namespace,
every tag inside it, and every entity-tag binding pointing at those tags.
There is no "namespace must be empty" check — confirm with the user before
calling it against a shared cluster. `namespaces/bulk-delete` has the same
cascade behavior across multiple IDs.
