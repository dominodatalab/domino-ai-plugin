# Calling models through LLM Gateway 2.0

Applies to Domino 6.3 and Domino Cloud where an administrator has deployed LLM Gateway 2.0 (early access). All examples use:

- `GATEWAY`: the App's URL without a trailing slash (`https://<domino or apps host>/apps/<app id or vanity URL>`), kept in a Domino environment variable such as `LLM_GATEWAY_URL`.
- `token()`: the bearer. Inside a Domino execution it is the access token from `$DOMINO_API_PROXY/access-token` (`http://localhost:8899/access-token`), re-read before every request because it is short-lived; outside Domino a Personal Access Token or a gateway token (`dgw_...`) from an environment variable. Never a legacy user API key.
- `model`: a gateway **alias** name, never a vendor model name. List them with `GET {GATEWAY}/v1/models`.

```python
import os
import requests

GATEWAY = os.environ["LLM_GATEWAY_URL"].rstrip("/")

def token() -> str:
    proxy = os.environ.get("DOMINO_API_PROXY")
    if proxy:
        return requests.get(f"{proxy}/access-token", timeout=5).text.strip()
    return os.environ["LLM_GATEWAY_TOKEN"]
```

Build the client right before the call (or refresh its key) so a long-running Job or App never sends an expired token. Constructing an OpenAI client is cheap.

## List the aliases you can use

```python
r = requests.get(f"{GATEWAY}/v1/models", headers={"Authorization": f"Bearer {token()}"}, timeout=10)
r.raise_for_status()
for m in r.json()["data"]:          # OpenAI list shape: {"object": "list", "data": [{"id": ...}]}
    print(m["id"])
```

`GET {GATEWAY}/v1/whoami` shows how the gateway resolved your identity, which is the first thing to check when access you expect is refused.

## OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url=f"{GATEWAY}/v1", api_key=token())
response = client.chat.completions.create(
    model="my-gateway-alias",
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.2,
    max_tokens=512,
    extra_headers={"X-LLM-Tag-team": "research"},   # optional attribution tag
)
print(response.choices[0].message.content)
```

Tool calling, JSON mode and the other chat-completions parameters pass through; whether the upstream model honours one is the model's business. The Responses API is served at `{GATEWAY}/v1/responses` (`client.responses.create(model="my-gateway-alias", input="Hello")`) and embeddings at `{GATEWAY}/v1/embeddings` (`client.embeddings.create(model="<embedding alias>", input=[...])`).

## Anthropic SDK

The Anthropic-compatible path is `{GATEWAY}/anthropic`. Pass the bearer as `auth_token` (sent as `Authorization: Bearer`); `api_key` would be sent as `x-api-key`, which the gateway does not accept, and you get a 401.

```python
from anthropic import Anthropic

client = Anthropic(base_url=f"{GATEWAY}/anthropic", auth_token=token())
message = client.messages.create(
    model="my-gateway-alias",
    max_tokens=512,
    messages=[{"role": "user", "content": "Hello"}],
)
print(message.content[0].text)
```

Which Anthropic-specific request features reach the upstream model depends on the provider behind the alias; ask the administrator what an alias is backed by if a feature such as prompt caching or extended thinking matters. The Python Anthropic SDK does not read `ANTHROPIC_CUSTOM_HEADERS`; pass attribution tags with `default_headers={"X-LLM-Tag-team": "research"}`.

## Pydantic AI

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

model = OpenAIChatModel(
    "my-gateway-alias",
    provider=OpenAIProvider(base_url=f"{GATEWAY}/v1", api_key=token()),
)
agent = Agent(model)
print(agent.run_sync("Hello").output)
```

Rebuild the provider (or the agent) per batch of calls in a long-running process so the token stays fresh.

## LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="my-gateway-alias", base_url=f"{GATEWAY}/v1", api_key=token())
print(llm.invoke("What is machine learning?").content)
```

## Plain HTTP

```python
r = requests.post(
    f"{GATEWAY}/v1/chat/completions",
    headers={"Authorization": f"Bearer {token()}", "X-LLM-Tag-team": "research"},
    json={"model": "my-gateway-alias", "messages": [{"role": "user", "content": "Hello"}]},
    timeout=120,
)
r.raise_for_status()
print(r.json()["choices"][0]["message"]["content"])
```

## Streaming

```python
client = OpenAI(base_url=f"{GATEWAY}/v1", api_key=token())
with client.chat.completions.stream(model="my-gateway-alias",
                                    messages=[{"role": "user", "content": "Write a haiku about the Alps"}]) as stream:
    for event in stream:
        if event.type == "content.delta":
            print(event.delta, end="", flush=True)
```

Or `stream=True` on `chat.completions.create` and read `chunk.choices[0].delta.content`.

## Attribution headers

| Header | Effect |
|---|---|
| `X-LLM-Tag-<key>: <value>` | Caller-defined tag stored with the request and usable to slice usage in the gateway UI. Attribution only; never rely on it for access control. |
| `X-LLM-Tag-Bill-Org: <org id>` | For members of several organizations: bill this request against that organization's grant and budget. |
| `X-LLM-Api-Key: <provider key>` | Bring your own provider key, where the administrator has allowed it for the alias; the call is billed to your provider account. |

## Errors to expect

Read the response body: the gateway says in words what refused the call.

- `401`: missing or expired bearer. The access token is short-lived, so re-read it per call; an expired gateway token answers `401 Token expired`; the Anthropic path answers 401 when the credential arrives in `x-api-key` instead of `Authorization`.
- A `4xx` whose body names a grant, a budget or a guardrail rule: no access to the alias, the applicable budget is spent for its period, or a rule denied the prompt or response. Ask the administrator for access or budget, or change the prompt.
- `403 Admin access required`: an administrator-only route; developers do not need those.
- An error on `model`: not an alias you can use; list `GET /v1/models` and use an exact id.
- An HTML error page at the base URL: the App is not deployed, not running, or the URL is wrong. Confirm it with the administrator.
- `413` from the App proxy: the request body is too large (usually a very large tool result); trim it.
- A `200` carrying `X-LLM-Fallback-Served-By` and `X-LLM-Fallback-Reason` headers: the administrator configured a fallback alias and it served the request, so the answer came from a different upstream model.

## Tracing gateway calls

Gateway calls made with the OpenAI or Anthropic SDK are ordinary SDK calls, so MLflow autologging and the Domino agents SDK capture them with no gateway-specific work:

```python
import mlflow
mlflow.openai.autolog()        # or mlflow.anthropic.autolog()
```

See the `domino-genai-tracing` skill. The gateway's own usage record (tokens, latency, estimated cost per request) is separate and visible to the administrator in the gateway UI.
