# Standard 8-step governance workflow

The end-to-end sequence for putting one model under governance, with full request bodies for each step, and where the results appear in the Domino UI.

Base URL, auth and the `TOKEN` conditional in the curl examples: [SKILL.md Configuration](./SKILL.md#configuration). Endpoint table: [API-GOVERNANCE.md](./API-GOVERNANCE.md#endpoints).

## Key Concepts

### Policy (Template)
A **policy** is a reusable governance template that defines the stages, evidence requirements, and approval gates a model must pass through. Examples: SR 11-7, NIST AI RMF, internal model risk frameworks. Policies are usually authored by administrators (Policy Builder or YAML in the UI), and the same lifecycle is public API: `POST /policies`, `POST /policies/{id}/versions`, `PUT /policies/{id}/definition`, `PUT /policies/{id}/status`, `POST /rpc/publish-policy-version`; see [POLICY-LIFECYCLE.md](./POLICY-LIFECYCLE.md).

### Bundle (Living Document)
A **bundle** is the compliance document for a *specific model* in a *specific project*. It follows a policy and accumulates evidence as the model progresses through development, validation, and approval. One project can have multiple bundles (e.g., one per model version).

### Evidence (Proof)
Evidence comes in two forms:
1. **Attachments** — Files, model versions, and reports attached to the bundle (visible in the "Attachments" tab)
2. **EvidenceSet answers** — Responses to policy-defined form questions (visible in the "Evidence" tab for each stage)

### Finding (Issue)
A **finding** documents a problem, risk, or concern discovered during review. Findings have severity levels and are tracked as part of the audit trail.

## Steps

Follow these steps when setting up governance for a model:

### Step 1: Discover Policies
```bash
curl -s "$BASE/policy-overviews" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"}
```
Review available templates. Note the `id` of the policy you want to use.

### Step 2: Get the Project ID
The project ID is needed to create a bundle. Use the `DOMINO_PROJECT_ID` environment variable (available inside Domino) or list projects with `GET /api/projects/beta/projects` ([domino-projects](../domino-projects/PROJECTS-API.md)).

### Step 3: Create a Bundle
Attachments may be inline on `POST /bundles` or added later via `POST /bundles/{id}/attachments`. Prefer inline when creating and attaching a model in one step (see [ONBOARD-MODEL.md](./ONBOARD-MODEL.md)).

```bash
curl -X POST "$BASE/bundles" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -d '{
    "projectId": "your-project-id",
    "name": "My Model v1.0",
    "policyId": "policy-uuid"
  }'
```
Save the returned `id` as your `BUNDLE_ID`.

### Step 4: Inspect the Bundle
```bash
curl -s "$BASE/bundles/$BUNDLE_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"}
```
This reveals the policy's stage structure, attachments, and approval status.

### Step 5: Attach Evidence
See [EVIDENCE-WORKFLOW.md](./EVIDENCE-WORKFLOW.md) for full details. `type` is one of `ModelVersion`, `Report`, `DatasetSnapshotFile`, `Endpoint`, `NetAppVolumeSnapshotFile`, `FlowArtifact`, `FlowArtifactFile`; the two most common:

```bash
# Attach a registered model version
curl -X POST "$BASE/bundles/$BUNDLE_ID/attachments" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H "Content-Type: application/json" \
  -d '{"type":"ModelVersion","identifier":{"name":"model-name","version":5},"name":"Display Name"}'

# Attach a project file (notebook, report, etc.)
curl -X POST "$BASE/bundles/$BUNDLE_ID/attachments" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H "Content-Type: application/json" \
  -d '{"type":"Report","identifier":{"branch":"main","commit":"abc...","source":"git","filename":"path/to/file"},"name":"Display Name"}'
```

### Step 6: Answer Evidence Questions (EvidenceSet)

Evidence questions are the interactive forms shown in the Domino UI under each stage's "Evidence" tab. They are defined in the policy YAML as `evidenceSet` items.

#### 6a. Discover EvidenceSet IDs

EvidenceSet IDs are NOT in the bundle response. Fetch them from the **policy** endpoint:

```bash
curl -s "$BASE/policies/$POLICY_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"}
```

The response contains `stages[]` → `evidenceSet[]` → `artifacts[]` with full UUIDs for each evidence item and artifact.

#### 6b. Submit Answers

```bash
curl -X POST "$BASE/rpc/submit-result-to-policy" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -d '{
    "bundleId": "bundle-uuid",
    "policyId": "policy-uuid",
    "evidenceId": "evidence-uuid",
    "content": {
      "artifact-uuid": "value"
    }
  }'
```

**Key details**:
- Use `policyId` (NOT `policyVersionId`)
- `evidenceId` is the evidence set item UUID (from policy response)
- `content` is a map of `{artifactId: value}`
- For **radio/textinput/textarea/select**: value is a string
- For **checkbox/multiSelect**: value is an array of strings
- Submit one artifact at a time per call, or multiple artifacts in the same evidence item together

### Step 7: Progress Stages
Stage completion follows evidence, approvals and workflow events ([BUNDLE-LIFECYCLE.md](./BUNDLE-LIFECYCLE.md#progressing-through-stages)). After evidence and approvals:

1. Publish approval events ([APPROVAL-GATE.md](./APPROVAL-GATE.md)):
```bash
curl -X POST "$BASE/rpc/publish-approval-event" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -d '{
    "bundleId": "bundle-uuid",
    "policyId": "policy-uuid",
    "projectId": "project-uuid",
    "eventType": "RequestApproved",
    "approvalId": "approval-uuid"
  }'
```

2. When the policy requires explicitly setting the primary stage name:
```bash
curl -X PATCH "$BASE/bundles/$BUNDLE_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -d '{"stage": "Next stage name from policy"}'
```

Re-fetch the bundle and verify `stage` or `currentStageInfo.status` changed before continuing.

### Step 8: Document Findings (if any)
```bash
curl -X POST "$BASE/findings" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H "Content-Type: application/json" \
  -d '{
    "bundleId": "bundle-uuid",
    "policyVersionId": "policy-version-uuid",
    "name": "Finding title",
    "description": "Detailed description...",
    "severity": "High",
    "approver": {"id": "org-uuid", "name": "model-gov-org"},
    "assignee": {"id": "user-uuid", "name": "username"}
  }'
```
Close or resolve with **PUT** `/findings/{id}` and `"status": "Done"` (not `PATCH` or `state: Closed`). See [EVIDENCE-ROUND-TRIP.md](./EVIDENCE-ROUND-TRIP.md).
Get the `policyVersionId` and user/org IDs from the bundle response (Step 4).

## Viewing in Domino UI

After creating a bundle and attaching evidence, the bundle is visible in the Domino UI:
**Project** > **Govern** > **Bundles** > click the bundle name

The UI shows:
- **Overview** — Stage progression and classification
- **Evidence** tab (per stage) — Interactive forms for evidenceSet questions
- **Attachments** tab — Files, model versions, and reports
- **Findings** tab — Documented issues with severity
