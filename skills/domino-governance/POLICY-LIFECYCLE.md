# Policy lifecycle and rollout

Policy admin drafts a policy, creates a version, PUTs the definition (escaped YAML), publishes, bulk-attaches to in-scope bundles, triggers re-evidence, retires the old version.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

Administrators usually author policies in the UI (Policy Builder or YAML); every step below is the public API equivalent.

## Core calls

```python
POST /policies {"name": policy_name, "description": "...", "labels": {}}
# labels is required on 6.3 (send {} if none); optional parentID nests the policy

GET /policies/{policy_id}
# full structure: stages[].approvals, stages[].evidenceSet, status (Draft | Published | Archived)

POST /policies/{policy_id}/versions {"definitionYAML": definition_yaml_string}
# body optional; 409 if a draft version already exists; treat as idempotent

PUT /policies/{policy_id}/definition {"definition": definition_yaml_string}

PUT /policies/{policy_id}/status {"status": "Published"}
# Draft | Published | Archived

POST /rpc/publish-policy-version {
    "policyId": policy_id,
    "upgradeStrategy": {"approvals": {"strategy": "retain"}},   # retain | reset existing approvals
    "bundleIds": [bundle_id],      # optional: bundles to move to the new version
    "version": "...", "notes": "...",
}

POST /rpc/add-policies-to-bundle {"bundleId": bundle_id, "policyIds": [policy_id]}
```

## Gotchas

- PUT definition takes an escaped YAML string.
- Publishing a version does not auto-attach to existing bundles; bulk attach is a separate RPC (`add-policies-to-bundle`), and `publish-policy-version` upgrades the bundles it names with the chosen approval strategy.
- Retiring a version does not detach from bundles already on it.
- Composition: lifecycle + regulation + cross-cutting policies all apply simultaneously on one bundle.
