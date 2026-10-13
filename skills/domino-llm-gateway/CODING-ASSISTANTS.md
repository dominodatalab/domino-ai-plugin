# Coding assistants through LLM Gateway 2.0

Applies to Domino 6.3 and Domino Cloud where an administrator has installed the LLM Gateway 2.0 extension (early access). Routing a coding assistant through the gateway puts its model calls under the same grants, budgets, guardrails and usage tracking as any other call.

**Offer it, never impose it.** Where the extension is installed, ask the user whether they want the assistant routed through the gateway or kept on the vendor sign-in the Domino Standard Environment supports (the `domino-workspaces` skill covers that sign-in). Do not switch to the gateway unless they choose it. The public docs (https://docs.domino.ai/cloud/platform-capabilities/features/coding-assistants/reuse-credentials#use-with-domino-llm-gateway-2-0) say the routing is possible and send users to their Domino field representative for the recommended setup; what follows is the generic configuration in the assistant's own documented settings, for Claude Code from a Workspace.

Shared facts:

- The extension injects nothing: no `ANTHROPIC_*` or `OPENAI_*` variable appears in a Workspace. `<base>` is the gateway App's URL (from `LLM_GATEWAY_URL` if the user created it, else asked for); `<alias>` is an alias from `GET <base>/v1/models`, possibly prefixed such as `domino/<name>`.
- Inside a Workspace the bearer is the access token from `$DOMINO_API_PROXY/access-token` (`http://localhost:8899/access-token`). It is short-lived, so the assistant needs a credential helper that re-fetches it, not a pasted value.
- On a laptop the bearer is a Domino bearer the user stored, for example a Personal Access Token; a `dgw_` gateway token may not pass the App login redirect, so if the assistant is answered with a login page or 401, use a Domino bearer.
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

Exactly this, with `--model domino/<alias>`, answered through the gateway from a DSE Workspace (the call appeared in the gateway's usage log; no other credential existed). Claude Code prints `[claude-code:unrecognized_model]` for a gateway alias; it is a warning only.

How the helper behaves (Claude Code settings reference): the output is cached for five minutes by default, or for `CLAUDE_CODE_API_KEY_HELPER_TTL_MS`; it is re-run after that lifetime, when a request fails with 401 or 403, and (from v2.1.246) when the cached output is a JWT that has expired. Set the TTL below the access token's lifetime so a stale token is not sent. The helper's output is sent as both the `Authorization: Bearer` and `X-Api-Key` headers; the gateway reads the bearer (bearer plus `x-api-key` together is accepted).

Credential precedence matters. Claude Code's documented order is `ANTHROPIC_AUTH_TOKEN`, then `ANTHROPIC_API_KEY`, then `apiKeyHelper`, then `CLAUDE_CODE_OAUTH_TOKEN`: a set `ANTHROPIC_AUTH_TOKEN` is used instead of the helper, and a set `ANTHROPIC_API_KEY` outranks the helper too and is sent only as `x-api-key`, which the App proxy treats as no credential (a 302 to the login page, not a clear error). Before starting a gateway session, unset both in the shell and check that no Domino user, Project or environment variable sets them (`CLAUDE_CODE_OAUTH_TOKEN` ranks below the helper and is not a problem). Run `/status` in Claude Code to confirm the `Anthropic base URL` line shows the gateway and the credential line names the `apiKeyHelper`.

For a whole team, an administrator can set `ANTHROPIC_BASE_URL` as a Domino environment variable (in the UI or with the routes in [domino-api-intro](../domino-api-intro/SKILL.md#environment-variables-as-the-secret-store)) and write the project-local settings file from the Compute Environment's pre-run script (the mechanism the reuse-credentials page describes), writing it only when absent or merging with `jq` so a user's existing project settings survive, and only for users who opted in. Optional attribution: `ANTHROPIC_CUSTOM_HEADERS="X-LLM-Tag-projectname: $DOMINO_PROJECT_NAME"` tags every request with the Project.

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

## Other hosts

Any assistant that accepts an OpenAI-compatible base URL (`<base>/v1`) or an Anthropic-compatible one (`<base>/anthropic`) plus a bearer token can be pointed at the gateway: configure it the way that host documents, with the alias as the model and, inside Domino, a credential helper rather than a pasted token. Codex, for example, supports custom model providers in its configuration, but routing Codex through the gateway has not been tested; ask the Domino field representative before relying on it. Hosts that cannot change their API endpoint, or that only accept their vendor's own key, cannot be routed through the gateway.
