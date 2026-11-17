# CI/CD for a React app on Domino with GitHub Actions

A push to `uat` or `main` builds the app once in CI, commits the build on a commit tagged `build-<label>`, and starts the App on that commit in a Domino project with python-domino. `app.sh` only serves the build, so the App starts in seconds and needs neither npm nor registry access. The App is published once by a person; CI restarts it on the new build on every push. Build labels: [FRAMEWORKS.md](./FRAMEWORKS.md#build-once-and-version-builds).

## Architecture

```
dev branch  -> workspace (manual test)
uat branch  -> GitHub Action -> UAT project:  App restarted on the new build
main branch -> GitHub Action -> Prod project: App restarted on the new build
```

## One-time setup in Domino (once, by a person)

1. **Identity.** Ask a Domino admin for a service account and a token (https://docs.domino.ai/cloud/admin/identity-and-access/manage-users/service-accounts). A service account is the right identity for CI; a user API key works for a pipeline that should act as you. Two things from that page matter here: a service account inherits the roles of the admin who created it, so have the admin trim its roles before generating the token (the token captures the roles at creation); and tokens expire after four months by default, so plan to rotate `DOMINO_TOKEN`.
2. **Git credential for the service account.** Git credentials are per account. Because the service account starts every App instance, the admin adds a token Git credential that can read this repository to the service account itself (same page, "Add Git credentials to a service account"; API `POST /api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/tokengitcredentials`). Use a read-only GitHub token.
3. **Projects.** Create the UAT and production projects as Git-based projects whose main repository is this GitHub repository (https://docs.dominodatalab.com/en/6.1/user_guide/23862a/link-a-github-account-to-domino/ for the human's own credential). Add the service account as a collaborator with edit rights on both projects. (`POST /api/projects/v2/projects` with `mainRepository.uri`, `serviceProvider` and `gitCredentialId` automates this; not covered here.)
4. **Environment variables.** In each project add `MODEL_API_URL` and `MODEL_API_TOKEN` as Project environment variables (**Settings > Environment variables**, or `POST /v4/projects/{projectId}/environmentVariables` (non-public route; may change in a future Domino version) as [domino-api-intro](../domino-api-intro/SKILL.md#environment-variables-as-the-secret-store) shows; the token is a Model Access Token from the endpoint's **Settings > Invocation**). The App reads them at start; they never pass through GitHub.
5. **IDs.** Note the Compute Environment ID (the environment must contain `node` 18 or later; npm is not needed) and the Hardware Tier ID. `GET /api/environments/beta/environments` and `GET /api/hardwaretiers/v1/hardwaretiers` list them.
6. **The App.** Commit a first build (run the workflow's build step once), then publish the App in each project (**Deployments > Apps > Publish Domino App**, launch file `app-code/app.sh`, sharing as needed) and note its ID: `GET /api/apps/beta/apps?projectId=<projectId>` (`items[].id`).

## Repository layout

```
.
├── app-code/                 # Vite app from the domino-app-init template: src/, vite.config.js,
│                             #   package.json, server.js, app.sh, scripts/build-dist.sh, scripts/stamp.sh
├── cicd/deploy_app.py
└── .github/workflows/deploy.yml
```

The App's entry point is `app-code/app.sh`; it serves the build in `app-code/dist/<label>/` whose stamp matches the code and never builds.

## GitHub configuration

| Kind | Name | Value |
|---|---|---|
| Secret | `DOMINO_TOKEN` | Service account token |
| Variable | `DOMINO_URL` | Public URL of the deployment (what you open in the browser), no trailing slash |
| Variable | `PROJECT_NAME` | Domino project name (`-uat` suffix in the UAT environment) |
| Variable | `PROJECT_OWNER` | Username of the project owner |
| Variable | `APP_ID` | ID of the App published in step 6 |
| Variable | `ENVIRONMENT_ID` | Compute Environment ID |
| Variable | `HARDWARE_TIER_ID` | Hardware Tier ID, for example `small-k8s` |

Create `uat` and `production` GitHub environments (Settings > Environments), add the secret and variables to each, and require reviewers on `production` for a manual gate. The runner is outside Domino and cannot read Domino Project or user environment variables, so the GitHub secret is its own copy of a service account token created in Domino. To act as yourself instead, store your user API key, pass it to `Domino(...)` as `api_key=` in place of `auth_token=`, and send it as `X-Domino-Api-Key` in the script's `requests` call. `DOMINO_URL` and `DOMINO_TOKEN` here are GitHub names the runner reads, not variables Domino injects.

## Workflow

`.github/workflows/deploy.yml`:

```yaml
name: Deploy to Domino
on:
  push:
    branches: [uat, main]

permissions:
  contents: write   # pushes the build tag

# One deploy per branch at a time, so two pushes cannot race the restart.
concurrency:
  group: domino-deploy-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.ref_name == 'main' && 'production' || 'uat' }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: '26'
          cache: npm
          cache-dependency-path: app-code/package-lock.json

      - name: Build once and tag it
        working-directory: app-code
        run: |
          LABEL="$(date -u +%Y.%m.%d).${{ github.run_number }}"
          DIST_DIR=dist KEEP_BUILDS=1 BUILD_LABEL="$LABEL" bash scripts/build-dist.sh
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -f dist
          git commit -q -m "Build $LABEL of $GITHUB_SHA"
          git tag "build-$LABEL"
          git push origin "build-$LABEL"
          echo "BUILD_LABEL=$LABEL" >> "$GITHUB_ENV"
          echo "BUILD_SHA=$(git rev-parse HEAD)" >> "$GITHUB_ENV"

      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: '3.12'   # matches the Domino Standard Environment's Python 3.12

      - name: Deploy to Domino
        env:
          DOMINO_URL: ${{ vars.DOMINO_URL }}
          DOMINO_TOKEN: ${{ secrets.DOMINO_TOKEN }}
          PROJECT_NAME: ${{ vars.PROJECT_NAME }}
          PROJECT_OWNER: ${{ vars.PROJECT_OWNER }}
          APP_ID: ${{ vars.APP_ID }}
          ENVIRONMENT_ID: ${{ vars.ENVIRONMENT_ID }}
          HARDWARE_TIER_ID: ${{ vars.HARDWARE_TIER_ID }}
          BUILD_SHA: ${{ env.BUILD_SHA }}
          BUILD_LABEL: ${{ env.BUILD_LABEL }}
        run: |
          pip install dominodatalab requests
          python cicd/deploy_app.py
```

## Deploy script

`cicd/deploy_app.py` starts the App on the build commit with python-domino `app_publish`, which stops the running App first and wraps the Domino Internal API (`/v4/modelProducts/{appId}/start` and `.../stop`; non-public routes; may change in a future Domino version), then polls `app_get_status` and reads the viewer URL from `GET /api/apps/beta/apps/{appId}`. More on these calls: [API-APPS.md](./API-APPS.md#start-and-stop).

```python
#!/usr/bin/env python3
"""Restart a Domino App on a new build from CI (python-domino app_publish)."""
import os
import sys
import time

import requests
from domino import Domino

BASE = os.environ["DOMINO_URL"].rstrip("/")
TOKEN = os.environ["DOMINO_TOKEN"]
APP_ID = os.environ["APP_ID"]
BUILD_SHA = os.environ["BUILD_SHA"]          # the commit tagged build-<label>: source plus its build
BUILD_LABEL = os.environ["BUILD_LABEL"]


def main():
    domino = Domino(f"{os.environ['PROJECT_OWNER']}/{os.environ['PROJECT_NAME']}", host=BASE, auth_token=TOKEN)
    print(f"starting App {APP_ID} on build {BUILD_LABEL} ({BUILD_SHA})")
    domino.app_publish(
        app_id=APP_ID,
        hardware_tier_id=os.environ["HARDWARE_TIER_ID"],
        environment_id=os.environ["ENVIRONMENT_ID"],
        commit_id=BUILD_SHA,
    )
    for _ in range(90):
        status = domino.app_get_status(APP_ID)
        print(f"status: {status}")
        if status == "Running":
            app = requests.get(f"{BASE}/api/apps/beta/apps/{APP_ID}",
                               headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60).json()
            print(f"deployed: {app.get('url')}")
            return
        if status in ("Failed", "Error"):
            sys.exit(f"App start ended with status {status}; read the instance logs in Domino")
        time.sleep(10)
    sys.exit("timed out waiting for the App to start")


if __name__ == "__main__":
    main()
```

The build tag is pushed once and never moved, so the commit the App runs holds both its source and its build; the commits stay off the branch, which never carries build output. CI keeps one build per commit (`KEEP_BUILDS=1`); a reverted commit is rebuilt by its own push.

## Monitoring and going back

- GitHub: the workflow log prints the status transitions and the App URL.
- Domino: the App details page shows the App's logs; the API equivalent is in [API-APPS.md](./API-APPS.md#logs).
- Going back: rolling back to an earlier App version is not available on Domino 6.1. Push a `git revert`; the workflow builds it and restarts the App on it.

Public example repository (older API usage, for layout reference only): https://github.com/dominodatalab/domino-blueprints/tree/main/React-app-deployment-with-CICD
