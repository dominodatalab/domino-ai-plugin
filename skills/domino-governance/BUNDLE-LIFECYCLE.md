# Bundle Lifecycle

Base URL, auth and the `TOKEN` conditional in the curl examples: [SKILL.md Configuration](./SKILL.md#configuration).

## How Policies Define Stage Sequences

A policy template defines an ordered sequence of stages that a model must pass through. A typical MRM policy might use stages like:

```
Model Initiation → Development → Validation & Testing → Deployment Approval → Ongoing Monitoring → Decommission
```

Each stage has:
- **Stage ID**: A UUID (discovered via `GET /bundles/{bundleId}` → `stages[]`)
- **Name**: Human-readable label
- **Approvals**: Organizations that must sign off before the stage can advance
- **EvidenceSet**: Form-based questions to be answered (discovered via `GET /policies/{policyId}`)
- **Attachments**: Model versions, project files (reports), dataset snapshot files, endpoints, NetApp Volume snapshot files and Flow artifacts linked to the bundle (see [EVIDENCE-WORKFLOW.md](./EVIDENCE-WORKFLOW.md#attachment-types))

### Stage Gating

Policies with `enforceSequentialOrder: true` require stages to be completed in order. A stage typically requires:
1. All evidence questions answered
2. Approval from the designated organization(s)

## Creating a Bundle

### Prerequisites
1. **Project ID**: Available as `DOMINO_PROJECT_ID` env var inside Domino, or from the bundle creation response
2. **Policy ID**: Discover via `GET /policy-overviews`

### Create the Bundle
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

The response includes:
- `id` — The bundle ID (use this for all subsequent operations)
- `policyId` — The policy UUID (used for evidence submission)
- `policyVersionId` — The policy version UUID (used for findings)
- `stages` — The full stage structure inherited from the policy
- `stageApprovals` — Approval requirements per stage with org/user IDs
- `attachments` — Evidence attached to the bundle
- `classificationValue` — Auto-populated if policy has classification rules

### One Bundle Per Model Version
Best practice: create a new bundle for each significant model version. This keeps the audit trail clean:
- `My Model v1.0` — initial model
- `My Model v1.1` — retrained with new features
- `My Model v2.0` — architecture change

## Discovering Stage IDs

After creating a bundle, inspect it to find the stage IDs:

```bash
curl -s "$BASE/bundles/$BUNDLE_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"}
```

The response includes a `stages` array:
```json
{
    "bundleId": "...",
    "stageId": "3a32d944-...",
    "stage": {
        "id": "3a32d944-...",
        "name": "Model Initiation",
        "policyVersionId": "102f6b3b-..."
    }
}
```

EvidenceSet IDs come from `GET /policies/{policyId}`, not from the bundle ([EVIDENCE-WORKFLOW.md](./EVIDENCE-WORKFLOW.md#discovering-evidenceset-ids)).

## Progressing Through Stages

Stage **status** on the bundle (`currentStageInfo.status`) is `NotStarted`, `InProgress`, or `Done`, derived from results and approvals.

### Assign a stage owner
`PATCH /bundles/{bundleId}/stages/{stageId}` accepts **assignee** only:
```bash
curl -X PATCH "$BASE/bundles/$BUNDLE_ID/stages/$STAGE_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -d '{"assignee": {"id": "user-uuid", "name": "username"}}'
```

### Complete a stage and move on
After evidence is submitted and approvals are recorded:

1. `POST /rpc/publish-approval-event` with the appropriate `eventType` (for example `RequestApproved`). See [APPROVAL-GATE.md](./APPROVAL-GATE.md).
2. When needed, set the primary stage name on the bundle:
```bash
curl -X PATCH "$BASE/bundles/$BUNDLE_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -d '{"stage": "Validation & Testing"}'
```

Re-fetch the bundle and confirm `stage` (name string) or `currentStageInfo.status` changed.

If the policy enforces gating and required questions are unanswered, advance steps may fail or leave the bundle non-compliant.

## Approval Gating

Each stage has designated approvers (organizations, or users when the policy allows); one of them signs off in the UI or through `GET /bundles/{bundleId}/approvals`, `POST /rpc/publish-approval-event` and `POST /rpc/update-approval`, then the bundle is re-fetched to confirm the stage moved: [APPROVAL-GATE.md](./APPROVAL-GATE.md). The bundle's `stageApprovals` lists the approving organizations, the current approval status and approver IDs (used when creating findings).

## Checking Bundle Status

At any point, inspect the current state (fields: [Create the Bundle](#create-the-bundle)):
```bash
curl -s "$BASE/bundles/$BUNDLE_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"}
```

## Listing All Bundles in a Project

To see all bundles:
```bash
curl -s "$BASE/bundles?projectId=$PROJECT_ID" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"}
```

This returns summaries of all bundles, useful for checking if a bundle already exists before creating a duplicate.
