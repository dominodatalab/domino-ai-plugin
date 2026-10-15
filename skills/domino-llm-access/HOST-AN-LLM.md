# Host an LLM: UI walkthrough

Register a model, deploy it with vLLM on a GPU hardware tier, call its OpenAI-compatible endpoint, and monitor it. Source: https://docs.domino.ai/cloud/platform-capabilities/features/llms/host-an-llm (6.3: replace `cloud` with `6.3`). For the REST routes see [HOST-AN-LLM-API.md](./HOST-AN-LLM-API.md).

## Before you start

- **Permissions**: Project Collaborator, to register models and create endpoints.
- **Hardware**: a GPU-enabled hardware tier. CPU tiers do not give acceptable latency. The tier's GPU memory must hold the model's weights: a 7B-parameter model needs at least about 16 GB of VRAM; use 24 GB or more from 13B parameters. Start with a tier that meets the requirement, watch the Performance tab, then scale. If many users call the endpoint concurrently, a minimal GPU tier slows down; use a larger tier or a second endpoint.
- **Model access**: for Hugging Face models the user must have access; some require accepting a license on Hugging Face first. Gated models need a Hugging Face token at registration time.

## Step 1: register a model

Go to **Models** > **Register**. Choose the source:

- a **Hugging Face** model the user has access to, or
- an **experiment run** that logged an MLflow model.

Complete the required fields.

## Step 2: create an endpoint

From the registered model's **Endpoints** tab, click **Create endpoint**:

1. Complete the endpoint configuration details.
2. Under **Environment**, select **Domino vLLM Environment**. It is pre-configured with the vLLM runtime, which provides the OpenAI-compatible API.
3. Under **Hardware Tier**, select a GPU-enabled tier sized for the model.
4. Configure access by adding users or organizations.
5. Some models need extra vLLM arguments to work with agent frameworks' tool calling. Under **Configuration** > **Advanced** > **vLLM arguments** add `--enable-auto-tool-choice` and `--tool-call-parser hermes`.
6. Click **Create endpoint**.

## Step 3: get the URL and call the endpoint

When the endpoint is **Running**, open its **Calling** tab. It shows:

- the endpoint URL, which is the `base_url` for an OpenAI-style client, and
- a code snippet for the OpenAI Python SDK.

Inside a Workspace, Job or App the bearer token comes from `$DOMINO_API_PROXY/access-token` (by default `http://localhost:8899/access-token`); in an App it is the publisher's token. It is short-lived, so fetch it per call in an App or long Job. Outside Domino use a Personal Access Token.

With the OpenAI SDK:

```python
import os
import requests
from openai import OpenAI

ENDPOINT_URL = os.environ["LLM_ENDPOINT_URL"]

def token() -> str:                                      # in-run access token, fresh per call
    proxy = os.environ.get("DOMINO_API_PROXY", "http://localhost:8899")
    return requests.get(f"{proxy}/access-token", timeout=5).text.strip()

client = OpenAI(base_url=ENDPOINT_URL, api_key=token())
response = client.chat.completions.create(
    model="your-model-name",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

With Pydantic AI:

```python
import os
import requests
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

ENDPOINT_URL = os.environ["LLM_ENDPOINT_URL"]

def token() -> str:                                      # in-run access token, fresh per call
    proxy = os.environ.get("DOMINO_API_PROXY", "http://localhost:8899")
    return requests.get(f"{proxy}/access-token", timeout=5).text.strip()

def make_agent() -> Agent:                               # build per request in an App
    model = OpenAIChatModel(
        "your-model-name",
        provider=OpenAIProvider(base_url=ENDPOINT_URL, api_key=token()),
    )
    return Agent(model)

print(make_agent().run_sync("Summarize the latest quarterly report.").output)
```

`your-model-name` is the `servedModelName` configured on the endpoint. The OpenAI Responses API is also supported. Store the URL as a Domino environment variable (for example `LLM_ENDPOINT_URL`) rather than hard-coding it, so swapping endpoints is a configuration change.

## Step 4: monitor

The endpoint detail page has:

- **Overview**: configuration details and deployment status.
- **Performance**: token usage and latency over time.
- **Usage**: invocation frequency.

The same numbers are available from the metrics routes in [HOST-AN-LLM-API.md](./HOST-AN-LLM-API.md).

## Troubleshooting

| Problem | What to check |
|---|---|
| Hugging Face model not in the list | The user must have access to the model; some require accepting a license agreement on Hugging Face first. |
| Endpoint stuck in **Starting** | Model size versus the tier's GPU memory. Read the endpoint logs for the specific error. |
| Slow responses or timeouts | Performance tab for latency patterns; if concurrent requests exceed capacity, use a larger tier or deploy a second endpoint. |
| Users cannot access the endpoint | They or their organization must be in the endpoint's access controls and hold the required Project permissions. |
| Tool calls fail from an agent framework | Add `--enable-auto-tool-choice --tool-call-parser hermes` to the vLLM arguments (Step 2). |
