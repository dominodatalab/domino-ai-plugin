# Property values

Assign, read, clear and delete the values that defined properties
([PROPERTIES.md](./PROPERTIES.md)) hold on a specific entity, addressed by `entityType`
and `entityId`.

All examples assume `BASE` and `H` from [SKILL.md](./SKILL.md#configuration).

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/property-values/{entityType}/{entityId}` | GET | All property values for an entity |
| `/property-values/{entityType}/{entityId}` | PATCH | Set or clear values in a batch |
| `/property-values/{entityType}/{entityId}` | DELETE | Remove every stored value |

`entityType` is one of the target's entity types ([SKILL.md](./SKILL.md#which-path-applies)).
All three take a `version` query parameter: required for `app_version`, omitted for all
other types (`model_version` is referenced by its version UUID).

## Versioned entities

Apps and Models (and Policies on Cloud) carry values globally and independently per
version:

```bash
# App version: the app id plus ?version=<n>
curl -s -H "$H" "$BASE/property-values/app_version/<app-id>?version=5"

# Model version: the model-version UUID as the entity id, no version parameter
curl -s -H "$H" "$BASE/property-values/model_version/<model-version-uuid>"
```

## Get values

Returns the properties permitted for the entity type grouped by `groupName` (ungrouped
under `Miscellaneous`), including unset ones, so a UI can render the full form from one
call.

```bash
curl -s -H "$H" "$BASE/property-values/project/<project-id>"
```

```json
{
  "entityId": "<project-id>",
  "entityType": "project",
  "groups": [
    {"groupName": "Finance",
     "fields": [
       {"propertyId": "...", "propertyLabel": "Budget", "type": "number", "status": "active", "value": "50000"},
       {"propertyId": "...", "propertyLabel": "Review Status", "type": "select", "status": "active",
        "allowedValues": [{"value": "Draft"}, {"value": "Approved"}]}
     ]}
  ]
}
```

`multi_select` fields return `values[]`; every other type returns `value`.

## Set or clear values (PATCH)

Body: `{"items": [...]}`; each item needs `propertyId` plus `value` (scalar types),
`values` (`multi_select`) or an empty `value` to clear. Optional `copyPolicy` applies to
templates only (below). The response reports per-item outcomes.

```bash
curl -s -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"items":[
        {"propertyId":"<budget-id>","value":"50000"},
        {"propertyId":"<review-status-id>","value":"Approved"},
        {"propertyId":"<areas-id>","values":["Oncology","Cardiology"]},
        {"propertyId":"<owner-id>","value":""}
      ]}' \
  "$BASE/property-values/project/<project-id>"
```

```json
{
  "entityId": "<project-id>", "entityType": "project",
  "applied": [{"propertyId": "<budget-id>", "action": "set"}, {"propertyId": "<owner-id>", "action": "cleared"}],
  "errors":  [{"propertyId": "<areas-id>", "error": "value is not one of the allowed values"}]
}
```

Rules:

- Values are validated against the property's type and, for select types, against
  `allowedValues`. A bad item lands in `errors[]` (`propertyId`, `error`) and does not
  abort the batch.
- `value` and `values` are mutually exclusive per item: `values[]` for `multi_select`,
  `value` for everything else.
- Clearing: an item with an empty `value` removes a stored value. `applied[].action` is
  `set`, `cleared` or `noop` (nothing was stored).

## Copy policy (templates)

On `project_template` entities an item may carry `copyPolicy`, which decides what a
project created from the template starts with
(https://docs.domino.ai/cloud/platform-capabilities/core-concepts/knowledge-management/properties#carry-property-values-into-new-projects):

| `copyPolicy` | Behavior on instantiation |
|--------------|---------------------------|
| `copy` | The template's value is copied into the new project |
| `emptyRequired` | Starts empty; the user must supply a value before the project can be created |
| `emptyOptional` | Starts empty; optional |

```bash
curl -s -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"items":[{"propertyId":"<budget-id>","value":"0","copyPolicy":"emptyRequired"}]}' \
  "$BASE/property-values/project_template/<template-id>"
```

Values on a template's Datasets, NetApp Volumes and Apps carry over to the corresponding
assets in the new project. To copy values between two existing entities, `GET` the
source and `PATCH` the target; `POST /rpc/copy-property-values` is not a user route
([BULK-OPS.md](./BULK-OPS.md#copy-routes-internal-service-account-only)).

## Delete all values

```bash
curl -s -X DELETE -H "$H" "$BASE/property-values/project/<project-id>"
# {"removedCount": 4}
curl -s -X DELETE -H "$H" "$BASE/property-values/app_version/<app-id>?version=5"
```

Definitions are untouched.

## Permissions

Setting values needs edit rights on the specific asset (its owner, or an admin). Reading
needs view access. A `403` on a write means you cannot edit that project, model, app,
dataset or volume; it is unrelated to the Librarian role needed for definitions.

## Common workflows

### Fill in a project's properties

```bash
curl -s -H "$H" "$BASE/property-values/project/$DOMINO_PROJECT_ID"
curl -s -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"items":[{"propertyId":"<budget-id>","value":"75000"},{"propertyId":"<review-status-id>","value":"In Review"}]}' \
  "$BASE/property-values/project/$DOMINO_PROJECT_ID"
```

### Set one property across many entities

There is no batch-across-entities route; loop per entity.

```bash
while IFS=, read -r eid val; do
  curl -s -X PATCH -H "$H" -H "Content-Type: application/json" \
    -d "{\"items\":[{\"propertyId\":\"<prop-id>\",\"value\":\"$val\"}]}" \
    "$BASE/property-values/project/$eid" > /dev/null && echo "set $eid=$val"
done < values.csv
```

Refresh `H` periodically on long runs; access tokens expire.
