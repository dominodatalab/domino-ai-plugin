# Legacy AI Gateway (Domino 6.3, only where enabled)

Applies to Domino 6.3 **only where an administrator has explicitly enabled the AI Gateway**. It is not enabled by default in 6.3 and has been **removed from Domino Cloud**: on Cloud the Gateway LLMs UI, the `/api/aigateway/*` routes and the gateway audit trail do not exist (a live Cloud deployment returned 404 for `GET /api/aigateway/v1/endpoints` on 2026-10-12, and the Cloud public spec has no `/api/aigateway` path). Before using anything on this page, confirm the deployment is 6.3 (`GET $DOMINO_API_HOST/version`, with the bearer) and that the gateway is enabled: **Develop** > **Gateway LLMs** in the UI, or ask the administrator. The routes below are in the 6.3 spec whether or not the gateway is on, and how a disabled gateway answers them has not been observed (it may be 404, an error, or an empty list); a 404 from an in-run host can also mean the sidecar lacks the route (`domino-api-intro`, HOSTS.md), so retry the public deployment URL with a PAT before reading it as "off". If the deployment is not 6.3 or the gateway is not enabled, use SKILL.md Option A or B instead; do not try to enable the gateway.

## What it is

The legacy AI Gateway is a proxy between Domino executions and external LLM providers such as OpenAI or AWS Bedrock, built on an MLflow Deployments Server. Each **endpoint** forwards requests to one provider model. Provider credentials given at endpoint creation are stored in Domino's central vault and never exposed to callers. Access is per endpoint: everyone, or specific users and organizations. All endpoint activity is logged to Domino's central audit system.

## Where it is in the UI

- Users: **Develop** > **Gateway LLMs** lists endpoints (search by name, type, provider or model). Inside a Workspace, the **Gateway LLMs** side panel lists the endpoints available to the user and has a **Copy Code** icon that produces a ready-to-run query snippet.
- Admins: **Endpoints** > **Gateway LLMs** creates and manages endpoints; the creation modal's second step sets permissions. **Download logs** exports the last six months of endpoint activity as `txt` or `json`; the admin page places the button on **Endpoints** > **Gateway LLMs**, the user page on **Endpoints** > **Gateway Domino endpoints**.

## How code calls it

Callers use the **MLflow Deployment Client**. Domino supports `predict()`, `get_endpoint()` and `list_endpoints()`. Start from the snippet the Workspace side panel copies for the endpoint; it is generated for the deployment and is the authoritative form of the call.

There is **no OpenAI-compatible base URL** for the legacy gateway and no `/api/aigateway/v1/chat/completions` or `/api/aigateway/v1/openai` route. Earlier versions of this skill documented those; they exist in neither public spec. For an OpenAI-compatible interface, host the model in Domino (SKILL.md Option B).

## Management API (`/api/aigateway/v1`, 6.3 spec only)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/aigateway/v1/endpoints` | Query: `offset`, `limit`, `sortByField`, `shouldSortAscending`, `searchFilter` |
| POST | `/api/aigateway/v1/endpoints` | Create; body below |
| GET | `/api/aigateway/v1/endpoints/{endpointName}` | Optional query `numInputTokens` |
| PATCH | `/api/aigateway/v1/endpoints/{endpointName}` | Any of `endpointName`, `endpointType`, `modelProvider`, `modelName`, `modelConfig` |
| DELETE | `/api/aigateway/v1/endpoints/{endpointName}` | |
| GET | `/api/aigateway/v1/endpoints/{endpointName}/permissions` | |
| PATCH | `/api/aigateway/v1/endpoints/{endpointName}/permissions` | Body: `isEveryoneAllowed` (boolean), `userIds` (array) |
| GET | `/api/aigateway/v1/audit` | Query: `endpointIds`, `endpointNames`, `startTime`, `endTime` |

Endpoints are addressed by **name**, which must be unique on the deployment.

Create body (required: `endpointName`, `endpointType`, `endpointPermissions`, `modelProvider`, `modelName`, `modelConfig`), taken from the 6.3 spec and not exercised against a live 6.3 deployment:

```python
import os
import requests

token = requests.get("http://localhost:8899/access-token").text.strip()
base_url = os.environ["DOMINO_API_HOST"].rstrip("/")
headers = {"Authorization": f"Bearer {token}"}

body = {
    "endpointName": "openai-chat",
    "endpointType": "llm/v1/chat",          # the MLflow Deployments Server endpoint type
    "modelProvider": "openai",              # an MLflow Deployments Server provider name
    "modelName": "gpt-4o",
    "modelConfig": {"openai_api_key": os.environ["OPENAI_API_KEY"]},   # provider-specific keys, vaulted by Domino
    "endpointPermissions": {"isEveryoneAllowed": False, "userIds": ["<user id>"]},
}
requests.post(f"{base_url}/api/aigateway/v1/endpoints", headers=headers, json=body)
```

The spec types `modelConfig` as an opaque object and `endpointType`, `modelProvider`, `modelName` as strings; their accepted values come from the MLflow Deployments Server's provider list and provider-specific configuration parameters, which Domino's documentation links rather than restates. Confirm them there before generating a body.

Audit export:

```python
requests.get(f"{base_url}/api/aigateway/v1/audit", headers=headers,
             params={"endpointNames": "openai-chat", "startTime": "2026-04-01T00:00:00Z", "endTime": "2026-10-01T00:00:00Z"}).json()
```

Admins can also query the audit trail in MongoDB (**Admin** > **Advanced** > **MongoDB**): `db.audit_trail.find({ kind: "AccessGatewayEndpoint" })`.

## Migrating away

Cloud has removed the gateway and 6.3 ships it disabled, so treat any gateway code as a migration candidate (steps from the LLM Gateway 2.0 docs page):

1. **Find the code.** Search the Project for `mlflow.deployments.get_deploy_client(...)` and for `predict()`, `get_endpoint()` or `list_endpoints()` against a Domino AI Gateway target, and for any `/api/aigateway/` URL. All of it fails on Cloud and on a 6.3 deployment where the gateway is disabled.
2. **Pick the replacement.** LLM Gateway 2.0 if the team needs centralized tracking, budgets or guardrails; otherwise a provider SDK (SKILL.md Option A) or a Domino-hosted endpoint (Option B).
3. **Move the credentials.** Provider keys the gateway held in Domino's central vault are no longer reachable through it. Store them as Project environment variables (or as inputs to the LLM Gateway 2.0 configuration) and read them with `os.environ`.
4. **Update the calls and rerun** the affected Jobs, Apps and agents end to end.

## Documentation

- https://docs.domino.ai/6.3/platform-capabilities/features/llms/ai-gateway
- https://docs.domino.ai/6.3/admin/platform-configuration/ai-gateway
- https://docs.domino.ai/6.3/admin/operations/audit-logs/ai-gateway-logs
- MLflow Deployments Server: https://mlflow.org/docs/latest/llms/deployments/index.html
