# Bulk operations and merging

Routes for bulk lifecycle work on a taxonomy:

- `POST /tags/bulk-delete` and `POST /namespaces/bulk-delete`
- `POST /rpc/merge-tags`: collapse duplicate tags into one
- `POST /rpc/copy-entity-tags` and `POST /rpc/copy-property-values` exist but are
  internal (see the last section)

All assume `BASE` and `H` from [SKILL.md](./SKILL.md#configuration).

## Bulk delete

```bash
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"ids":["<tag-1>","<tag-2>","<tag-3>"]}' "$BASE/tags/bulk-delete"
# 200 -> {"deletedCount":3}

curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"ids":["<ns-1>","<ns-2>"]}' "$BASE/namespaces/bulk-delete"
# 200 -> {"deletedCount":2}
```

Both routes take `{"ids": [...]}` (`ids` required, at least one id) and return
`{"deletedCount": N}`. Deleting a tag removes its entity assignments. Deleting a
namespace removes its tags, but fails while any of those tags still has assignments
([API-TAGS.md](./API-TAGS.md#namespace-delete-fails)); expect the bulk route to apply
the same rule and untag (or bulk-delete the tags) first. There is no undo, so confirm with the user and
prefer `status: deprecated` on shared deployments.

## Merge tags

```bash
for dup in "<dup-1>" "<dup-2>"; do
  curl -s -X POST -H "$H" -H "Content-Type: application/json" \
    -d "{\"sourceTagIds\":[\"$dup\"],\"targetTagId\":\"<canonical>\"}" "$BASE/rpc/merge-tags"
done
# 200 -> {"targetTag":{"id","label"},"mergedCount":1,"reassignedEntities":17}
```

`sourceTagIds` and `targetTagId` are required. Every assignment on the source tags moves
to the target and the source tags are deleted; merging cannot be undone.
Merge **one source tag per call**: a single call with two source tags that sit on the same
entity returns `500 failed to merge tags`, while one source at a time succeeds (`reassignedEntities` is 0 when the entity
already carried the target).

## Copy routes (internal, service-account only)

`POST /rpc/copy-entity-tags` and `POST /rpc/copy-property-values` take
`{"entityType", "sourceEntityId", "targetEntityId"}` (all required, same type). The
spec marks them "Internal, service-account only"; they copy the source's assignments
**replacing the target's existing tags** (or values). Do not offer them as a
user workflow: with a user token both return
`403 insufficient permissions: requires service account`, and a
service-account call against an entity that already has tags or values wipes them. To give a new project the same
classification as an existing one, create it from a Project Template (tags and property
values carry over) or re-apply the tags with `POST /rpc/tag-entity`.

## Patterns

### Bulk-tag during onboarding

Drive `POST /rpc/tag-entity` from a CSV of `entityType,entityId,tagId` rows; there is no
batch tag-entity route.

```bash
while IFS=, read -r etype eid tag; do
  curl -s -X POST -H "$H" -H "Content-Type: application/json" \
    -d "{\"entityType\":\"$etype\",\"entityId\":\"$eid\",\"tagIds\":[\"$tag\"]}" \
    "$BASE/rpc/tag-entity" > /dev/null && echo "tagged $etype/$eid"
done < onboarding.csv
```

For thousands of rows, parallelize with `xargs -P` and refresh the token periodically.

### De-duplicate after free-form tagging

1. `GET $BASE/tags?namespaceId=<id>&limit=200` and group by normalized label.
2. Pick one canonical id per group.
3. `POST $BASE/rpc/merge-tags` per group. Log `mergedCount` and `reassignedEntities`.

### Retire a dimension

Deprecate the namespace (`PUT /namespaces/{id}` with `status: deprecated`) to stop new
assignments while keeping history. To remove it outright, delete its tags first
(`POST /tags/bulk-delete` unassigns them), then `DELETE /namespaces/{id}`; the namespace
delete is refused while assignments remain.
