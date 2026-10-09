---
trigger: always_on
alwaysApply: true
description: "Domino Data Lab: API proxy auth, where to write code, artifacts and data, environment variables, docs and feedback"
---

Domino Data Lab. When DOMINO_API_PROXY is set (Workspace, Job, App, endpoint), call $DOMINO_API_PROXY/<path> with no Authorization header; the proxy adds the user's token ($DOMINO_API_PROXY/access-token returns it). Outside Domino send a Personal Access Token as Authorization: Bearer <token>. API keys (X-Domino-Api-Key, DOMINO_USER_API_KEY) are deprecated. Never print or hard-code tokens.
/mnt is the execution volume: small (10 GiB default), kept across a Workspace stop. Bulk and scratch go in a Dataset or Volume; all else is lost.
Check the docs: domino_docs MCP (search_domino, version Cloud or 6.3; query_docs_filesystem_domino) or https://docs.domino.ai/llms.txt (page URL + .md gives Markdown).
If a docs page is wrong or incomplete, propose feedback and ask; only after a yes call domino_docs submit_feedback (path, feedback) with no credentials, hostnames, names, paths, data or code.

## Paths

DOMINO_IS_GIT_BASED selects the row; DOMINO_WORKING_DIR, DOMINO_ARTIFACTS_DIR, DOMINO_DATASETS_DIR, DOMINO_IMPORTED_CODE_DIR and DOMINO_IMPORTED_DATA_DIR hold the actual mounts.

| | Git-based (true) | DFS (false) |
|-|-|-|
| Code | /mnt/code: commit and push, never auto-committed | /mnt: synced on Workspace sync or Job end |
| Artifacts (outputs to keep) | /mnt/artifacts | with the code |
| Project Datasets | /mnt/data/<name> | /domino/datasets/local/<name> |
| Imported Datasets | /mnt/imported/data/<name> | /domino/datasets/<name> |
| Imported Git repos | /mnt/imported/code/<repo> | /repos/<repo> |
| NetApp Volumes | /mnt/netapp-volumes/<name> | /domino/netapp-volumes/<name> |

- Bulk data, checkpoints and scratch go in a Dataset or Volume (no Domino size cap), not in code or artifacts; the execution volume defaults to 10 GiB.
- Snapshots mount read-only under .../snapshots/<name>/; write to the live path.
- A Workspace stop keeps /mnt only; home directory and installed packages are lost unless Package or Home Directory Persistence is on. Apps and endpoints never sync files back: write to a Dataset.

## Environment variables

- DOMINO_PROJECT_ID, DOMINO_PROJECT_OWNER, DOMINO_PROJECT_NAME: the current Project.
- User and Project variables (credentials, config) are also set: run env before asking for a secret.
