---
name: domino-python-sdk
description: Programmatically interact with Domino using python-domino SDK and REST APIs. Covers authentication, running jobs, managing projects, file operations, model deployment, and automation. Use when automating Domino workflows, integrating with CI/CD, or building custom tooling around Domino.
---

# Domino Python SDK Skill

## Description
This skill helps users work with the Domino Python SDK (python-domino) and REST APIs to programmatically interact with Domino.

## Activation
Activate this skill when users want to:
- Use the Domino Python SDK
- Make API calls to Domino
- Automate Domino workflows
- Integrate Domino with external systems
- Query Domino programmatically

## Overview

Domino provides two main programmatic interfaces:
- **python-domino**: Python SDK for common operations
- **REST API**: Full HTTP API for all Domino features

## Installation

### python-domino
```bash
# Install from PyPI
pip install dominodatalab

# Or install with extras
pip install "dominodatalab[data]"
```

### In Domino Environment
Add to requirements.txt:
```
dominodatalab>=1.4.0
```

Or Dockerfile:
```dockerfile
RUN pip install dominodatalab
```

## Authentication

Canonical guide: https://docs.domino.ai/cloud/reference/api/domino-api-authentication

**Do not use API keys** (`X-Domino-Api-Key`, `DOMINO_USER_API_KEY`, `api_key=`). Use PAT or service account tokens only when calling from **outside** a run.

### In-run (workspace, job, app backend)

Domino injects `DOMINO_USER_HOST` / `DOMINO_API_HOST` (same base; prefer `DOMINO_USER_HOST`). When JWT credential propagation is enabled, `DOMINO_API_PROXY` is the forwarded platform API base (not the same as `http://localhost:8899/access-token`).

| Pattern | When | Code |
|---------|------|------|
| **API proxy (preferred)** | `DOMINO_API_PROXY` is set (Domino **5.4.0+** in runs with JWT credential propagation configured) | Call `{DOMINO_API_PROXY}{path}` with **no** `Authorization` header. The JWT sidecar adds the **starting user** access JWT on the forwarded request. |
| **Access token + platform host** | Older deployments, or you intentionally call `DOMINO_USER_HOST` / `DOMINO_API_HOST` instead of the proxy URL | Fetch a short-lived JWT, then Bearer on the platform base. |

**API proxy (preferred on 5.4.0+):**

```python
import os
import requests

base_url = os.environ["DOMINO_API_PROXY"].rstrip("/")
headers = {}

response = requests.get(f"{base_url}/v4/users/self")
```

```bash
curl "$DOMINO_API_PROXY/v4/users/self"
```

The proxy is not guaranteed on every deployment or run type. If `DOMINO_API_PROXY` is missing, use the access-token pattern or PAT from outside the cluster.

**Access token + `DOMINO_USER_HOST` (legacy-friendly in-run):** use the [In-run setup block](#in-run-setup-block-for-examples-in-this-skill) below; it covers both proxy and access-token paths.

Pre-5.4.0 `DOMINO_TOKEN_FILE` legacy note: [API-REFERENCE.md](./API-REFERENCE.md#authentication).

### Outside a run (laptop, CI, cron outside Domino)

Your code is **not** executing inside a Domino workspace, job, or app container. Domino does **not** inject `DOMINO_API_PROXY`, `DOMINO_USER_HOST`, or an access-token sidecar. You must supply both:

1. **Base URL** — the deployment URL users open in the browser (HTTPS), for example `https://yourcompany.engineering.domino.tech`. Not `http://127.0.0.1:8763` and not values copied from an in-run environment.
2. **Credential** — `Authorization: Bearer` with a token you store securely (secret manager, CI variable, not committed to git):
   - **Personal Access Token (PAT)** when the automation acts as you. Create under Account settings or `POST /api/pat/v1/tokens` while already authenticated.
   - **Service account token** when a pipeline or integration runs without a human user. An admin provisions the service account and token.

```python
import requests

deployment_url = "https://yourcompany.engineering.domino.tech"
pat = "..."  # from your secret store; never hardcode in shared repos

response = requests.get(
    f"{deployment_url.rstrip('/')}/v4/users/self",
    headers={"Authorization": f"Bearer {pat}"},
)
```

See https://docs.domino.ai/cloud/reference/api/domino-api-authentication .

### In-run setup block (for examples in this skill)

Use inside a workspace, job, or app only:

```python
import os
import requests

if os.environ.get("DOMINO_API_PROXY"):
    base_url = os.environ["DOMINO_API_PROXY"].rstrip("/")
    headers = {}
else:
    base_url = (os.environ.get("DOMINO_USER_HOST") or os.environ.get("DOMINO_API_HOST") or "").rstrip("/")
    token = requests.get("http://localhost:8899/access-token").text.strip()
    headers = {"Authorization": f"Bearer {token}"}
```

### python-domino inside Domino

```python
from domino import Domino

domino = Domino("owner/project-name")
```

Configure the SDK with host + Bearer token per the product auth page. Never pass `api_key=`.

## Common Operations

python-domino calls for projects, jobs (runs), workspaces, files, datasets, environments and Model APIs, the separate Domino Data API client, CI/CD and batch automation examples, error handling, and retry/logging helpers: [SDK-EXAMPLES.md](./SDK-EXAMPLES.md).

## REST API

Quick `requests` example and the common-endpoint summary: [API-REFERENCE.md](./API-REFERENCE.md#quick-start). Per-area catalogs: [Reference files](#reference-files).

## Best Practices

### 1. Follow [Authentication](#authentication)
Proxy without a header when `DOMINO_API_PROXY` is set; otherwise access-token + platform host; PAT/SA only outside a run.

Rate-limit retry and API-call logging helpers: [SDK-EXAMPLES.md](./SDK-EXAMPLES.md#best-practices).

## Reference files

For comprehensive REST API documentation, see these specialized guides:

| Guide | Description |
|-------|-------------|
| [SDK-EXAMPLES.md](SDK-EXAMPLES.md) | python-domino common operations, Domino Data API, automation examples, error handling |
| [API-PROJECTS.md](API-PROJECTS.md) | Projects, collaborators, Git repos, goals |
| [API-JOBS.md](API-JOBS.md) | Jobs, scheduled jobs, logs, tags |
| [API-DATASETS.md](API-DATASETS.md) | Datasets, snapshots, tags, grants |
| [API-MODELS.md](API-MODELS.md) | Model APIs, deployments, registry |
| [API-MODEL-SERVING.md](API-MODEL-SERVING.md) | Lifecycle, v1/v2 registry split, invoke vs management |
| [API-ENVIRONMENTS.md](API-ENVIRONMENTS.md) | Environments, revisions, Dockerfile |
| [API-APPS.md](API-APPS.md) | Apps endpoint catalog (see [apps/API-APPS.md](../domino-apps/API-APPS.md) for v1 automation) |
| [API-ADMIN.md](API-ADMIN.md) | Users, orgs, hardware tiers, data sources |
| [API-REFERENCE.md](API-REFERENCE.md) | Complete endpoint reference |

## Documentation Reference

OpenAPI and route discovery: [API-SPECS.md](../domino-api-intro/API-SPECS.md).

**Product docs:**
- [Domino API authentication](https://docs.domino.ai/cloud/reference/api/domino-api-authentication)
- [python-domino Library](https://docs.domino.ai/cloud/reference/python-sdk/python-wrapper-for-domino-api)
- [GitHub Repository](https://github.com/dominodatalab/python-domino)
