---
name: domino-llm-access
description: Call Large Language Models from code running in Domino and choose how the model is reached. Option A, an external provider (OpenAI, Anthropic, AWS Bedrock, Azure OpenAI, Google Vertex AI) with the API key stored as a Domino environment variable. Option B, a Domino-hosted model endpoint (vLLM, OpenAI-compatible) created from a Hugging Face model or a registered model and called with an OpenAI-style client and the in-run access token. Covers the Host an LLM UI and REST API (/api/gen-ai/beta), endpoint metrics and logs, LLM Gateway 2.0, and the legacy AI Gateway. Use when a user asks how to call an LLM from a Workspace, Job, App or agent, where to put an LLM API key, how to get an endpoint base_url or token, how to host, deploy or serve an LLM with vLLM, how to use or migrate off the AI Gateway, or what LLM Gateway 2.0 is.
compatibility: Domino 6.3 and Domino Cloud. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a Personal Access Token. The legacy AI Gateway section applies to Domino 6.3 only, and only where an administrator has enabled it.
---

# LLM access in Domino

Applies to Domino 6.3 and Domino Cloud. One section differs between them (the legacy AI Gateway); read "Which path applies" first.

## Which path applies

Both targets offer the same two ways to reach a model:

- **Option A: external provider.** Code calls OpenAI, Anthropic, Bedrock, Azure OpenAI or Vertex AI through the provider's SDK; Domino injects the API key as an environment variable.
- **Option B: Domino-hosted endpoint.** Domino serves a registered model (from Hugging Face or an experiment run) with vLLM on a GPU hardware tier behind an OpenAI-compatible URL.

What differs is the gateway in front of external providers:

| Deployment | Legacy AI Gateway | LLM Gateway 2.0 |
|---|---|---|
| **Domino Cloud** | Removed: no Gateway LLMs UI, no `/api/aigateway/*` routes, no audit trail; MLflow Deployment Client code against it fails. | Successor; on request from the Domino field team, deployed as a Domino App. |
| **Domino 6.3** | Present but off by default; works only where an administrator enabled it. | Same as Cloud. |

Find the deployment: `GET $DOMINO_API_HOST/version` (the route `python-domino` uses; send the bearer) returns JSON with a `version` field. `6.3.x` is self-managed 6.3; Cloud reports a later build (`6.4.0` at the time of writing). On 6.3, whether the legacy gateway is enabled is an administrator setting: confirm it in the UI (**Develop** > **Gateway LLMs** lists endpoints only where it is on) or with the administrator. Do not infer it from a 404: in a run, `DOMINO_API_HOST` may be a sidecar that lacks some `/api/*` routes (`domino-api-intro`, HOSTS.md), so retry the public deployment URL with a PAT before concluding anything, and never try to enable the gateway yourself. Below 6.3 this skill does not apply: say so and point to docs.dominodatalab.com for that version. Never tell the user to reinstall or change the plugin.

Choose Option A for a frontier model when prompts may leave the cluster; choose Option B when external providers are not permitted, data must stay resident, or the model was fine-tuned in-house. Endpoints are OpenAI-compatible, so OpenAI-style client code moves between the two by changing `base_url` and the key. For agents, `@add_tracing` (`domino-genai-tracing` skill) captures every LLM call wherever the model runs.

## Option A: call an external provider

1. Install the provider's SDK in the Compute Environment (Dockerfile instruction such as `RUN pip install openai`) or in the Workspace.
2. Store the API key as a Domino environment variable in the Project's settings. Domino injects Project environment variables into Workspaces and Jobs, so the key stays out of code and version control.
3. Read it with `os.environ` and call the SDK as anywhere else.

| Provider | Package | Environment variable(s) |
|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| AWS Bedrock | `boto3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Azure OpenAI | `openai` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| Google Vertex AI | `google-cloud-aiplatform` | Service account credentials |

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = client.chat.completions.create(
    model="gpt-5.4-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Never hard-code, commit, or pass keys on a command line.

## Option B: host a model in Domino

Needs **Project Collaborator** permission and a **GPU hardware tier** whose memory holds the model's weights (about 16 GB for a 7B model, 24 GB or more from 13B). UI walkthrough: [HOST-AN-LLM.md](./HOST-AN-LLM.md). REST equivalent (`/api/gen-ai/beta`, identical on 6.3 and Cloud): [HOST-AN-LLM-API.md](./HOST-AN-LLM-API.md).

Once the endpoint is **Running**, its **Calling** tab shows the URL (the `base_url`) and a ready-made snippet. Inside a Workspace, Job or App the bearer is the in-run access token:

```python
import os
import requests
from openai import OpenAI

ENDPOINT_URL = os.environ["DOMINO_LLM_ENDPOINT_URL"]            # copied from the Calling tab
API_KEY = requests.get("http://localhost:8899/access-token").text  # in-run access token

client = OpenAI(base_url=ENDPOINT_URL, api_key=API_KEY)
response = client.chat.completions.create(
    model="your-model-name",   # the endpoint's servedModelName
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

The OpenAI Responses API is also supported. Keep the URL in a Domino environment variable such as `DOMINO_LLM_ENDPOINT_URL` so promoting from a development to a production endpoint is a configuration change. The access token is short-lived and exists only inside a Domino execution; code outside Domino uses a Personal Access Token as the bearer. Legacy user API keys are deprecated; do not use them.

## Gateways

**LLM Gateway 2.0** (Cloud and 6.3, on request) is the successor to the legacy AI Gateway: centralized external-provider access with usage tracking across users, Projects and models, per-team and per-model budgets, prompt and response guardrails, and broader model and vendor coverage. Domino distributes it as a binary deployed as a Domino App, obtained from the user's Domino field representative; there is no self-service install and no public API to document. Do not invent configuration for it.

**Legacy AI Gateway** (6.3 only, where enabled): [LEGACY-AI-GATEWAY.md](./LEGACY-AI-GATEWAY.md) covers the Gateway LLMs UI, the MLflow Deployment Client calls it supports, the `/api/aigateway/v1` routes with verified bodies, and the audit download.

**Migrating off the legacy AI Gateway** (code using the MLflow Deployment Client or `/api/aigateway/` URLs fails on Cloud and on a 6.3 deployment with the gateway disabled): the steps are in [LEGACY-AI-GATEWAY.md](./LEGACY-AI-GATEWAY.md#migrating-away).

Before generating API code, confirm routes against the deployment's own reference at `https://<domino-domain>/docs`; the published specs this skill was checked against are listed in [HOST-AN-LLM-API.md](./HOST-AN-LLM-API.md).

## Documentation

- Set up LLM access: https://docs.domino.ai/cloud/platform-capabilities/features/llms (6.3: replace `cloud` with `6.3`)
- Host an LLM: https://docs.domino.ai/cloud/platform-capabilities/features/llms/host-an-llm
- LLM Gateway 2.0 and migration: https://docs.domino.ai/cloud/platform-capabilities/features/llms/llm-gateway
- Legacy AI Gateway (6.3): https://docs.domino.ai/6.3/platform-capabilities/features/llms/ai-gateway
- API authentication: https://docs.domino.ai/cloud/reference/api/domino-api-authentication
