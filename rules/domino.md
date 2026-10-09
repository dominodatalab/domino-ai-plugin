---
trigger: always_on
description: "Domino Data Lab: API proxy auth, environment variables, docs and feedback"
---

Domino Data Lab. In an execution (Workspace, Job, App, endpoint) with DOMINO_API_PROXY set, call $DOMINO_API_PROXY/<path> with no Authorization header; the proxy adds the user's token. $DOMINO_API_PROXY/access-token returns that bearer token when needed. Outside Domino send a Personal Access Token as Authorization: Bearer <token> to the deployment URL. API keys (X-Domino-Api-Key, DOMINO_USER_API_KEY) are deprecated. Never print or hard-code tokens.
Check the docs rather than guess: domino_docs MCP server (search_domino, version Cloud or 6.3; query_docs_filesystem_domino) or https://docs.domino.ai/llms.txt (page URL + .md gives Markdown).
If a docs page is wrong, outdated or missing a step, recommend feedback and ask the user; only after a yes call domino_docs submit_feedback (path, feedback) with no credentials, hostnames, names, paths, data or code.

## Environment variables

- DOMINO_PROJECT_ID, DOMINO_PROJECT_OWNER, DOMINO_PROJECT_NAME: the current Project.
- DOMINO_IS_GIT_BASED: true, code is a Git repo (commit and push); false, files sync from DOMINO_WORKING_DIR.
- DOMINO_DATASETS_DIR, DOMINO_ARTIFACTS_DIR: Dataset and Artifact mounts.
- User and Project variables (credentials, config) are also set: run env before asking for a secret.

The execution volume is small: keep large or scratch files in a Dataset (DOMINO_DATASETS_DIR) or a NetApp Volume.
