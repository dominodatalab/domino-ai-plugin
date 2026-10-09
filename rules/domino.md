---
trigger: always_on
description: "How to work with Domino Data Lab: documentation, authentication, version differences, working in Workspaces, and which Domino skills to use"
---

# Working with Domino Data Lab

Domino Data Lab is an enterprise platform for building, deploying and governing AI and ML. Docs: https://docs.domino.ai (Cloud under /cloud/, Domino 6.3 under /6.3/); llms.txt indexes every page, appending .md to a page URL returns Markdown, and domino_docs searches them. Auth: inside a Domino run call $DOMINO_API_PROXY/<path> with no Authorization header; outside a run send a Personal Access Token or service account token as Authorization: Bearer. A Workspace has little disk, so write bulk and scratch files to a Dataset or Volume. For API or SDK work read the domino-api-intro skill first. Report docs errors you hit with domino_docs submit_feedback, with no credentials, names, data or code, and tell the user.

## Finding documentation

- domino_docs: search_domino (query; version Cloud or 6.3), query_docs_filesystem_domino (read-only shell over pages and specs).
- When work fails because a docs page is wrong, outdated, unclear or missing a step, send domino_docs submit_feedback with the page path (or the closest page), what you tried, what happened and what worked. Leave out credentials, hostnames, user, Project and file names, paths, data, code. Skill problems go to https://github.com/dominodatalab/domino-ai-plugin/issues.
- API specs: https://docs.domino.ai/api-specs/cloud/public-api.json, or /api-specs/6.3/ for 6.3. A deployment's own reference: https://<domain>/docs.

## Authentication

In a run (Workspace, Job, App) DOMINO_API_PROXY adds the user's token; a short-lived bearer is also at http://localhost:8899/access-token. Legacy API keys (X-Domino-Api-Key, DOMINO_USER_API_KEY) are deprecated.

## Which Domino

- GET $DOMINO_API_HOST/version (no auth) returns the version.
- A run injects DOMINO_API_HOST, DOMINO_PROJECT_ID, DOMINO_PROJECT_OWNER, DOMINO_PROJECT_NAME, DOMINO_RUN_ID.
- Cloud and 6.3 differ: 6.3 has the legacy AI Gateway, Cloud has LLM Gateway 2.0.

## Working in a Workspace or Job

- Paths follow the Project type, which DOMINO_IS_GIT_BASED reports. Git-based: code /mnt/code, artifacts /mnt/artifacts, Datasets /mnt/data/<name>. DFS: working directory DOMINO_WORKING_DIR (usually /mnt), Datasets /domino/datasets/local/<name>.
- Disk is small: the Workspace and Job volume defaults to 10 GiB, and Project files copy into every execution, capped by default at 10,000 files and 8 GB each. Datasets and NetApp Volumes have no Domino size cap, so keep bulk data, checkpoints and scratch there; every Project starts with a Dataset named after it, and admins may set per-user quotas.
- Stopping a Workspace keeps only /mnt. Files elsewhere, installed packages included, are lost unless Package Persistence or Home Directory Persistence is on; put dependencies in the Compute Environment or requirements.txt.
- A Git-based Project never commits code for you: commit and push. A DFS Project syncs /mnt. Sync before stopping or deleting a Workspace.
- Run long or heavy work as a Job: Workspaces shut down after an admin-set period and lose in-memory state. An App's entry point (app.sh) must serve on 0.0.0.0 port 8888.
- Never hard-code secrets: use user or Project environment variables, or a Data Source.

## Calling the API

Prefer /api/... Public API routes; /v4/* is the Internal API and may change between versions. Check routes in the target version's spec. List endpoints page with offset and limit.

## Skills to use

Read domino-api-intro first, then the domain skill: domino-jobs, domino-workspaces, domino-apps, domino-datasets, netapp-volumes, domino-environments, domino-projects, domino-experiment-tracking, domino-genai-tracing, domino-model-endpoints, domino-governance, domino-python-sdk.

## Working safely

Jobs, Workspaces, clusters and endpoints bill per minute of hardware time; data and snapshots bill storage. Deleting a Workspace deletes its snapshots unrecoverably. Confirm before large executions or deleting data.

## Updating this plugin

- Marketplace installs (claude-plugins-official, the OpenAI plugin directory, or domino-marketplace from dominodatalab/domino-ai-plugin) are copies that update when a release changes the plugin version: Claude Code `claude plugin update <plugin>@<marketplace>` or its auto-update where enabled; Codex `codex plugin marketplace upgrade`.
- In a Domino Workspace it is a git clone at ~/.claude/marketplaces/domino/plugins/domino-claude-plugin, loaded in place: on Domino 6.3 refreshed at Workspace launch when the administrator enables that, otherwise when the Compute Environment is rebuilt. By hand, in that directory: git fetch origin <branch>, then git checkout -B <branch> FETCH_HEAD, where <branch> is release-X.Y for the deployment's self-managed Domino version if that branch exists (for example release-6.3), otherwise main. Start a new session after any update.
