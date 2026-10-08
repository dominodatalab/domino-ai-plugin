# NetApp Volumes REST API

Python examples for the NetApp Volumes REST API: create a volume, attach it to a project, create/tag/restore snapshots, update grants, mount volumes in jobs, list volumes and snapshots, and fetch the swagger spec. Mount paths and in-run file access are in [DATA-ACCESS.md](./DATA-ACCESS.md).

## Authentication and base URLs

All examples below reuse the `headers`, `api_url`, and `remotefs_url` set up in the first snippet.

## Create a volume

### Via REST API
```python
import os
import requests

# Auth token from in-cluster token service
token = requests.get("http://localhost:8899/access-token").text.strip()
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

api_url = os.environ["DOMINO_API_HOST"]
remotefs_url = os.environ["DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT"]

# Look up your user ID (username is available in the DOMINO_USER_NAME env var)
user_resp = requests.get(
    f"{api_url}/v4/users?userName={os.environ['DOMINO_USER_NAME']}",
    headers=headers
).json()
user_id = user_resp[0]["id"]

# Create a volume (capacity is in bytes; grants is required)
response = requests.post(
    f"{remotefs_url}/remotefs/v1/volumes",
    headers=headers,
    json={
        "name": "large-training-data",
        "description": "Multi-TB training dataset for vision models",
        "filesystemId": "<filesystem-id>",
        "capacity": 5_000_000_000_000,  # 5 TB in bytes
        "grants": [
            {"targetId": user_id, "targetRole": "VolumeOwner"}
        ]
    }
)
volume = response.json()
print(f"Created volume ID: {volume['id']}")
```

## Add a volume to a project

### Via REST API
```python
# Attach a volume to a project
requests.post(
    f"{remotefs_url}/remotefs/v1/rpc/attach-volume-to-project",
    headers=headers,
    json={
        "volumeId": "<volume-id>",
        "projectId": "<project-id>"
    }
)
```

## Snapshots

### Create a Snapshot via REST API
```python
# Create snapshot with description and one or more tags (tagNames is an array)
response = requests.post(
    f"{remotefs_url}/remotefs/v1/snapshots",
    headers=headers,
    json={
        "volumeId": "<volume-id>",
        "description": "Added Q4 customer records — 50M new rows",
        "tagNames": ["v2.0"]
    }
)
snapshot = response.json()
print(f"Snapshot ID: {snapshot['id']}")
```

### Add a Tag to an Existing Snapshot
```python
requests.post(
    f"{remotefs_url}/remotefs/v1/snapshots/{snapshot_id}/tags",
    headers=headers,
    json={"name": "production"}
)
```

### Create Snapshot After a Job Run
```python
# Snapshot tied to a specific Domino run for reproducibility
requests.post(
    f"{remotefs_url}/remotefs/v1/rpc/create-snapshot-from-run",
    headers=headers,
    json={
        "volumeId": "<volume-id>",
        "runId": "<domino-run-id>",
        "userId": "<user-id>",
        "description": "post-training-run-42"
    }
)
```

### Restore a Snapshot
```python
requests.post(
    f"{remotefs_url}/remotefs/v1/rpc/restore-snapshot",
    headers=headers,
    json={"snapshotId": "<snapshot-id>"}
)
```

## Roles and permissions

### Update Permissions via REST API
```python
# targetRole values: "VolumeOwner", "VolumeEditor", "VolumeReader"
requests.put(
    f"{remotefs_url}/remotefs/v1/volumes/{volume_id}/grants",
    headers=headers,
    json=[
        {"targetId": "<user-id>", "targetRole": "VolumeEditor"},
        {"targetId": "<other-user-id>", "targetRole": "VolumeReader"}
    ]
)
```

## Using NetApp Volumes in Jobs

### Via Domino REST API
```python
requests.post(
    f"{api_url}/api/jobs/v1/jobs",
    headers=headers,
    json={
        "projectId": "<project-id>",
        "runCommand": "python train.py",
        "hardwareTierId": "<hardware-tier-id>",
        "environmentId": "<environment-id>",  # required — use DOMINO_ENVIRONMENT_ID env var
        "netAppVolumeIds": ["<volume-id>"],
        "snapshotNetAppVolumesOnCompletion": True  # auto-snapshot mounted volumes when job finishes
    }
)
```

Set `snapshotNetAppVolumesOnCompletion: true` to automatically take a snapshot of all mounted NetApp volumes when the job completes. This is the recommended approach for training jobs — it captures the exact state of the volume at the end of the run without requiring a separate API call.

## Listing Volumes and Snapshots

```python
# List all volumes accessible to you
volumes = requests.get(
    f"{remotefs_url}/remotefs/v1/volumes",
    headers=headers
).json()

for v in volumes["data"]:
    capacity_tb = v["capacity"] / 1_000_000_000_000
    print(f"{v['name']} — {capacity_tb:.1f} TB — ID: {v['id']}")

# List snapshots for a volume
snapshots = requests.get(
    f"{remotefs_url}/remotefs/v1/snapshots",
    headers=headers,
    params={"volumeId": "<volume-id>"}
).json()

for s in snapshots["data"]:
    print(f"Snapshot {s['id']} v{s['version']} — {s.get('description', '')} — tags: {[t['name'] for t in s.get('tags', [])]}")
```

## Documentation Reference

Before writing or verifying any API call, use the cluster swagger to confirm current endpoint paths and field names. Use public docs for workflow context and field explanations.

**Get the cluster base URL:** `$DOMINO_API_HOST` (injected by Domino into every workspace, job, and app).

Fetch the NetApp Volumes swagger spec (requires bearer token):
```bash
TOKEN=$(curl -s http://localhost:8899/access-token)
# The swagger UI is only accessible via the external cluster URL (not $DOMINO_API_HOST).
# Derive it from the JWT iss claim — works in any workspace type.
CLUSTER_URL=$(echo $TOKEN | cut -d'.' -f2 | python3 -c "
import sys, base64, json, re
p = sys.stdin.read().strip()
p += '=' * (-len(p) % 4)
print(re.sub(r'/auth/realms/.*', '', json.loads(base64.b64decode(p))['iss']))
")
curl -H "Authorization: Bearer $TOKEN" "$CLUSTER_URL/domino-netapp-volumes/swagger/doc.json"
# Browser UI (must be logged in): $CLUSTER_URL/domino-netapp-volumes/swagger/index.html
```

**Public docs (workflow context and field explanations):**
- [NetApp Volumes REST API Reference](https://docs.dominodatalab.com/en/cloud/api_guide/b3b2a1/domino-netapp-volumes-api/)
- [Work with NetApp Volumes](https://docs.dominodatalab.com/en/cloud/user_guide/06da1b/work-with-netapp-volumes/)
- [Create NetApp Volumes](https://docs.dominodatalab.com/en/cloud/user_guide/e6887f/create-netapp-volumes-from-domino-or-a-project/)
- [Add or Remove NetApp Volumes on Projects](https://docs.dominodatalab.com/en/cloud/user_guide/306570/add-or-remove-netapp-volumes-on-projects/)
- [View and Edit NetApp Volumes](https://docs.dominodatalab.com/en/cloud/user_guide/93fa12/view-and-edit-netapp-volumes/)
- [Version Data with Snapshots](https://docs.dominodatalab.com/en/cloud/user_guide/dbdbff/version-data-with-snapshots/)
- [Access Data in Domino (comparison guide)](https://docs.dominodatalab.com/en/cloud/user_guide/16d9c1/access-data-in-domino/)
