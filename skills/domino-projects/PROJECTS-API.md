# Projects over REST and python-domino

Routes marked (Cloud) are Domino Cloud only. The python-sdk catalog for the same surface is [API-PROJECTS.md](../domino-python-sdk/API-PROJECTS.md).

## Setup

```python
import os, requests
# base and headers: the Python setup block in domino-api-intro/SKILL.md#authentication
base, headers = os.environ["DOMINO_API_PROXY"], {}   # in a run with the proxy
```

## Read

| Task | Call |
|------|------|
| List projects you can see | `GET /api/projects/beta/projects?offset=0&limit=10` → `projects[]` (`id`, `name`, `description`, `visibility`, `ownerId`, `ownerUsername`, `collaborators[]`, `isRestricted`), `metadata.totalCount` |
| Get one | `GET /api/projects/v1/projects/{projectId}` → `project` with the same fields; `collaborators[]` entries are `{id, role}` |
| Current project in a run | `$DOMINO_PROJECT_ID` (also `DOMINO_PROJECT_NAME`, `DOMINO_PROJECT_OWNER`) |
| Latest commit (beta) | `GET /api/projects/beta/projects/{projectId}/commits/latest` |
| File content at a commit | `GET /api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content` |
| Imported Git repositories | `GET /api/projects/v1/projects/{projectId}/repositories` |
| Goals | `GET /api/projects/v1/projects/{projectId}/goals` |
| Shared datasets | `GET /api/projects/v1/projects/{projectId}/shared-datasets` |
| Results settings (beta) | `GET` and `PUT /api/projects/beta/projects/{projectId}/results-settings` |

The beta list endpoint takes only `offset` and `limit`; filter by name client-side.

```python
projects, offset = [], 0
while True:
    page = requests.get(f"{base}/api/projects/beta/projects", headers=headers,
                        params={"offset": offset, "limit": 50}).json()
    projects += page["projects"]
    offset += 50
    if offset >= page["metadata"]["totalCount"]:
        break
mine = [p for p in projects if p["name"] == "churn-model"]
```

## Create

`POST /api/projects/v2/projects` (permissions `CreateProject`, `UseFileStorage`). Required: `name` (unique, no whitespace), `description`, `visibility` (`private`, `searchable`; `public` on 6.3 only). The caller owns the project unless `ownerId` names another user (organizations cannot own a project through this route). The create returns 200 with `{project{...}}`; `visibility` is accepted in either case and comes back capitalized (`Private`); a Git-based create takes `mainRepository{uri, serviceProvider, defaultRef{refType: "head"}}`; `DELETE /api/projects/beta/projects/{id}` returns `{"success": true}`, after which `GET` is 404.

DFS project:

```python
r = requests.post(f"{base}/api/projects/v2/projects", headers=headers, json={
    "name": "churn-model", "description": "Churn scoring", "visibility": "private"})
r.raise_for_status()
project_id = r.json()["project"]["id"]
```

Git-based project on an existing repository:

```python
r = requests.post(f"{base}/api/projects/v2/projects", headers=headers, json={
    "name": "churn-model", "description": "Churn scoring", "visibility": "private",
    "mainRepository": {
        "uri": "https://github.com/acme/churn-model.git",
        "serviceProvider": "github",            # bitbucket | bitbucketServer | github | githubEnterprise | gitLab | gitLabEnterprise | unknown
        "gitCredentialId": "<id from GET /api/users/beta/credentials/{userId}>",
        "defaultRef": {"refType": "branch", "value": "main"},   # head | branch | tag | commit
    }})
```

### Git credentials

List: public `GET /api/users/beta/credentials/{userId}` (6.3 and Cloud; needs `UpdateUser`) returns `credentials[]` with `id`, `name`, `gitServiceProvider`, `domain`, `fingerprint` and `protocol`; `userId` is `user.id` from `GET /api/users/v1/self`. Create: **Account Settings** > **Git Credentials**, or `POST /v4/accounts/{userId}/gitcredentials` (non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types); on 6.3 confirm it in your deployment's `/docs`). Keep the secret in a user environment variable (**Account Settings** > **User Environment Variables**) and read it from `os.environ`; never print or log it.

```python
user_id = requests.get(f"{base}/api/users/v1/self", headers=headers).json()["user"]["id"]
cred = {"type": "TokenGitCredentialDto", "accessType": "token", "name": "github-pat",      # personal access token
        "gitServiceProvider": "github", "token": os.environ["GITHUB_TOKEN"]}
# username and password: {"type": "PasswordGitCredentialDto", "accessType": "password", "username": "...", "password": "..."}
# SSH key:               {"type": "SshGitCredentialDto", "accessType": "key", "key": "<private key text>", "passphrase": "<optional>"}
r = requests.post(f"{base}/v4/accounts/{user_id}/gitcredentials", headers=headers, json=cred)   # non-public route; may change in a future Domino version
r.raise_for_status()
credential_id = r.json()["id"]      # {id, name, gitServiceProvider, domain, fingerprint, protocol}; the secret is never returned
```

