# Import and export: taxonomy migration

Three routes move a tag structure between Domino deployments. The file format is CSV.

- `POST /rpc/export-to-file`: the current taxonomy as CSV (`format` query, default `csv`)
- `POST /rpc/validate-file`: dry-run an import file (multipart upload)
- `POST /rpc/import-from-file`: apply an import file (multipart upload)

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/knowledge-management/tags#import-and-export
(the Tag Browser UI imports the same file; a sample is linked there). All examples assume
`BASE` and `H` from [SKILL.md](./SKILL.md#configuration).

## CSV format

Each row defines one tag and the file has **no header row**:

```
namespace_label,namespace_description,tag_path,tag_description
```

| Column | Required | Meaning |
|--------|----------|---------|
| `namespace_label` | Yes | Namespace name; created if it does not exist |
| `namespace_description` | No | Namespace description |
| `tag_path` | Yes | Slash-separated hierarchy: `Oncology/Phase-1` creates `Phase-1` under `Oncology` |
| `tag_description` | No | Tag description |

Example file (four columns, no header):

```csv
Indication,Therapeutic area,Oncology,
Indication,Therapeutic area,Oncology/Breast_Cancer,Breast cancer subtype
Analysis,Type of analysis,Interim,Pre-planned interim analysis
Analysis,Type of analysis,Interim/Milestone_01,First interim milestone
```

Parents are inferred from `tag_path`; give a parent its own row when it needs a
description.

## Export

```bash
curl -s -X POST -H "$H" "$BASE/rpc/export-to-file?format=csv" > taxonomy-export.csv
```

The response is `text/csv` covering the whole taxonomy (namespaces and tags, not
entity assignments). Keep the export in version control so changes are reviewable.

## Validate before import

```bash
curl -s -X POST -H "$H" -F "file=@taxonomy-import.csv" "$BASE/rpc/validate-file"
# 200 -> {"valid": true}
```

Multipart form data with the field name `file` (`-F "file=@<path>"`). Validation checks
structure and limits (`maxLabelLength`, `maxDepth` from `GET /config`) without changing
anything. A file that fails validation (on `validate-file` or `import-from-file`) returns
`422 {"errors": [{"line": N, "message": "..."}]}`; a bad request, missing token or
missing permission returns 400/401/403 with `{"message": "..."}`. Because the file has no
header row, a stray header line would be imported as a namespace named
`namespace_label`: check the first line yourself when generating files.

## Import

```bash
curl -s -X POST -H "$H" -F "file=@taxonomy-import.csv" "$BASE/rpc/import-from-file"
# 200 -> {"namespacesCreated": 2, "tagsCreated": 7}
```

Existing namespaces and tags with matching labels are reused; the counts report net-new
rows. Import writes namespaces and tags only; entity assignments are untouched.

## Recipes

### Promote a dev taxonomy to prod

```bash
# dev
curl -s -X POST -H "$H_DEV" "$BASE_DEV/rpc/export-to-file" > taxonomy-dev.csv
grep -v '^sandbox-' taxonomy-dev.csv > taxonomy-prod.csv      # drop sandbox namespaces

# prod: validate, then import
curl -s -X POST -H "$H_PROD" -F "file=@taxonomy-prod.csv" "$BASE_PROD/rpc/validate-file"
curl -s -X POST -H "$H_PROD" -F "file=@taxonomy-prod.csv" "$BASE_PROD/rpc/import-from-file"
```

`BASE_DEV` / `BASE_PROD` are each deployment's `/api/taxonomy/v1`; `H_DEV` / `H_PROD`
carry a PAT or service account token for that deployment.

### Round-trip backup

```bash
curl -s -X POST -H "$H" "$BASE/rpc/export-to-file" > "taxonomy-backup-$(date +%Y%m%d).csv"
head -1 "taxonomy-backup-$(date +%Y%m%d).csv"   # if this is a header line, drop it before importing
# restore: idempotent for rows that already exist
curl -s -X POST -H "$H" -F "file=@taxonomy-backup-20260508.csv" "$BASE/rpc/import-from-file"
```

### Reviewable changes

1. Export to `taxonomy.csv` and commit it.
2. Edit the CSV in a pull request.
3. After review: `validate-file`, then `import-from-file` on the target deployment.

Import only adds. For renames, re-parenting, deprecation or deletion use `PUT` and
`DELETE` on `/tags` and `/namespaces` ([API-TAGS.md](./API-TAGS.md)).
