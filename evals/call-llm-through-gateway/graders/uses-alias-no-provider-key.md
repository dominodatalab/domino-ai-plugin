---
type: llm
---

PASS if the rewritten `ask.py` sends requests to the gateway URL taken from the `LLM_GATEWAY_URL` environment variable (with `/v1` for an OpenAI-style client), uses the alias `support-llm` as the model, authenticates with a bearer token read from the Domino access-token endpoint (`$DOMINO_API_PROXY/access-token` or `http://localhost:8899/access-token`) at call time rather than once at import, and no longer reads `OPENAI_API_KEY` or any other provider key.
FAIL if a provider API key remains in the code, if the model is still a vendor model name, if the token is fetched once and cached for the life of the process, or if a legacy Domino user API key (`DOMINO_USER_API_KEY`, `X-Domino-Api-Key`) is used.
