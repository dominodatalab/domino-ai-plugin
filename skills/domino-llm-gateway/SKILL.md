---
name: domino-llm-gateway
description: Call Large Language Models through Domino LLM Gateway 2.0, the centrally governed gateway an administrator deploys as a Domino App in front of external providers and Domino-hosted models. Covers the gateway base URL, authentication with the in-run access token (fresh per call) or a Personal Access Token or gateway token outside Domino, model aliases and model discovery, the OpenAI-compatible and Anthropic-compatible paths from the OpenAI and Anthropic SDKs, Pydantic AI, LangChain and plain HTTP, streaming, attribution headers, refused calls (grants, budgets, guardrails), pointing a coding assistant such as Claude Code at the gateway, and what the administrator configures. Use when a user mentions LLM Gateway, Gateway 2.0, a gateway alias or URL, asks how to call a model through the Domino gateway, how to run a coding assistant through it, why a gateway call was refused, or what the gateway administrator must set up.
compatibility: Domino 6.3 and Domino Cloud, only where an administrator has deployed LLM Gateway 2.0 (early access) as a Domino App. Inside a Domino execution the bearer is the access token from DOMINO_API_PROXY/access-token (localhost:8899), re-read per call; outside Domino a Personal Access Token or a gateway-issued token. Legacy user API keys are not used.
---

# Domino LLM Gateway 2.0

Applies to Domino 6.3 and Domino Cloud, where an administrator has deployed LLM Gateway 2.0. It is in early access and not part of every deployment: Domino distributes it as a Domino App through the Domino field representative. If nobody has deployed it, say so and use the `domino-llm-access` skill (a Domino-hosted endpoint or a provider SDK); do not try to install it.

## What the gateway is

One base URL in front of many providers (external LLM vendors and Domino-hosted model endpoints). Provider keys stay in the gateway; callers authenticate with their Domino identity. Every request is tracked by user, Project and model with its tokens, latency and estimated cost; administrators grant access per **model alias**, set per-team and per-model budgets, and screen prompts and responses with guardrails. It replaces the legacy AI Gateway (removed from Cloud, disabled by default on 6.3).

## Base URL

The gateway is a Domino App, so its base is the App's URL as shown on its page in Domino, for example `https://<domino or apps host>/apps/<app id or vanity URL>`. Every API path hangs off that base:

| Family | Path | Use with |
|---|---|---|
| OpenAI-compatible | `<base>/v1` (`/models`, `/chat/completions`, `/embeddings`, `/responses`) | OpenAI SDK, Pydantic AI, LangChain, any OpenAI-style client |
| Anthropic-compatible | `<base>/anthropic` (`/v1/messages`) | Anthropic SDK, Claude Code |

Ask the user for the gateway URL if it is not in a Project environment variable such as `LLM_GATEWAY_URL` (not a `DOMINO_`-prefixed name: Domino reserves that prefix for its own variables, https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/manage-compute-environments/manage-environment-variables#reserved-variable-names-in-domino). An HTML error page at the base means the App is not deployed, not running, or the URL is wrong; say so instead of retrying.

## Authentication

Send `Authorization: Bearer <token>` on every request; `model` is always an alias name, never a vendor model name.

- **Inside a Domino Workspace, Job or App:** read the access token from `$DOMINO_API_PROXY/access-token` (the sidecar at `http://localhost:8899/access-token`). It is short-lived, so re-read it before every request instead of caching it in a long-running process.
- **Outside Domino (laptop, CI):** a Domino Personal Access Token, or a gateway token (prefix `dgw_`) an administrator issues in the gateway's Tokens page; both are static, so keep them in an environment variable. An expired gateway token gets `401 Token expired`.
- Legacy user API keys are deprecated and not used. The Anthropic path takes the bearer in `Authorization`, not `x-api-key`.

```python
import os
import requests
from openai import OpenAI

GATEWAY = os.environ["LLM_GATEWAY_URL"].rstrip("/")

def token() -> str:
    proxy = os.environ.get("DOMINO_API_PROXY")
    if proxy:                                         # inside Domino: fresh per call
        return requests.get(f"{proxy}/access-token", timeout=5).text.strip()
    return os.environ["LLM_GATEWAY_TOKEN"]        # outside: PAT or dgw_ token

def chat(messages, model="my-gateway-alias", **kwargs) -> str:
    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key=token())
    return client.chat.completions.create(model=model, messages=messages, **kwargs).choices[0].message.content
```

## Discover models

`GET <base>/v1/models` returns the OpenAI list shape (`data[].id`) with the aliases the caller may use.

## Call it

- OpenAI SDK, Responses API, embeddings, Pydantic AI, LangChain, plain HTTP and streaming: [CALLING-MODELS.md](./CALLING-MODELS.md).
- Anthropic SDK: `Anthropic(base_url=f"{GATEWAY}/anthropic", auth_token=token())`, then `client.messages.create(model="<alias>", ...)`.
- Attribution: `X-LLM-Tag-<key>: <value>` headers (for example `X-LLM-Tag-team: research`) slice usage; they are labels, not access control.
- Tracing: OpenAI and Anthropic SDK calls are autologged by `mlflow.openai.autolog()` / `mlflow.anthropic.autolog()`, so the `domino-genai-tracing` skill works unchanged.

## When a call is refused

Read the response body; the gateway says what refused the call. A `401` is a missing or expired bearer (re-read the access token per call; `401 Token expired` is an expired gateway token; the Anthropic path refuses a credential sent as `x-api-key`). A `4xx` whose body names a grant, a budget or a guardrail rule means no access to the alias, a spent budget for the period, or a denied prompt or response: ask the administrator for access or budget, or change the prompt. `403 Admin access required` is an administrator-only route. An error on `model` means it is not an alias you can use. `413` from the App proxy means the body is too large. Details and the fallback headers: [CALLING-MODELS.md](./CALLING-MODELS.md#errors-to-expect).

## Coding assistants through the gateway

A coding assistant that accepts a custom Anthropic- or OpenAI-compatible base URL and a bearer token can be pointed at the gateway, so its model calls fall under the same grants, budgets and guardrails: [CODING-ASSISTANTS.md](./CODING-ASSISTANTS.md). The public docs send users to their Domino field representative for the routing details.

## What the administrator configures

Providers, model aliases, access grants and budgets, guardrails, gateway tokens, and the usage and audit views, all in the gateway UI: [ADMIN-OVERVIEW.md](./ADMIN-OVERVIEW.md). Installation and operation are the administrator's domain; point them to the Domino field representative.

## Documentation

- LLM Gateway 2.0: https://docs.domino.ai/cloud/platform-capabilities/features/llms/llm-gateway
- Set up LLM access: https://docs.domino.ai/cloud/platform-capabilities/features/llms (6.3: replace `cloud` with `6.3`)
- Coding assistants and the gateway: https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/reuse-credentials#use-with-domino-llm-gateway-2-0
- Authentication: https://docs.domino.ai/cloud/reference/api/domino-api-authentication
