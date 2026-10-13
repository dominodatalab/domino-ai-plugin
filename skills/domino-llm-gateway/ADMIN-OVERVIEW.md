# LLM Gateway 2.0: what the administrator configures

Applies to Domino 6.3 and Domino Cloud where an administrator has installed the LLM Gateway 2.0 extension. It is installed separately and updated out of band, so its availability and version depend on the installation, not on the Domino version (early access; public starting point: https://docs.domino.ai/cloud/platform-capabilities/features/llms/llm-gateway).

Everything below happens in the gateway's own UI, by the gateway's owner or an administrator; a developer does not need any of it to call a model, only to understand why a call is refused.

- **Providers and aliases.** The administrator connects upstream providers (external LLM vendors and Domino-hosted model endpoints) and publishes **model aliases**, possibly under a prefix such as `domino/`. An alias is the name callers pass as `model`; which vendor model sits behind it is the administrator's choice and can change without callers changing code. Callers see only the aliases they are granted (`GET <base>/v1/models`), which can be far fewer than the catalog.
- **Access and budgets.** Access is granted per alias to users, organizations or everyone; a grant can carry a budget for a period, and an alias can carry an overall budget. A call to an alias the caller has no grant for, or whose budget is spent, is refused with a message that says so; the caller asks the administrator for access or budget.
- **Guardrails.** The administrator can screen prompts and responses at call time with rules whose outcome is to deny, redact or log. A denied call returns an error naming the rule; redaction changes the content. This is separate from scoring finished traces with evaluators (`domino-genai-tracing` skill).
- **Usage and audit.** The gateway records every request (user, Project, alias, tokens, latency, estimated cost) and every configuration change; the administrator reads them in the gateway UI and can attribute spend by the tags callers send (`X-LLM-Tag-<key>` headers).
- **Tokens for use outside Domino.** The administrator can issue gateway tokens (prefix `dgw_`) with an expiry for scripts, CI and laptops. A Domino access token passes the App proxy from outside Domino; if a gateway token or a Personal Access Token is answered with a login page or 401, use a Domino access token instead. Inside Domino nobody needs either: the access token from the sidecar is the bearer.

Installing, updating and operating the extension are not covered by this skill; point administrators to the material Domino provides with the gateway.
