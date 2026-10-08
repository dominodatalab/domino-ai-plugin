---
name: domino-governance
description: Manage model risk governance in Domino using policies, bundles, and evidence. Covers creating governance bundles, attaching model artifacts and MLflow results as evidence, progressing through policy stages, and documenting findings. Use when the user mentions governance, compliance, bundles, policies, model risk management, SR 11-7, NIST AI RMF, or audit trails.
---

# Domino Governance Skill

This skill provides knowledge for managing model risk governance in Domino Data Lab using the Governance API.

## Configuration

Authentication: https://docs.domino.ai/cloud/reference/api/domino-api-authentication . **Do not use API keys** (`X-Domino-Api-Key`, `DOMINO_USER_API_KEY`).

Governance REST lives at `/api/governance/v1/*`. Pick the base where `GET $BASE/policy-overviews` returns **HTTP 200** (try the table rows in order):

| Context | Base | Authorization |
|---------|------|----------------|
| In-run, `DOMINO_API_PROXY` set (5.4.0+ JWT credential propagation) | `{DOMINO_API_PROXY}/api/governance/v1` | None (proxy adds starting-user JWT) |
| In-run, no proxy, governance on platform API gateway | `{DOMINO_USER_HOST or DOMINO_API_HOST}/api/governance/v1` | Bearer from `GET http://localhost:8899/access-token` |
| In-run but proxy or sidecar returns **404** on `/api/governance/v1/*` (gateway off or governance not registered on 8763) | `{public deployment URL}/api/governance/v1` | Bearer PAT or SA token |
| Outside any run | `{public deployment URL}/api/governance/v1` | Bearer PAT or SA token |

Do **not** scrape the JWT `iss` claim to derive the cluster URL. Prefer `DOMINO_API_PROXY` in-run when step 1 succeeds; otherwise step 2 or 3.

