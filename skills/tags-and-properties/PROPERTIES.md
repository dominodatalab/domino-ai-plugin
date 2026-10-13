# Property definitions

Properties are typed metadata fields on Domino entities: a `Budget` number, a
`Review Date`, an `Owner` user, a `Status` select. This file covers definitions (the
schema); values are in [PROPERTY-VALUES.md](./PROPERTY-VALUES.md). Docs:
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/knowledge-management/properties.

All examples assume `BASE` and `H` from [SKILL.md](./SKILL.md#configuration).

## Tags vs properties

| | Tag | Property |
|---|---|---|
| Shape | Label in a namespace, optionally nested | Typed field |
| Value per entity | Present or absent | One typed value (`42`, `2026-01-31`, `"Oncology"`) |
| Grouping | Namespace | `groupName` (free-form string) |
| Entity scope | Any taggable type | Declared per property in `allowedEntities` |
| Routes | `/tags`, `/namespaces`, `/rpc/tag-entity` | `/properties`, `/property-values` |

## Property types

`type` is set at creation and is not a field on `PUT`; to change it, create a new
property.

| Type | Value format |
|------|--------------|
| `text` | string |
| `number` | numeric string (`"42"`, `"3.14"`) |
| `date` | `YYYY-MM-DD` |
| `boolean` | `"true"` or `"false"` |
| `url` | http(s) URL |
| `user` | a Domino user id |
| `organization` | a Domino organization id |
| `user_or_org` | a user or organization id |
| `select` | one of `allowedValues` |
| `multi_select` | a subset of `allowedValues`, sent as `values[]` |

`select` and `multi_select` need a non-empty `allowedValues`; each item is
`{"value": "...", "subfield": "..."}` with `subfield` optional. Limits from `GET /config`:
`maxSelectAllowedValuesCount` options, each at most `maxSelectAllowedValueLength`.

## Allowed entities

`allowedEntities` (at least one) lists the entity types the property applies to. Values
are the target's entity-type list ([SKILL.md](./SKILL.md#which-path-applies)):
properties apply to Apps, Projects, Project Templates, Datasets, NetApp Volumes,
Models and Environments (plus Policies and Policy Versions on Cloud), with Apps, Models
and Policies also carrying independent per-version values (`app_version`,
`model_version`, `policy_version`). A Project Template's values are carried into new
projects according to the copy policy ([PROPERTY-VALUES.md](./PROPERTY-VALUES.md#copy-policy-templates)).

## Labels and groups

- `label` is required and unique; at most `maxLabelLength` characters.
- `groupName` is optional; ungrouped properties appear under `Miscellaneous` in the
  values view.

## Endpoints

| Endpoint | Method | Purpose | Who |
|----------|--------|---------|-----|
| `/properties` | POST | Create | Librarian or admin |
| `/properties` | GET | List (`entityType`, `search`, `sort`, `order`, `limit`, `offset`) | any user |
| `/properties/{propertyId}` | GET | Get one | any user |
| `/properties/{propertyId}` | PUT | Update | Librarian or admin |
| `/properties/{propertyId}` | DELETE | Delete | Librarian or admin |
| `/property-groups` | GET | Distinct group names | any user |

## Create

`label`, `type` and `allowedEntities` are required; `description`, `groupName` and
`allowedValues` are optional.

```bash
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Budget","groupName":"Finance","description":"Approved budget in USD","type":"number","allowedEntities":["project"]}' \
  "$BASE/properties"
# 201 -> {"id","label","description","type","groupName","allowedEntities","allowedValues","status":"active",...}

curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Review Status","type":"select","allowedEntities":["project","model"],
       "allowedValues":[{"value":"Draft"},{"value":"In Review"},{"value":"Approved"}]}' \
  "$BASE/properties"
```

## Get and list

```bash
curl -s -H "$H" "$BASE/properties/<id>"
curl -s -H "$H" "$BASE/properties?entityType=project&search=budget&sort=label&order=asc&limit=50&offset=0"
# {"data":[{"id","label","type","groupName","allowedEntities","allowedValues","status"}],
#  "meta":{"pagination":{"total","limit","offset"},"search","filters","sort"}}
```

## Update

`label` and `allowedEntities` are required; `description`, `groupName` and
`allowedValues` are optional; `type` cannot be sent.

```bash
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"label":"Budget (USD)","description":"Approved annual budget","groupName":"Finance","allowedEntities":["project","app"]}' \
  "$BASE/properties/<id>"
# 200 -> updated property
```

## Delete

```bash
curl -s -X DELETE -H "$H" "$BASE/properties/<id>"
# 204
```

Deletion is a soft delete: existing property values are retained but no longer
surfaced. The property's `status` becomes `deleted` (`GET /properties/{id}` still
returns it), it leaves lists and value views, and there is no undelete route, so treat
deletion as final in practice.

## Property groups

```bash
curl -s -H "$H" "$BASE/property-groups"
# {"groups":["Finance","Governance"]}
```

Only real group names are returned; `Miscellaneous` is synthetic.

## Troubleshooting

- **403 on create, update or delete**: the caller lacks the Librarian or admin role.
  Reading definitions and setting values do not need it.
- **400 invalid entity type**: every `allowedEntities` entry must be in the target's
  enum ([SKILL.md](./SKILL.md#which-path-applies)); `policy`, `policy_version` and
  `data_source` exist only on Cloud.
- **400 on `allowedValues`**: send it only for `select` and `multi_select`, and send at
  least one value for those.
- **409 on create**: labels are unique; update the existing property instead.
- **Wrong type**: `type` is immutable; create a new property and migrate values.

## Spec

Per-deployment service document: `https://<domino-domain>/docs/openapi/data_taxonomy_service-swagger.json`
([API-SPECS.md](../domino-api-intro/API-SPECS.md)).
