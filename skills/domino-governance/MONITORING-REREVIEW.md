# Monitoring-driven re-review

Validator and approver handle a drift or monitor finding on an existing production bundle: bundle reopens, new evidence against current policy, re-approval, close finding, bundle back to approved.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

## Core calls

```python
POST /findings {**drift_finding, "bundleId": bundle_id}
# required: approver, assignee, bundleId, name, policyVersionId, severity

POST /rpc/submit-result-to-policy {"bundleId": bundle_id, "policyId": policy_id, **new_evidence}

POST /rpc/compute-policy {"bundleId": bundle_id, "policyId": policy_id}
# poll GET /results/latest?bundleID=bundle_id (API-GOVERNANCE.md "After compute-policy (polling)")

POST /rpc/publish-approval-event {**approval_event, "bundleId": bundle_id}

PUT /findings/{finding_id} {"status": "Done"}

GET /bundles/{bundle_id}/findings
# confirm no open findings (status not Done / WontDo)
```

## Gotchas

- Reopening a bundle does not detach old evidence.
- Policy may have been version-bumped; recompute against the version in effect at the new submission, not the original.
- Drift and quality signals come from Domino Model Monitoring ([domino-model-monitoring](../domino-model-monitoring/SKILL.md)), a separate service from governance: read the alert there, then open the finding here.
