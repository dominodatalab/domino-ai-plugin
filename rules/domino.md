---
trigger: always_on
description: "How to work with Domino Data Lab: documentation, authentication, version differences, and which Domino skills to use"
---

# Working with Domino Data Lab

Domino Data Lab is an enterprise platform for building, deploying and governing AI and ML systems. Docs: https://docs.domino.ai (Cloud under /cloud/, Domino 6.3 under /6.3/). https://docs.domino.ai/llms.txt indexes every page, appending .md to any page URL returns Markdown, and the domino_docs MCP server searches the same pages and OpenAPI specs. Auth: inside a Domino run call $DOMINO_API_PROXY/<path> with no Authorization header; outside a run send a Personal Access Token or service account token as Authorization: Bearer. Legacy API keys (X-Domino-Api-Key, DOMINO_USER_API_KEY) are deprecated. For API or SDK work read the domino-api-intro skill first.

## Finding documentation

- domino_docs tools: search_domino (query; optional version Cloud or 6.3), query_docs_filesystem_domino (read-only rg, cat, jq over pages and specs), submit_feedback (report a docs error).
- Public API specs: https://docs.domino.ai/api-specs/cloud/public-api.json and https://docs.domino.ai/api-specs/6.3/public-api.json. A deployment's own API reference: https://<domain>/docs.

## Authentication

- In a run (Workspace, Job, App) DOMINO_API_PROXY adds the user's token for you. A short-lived bearer is also served at http://localhost:8899/access-token.
- Outside a run: a Personal Access Token acts as you; a service account token is for pipelines.
- https://docs.domino.ai/cloud/reference/api/domino-api-authentication

## Which Domino

- GET $DOMINO_API_HOST/version returns JSON with a version key; no auth needed.
- A run injects DOMINO_API_HOST, DOMINO_PROJECT_ID, DOMINO_PROJECT_OWNER, DOMINO_PROJECT_NAME and DOMINO_RUN_ID.
- Cloud and 6.3 differ in places: 6.3 has the legacy AI Gateway, Cloud has LLM Gateway 2.0.

## Calling the API

- Prefer /api/... Public API routes. /v4/* routes are the Domino Internal API and may change between versions.
- Check the route exists in the target version's spec. List endpoints take offset and limit; a first page may be partial.

## Skills to use

domino-api-intro first for auth, hosts, pagination and errors, then the domain skill: domino-jobs (batch and scheduled runs), domino-workspaces (Jupyter, VS Code, RStudio), domino-apps (web apps behind the proxy), domino-datasets (versioned data, snapshots), domino-environments (compute environments), domino-projects (Git, collaboration), domino-experiment-tracking (MLflow runs, registry), domino-genai-tracing (LLM and agent traces), domino-model-endpoints (model APIs), domino-governance (policies, bundles, evidence), domino-python-sdk (python-domino, REST).

## Working safely

Running Jobs, Workspaces, clusters and endpoints incurs per-minute hardware-tier cost. Deleting a Workspace also deletes its snapshots, which cannot be recovered. Confirm with the user before starting large executions or deleting data.
