# AI Gateway (Gateway LLMs)

Applies to Domino 6.1. The AI Gateway is part of Domino 6.1 and is usable once an administrator has created endpoints; a user sees and calls only the endpoints shared with them. Confirm which exist in **Develop** > **Gateway LLMs** or with `GET /api/aigateway/v1/endpoints`. A 404 from the in-run base can mean the route is not served there ([HOSTS.md](../domino-api-intro/HOSTS.md#404-on-the-in-run-base)): retry on the deployment URL with a service-account token (or a user API key) before concluding anything. If **Gateway LLMs** is missing or lists no endpoint that fits, use SKILL.md Option A; never enable the gateway or create endpoints yourself.

## What it is

The AI Gateway is a proxy between Domino executions and external LLM providers such as OpenAI or AWS Bedrock, built on an MLflow Deployments Server. Each **endpoint** forwards requests to one provider model. Provider credentials given at endpoint creation are held by the gateway, managed by Domino, and never exposed to callers. Access is per endpoint: everyone, or specific users and organizations. All endpoint activity is logged to Domino's central audit system.

## Where it is in the UI

- Users: **Develop** > **Gateway LLMs** lists endpoints (search by name, type, provider or model). Inside a Workspace, the **Gateway LLMs** side panel lists the endpoints available to the user and has a **Copy Code** icon that produces a ready-to-run query snippet.
- Admins: **Endpoints** > **Gateway LLMs** creates and manages endpoints; the creation modal's second step sets permissions. **Download logs** exports the last six months of endpoint activity as `txt` or `json`; the admin page places the button on **Endpoints** > **Gateway LLMs**, the user page on **Endpoints** > **Gateway Domino endpoints**.

## How code calls it

Callers use the **MLflow Deployment Client**. Domino supports `predict()`, `get_endpoint()` and `list_endpoints()`. Start from the snippet the Workspace side panel copies for the endpoint; it is generated for the deployment and is the authoritative form of the call.

There is **no OpenAI-compatible base URL** for the gateway and no `/api/aigateway/v1/chat/completions` or `/api/aigateway/v1/openai` route. For an OpenAI-compatible interface, call the provider directly (SKILL.md Option A).

## Management API (`/api/aigateway/v1`)

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

Create body (required: `endpointName`, `endpointType`, `endpointPermissions`, `modelProvider`, `modelName`, `modelConfig`); if the call answers 400, confirm the body in your deployment's `/docs`:

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
    "modelName": "gpt-6.1-sol",             # example provider model name
    "modelConfig": {"openai_api_key": os.environ["OPENAI_API_KEY"]},   # provider key read from a Project or user environment variable; the gateway keeps it afterwards
    "endpointPermissions": {"isEveryoneAllowed": False, "userIds": ["<user id>"]},
}
requests.post(f"{base_url}/api/aigateway/v1/endpoints", headers=headers, json=body)
```

`modelConfig` is an opaque object and `endpointType`, `modelProvider`, `modelName` are strings; the accepted values are the MLflow Deployments Server's provider names and provider-specific configuration parameters (link under Documentation). Confirm them there before generating a body.

Audit export:

```python
requests.get(f"{base_url}/api/aigateway/v1/audit", headers=headers,
             params={"endpointNames": "openai-chat", "startTime": "2026-04-01T00:00:00Z", "endTime": "2026-10-01T00:00:00Z"}).json()
```

## Documentation

- https://docs.domino.ai/6.3/platform-capabilities/features/llms/ai-gateway
- https://docs.domino.ai/6.3/admin/platform-configuration/ai-gateway
- https://docs.dominodatalab.com/en/6.1/admin_guide/984c09/monitor-ai-gateway-large-language-model-llm-logs/
- MLflow Deployments Server: https://mlflow.org/docs/latest/llms/deployments/index.html
