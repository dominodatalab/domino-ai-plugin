# Governance API reference

Endpoint table, bundle field semantics, base-URL discovery shell setup with takeaways, and the compute-policy polling loop for the Domino Governance API (`/api/governance/v1`).

Auth, base table and rules: [SKILL.md Configuration](./SKILL.md#configuration).

## Base URL discovery

```bash
GOV="/api/governance/v1"
PREFIX="/policy-overviews"

# 1) In-run, proxy (try first when DOMINO_API_PROXY is set)
BASE="$DOMINO_API_PROXY$GOV"
curl -s "$BASE$PREFIX"

# 2) In-run, platform gateway (no proxy)
HOST="${DOMINO_USER_HOST:-$DOMINO_API_HOST}"
TOKEN="$(curl -s http://localhost:8899/access-token)"
BASE="$HOST$GOV"
curl -s "$BASE$PREFIX" -H "Authorization: Bearer $TOKEN"

# 3) Public deployment (outside run, or 404 on 1 and 2)
BASE="https://your-deployment.domino.tech$GOV"
TOKEN="$PAT_OR_SA_TOKEN"
curl -s "$BASE$PREFIX" -H "Authorization: Bearer $TOKEN"
```

**Takeaways for agents**

1. **Proxy + no header is correct only when routing works.** `DOMINO_API_PROXY` injects JWT ([product auth doc](https://docs.domino.ai/cloud/reference/api/domino-api-authentication)); it does not add `/api/governance/v1` if guardrails is not reachable on that path.
2. **Try steps 1 → 2 → 3** until `GET $BASE/policy-overviews` returns HTTP 200. Do not assume step 1 works on every deployment.
3. **In-run without proxy is not “use public URL.”** Use `DOMINO_USER_HOST` (or `DOMINO_API_HOST`) plus Bearer from `http://localhost:8899/access-token` when governance is on the platform API gateway.
4. **Public deployment URL + PAT/SA** when you are outside a run, or when step 1 or 2 returns **404** (common when the API gateway is off or governance is not registered on port 8763).
5. **Suffix is always** `/api/governance/v1` on whichever host/base you chose ([Governance API](https://docs.domino.ai/cloud/reference/api/governance-api)).

## Endpoints

All endpoints are under `$BASE` (`/api/governance/v1`). See [Configuration](./SKILL.md#configuration) for when to send `Authorization`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/policy-overviews` | GET | List available policy templates |
| `/bundles` | POST | Create a new governance bundle (optional inline `attachments`) |
| `/bundles/{bundleId}` | GET | Inspect bundle: stages, attachments, status |
| `/bundles/{bundleId}` | PATCH | Update bundle `state`, primary `stage` name, or `policyId` |
| `/bundles` | GET | List all bundles (filter by `projectId`) |
| `/bundles/{bundleId}/attachments` | POST | Attach evidence after create (model versions, reports) |
| `/bundles/{bundleId}/stages/{stageId}` | PATCH | Update stage **assignee** only (not stage completion) |
| `/rpc/submit-result-to-policy` | POST | Answer policy evidence questions |
| `/rpc/compute-policy` | POST | Recompute policy for a bundle (returns `ComputedPolicy`) |
| `/results/latest` | GET | Latest artifact results (`bundleID` query param) |
| `/rpc/publish-approval-event` | POST | Publish approval workflow events (approve, reject, etc.) |
| `/policies/{policyId}` | GET | Get full policy with evidenceSet IDs |
| `/findings` | POST | Create a finding (issue) during review |
| `/findings/{id}` | PUT | Update a finding (including `status`) |

**Bundle fields:** `stage` (string) is the primary policy stage name; set it with `PATCH /bundles/{id}` to move the workflow. `state` (`Active`, `Archived`, `Complete`) is bundle lifecycle; set when archiving or completing the bundle. `currentStageInfo.status` (`NotStarted`, `InProgress`, `Done`) is stage progress on GET only, not writable on `/stages/{stageId}`.

## After compute-policy (polling)

`POST /rpc/compute-policy` returns **200** with a `ComputedPolicy` body. Freshness lives on artifact results, not a single top-level flag.

1. Call `POST /rpc/compute-policy` with `bundleId` and `policyId`.
2. Poll `GET /results/latest?bundleID={bundleId}` (and optional `policyID`, `artifactID`) until the artifacts you care about have `isLatest: true`, or inspect `results[].isLatest` on the compute response when present.
3. Only then treat evidence as current for submit, stage advance, or read-context output.

Reuse this loop in every workflow that calls `compute-policy` (see [ONBOARD-MODEL.md](./ONBOARD-MODEL.md), [EVIDENCE-ROUND-TRIP.md](./EVIDENCE-ROUND-TRIP.md), [READ-CONTEXT.md](./READ-CONTEXT.md)).
