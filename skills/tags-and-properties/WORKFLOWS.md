# Taxonomy workflows

Worked examples by persona plus design practices. Workflow 1 (tag a project) is the quick
start in [SKILL.md](./SKILL.md#quick-start-tag-a-project). All examples assume `BASE`
and `H` from [SKILL.md](./SKILL.md#configuration).

## Workflow 2: build a hierarchical taxonomy (Librarian or admin)

```bash
NS=$(curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Analysis","allowMultipleAssignments":false}' "$BASE/namespaces" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

PARENT=$(curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"label\":\"Interim\",\"namespaceId\":\"$NS\"}" "$BASE/tags" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"label\":\"Milestone_01\",\"namespaceId\":\"$NS\",\"parentId\":\"$PARENT\"}" "$BASE/tags"
```

Nesting depth is capped at `maxDepth` from `GET /config`.

## Workflow 3: find entities by tag (discovery)

```bash
curl -s -H "$H" "$BASE/tags/<tag-id>/entities?entityTypes=project"
curl -s -H "$H" "$BASE/entities?tagIds=<tag-1>&tagIds=<tag-2>&entityTypes=project&includeDescendants=true"
```

Both return `{"data": [...], "meta": {"pagination": {"total", "limit", "offset"}}}`;
page with `limit` and `offset`. `tagIds` and `entityTypes` are repeated parameters.

## Workflow 4: autocomplete in a tagging UI

```bash
curl -s -H "$H" "$BASE/tags/autocomplete?q=clin&limit=10"
# {"items":[{"id":"...","path":"Clinical_Data"},{"id":"...","path":"Clinical_Data / SDTM"}]}
```

`q` is required; `namespaceId` narrows to one namespace. Show `path` verbatim to
disambiguate same-named tags in different branches.

## Workflow 5: define a property (Librarian or admin)

```bash
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Review Status","groupName":"Governance","type":"select",
       "allowedEntities":["project","model"],
       "allowedValues":[{"value":"Draft"},{"value":"In Review"},{"value":"Approved"}]}' \
  "$BASE/properties"
```

Details and limits: [PROPERTIES.md](./PROPERTIES.md).

## Workflow 6: set property values (data scientist)

```bash
curl -s -H "$H" "$BASE/property-values/project/$DOMINO_PROJECT_ID"
curl -s -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"items":[{"propertyId":"<budget-id>","value":"50000"},{"propertyId":"<review-status-id>","value":"Approved"}]}' \
  "$BASE/property-values/project/$DOMINO_PROJECT_ID"
```

Details, versioned entities and copy policies: [PROPERTY-VALUES.md](./PROPERTY-VALUES.md).

## Workflow 7: give a new project the same classification

Create the project from a Project Template: a project created from a template inherits
the template's tags, and its property values according to the `copyPolicy` chosen per
property ([PROPERTY-VALUES.md](./PROPERTY-VALUES.md#copy-policy-templates)). For an
existing project, read the source's tags with `GET /entity-tags` and apply them with
`POST /rpc/tag-entity`:

```bash
TAGS=$(curl -s -H "$H" "$BASE/entity-tags?entityType=project&entityIds=<source-id>" \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print(json.dumps([t['id'] for t in next(iter(d.values()))]))")
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"entityType\":\"project\",\"entityId\":\"<new-id>\",\"tagIds\":$TAGS}" "$BASE/rpc/tag-entity"
```

`POST /rpc/copy-entity-tags` is not a user route:
[BULK-OPS.md](./BULK-OPS.md#copy-routes-internal-service-account-only).

## Design practices

- **One namespace per dimension.** Keep orthogonal concepts (Indication, Analysis type)
  in separate namespaces so filters stay clean.
- **`allowMultipleAssignments: false`** for mutually exclusive concepts (Phase);
  `true` where an entity can carry several values (Indication).
- **Hierarchy via `parentId`**, not slashes in labels; autocomplete and the tree view
  render it.
- **Deprecate instead of delete** when a tag is still on entities.
- **Read `GET /config` once** and validate labels and depth client-side.
- **Pin tag ids, not labels**: labels can be renamed with `PUT /tags/{id}`.
- **Discovery routes**: `GET /taxonomy` for the tree, `GET /tags/autocomplete?q=` for
  typeahead, `GET /entities?tagIds=...` for filtered lists.
