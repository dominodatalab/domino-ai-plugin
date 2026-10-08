---
name: tags-and-properties
description: Manage Domino tags and properties via the Taxonomy API. Covers tags/namespaces (create, list, update, delete; tag entities — project, model, dataset, app, project_template, netapp_volume; query by tag; autocomplete; merge; CSV import/export) AND properties (typed metadata fields — text, number, date, boolean, url, user, organization, select, multi_select — with per-entity values, groups, and versioned entities like model_version/app_version). Use when organizing entities with tags, building hierarchical namespaces, defining typed metadata fields, setting property values on projects/models/apps, finding entities by tag, bulk-tagging during onboarding, or migrating taxonomy across environments.
---

# Domino Tags and Properties Skill

## Description

This skill covers Domino's Taxonomy API, which manages two complementary
metadata systems for organizing entities (projects, models, datasets, apps,
project templates, NetApp volumes):

- **Tags** — hierarchical labels grouped into namespaces. An entity either has
  a tag or it doesn't.
- **Properties** — typed metadata *fields* (`text`, `number`, `date`,
  `select`, …), each holding a value per entity.

It documents every public endpoint with curl examples that work today against
a Domino cluster where the taxonomy service is enabled. Properties are covered
in depth in [PROPERTIES.md](./PROPERTIES.md) (definitions) and
[PROPERTY-VALUES.md](./PROPERTY-VALUES.md) (per-entity values).

## Activation

Activate this skill when the user wants to:

- Tag a project, model, dataset, app, project template, or NetApp volume
- Find all entities that share a tag, or query by multiple tags
- Build a hierarchical taxonomy (namespaces with nested tags)
- Bulk-tag entities during onboarding
- Migrate a taxonomy tree across Domino environments (CSV export/import)
- Merge duplicate tags
- Tune autocomplete results in a tagging UI
- Define typed metadata fields (properties) — e.g. a `Budget` number, a
  `Review Date`, an `Owner` user, or a `Status` single-select
- Set, read, or clear property values on an entity (incl. versioned entities
  like `model_version` / `app_version`)
- Group properties or manage property definitions across a deployment

## Configuration

Auth via the local access-token endpoint. Never use `DOMINO_USER_API_KEY`.

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
# Taxonomy is served through the Domino API host gateway.
BASE="$DOMINO_API_HOST/api/taxonomy/v1"
H="Authorization: Bearer $TOKEN"
```

## Key Concepts

Namespaces group tags; tags nest via `parentId`; properties hold one typed
value per entity; `GET /config` returns the limits. Concept table and full
endpoint reference: [API-TAGS.md](./API-TAGS.md).

## Common Workflows

### Workflow 1 — Tag a project (data scientist)

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
BASE="$DOMINO_API_HOST/api/taxonomy/v1"
H="Authorization: Bearer $TOKEN"

# 1. Discover the tag you want to apply
curl -s -H "$H" "$BASE/tags/autocomplete?q=clinical" | python3 -m json.tool

# 2. Apply it to your project
curl -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"entityType\":\"project\",\"entityId\":\"$DOMINO_PROJECT_ID\",\"tagIds\":[\"<tag-id>\"]}" \
  "$BASE/rpc/tag-entity"

# 3. Verify
curl -s -H "$H" "$BASE/entity-tags?entityType=project&entityIds=$DOMINO_PROJECT_ID"
```

Workflows 2–6 (hierarchy, discovery, autocomplete, properties):
[WORKFLOWS.md](./WORKFLOWS.md).

## Rules and gotchas

`entityType` must be one of: `dataset`, `project`, `project_template`,
`model`, `app`, `netapp_volume`. Other values return 400.

> **Heads-up:** `tagIds` on `/entities` must be repeated per value
> (`?tagIds=A&tagIds=B`). Comma-separating returns
> `400 {"message":"invalid tag ID: A,B"}`. By contrast, `entityIds` on
> `/entity-tags` *is* comma-separated. Yes, the convention is inconsistent.

`DELETE /namespaces/{id}` and `namespaces/bulk-delete` cascade through every
tag and entity-tag binding with no confirmation — confirm with the user first.
Pin tag IDs, not labels, in automation.

## Properties

Properties are typed metadata *fields* — a complement to tags. Where a tag is
present-or-absent, a property holds a typed value per entity (`Budget = 50000`,
`Review Date = 2026-01-31`, `Status = "Approved"`).

Two layers:

1. **Definitions** — the field schema (`label`, `type`, `allowedEntities`,
   optional `groupName` and `allowedValues`). Managed under `/properties`;
   create/update/delete requires the Librarian or Admin role. Full reference:
   [PROPERTIES.md](./PROPERTIES.md).
2. **Values** — the value a property holds for a specific entity. Managed under
   `/property-values/{entityType}/{entityId}`; permissions are per-entity, not
   role-based. Full reference: [PROPERTY-VALUES.md](./PROPERTY-VALUES.md).

`type` is immutable after creation. `select`/`multi_select` require
`allowedValues`; other types reject it. `project_template` is not allowed in
`allowedEntities` — use `project` and it applies to templates too. See
[PROPERTIES.md](./PROPERTIES.md).

`multi_select` properties take a `values[]` array; all other types use `value`.
An empty `value` clears the property. Versioned entities (`model_version`,
`app_version`) require a `?version=` query param. See
[PROPERTY-VALUES.md](./PROPERTY-VALUES.md).

## Bulk Operations and Tag Merging

See [BULK-OPS.md](./BULK-OPS.md) for `tags/bulk-delete`,
`namespaces/bulk-delete`, and `rpc/merge-tags`.

## Import / Export

See [IMPORT-EXPORT.md](./IMPORT-EXPORT.md) for `rpc/export-to-file`,
`rpc/import-from-file`, and `rpc/validate-file` — useful for migrating a
taxonomy across Domino environments.

## Reference files

- [API-TAGS.md](./API-TAGS.md) — concept table, endpoint table, curl reference for namespaces/tags/entity-tags/tree/config, troubleshooting
- [WORKFLOWS.md](./WORKFLOWS.md) — Workflows 2–6 and best practices
- [PROPERTIES.md](./PROPERTIES.md) — property definitions (typed metadata fields)
- [PROPERTY-VALUES.md](./PROPERTY-VALUES.md) — setting property values on entities
- [BULK-OPS.md](./BULK-OPS.md) — bulk-delete + merge-tags + migration patterns
- [IMPORT-EXPORT.md](./IMPORT-EXPORT.md) — CSV export/import for taxonomy migration

## Documentation Reference

Before writing or verifying any API call, use the cluster swagger to confirm current endpoint paths and field names. Use public docs for workflow context and field explanations.

**Taxonomy API base:** `$DOMINO_API_HOST/api/taxonomy/v1` (served through the
Domino API host gateway; `$DOMINO_API_HOST` is populated automatically in
workspaces, jobs, and apps).

Fetch the taxonomy swagger spec (requires bearer token):
```bash
TOKEN=$(curl -s http://localhost:8899/access-token)

curl -H "Authorization: Bearer $TOKEN" "$DOMINO_API_HOST/api/taxonomy/swagger/doc.json"

# Browser UI — use the external cluster URL (must be logged in):
# https://<your-cluster>/api/taxonomy/swagger/index.html
```

**Public docs (workflow context and field explanations):**
- [Taxonomy API guide](https://docs.dominodatalab.com/en/cloud/api_guide/fc6b7c/taxonomy-api/)
