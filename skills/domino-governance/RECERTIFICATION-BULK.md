# Periodic recertification (bulk)

Risk officer lists all production bundles, re-evidences each against current policy, re-approves or flags an exception, archives retired bundles, writes an audit entry per bundle.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

## Core calls

```python
GET /bundles?projectId={project_id}&offset={offset}&limit={page_size}
# repeat until a page returns fewer than page_size rows

POST /rpc/submit-result-to-policy {"bundleId": bundle_id, "policyId": policy_id, **evidence}
POST /rpc/compute-policy {"bundleId": bundle_id, "policyId": policy_id}
# poll GET /results/latest?bundleID=bundle_id (API-GOVERNANCE.md "After compute-policy (polling)")
POST /rpc/publish-approval-event {**approval, "bundleId": bundle_id}

PATCH /bundles/{bundle_id} {"state": "Archived"}

POST /findings {
    "bundleId": bundle_id,
    "policyVersionId": policy_version_id,
    "name": "Waiver: ...",
    "description": justification,
    "severity": "Medium",
    "approver": {...},
    "assignee": {...},
    "dueDate": expiry_iso8601,
}
```

## Gotchas

- Bulk list must paginate (offset/limit); do not assume a single page.
- Recertify against current policy version, not the version at original approval.
- Exceptions use a finding with `dueDate`, not `expiresAt`.
- Run the periodic sweep as a Domino scheduled Job ([domino-jobs](../domino-jobs/SKILL.md)), not an external cron.