`gitServiceProvider` is `github`, `gitlab`, `githubEnterprise`, `gitlabEnterprise`, `bitbucket`, `bitbucketServer` or `unknown` (this route spells GitLab in lower case; `mainRepository.serviceProvider` takes the public enum with `gitLab` and `gitLabEnterprise`, and the public list capitalises the provider, `Github`). `domain` is required for `githubEnterprise`, `gitlabEnterprise`, `bitbucketServer` and `unknown` (400 without it) and defaults to the provider's public host otherwise. A Bitbucket Server HTTP access token goes in as `PasswordGitCredentialDto` with the username and the token as `password`. Creation does not contact the provider, so prove a credential by creating or syncing a Git-based project with it. Also internal: `GET /v4/accounts/{userId}/gitcredentials` (same fields as the public list) and `DELETE /v4/accounts/{userId}/gitcredentials/{credentialId}`; creating for another user needs `UpdateUser`. Service accounts use the public routes under `/api/serviceAccounts/v1/serviceAccounts/{serviceAccountIdpId}/` (`tokengitcredentials`, `sshgitcredentials`, `passwordgitcredentials`; list and delete at `gitcredentials`).

Optional: `repoToCreate{credentialId, owner, repositoryToCreateName, visibility, serviceProvider}` to have Domino create the repository; `templateDetails{templateId, name, templateRevisionId, templateType, importToMainRepo, forceImport}` to start from a project template; `billingTag{tag}`; `isRestricted` (needs `ProjectClassifier`). The older `POST /api/projects/beta/projects` takes `NewProjectV1`: the same fields, plus `repoToCreate.repositoryTemplateName`.

## Collaborators and visibility

```python
requests.post(f"{base}/api/projects/v1/projects/{project_id}/collaborators", headers=headers,
              json={"id": "<user or organization id>", "role": "contributor"})
# roles: contributor | resultsConsumer | launcherUser | projectImporter (the owner role is not assignable)
requests.delete(f"{base}/api/projects/v1/projects/{project_id}/collaborators/<collaboratorId>", headers=headers)
```

Needs `ManageCollaborators`; adding a user who is already a member returns 400. User ids are the `ownerId` and `collaborators[].id` values returned by the project routes; the users API is in [API-ADMIN.md](../domino-python-sdk/API-ADMIN.md).

No public route changes visibility after creation. Use **Settings** > **Access & Sharing**, or the Domino Internal API route `PATCH /v4/projects/{projectId}/visibility` with `{"visibility": "Private"}` (`Public`, `Searchable` or `Private`; non-public route; may change in a future Domino version). It answers 200 with an empty body, `GET /api/projects/v1/projects/{projectId}` then reports the new value, and an unknown value returns 400 with a JSON validation error; `Public` is not offered on Domino Cloud. On 6.3, confirm the route in your deployment's `/docs` first.

```python
requests.patch(f"{base}/v4/projects/{project_id}/visibility", headers=headers,   # non-public route; may change in a future Domino version
               json={"visibility": "Searchable"}).raise_for_status()
```

## Project settings (defaults)

No python-domino method and no public route cover the defaults every Workspace and Job starts with; set them in **Settings** > **Hardware & Environment**, or with the Domino Internal API (`GET` and `PUT /v4/projects/{projectId}/settings`, non-public route; may change in a future Domino version; `PUT` answers 200 and the following `GET` returns the new tier; on 6.3 confirm in `/docs`). The `PUT` body (`ProjectSettingsUpdateDto`) takes `defaultEnvironmentId`, `defaultEnvironmentRevisionSpec` (`ActiveRevision`, `LatestRevision`, `RestrictedRevision`, or `{"revisionId": "..."}`), `defaultHardwareTierId` and `defaultVolumeSizeGiB`; `GET` also returns `sparkClusterMode` and `minVolumeSizeGiB`, `maxVolumeSizeGiB`, `recommendedVolumeSizeGiB`, which are not settable here.

```python
settings = requests.get(f"{base}/v4/projects/{project_id}/settings", headers=headers).json()   # non-public route; may change in a future Domino version
requests.put(f"{base}/v4/projects/{project_id}/settings", headers=headers, json={
    "defaultEnvironmentId": settings["defaultEnvironmentId"],
    "defaultEnvironmentRevisionSpec": settings["defaultEnvironmentRevisionSpec"],
    "defaultHardwareTierId": "medium-k8s",                        # a tier id from GET /api/hardwaretiers/v1/hardwaretiers
    "defaultVolumeSizeGiB": settings["defaultVolumeSizeGiB"],
}).raise_for_status()
```