Shell setup for all three rows and the takeaways for agents: [API-GOVERNANCE.md](./API-GOVERNANCE.md#base-url-discovery).

**Examples below:** Omit `Authorization` only when `TOKEN` is unset (proxy path). For gateway or public URL, set `TOKEN` and use `${TOKEN:+-H "Authorization: Bearer $TOKEN"}` in curl blocks.

## Key Concepts

Definitions of policy (template), bundle (living document), evidence (proof) and finding (issue): [STANDARD-WORKFLOW.md](./STANDARD-WORKFLOW.md#key-concepts).

## Reference files

When automating a specific flow, open the matching workflow file first instead of re-deriving from the 8-step section below.

- [STANDARD-WORKFLOW.md](./STANDARD-WORKFLOW.md) - Full request bodies for the 8-step workflow, and where bundles appear in the Domino UI
- [API-GOVERNANCE.md](./API-GOVERNANCE.md) - Endpoint table, bundle fields, base-URL shell setup, compute-policy polling
- [BUNDLE-LIFECYCLE.md](./BUNDLE-LIFECYCLE.md) - Stage sequences, creating bundles, progressing stages
- [EVIDENCE-WORKFLOW.md](./EVIDENCE-WORKFLOW.md) - Attachment types, evidence submission, findings
- [ONBOARD-MODEL.md](./ONBOARD-MODEL.md) - Onboard a model into governance
- [EVIDENCE-ROUND-TRIP.md](./EVIDENCE-ROUND-TRIP.md) - Evidence round-trip with findings
- [APPROVAL-GATE.md](./APPROVAL-GATE.md) - Approval gate automation
- [MONITORING-REREVIEW.md](./MONITORING-REREVIEW.md) - Monitoring-driven re-review
- [RECERTIFICATION-BULK.md](./RECERTIFICATION-BULK.md) - Periodic recertification (bulk)
- [AUDIT-EXPORT.md](./AUDIT-EXPORT.md) - Regulatory audit export
- [POLICY-LIFECYCLE.md](./POLICY-LIFECYCLE.md) - Policy lifecycle and rollout
- [MODEL-RETIREMENT.md](./MODEL-RETIREMENT.md) - Model retirement
- [WAIVER-EXCEPTION.md](./WAIVER-EXCEPTION.md) - Exception or waiver
- [READ-CONTEXT.md](./READ-CONTEXT.md) - Read governance context for downstream use

## Governance API Reference

All endpoints are under `$BASE` (`/api/governance/v1`). See [Configuration](#configuration) for when to send `Authorization`.

Endpoint table and bundle field semantics: [API-GOVERNANCE.md](./API-GOVERNANCE.md#endpoints).

## Standard 8-Step Governance Workflow

Full request bodies for each step: [STANDARD-WORKFLOW.md](./STANDARD-WORKFLOW.md).

Follow these steps when setting up governance for a model:

1. **Discover policies** — `GET $BASE/policy-overviews`; note the `id` of the policy you want to use.
2. **Get the project ID** — `DOMINO_PROJECT_ID` inside Domino, or look it up via the gateway API.
3. **Create a bundle** — `POST $BASE/bundles` with `projectId`, `name`, `policyId` (attachments may be inline). Save the returned `id` as `BUNDLE_ID`.
4. **Inspect the bundle** — `GET $BASE/bundles/$BUNDLE_ID` for stages, attachments and approval status. It does NOT return evidenceSet IDs.
5. **Attach evidence** — `POST $BASE/bundles/$BUNDLE_ID/attachments`; only `ModelVersion` and `Report` types.
6. **Answer evidence questions** — evidenceSet and artifact UUIDs come from `GET $BASE/policies/$POLICY_ID`; submit with `POST $BASE/rpc/submit-result-to-policy` using `policyId` (NOT `policyVersionId`) and `content` as `{artifactId: value}`.
7. **Progress stages** — `POST $BASE/rpc/publish-approval-event`, then `PATCH $BASE/bundles/$BUNDLE_ID` with `{"stage": ...}` when the policy requires it. `PATCH .../stages/{stageId}` updates **assignee** only. Re-fetch and verify `stage` or `currentStageInfo.status` changed.
8. **Document findings** — `POST $BASE/findings`; close with **PUT** `/findings/{id}` and `"status": "Done"`.

## Known platform behaviors

Short pointers; full gotchas live in the workflow files linked under [Reference files](#reference-files).

| Behavior | Where |
|----------|--------|
| Governance base URL (proxy vs gateway vs public on 404) | [Configuration](#configuration) |
| Verify stage actually advanced after approvals | [APPROVAL-GATE.md](./APPROVAL-GATE.md), [BUNDLE-LIFECYCLE.md](./BUNDLE-LIFECYCLE.md) |
| Poll after `compute-policy` | [API-GOVERNANCE.md](./API-GOVERNANCE.md#after-compute-policy-polling) |
| `ModelVersion` attachment `identifier.name` | [EVIDENCE-WORKFLOW.md](./EVIDENCE-WORKFLOW.md), [ONBOARD-MODEL.md](./ONBOARD-MODEL.md) |
| Draft vs submitted evidence (`isLatest`) | [EVIDENCE-WORKFLOW.md](./EVIDENCE-WORKFLOW.md) |
| Close findings (PUT + `status`, new evidence first) | [EVIDENCE-ROUND-TRIP.md](./EVIDENCE-ROUND-TRIP.md) |
| Policy version retire / upgrade on bundles | [POLICY-LIFECYCLE.md](./POLICY-LIFECYCLE.md) |
| Multi-bundle per model | [READ-CONTEXT.md](./READ-CONTEXT.md) |
| Policy attach RPC vs nucleus guardrails proxy | [POLICY-LIFECYCLE.md](./POLICY-LIFECYCLE.md) |
| Open findings before stage advance | [EVIDENCE-ROUND-TRIP.md](./EVIDENCE-ROUND-TRIP.md) |

## Documentation Reference

OpenAPI and route discovery: [API-SPECS.md](../domino-api-intro/API-SPECS.md) (public routes section).

**Governance API base:** See [Configuration](#configuration) (proxy, in-run gateway + access-token, or public URL + PAT/SA when governance 404s on the sidecar). Do not scrape the JWT `iss` claim.

**Product docs:**
- Governance overview: https://docs.domino.ai/cloud/platform-capabilities/features/governance
- Governance API: https://docs.domino.ai/cloud/reference/api/governance-api

For governance workflows and pitfalls, see [Reference files](#reference-files).
