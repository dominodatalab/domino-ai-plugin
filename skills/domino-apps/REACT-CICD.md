# CI/CD for a React app on Domino with GitHub Actions

A push to `uat` or `main` builds the app and deploys it to a Domino project through the Public API. Domino runs `app.sh` (which installs and builds) when the App starts; CI creates the App once, then creates and starts a new version on every push.

## Architecture

```
dev branch  -> workspace (App Preview, manual test)
uat branch  -> GitHub Action -> UAT project:  new App version, started
main branch -> GitHub Action -> Prod project: new App version, started
```

## One-time setup in Domino (done by a person in the UI)

1. **Identity.** Ask a Domino admin for a service account and a token (https://docs.domino.ai/cloud/admin/identity-and-access/manage-users/service-accounts). A Personal Access Token works for a pipeline that should act as you; a service account is the right identity for CI. Two things from that page matter here: a service account inherits the roles of the admin who created it, so have the admin trim its roles before generating the token (the token captures the roles at creation); and tokens expire after four months by default, so plan to rotate `DOMINO_TOKEN`. Legacy user API keys are deprecated; do not use `DOMINO_USER_API_KEY`.
2. **Git credential for the service account.** Git credentials are per account. Because the service account starts every App instance, the admin adds a token Git credential that can read this repository to the service account itself (same page, "Add Git credentials to a service account"; API `POST /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/tokengitcredentials`, present in both specs). Use a read-only GitHub token.
3. **Projects.** Create the UAT and production projects as Git-based projects whose main repository is this GitHub repository (https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/link-github-account-to-domino for the human's own credential). Add the service account as a collaborator with edit rights on both projects. (`POST /api/projects/v2/projects` with `mainRepository.uri`, `serviceProvider` and `gitCredentialId` automates this; not covered here.)
4. **Environment variables.** In each project's settings add `MODEL_API_URL` and `MODEL_API_TOKEN` (a Model Access Token from the endpoint's **Settings > Invocation**). The App reads them at start; they never pass through GitHub.
5. **IDs.** Note the Compute Environment ID (the environment must contain Node) and the Hardware Tier ID. `GET /api/environments/beta/environments` and `GET /api/hardwaretiers/v1/hardwaretiers` list them.

## Repository layout

```
.
├── app-code/                 # Vite app: src/, vite.config.js, package.json, server.js
├── app.sh                    # Domino entry point; builds and serves app-code/
├── cicd/deploy_app.py
└── .github/workflows/deploy.yml
```

```bash
#!/bin/bash
# app.sh (repo root); the Vite app lives in app-code/
set -e
cd "$(dirname "$0")/app-code"
npm ci                  # needs npm registry egress or a private mirror in .npmrc
npm run build
node server.js          # or: npx serve -s dist -l 8888 --no-clipboard
```

## GitHub configuration

| Kind | Name | Value |
|---|---|---|
| Secret | `DOMINO_TOKEN` | Service account token (or a PAT) |
| Variable | `DOMINO_URL` | Public URL of the deployment (what you open in the browser), no trailing slash |
| Variable | `PROJECT_NAME` | Domino project name (`-uat` suffix in the UAT environment) |
| Variable | `PROJECT_OWNER` | Username of the project owner |
| Variable | `APP_NAME` | App name inside that project |
| Variable | `ENVIRONMENT_ID` | Compute Environment ID |
| Variable | `HARDWARE_TIER_ID` | Hardware Tier ID, for example `small-k8s` |

Create `uat` and `production` GitHub environments (Settings > Environments), add the secret and variables to each, and require reviewers on `production` for a manual gate. The runner is outside Domino and cannot read Domino Project or user environment variables, so the GitHub secret is its own copy of a token created in Domino (**Account Settings > Personal Access Token**, or a service account token).

## Workflow

`.github/workflows/deploy.yml`:

```yaml
name: Deploy to Domino
on:
  push:
    branches: [uat, main]

permissions:
  contents: read

# One deploy per branch at a time, so two pushes cannot race createAndStart.
concurrency:
  group: domino-deploy-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.ref_name == 'main' && 'production' || 'uat' }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v7
        with:
          node-version: '24'
          cache: npm
          cache-dependency-path: app-code/package-lock.json

      - name: Build (fail here, not inside Domino)
        working-directory: app-code
        run: |
          npm ci
          npm run build

      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'

      - name: Deploy to Domino
        env:
          DOMINO_URL: ${{ vars.DOMINO_URL }}
          DOMINO_TOKEN: ${{ secrets.DOMINO_TOKEN }}
          PROJECT_NAME: ${{ vars.PROJECT_NAME }}
          PROJECT_OWNER: ${{ vars.PROJECT_OWNER }}
          APP_NAME: ${{ vars.APP_NAME }}
          ENVIRONMENT_ID: ${{ vars.ENVIRONMENT_ID }}
          HARDWARE_TIER_ID: ${{ vars.HARDWARE_TIER_ID }}
          GIT_BRANCH: ${{ github.ref_name }}
        run: |
          pip install requests
          python cicd/deploy_app.py
```

## Deploy script

`cicd/deploy_app.py` uses only routes in the 6.3 and Cloud public specs: `GET /api/projects/beta/projects`, `GET /api/apps/v1/apps`, `POST /api/apps/v1/apps`, `POST /api/apps/v1/apps/{appId}/versions/{versionId}/start`, `POST /api/apps/v1/apps/{appId}/versions/createAndStart`, `GET /api/apps/v1/apps/{appId}/versions/{versionId}`, `GET /api/apps/v1/apps/{appId}`. Bodies are documented in [API-APPS.md](./API-APPS.md). The project lookup pages through every project the token can see (a service account with broad roles sees many), so keep the roles narrow.

```python
#!/usr/bin/env python3
"""Create or update a Domino App from CI through the Public API (/api/apps/v1)."""
import os
import sys
import time

import requests

BASE = os.environ["DOMINO_URL"].rstrip("/")
HEADERS = {"Authorization": f"Bearer {os.environ['DOMINO_TOKEN']}", "Content-Type": "application/json"}
PROJECT_NAME = os.environ["PROJECT_NAME"]
PROJECT_OWNER = os.environ["PROJECT_OWNER"]
APP_NAME = os.environ["APP_NAME"]
ENVIRONMENT_ID = os.environ["ENVIRONMENT_ID"]
HARDWARE_TIER_ID = os.environ["HARDWARE_TIER_ID"]
GIT_BRANCH = os.environ.get("GIT_BRANCH", "main")
VISIBILITY = os.environ.get("APP_VISIBILITY", "AUTHENTICATED")  # AUTHENTICATED | GRANT_BASED | GRANT_BASED_STRICT | PUBLIC


def call(method, path, **kwargs):
    resp = requests.request(method, BASE + path, headers=HEADERS, timeout=60, **kwargs)
    if resp.status_code >= 400:
        sys.exit(f"{method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json() if resp.text else {}


def find_project():
    offset = 0
    while True:
        page = call("GET", "/api/projects/beta/projects", params={"limit": 100, "offset": offset})
        for project in page["projects"]:
            if project["name"] == PROJECT_NAME and project["ownerUsername"] == PROJECT_OWNER:
                return project["id"]
        if len(page["projects"]) < 100:  # last page; metadata.totalCount is not guaranteed by the spec
            sys.exit(f"project {PROJECT_OWNER}/{PROJECT_NAME} not found")
        offset += 100


def find_app(project_id):
    page = call("GET", "/api/apps/v1/apps", params={"projectId": project_id, "name": APP_NAME, "limit": 50})
    return next((app for app in page["items"] if app["name"] == APP_NAME), None)  # name filter is a substring match


def version_spec():
    return {
        "content": {"environmentId": ENVIRONMENT_ID, "gitRef": {"type": "branches", "value": GIT_BRANCH}},
        "deployment": {"hardwareTierId": HARDWARE_TIER_ID},
    }


def wait_until_running(app_id, version_id):
    """Poll the version we started, not the App, so a concurrent start cannot confuse the result."""
    for _ in range(90):
        version = call("GET", f"/api/apps/v1/apps/{app_id}/versions/{version_id}")
        status = (version.get("currentInstance") or {}).get("status")
        print(f"status: {status}")
        if status == "Running":
            print(f"deployed: {call('GET', f'/api/apps/v1/apps/{app_id}')['url']}")
            return
        if status in ("Succeeded", "Failed", "Error", "Stopped"):
            # Succeeded means app.sh exited instead of serving; read the instance logs in Domino
            sys.exit(f"deployment ended with status {status}; read the instance logs in Domino")
        time.sleep(10)
    sys.exit("timed out waiting for the App to start")


def main():
    project_id = find_project()
    app = find_app(project_id)
    if app is None:
        print(f"creating App {APP_NAME}")
        app = call("POST", "/api/apps/v1/apps", json={
            "projectId": project_id,
            "name": APP_NAME,
            "entryPoint": "app.sh",
            "visibility": VISIBILITY,
            "discoverable": True,
            "initialVersion": version_spec(),
        })
        # currentVersion is the newly created version here (6.3 and Cloud); latestVersion is Cloud-only
        version_id = (app.get("latestVersion") or app["currentVersion"])["id"]
        # json={} matters: the v1 start route returns 415 on an empty body
        call("POST", f"/api/apps/v1/apps/{app['id']}/versions/{version_id}/start", json={})
    else:
        print(f"creating and starting a new version of {APP_NAME} ({app['id']})")
        result = call("POST", f"/api/apps/v1/apps/{app['id']}/versions/createAndStart", json=version_spec())
        version_id = result["version"]["id"]
        if result.get("warnings"):
            sys.exit(f"version {version_id} saved but not started: {result['warnings']}")
    wait_until_running(app["id"], version_id)


if __name__ == "__main__":
    main()
```

Pin a version to the exact pushed commit instead of the branch head with `{"type": "commitId", "value": os.environ["GITHUB_SHA"]}`.

## Monitoring and rollback

- GitHub: the workflow log prints the status transitions and the App URL.
- Domino: the App details page shows per-instance logs and resource use; the API equivalent is in [API-APPS.md](./API-APPS.md) (Logs).
- Rollback: any published version can be deployed. In the UI select the earlier version on the App details page and **Deploy**; over the API, `POST /api/apps/v1/apps/{appId}/versions/{oldVersionId}/start` with `{}`, which stops the running version and restarts the old one on its original commit (verified live on Cloud 6.4.0). A `git revert` pushed to the branch also produces a new version through the workflow.

Public example repository (older API usage, for layout reference only): https://github.com/dominodatalab/domino-blueprints/tree/main/React-app-deployment-with-CICD