## Copy, status, goals, archive

```python
# Deep copy of a Git-based project into a new repository
# (reference copy instead: "gitCodeRepoSpec": {"credentialId": ..., "referenceCopy": {"mainRepoUrl": "https://github.com/acme/churn-model.git"}})
requests.post(f"{base}/api/projects/v1/projects/{project_id}/copy-project", headers=headers, json={
    "name": "churn-model-v2", "visibility": "private", "copyDatasets": True,
    "gitCodeRepoSpec": {"credentialId": "<PAT credential id>",
                        "deepCopy": {"newRepoName": "churn-model-v2", "newRepoOwnerName": "acme", "visibility": "private"}}})

requests.put(f"{base}/api/projects/v1/projects/{project_id}/status", headers=headers,
             json={"status": "complete", "isBlocked": False, "completedMessage": "Model shipped"})   # or "active"; isBlocked with blockedReason

requests.post(f"{base}/api/projects/v1/projects/{project_id}/goals", headers=headers,
              json={"title": "AUC >= 0.85 on the holdout set", "description": "Q4 target"})
# PATCH .../goals/{goalId}, DELETE .../goals/{goalId}

requests.delete(f"{base}/api/projects/beta/projects/{project_id}", headers=headers)   # archive (ArchiveProject permission)
```

`copyDatasets` is required on copy. Copying a Git-based project needs a personal-access-token credential (not SSH) and, on GitHub, a template repository; a Dataset that is already being copied makes the call fail, so retry later. Only the owner can archive.

## Repositories

```python
requests.post(f"{base}/api/projects/v1/projects/{project_id}/repositories", headers=headers, json={
    "uri": "https://github.com/acme/shared-utils.git", "name": "shared-utils",
    "serviceProvider": "github", "gitCredentialId": "<credential id>",
    "defaultRef": {"refType": "branch", "value": "main"}})     # ChangeProjectSettings permission
requests.delete(f"{base}/api/projects/v1/projects/{project_id}/repositories/<repositoryId>", headers=headers)
```

(Cloud) `PUT /api/projects/v1/projects/{projectId}/repositories/{repositoryId}/default-ref` with `{"refType": "branch", "value": "develop"}` changes what later runs check out; use `_` as the repository id for a Git-based project's main repository. Also (Cloud): `GET .../repositories/{repositoryId}/readme`, `/file-metadata`, `/rendered-file`. Imported repositories mount at `/mnt/imported/code/<name>` (Git-based) or `/repos/<name>` (DFS).

## Shared datasets

`POST /api/projects/v1/projects/{projectId}/shared-datasets` with `{"datasetId": "..."}`; `DELETE .../shared-datasets/{datasetId}`. See `domino-datasets`.

## python-domino

Every method needs a client bound to one project: `Domino("owner/project")`; the `project` argument is required (host from `DOMINO_API_HOST`, auth from the proxy or a token). Methods:

| Method | Does | Note |
|--------|------|------|
| `project_create(project_name, owner_username=None)` | Creates a DFS project through the legacy `POST /project` route (non-public route; may change in a future Domino version) | Prefer the REST v2 route above for Git-based projects and templates |
| `projects_list(relationship="Owned", show_completed=False)` | Lists projects through `GET /v4/gateway/projects` (non-public route; may change in a future Domino version) | |
| `project_archive(project_name)` | Archives by name through `DELETE /v4/projects/{id}` (non-public route; may change in a future Domino version) | The public equivalent is `DELETE /api/projects/beta/projects/{projectId}` |
| `fork_project(target_name)` | Forks the bound project through the internal `/v4/projects/{id}/fork` route (may change in a future Domino version) | Forks are unavailable on Domino Cloud |
| `collaborators_get()`, `collaborators_add(username_or_email, message="")`, `collaborators_remove(username_or_email)` | Collaborators | All three use Domino Internal API routes (non-public; may change in a future Domino version) |
| `get_user_id(username_or_email)` | Resolves a username or email to a user id (`/v4/users`, non-public route; may change in a future Domino version) | Useful before the public collaborator route above |
| `project_billing_tag(...)`, `project_billing_tag_update(...)`, `project_billing_tag_reset(...)` | Billing tags | |

There is no `project_update`, `project_info` or `project_settings` method; defaults (environment, hardware tier, volume size) are set in the UI or with the internal settings route above. Full inventory: [domino-python-sdk](../domino-python-sdk/SKILL.md).
