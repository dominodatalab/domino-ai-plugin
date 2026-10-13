# Coding assistants through LLM Gateway 2.0

Routing a coding assistant through the gateway puts its model calls under the same grants, budgets, guardrails and usage tracking as any other call.

**Offer it, never impose it.** Where the extension is installed, ask the user whether they want the assistant routed through the gateway or kept on the vendor sign-in the Domino Standard Environment supports (the `domino-workspaces` skill covers that sign-in). Do not switch to the gateway unless they choose it. Docs: https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/reuse-credentials#use-with-domino-llm-gateway-2-0. Below: the configuration in the assistant's own settings, for Claude Code and Codex.

Shared facts:

- `<base>` is the gateway App's URL and `<alias>` an alias from `GET <base>/v1/models`, possibly prefixed such as `domino/<name>` ([SKILL.md](./SKILL.md#find-and-detect-the-gateway)); nothing is injected into a Workspace.
- Inside a Workspace the bearer is the access token from `$DOMINO_API_PROXY/access-token` (`http://localhost:8899/access-token`). It is short-lived, so the assistant needs a credential helper that re-fetches it, not a pasted value.
- On a laptop the bearer is a Domino bearer the user stored, for example a Personal Access Token ([SKILL.md](./SKILL.md#authentication)).
- Assistants make many small requests per turn, so a tight per-user budget refuses them mid-session; plan budgets accordingly.

## Claude Code

Claude Code uses the gateway's Anthropic-compatible path. Its own gateway documentation (https://code.claude.com/docs/en/llm-gateway-connect) defines the three pieces used here: `ANTHROPIC_BASE_URL`, a credential (`apiKeyHelper` for one that rotates, or `ANTHROPIC_AUTH_TOKEN` for a static bearer), and the model name.

### In a Workspace

Use `apiKeyHelper`, which runs a command and sends its output as the bearer. Put it in the project-local settings file, which Claude Code reads when started inside the project directory and keeps out of git (add `.claude/settings.local.json` to `.gitignore` if you create it by hand). Do not overwrite `~/.claude/settings.json`: on environments with home-directory persistence it holds the user's other settings.

```bash
mkdir -p "$DOMINO_WORKING_DIR/.claude"
cat > "$DOMINO_WORKING_DIR/.claude/settings.local.json" <<'EOF'
{
  "env": {
    "ANTHROPIC_BASE_URL": "<base>/anthropic",
    "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "60000"
  },
  "apiKeyHelper": "curl -sf http://localhost:8899/access-token"
}
EOF
cd "$DOMINO_WORKING_DIR" && claude --model <alias>
```

Claude Code prints `[claude-code:unrecognized_model]` for a gateway alias; it is a warning only. Confirm the routing in the gateway's usage view: each turn appears as a request for the alias.

How the helper behaves (Claude Code settings reference): the output is cached for five minutes by default, or for `CLAUDE_CODE_API_KEY_HELPER_TTL_MS`; it is re-run after that lifetime, when a request fails with 401 or 403, and (from v2.1.246) when the cached output is a JWT that has expired. Set the TTL below the access token's lifetime so a stale token is not sent. The helper's output is sent as both the `Authorization: Bearer` and `X-Api-Key` headers; the gateway reads the bearer (bearer plus `x-api-key` together is accepted).

Credential precedence matters. Claude Code's documented order is `ANTHROPIC_AUTH_TOKEN`, then `ANTHROPIC_API_KEY`, then `apiKeyHelper`, then `CLAUDE_CODE_OAUTH_TOKEN`: a set `ANTHROPIC_AUTH_TOKEN` is used instead of the helper, and a set `ANTHROPIC_API_KEY` outranks the helper too and is sent only as `x-api-key`, which the App proxy treats as no credential (a 302 to the login page, not a clear error). Before starting a gateway session, unset both in the shell and check that no Domino user, Project or environment variable sets them (`CLAUDE_CODE_OAUTH_TOKEN` ranks below the helper and is not a problem). Run `/status` in Claude Code to confirm the `Anthropic base URL` line shows the gateway and the credential line names the `apiKeyHelper`.

For a whole team, an administrator can set `ANTHROPIC_BASE_URL` as a Domino environment variable (in the UI or with the routes in [domino-api-intro](../domino-api-intro/SKILL.md#environment-variables-as-the-secret-store)) and write the project-local settings file from the Compute Environment's pre-run script, writing it only when absent or merging with `jq` so a user's existing project settings survive, and only for users who opted in. Optional attribution: `ANTHROPIC_CUSTOM_HEADERS="X-LLM-Tag-projectname: $DOMINO_PROJECT_NAME"` tags every request with the Project.

### From a laptop

```bash
export ANTHROPIC_BASE_URL="<base>/anthropic"
export ANTHROPIC_AUTH_TOKEN="<a Domino bearer the user stored, for example a Personal Access Token>"
claude --model <alias>
```

Verify first with the one-token request from the Claude Code gateway page (`POST $ANTHROPIC_BASE_URL/v1/messages` with `Authorization: Bearer`); a `404` naming an unknown model still proves the URL and credential work, while a 302 to the Domino login page means the bearer was not accepted.

### Claude Code specifics

- Claude Code may also call a smaller model for background work (titles, summaries) by that model's own name. If the gateway has no alias of that exact name, those calls would fail quietly and only the main conversation works; ask the administrator to publish an alias with that name if titles and summaries matter.
- Which Anthropic features reach the model (prompt caching, extended thinking, native tool use) depends on the provider behind the alias; a non-Anthropic alias works through the Anthropic path with the gateway translating. Ask the administrator what the alias is backed by.

## Codex

Codex uses the gateway's OpenAI-compatible path with its Responses wire protocol. Its configuration reference (https://developers.openai.com/codex/config-reference) defines the pieces used here: an entry in the `model_providers` table (`base_url`, `wire_api`, and either `env_key` or a command-backed `auth` table), `model_provider` to select that entry, and `model` for the alias.

Where the provider entry can live: `~/.codex/config.toml` (user-level; `CODEX_HOME` moves the directory), or a profile file beside it, `~/.codex/<name>.config.toml`, which Codex layers over `config.toml` only when started with `-p <name>`. Codex ignores `model_provider` and `model_providers` in a project-local `.codex/config.toml`, so a project-local file cannot do for Codex what `.claude/settings.local.json` does for Claude Code; the profile file is the equivalent. The user's own settings and sign-in stay untouched, and omitting `-p` switches back.

### In a Workspace

The in-run access token is short-lived, so the provider gets a command-backed `auth` table that re-runs `curl` against the sidecar. Codex refreshes that credential every `refresh_interval_ms`, 300000 by default, which can exceed the token's lifetime; set it lower so a stale token is never sent. Do not combine `auth` with `env_key`.

```bash
cat > ~/.codex/domino.config.toml <<'EOF'
model_provider = "domino"
model = "<alias>"

[model_providers.domino]
name = "Domino LLM Gateway"
base_url = "<base>/v1"
wire_api = "responses"
env_http_headers = { "X-LLM-Tag-projectname" = "DOMINO_PROJECT_NAME" }

[model_providers.domino.auth]
command = "curl"
args = ["-sf", "http://localhost:8899/access-token"]
refresh_interval_ms = 120000
EOF
cd "$DOMINO_WORKING_DIR" && codex -p domino
```

`~/.codex` in a Workspace holds the user's Codex skills and sessions and, on environments with home-directory persistence, their `config.toml`; add the profile file beside it rather than replacing `config.toml`. `env_http_headers` sends an environment variable's value as a request header, so every request carries the Project name as the gateway tag `projectname` (optional; `http_headers` sends a fixed value instead). The one-shot check is `codex exec -p domino "Reply OK"`; confirm the routing in the gateway's usage view, where each turn appears as a request for the alias.

Two lines in Codex's output are expected and harmless: `warning: Model metadata for '<alias>' not found. Defaulting to fallback metadata` (Codex has no built-in limits for a gateway alias; set `model_context_window` in the profile if the alias's backing model has a known window) and `ERROR ... failed to refresh available models ... failed to decode models response` (Codex asks the provider for a model list in a format the gateway does not return; the session continues). No `codex login` is needed for the gateway: the provider entry carries its own credential and `requires_openai_auth` stays off.

For a whole team, an administrator can write the profile file from the Compute Environment's pre-run script, taking `<base>` from `LLM_GATEWAY_URL`, only for users who opted in and only when the file is absent.

### From a laptop

The same profile file, with `env_key` in place of the `auth` table and the bearer in that variable:

```toml
model_provider = "domino"
model = "<alias>"

[model_providers.domino]
name = "Domino LLM Gateway"
base_url = "<base>/v1"
wire_api = "responses"
env_key = "LLM_GATEWAY_TOKEN"
```

```bash
export LLM_GATEWAY_TOKEN="<a Domino bearer the user stored, for example a Personal Access Token>"
codex -p domino
```

A credential that rotates on the laptop uses the `auth` table instead, with `command` set to a script that prints the bearer. Verify the URL and bearer first with `GET <base>/v1/models`, which also lists the aliases to choose from.

### Codex specifics

- Codex sends every turn to `<base>/v1/responses`, streamed, with its tool definitions and a prompt of several thousand tokens; prompt-token counts in the usage view reflect that, and a per-user budget sized for chat requests refuses Codex quickly.
- `codex exec -m <alias>` or `-c model=<alias>` picks another alias for one run. `codex --help` listing `-p, --profile` confirms the installed Codex supports profile files.
- Which model features reach the model (reasoning, tool calls) depends on the provider behind the alias; ask the administrator what the alias is backed by.

## Other hosts

Any assistant that accepts an OpenAI-compatible base URL (`<base>/v1`) or an Anthropic-compatible one (`<base>/anthropic`) plus a bearer token can be pointed at the gateway: configure it the way that host documents, with the alias as the model and, inside Domino, a credential helper rather than a pasted token. Hosts that cannot change their API endpoint, or that only accept their vendor's own key, cannot be routed through the gateway.
