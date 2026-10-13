# Calling models through LLM Gateway 2.0

Applies to Domino 6.3 and Domino Cloud where an administrator has installed the LLM Gateway 2.0 extension (early access). Every recipe below was run from a Domino Workspace against a live gateway on an internal Domino test cluster, except where marked unverified. All examples use:

- `GATEWAY`: the gateway App's URL without a trailing slash, from `LLM_GATEWAY_URL` if the user created that Project or user environment variable, else asked for. Nothing is injected.
- `token()`: the bearer. Inside a Domino execution it is the access token from `$DOMINO_API_PROXY/access-token` (the same value as `http://localhost:8899/access-token`), re-read before every request because it is short-lived; outside Domino a Domino bearer the user stored, for example a Personal Access Token in `LLM_GATEWAY_TOKEN` (a Domino access token worked from a laptop in testing; a PAT and `dgw_` gateway tokens are unverified). Never a legacy user API key.
- `model`: an alias from `GET {GATEWAY}/v1/models`. Aliases are administrator-defined and may carry a prefix such as `domino/`; `domino/example-alias` below is a placeholder.
- The SDKs are **not** in the Domino Standard Environment. To try: `pip install openai anthropic "pydantic-ai-slim[openai]" langchain-openai`; for repeat use add the ones you need to the Compute Environment's Dockerfile instructions.

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

## Detect the gateway and list the aliases you can use

```python
r = requests.get(f"{GATEWAY}/v1/models", headers={"Authorization": f"Bearer {token()}"}, timeout=10)
r.raise_for_status()                # JSON here proves the gateway is installed and the bearer works
for m in r.json()["data"]:          # OpenAI list shape: {"object": "list", "data": [{"id": ..., "owned_by": ...}]}
    print(m["id"])
```

`GET {GATEWAY}/health` returns `{"status": "ok", "service": "llm-gateway"}` with a bearer. `GET {GATEWAY}/v1/whoami` returns `resolved_identity` (user, organizations, token name), the first thing to check when access you expect is refused; inside a Workspace it does not carry the Project. Do not test the base URL itself: with a bearer `{GATEWAY}/` is the gateway's UI (200 HTML), without one every route is a 302 to the Domino login page.

## OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url=f"{GATEWAY}/v1", api_key=token())
response = client.chat.completions.create(
    model="domino/example-alias",                     # an alias from /v1/models
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.2,
    max_tokens=512,                                   # keep generous: some aliases spend tokens on reasoning first
    extra_headers={"X-LLM-Tag-team": "research"},     # optional attribution tag
)
print(response.choices[0].message.content)
```

Tool calling, JSON mode and the other chat-completions parameters pass through; whether the upstream model honours one is the model's business. The Responses API is served at `{GATEWAY}/v1/responses` (`client.responses.create(model="domino/example-alias", input="Hello")`, verified). Embeddings at `{GATEWAY}/v1/embeddings` need an embedding alias the administrator published; without one the call fails with `400 ... not implemented` (an alias of the wrong kind), so list `/v1/models` and ask the administrator which alias embeds.

## Anthropic SDK

The Anthropic-compatible path is `{GATEWAY}/anthropic`. Pass the bearer as `auth_token` (sent as `Authorization: Bearer`). With `api_key=` the SDK sends only `x-api-key`, the App proxy answers with a 302 to the login page, and the SDK hands that HTML back as a string, so `message.content` fails with `AttributeError: 'str' object has no attribute 'content'` rather than a clear auth error.

```python
from anthropic import Anthropic

client = Anthropic(base_url=f"{GATEWAY}/anthropic", auth_token=token())
message = client.messages.create(
    model="domino/example-alias",       # any alias; the gateway translates non-Anthropic ones
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
    "domino/example-alias",
    provider=OpenAIProvider(base_url=f"{GATEWAY}/v1", api_key=token()),
)
agent = Agent(model)
print(agent.run_sync("Hello").output)
```

Rebuild the provider (or the agent) per batch of calls in a long-running process so the token stays fresh.

## LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="domino/example-alias", base_url=f"{GATEWAY}/v1", api_key=token())
print(llm.invoke("What is machine learning?").content)
```

## Plain HTTP

```python
r = requests.post(
    f"{GATEWAY}/v1/chat/completions",
    headers={"Authorization": f"Bearer {token()}", "X-LLM-Tag-team": "research"},
    json={"model": "domino/example-alias", "messages": [{"role": "user", "content": "Hello"}]},
    timeout=120,
)
r.raise_for_status()
print(r.json()["choices"][0]["message"]["content"])
```

## Streaming

```python
client = OpenAI(base_url=f"{GATEWAY}/v1", api_key=token())
with client.chat.completions.stream(model="domino/example-alias",
                                    messages=[{"role": "user", "content": "Write a haiku about the Alps"}]) as stream:
    for event in stream:
        if event.type == "content.delta":
            print(event.delta, end="", flush=True)
```

Or `stream=True` on `chat.completions.create` and read `chunk.choices[0].delta.content`. Both verified.

## Attribution headers

| Header | Effect |
|---|---|
| `X-LLM-Tag-<key>: <value>` | Caller-defined tag stored with the request and usable to slice usage in the gateway UI. Attribution only; never rely on it for access control. |
| `X-LLM-Tag-Bill-Org: <org id>` | For members of several organizations: bill this request against that organization's grant and budget. |
| `X-LLM-Api-Key: <provider key>` | Bring your own provider key, where the administrator has allowed it for the alias; the call is billed to your provider account. |

## Errors to expect

Observed on a live gateway unless marked otherwise.

- **302 redirect to the Domino login page (HTML)**: no bearer, a malformed or expired bearer, or a credential sent only as `x-api-key`. The Domino App proxy answers before the gateway sees the request, so there is no 401 here. Re-read the access token per call; with the Anthropic SDK use `auth_token=`.
- `404` with `"Model '<name>' not found"` (`invalid_request_error`; `not_found_error` on the Anthropic path): not an alias you can use. List `GET /v1/models` and use an exact id.
- `400` with `... not implemented` (`unsupported`): the alias is not the kind the route needs, for example a chat alias on `/v1/embeddings`.
- A `4xx` whose body names a grant, a budget or a guardrail rule: no access to the alias, the applicable budget is spent for its period, or a rule denied the prompt or response. Ask the administrator for access or budget, or change the prompt. (Not reproduced in testing; the test identity held every grant.)
- `403` such as `Only a gateway admin can manage gateway admins`: an administrator-only route; developers do not need those.
- `413` from the App proxy: the request body is too large (usually a very large tool result); trim it.
- `401 Token expired`: the gateway's own answer for an expired `dgw_` token; unverified, and reachable only if the token passes the App proxy.
- A `200` carrying `X-LLM-Fallback-Served-By` and `X-LLM-Fallback-Reason` headers: the administrator configured a fallback alias and it served the request (not observed; no fallback was configured).

## Tracing gateway calls

Gateway calls made with the OpenAI or Anthropic SDK are ordinary SDK calls, so MLflow autologging and the Domino agents SDK capture them with no gateway-specific work (verified: one trace per call):

```python
import mlflow
mlflow.openai.autolog()        # or mlflow.anthropic.autolog()
```

See the `domino-genai-tracing` skill, which has no dependency on the gateway. The gateway's own usage record (tokens, latency, estimated cost per request) is separate and visible to the administrator in the gateway UI.
