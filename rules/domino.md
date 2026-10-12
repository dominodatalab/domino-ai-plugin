---
trigger: always_on
alwaysApply: true
description: "Domino Data Lab: API proxy auth, where to write code, artifacts and data, environment variables, docs and feedback"
---

Domino Data Lab. Inside Domino (DOMINO_API_PROXY set), call $DOMINO_API_PROXY/<path> with no Authorization header; the proxy adds your token (/access-token returns it). Outside Domino use a Personal Access Token as Authorization: Bearer. API keys (X-Domino-Api-Key, DOMINO_USER_API_KEY) are deprecated; never print or hard-code tokens.
DOMINO_WORKING_DIR (and /mnt/artifacts if Git-based) is small and kept across a stop; bulk and scratch go in a Dataset or Volume; all else is lost.
Load the matching domino-* skill before searching the docs; its recipes are tested on live clusters.
Docs: domino_docs MCP (search_domino, version Cloud or 6.3; query_docs_filesystem_domino) or https://docs.domino.ai/llms.txt (.md for Markdown).
If a docs page is wrong, propose feedback and ask; only after a yes call submit_feedback (path, feedback) with no credentials, hostnames, names, paths, data or code.

## Paths

DOMINO_IS_GIT_BASED selects the column; DOMINO_WORKING_DIR, DOMINO_ARTIFACTS_DIR (unset in DFS), DOMINO_DATASETS_DIR, DOMINO_IMPORTED_CODE_DIR and DOMINO_IMPORTED_DATA_DIR hold the actual mounts when set.

| | Git-based (true) | DFS (false) |
|-|-|-|
| Code | /mnt/code: commit and push, never auto-committed | /mnt: synced on Workspace sync or Job end |
| Artifacts (outputs to keep) | /mnt/artifacts | with the code |
| Project Datasets | /mnt/data/<name> | /domino/datasets/local/<name> |
| Imported Datasets | /mnt/imported/data/<name> | /domino/datasets/<name> |
| Imported Git repos | /mnt/imported/code/<repo> | /repos/<repo> |
| NetApp Volumes | /mnt/netapp-volumes/<name> | /domino/netapp-volumes/<name> |

- Bulk data, checkpoints and scratch go in a Dataset or Volume (no Domino size cap), not in code or artifacts; the execution volume is admin-set, often 10 GiB (df -h $DOMINO_WORKING_DIR).
- Snapshots mount read-only under .../snapshots/<name>/; write to the live path.
- A Workspace stop keeps only the Code and Artifacts paths above; home directory and installed packages are lost unless Package or Home Directory Persistence is on. Apps and endpoints never sync files back: write to a Dataset.

## Environment variables

- DOMINO_PROJECT_ID, DOMINO_PROJECT_OWNER, DOMINO_PROJECT_NAME: the current Project.
- User and Project variables (credentials, config) are also set. Check by name only, e.g. env | cut -d= -f1 | grep -i NAME or [ -n "$NAME" ] && echo set; never print values or dump env.
