# Model retirement

Model owner archives the bundle (`PATCH /bundles/{bundleId}` with `"state": "Archived"`) and retires the registered model in the model registry.

Base URL and auth: [SKILL.md Configuration](./SKILL.md#configuration).

## Core calls

```python
PATCH /bundles/{bundle_id} {"state": "Archived"}
```

Registered model retirement is a model-registry call (e.g. `/api/registeredmodels/v1/{modelName}`), not governance.

## Gotchas

- Archiving a bundle blocks new evidence submissions (state guard).
- Detaching policies does not delete the policy.
