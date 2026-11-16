---
name: domino-llm-access
description: Decide and implement how code running in Domino reaches a Large Language Model - the AI Gateway (Gateway LLMs) where an administrator has created endpoints, called with the MLflow Deployment Client and managed over /api/aigateway/v1, or an external provider (OpenAI, Anthropic, AWS Bedrock, Azure OpenAI, Google Vertex AI) with the API key stored as a Domino environment variable. Use when a user asks how to call an LLM from a Workspace, Job, App or agent, which LLM path to use, where to put an LLM API key, how to use, create or audit Gateway LLMs endpoints, or whether an LLM can be hosted or served in Domino.
compatibility: Domino 6.1. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a service-account token (Bearer) or a user API key.
---

# LLM access in Domino

Applies to Domino 6.1.

## Which path applies

Two ways exist; pick in this order:

1. **AI Gateway** (Gateway LLMs): the governed path where an administrator has created endpoints. Administrators create endpoints that hold the provider credentials, grant access per user, and every call is audited. Callers use the MLflow Deployment Client. Where an endpoint for the model the user needs is listed for them, use it: [LEGACY-AI-GATEWAY.md](./LEGACY-AI-GATEWAY.md).
2. **Option A: external provider**, where no gateway endpoint fits. Code calls OpenAI, Anthropic, Bedrock, Azure OpenAI or Vertex AI through the provider's SDK; Domino injects the API key as an environment variable.

Hosting an LLM in Domino (a vLLM endpoint behind an OpenAI-compatible URL) and LLM Gateway 2.0 are not available on Domino 6.1.

Find the deployment: `GET $DOMINO_API_HOST/version` (send the bearer) returns `version`; `6.1.x` is Domino 6.1. Find the gateway endpoints the user may call in the UI (**Develop** > **Gateway LLMs**, or the **Gateway LLMs** side panel in a Workspace) or with `GET /api/aigateway/v1/endpoints`. An empty list means no endpoint is shared with the user: ask the administrator to create one, or use Option A. Do not infer that the gateway is absent from a 404 (retry per [HOSTS.md](../domino-api-intro/HOSTS.md#404-on-the-in-run-base)). Never tell the user to reinstall or change the plugin.

Choose the gateway when provider keys must stay with administrators or calls must be audited; choose Option A when the user holds their own provider key and no gateway endpoint serves the model.

## Option A: call an external provider

1. Install the provider's SDK in the Compute Environment (Dockerfile instruction such as `RUN pip install openai`) or in the Workspace.
2. Store the API key as a Project environment variable; Domino injects it into Workspaces and Jobs, so it stays out of code and version control.
3. Read it with `os.environ` and call the SDK as anywhere else.

| Provider | Package | Environment variable(s) |
|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| AWS Bedrock | `boto3` | `AWS_PROFILE` with AWS credential propagation where the administrator configured it (`domino-data-connectivity`): the profile name is deployment-specific, from the user or administrator, never guessed; if no profile is available in the run, use the keys. Else `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Azure OpenAI | `openai` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| Google Vertex AI | `google-cloud-aiplatform` | Service account credentials |

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = client.chat.completions.create(
    model="gpt-6.1-sol",            # example model name; use one your account can call
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Never hard-code, commit, or pass keys on a command line.

## AI Gateway

[LEGACY-AI-GATEWAY.md](./LEGACY-AI-GATEWAY.md) covers the Gateway LLMs UI, the MLflow Deployment Client calls it supports, the `/api/aigateway/v1` routes and bodies, and the audit download. The gateway has no OpenAI-compatible base URL; code that needs one uses Option A.

## Documentation

- Set up LLM access: https://docs.domino.ai/cloud/platform-capabilities/features/llms (6.3: replace `cloud` with `6.3`)
- AI Gateway: https://docs.domino.ai/6.3/platform-capabilities/features/llms/ai-gateway
- Authentication: https://docs.domino.ai/cloud/reference/api/domino-api-authentication
