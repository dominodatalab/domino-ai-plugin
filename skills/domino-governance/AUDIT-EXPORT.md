# Regulatory audit export

Auditor exports one bundle: full attachment list and content, all evidence submissions and results history, all findings and comments and resolutions, all approval events, policy versions in effect at each approval, bundle report PDF, zipped.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

## Core calls

```python
GET /bundles/{bundle_id}
# attachments = bundle["attachments"]

GET /bundles/{bundle_id}/findings

GET /results?bundleID={bundle_id}
# optional policyID, artifactID

GET /bundles/{bundle_id}/approvals

GET /bundles/{bundle_id}/report
# application/pdf binary; write response bytes to a file, do not expect JSON base64
```

## Gotchas

- Attachments may be large; stream, do not load into memory.
- Policy versions in effect = policy version at each approval event timestamp, not latest.
- Export is read-only; never mutate.
- Keep the zip in Domino (a Dataset, or the results of the Job that built it) unless the auditor names another destination.
