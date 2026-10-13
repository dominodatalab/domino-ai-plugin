# Read governance context for downstream use

Agent or extension, given a modelId or bundleId, lists bundles, computes policy, waits for latest results, gets findings, and returns structured context for an LLM, dashboard, or report.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

## Core calls

```python
GET /bundles?projectId={project_id}&offset={offset}&limit={limit}

# Filter by bundle_id, or by registered_model_name on attachments:
#   a["type"] == "ModelVersion" and a["identifier"]["name"] == registered_model_name

# Per matching bundle:
POST /rpc/compute-policy {"bundleId": bundle_id, "policyId": policy_id}
GET /results/latest?bundleID={bundle_id}
# poll until artifacts you expose have isLatest=true (API-GOVERNANCE.md "After compute-policy (polling)")

GET /bundles/{bundle_id}/findings
```

## Gotchas

- Only `isLatest=true` results count as evidence; drafts are noise.
- Multi-bundle per model means return all matches, not first.
