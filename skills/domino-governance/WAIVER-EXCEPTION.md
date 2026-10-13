# Exception or waiver

Submitter and approver request a deviation on a bundle, document justification, get approver sign-off, track expiry via finding due date, write an audit entry, bundle proceeds despite missing evidence.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

## Core calls

```python
POST /findings {
    "bundleId": bundle_id,
    "policyVersionId": policy_version_id,
    "name": "Waiver: <short title>",
    "description": justification,
    "severity": "Medium",
    "approver": {...},
    "assignee": {...},
    "dueDate": expiry_iso8601,
}
```

## Gotchas

- Waiver is modeled as a finding with `dueDate` for expiry, not a separate API or `expiresAt` field.
- Create requires approver, assignee, bundleId, name, policyVersionId, severity.
- Expiring waivers need a re-review trigger: a Domino scheduled Job ([domino-jobs](../domino-jobs/SKILL.md)) that reads `GET /bundles/{bundle_id}/findings` and flags waivers past `dueDate`, not an external cron.
