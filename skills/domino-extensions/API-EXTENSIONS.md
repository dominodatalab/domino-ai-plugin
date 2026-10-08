# Extensions REST surface and Apps-API caveats

Beta Extensions routes, a create-Extension request sample, official-install API analogs, and Apps-API behaviors that affect Extension Apps; read before automating Extension creation or the install lifecycle from code.

## REST surface

REST surface (beta): prefix **`/api/extensions/beta/`** (`extensions`, `extensions-ui`, `official-installs`, ...). Confirm operation IDs and bodies in [API-SPECS.md](../domino-api-intro/API-SPECS.md) (public routes section).

```python
import os
import requests

if os.environ.get("DOMINO_API_PROXY"):
    base_url = os.environ["DOMINO_API_PROXY"].rstrip("/")
    headers = {}
else:
    base_url = (os.environ.get("DOMINO_USER_HOST") or os.environ.get("DOMINO_API_HOST") or "").rstrip("/")
    token = requests.get("http://localhost:8899/access-token").text.strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

body = {
    "name": "My Extension",
    "enabled": True,
    "appId": "app-id-from-publish",
    "uiMountPointTypeConfigs": {
        "projectSidebar": {
            "enabled": True,
            "allProjects": True,
            "urlConfig": {"contextualQueryParams": ["projectId"]},
        }
    },
}
response = requests.post(f"{base_url}/api/extensions/beta/extensions", headers=headers, json=body)
```

## Official Extension install (manifest-driven)

For Domino-built Extensions, an admin installs from **Manage Domino-official Extensions** in the Admin panel. The installer creates project, environment, App, and Extension from the release manifest (background job with retry/cancel). API analogs: `official-install-menu`, `POST .../official-installs`, snapshot status endpoints under `/api/extensions/beta/official-installs/`.

## Platform caveats (Apps API + Extensions)

These affect Extension Apps the same as standalone Apps:

| Topic | Behavior |
|-------|----------|
| **`netAppVolumeIds` on App version create** | Accepted in the API but NetApp volumes may **not mount** (silent no-op vs workspace parity). Prefer explicit volume workflows; manifest `mountNetAppVolumes` does not fix API no-op alone. |
| **App delete and vanity URL** | Deleting an App may **not release** its vanity URL for immediate reuse; recreate failures may need admin cleanup. |
| **Apps beta vs v1** | Extension backing Apps may be created or published through beta or v1 routes; confirm routes in [API-SPECS.md](../domino-api-intro/API-SPECS.md) (public routes section). Prefer documented v1 publish flows for new automation where available. |

## Related API reference

OpenAPI and route discovery: [API-SPECS.md](../domino-api-intro/API-SPECS.md).

- Apps publish chain: [python-sdk/API-APPS.md](../domino-python-sdk/API-APPS.md)
