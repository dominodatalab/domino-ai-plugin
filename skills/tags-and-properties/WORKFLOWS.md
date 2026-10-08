# Taxonomy workflows

Worked end-to-end examples by persona (building a hierarchy, discovering entities by tag, autocomplete, defining a property, setting property values) plus taxonomy design best practices. Workflow 1 (tag a project) is the quick start in [SKILL.md](./SKILL.md).

All examples assume the configuration block from [SKILL.md](./SKILL.md#configuration):

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
BASE="$DOMINO_API_HOST/api/taxonomy/v1"
H="Authorization: Bearer $TOKEN"
```

### Workflow 2 — Build a hierarchical taxonomy (governance admin)

```bash
# Create a namespace
NS=$(curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Analysis","description":"Type of analysis","allowMultipleAssignments":false}' \
  "$BASE/namespaces" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Create a parent tag
PARENT=$(curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"label\":\"Interim\",\"namespaceId\":\"$NS\"}" \
  "$BASE/tags" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Create a child tag under it
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"label\":\"Milestone_01\",\"namespaceId\":\"$NS\",\"parentId\":\"$PARENT\"}" \
  "$BASE/tags"
```

Tag depth is capped at `maxDepth` from `GET /config` (5 on most deployments).

### Workflow 3 — Find all entities with a tag (discovery)

```bash
# Single tag
curl -s -H "$H" "$BASE/tags/<tag-id>/entities" | python3 -m json.tool

# Multiple tags (intersection) — tagIds is a REPEATED query parameter, not comma-separated
curl -s -H "$H" "$BASE/entities?tagIds=<tag-id-1>&tagIds=<tag-id-2>&entityType=project"
```

Both endpoints return paginated results with `meta.pagination.{total,limit,offset}`.
Paginate with `?limit=50&offset=50`.

> **Heads-up:** `tagIds` on `/entities` must be repeated per value
> (`?tagIds=A&tagIds=B`). Comma-separating returns
> `400 {"message":"invalid tag ID: A,B"}`. By contrast, `entityIds` on
> `/entity-tags` *is* comma-separated. Yes, the convention is inconsistent.

### Workflow 4 — Autocomplete in a tagging UI (discovery)

```bash
curl -s -H "$H" "$BASE/tags/autocomplete?q=clin"
```

Response:

```json
{"items":[
  {"id":"23ca6d78-...","path":"Clinical_Data"},
  {"id":"0b55bf67-...","path":"Clinical_Data / SDTM"},
  {"id":"57454f72-...","path":"Clinical_Data / ADaM"}
]}
```

`path` shows the full hierarchy with ` / ` between levels — surface it
verbatim in the UI to disambiguate same-named tags in different branches.

### Workflow 5 — Define a property (governance admin)

```bash
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{
        "label":"Review Status",
        "groupName":"Governance",
        "type":"select",
        "allowedEntities":["project","model"],
        "allowedValues":[{"value":"Draft"},{"value":"In Review"},{"value":"Approved"}]
      }' \
  "$BASE/properties"
# 201 → full Property with id, status, timestamps
```

`type` is immutable after creation. `select`/`multi_select` require
`allowedValues`; other types reject it. `project_template` is not allowed in
`allowedEntities` — use `project` and it applies to templates too. See
[PROPERTIES.md](./PROPERTIES.md).

### Workflow 6 — Set property values on an entity (data scientist)

```bash
# See which properties apply and their current values
curl -s -H "$H" "$BASE/property-values/project/$DOMINO_PROJECT_ID" | python3 -m json.tool

# Set several at once (best-effort batch: per-item failures don't abort)
curl -s -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"items":[
        {"propertyId":"<budget-id>","value":"50000"},
        {"propertyId":"<review-status-id>","value":"Approved"}
      ]}' \
  "$BASE/property-values/project/$DOMINO_PROJECT_ID"
```

`multi_select` properties take a `values[]` array; all other types use `value`.
An empty `value` clears the property. Versioned entities (`model_version`,
`app_version`) require a `?version=` query param. See
[PROPERTY-VALUES.md](./PROPERTY-VALUES.md).

## Best Practices

- **One namespace per dimension.** Don't pile orthogonal concepts (e.g.
  Indication and Analysis Type) into one namespace; separate so users can
  filter cleanly.
- **Use `allowMultipleAssignments=false`** for mutually exclusive concepts
  (e.g. "Phase" — a project is in exactly one phase). Use `true` when an
  entity can plausibly carry several values from the same namespace
  (e.g. multiple "Indication" tags).
- **Hierarchy via `parentId`** rather than encoding hierarchy into labels
  (e.g. `Clinical_Data/SDTM`). This lets autocomplete and tree views render
  the structure for you.
- **Query `GET /config` once** at app startup and cache `maxLabelLength` /
  `maxDepth` for client-side validation.
- **Pin tag IDs, not labels.** Tag labels can be renamed via `PUT /tags/{id}`;
  IDs are stable. Workflows that automate tagging should reference tag IDs.
- **Discoverability**: use `GET /taxonomy` for full-tree views,
  `GET /tags/autocomplete?q=...` for typeaheads, and
  `GET /entities?tagIds=A&tagIds=B&entityType=...` (one `tagIds` per value,
  not comma-separated) for filtered lists.
