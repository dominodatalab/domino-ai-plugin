# Mount paths and data access

Where NetApp Volumes and their snapshots appear inside a Workspace, Job or App, how
tagged and pinned snapshots mount, read/write examples, and file-handling practices. The
REST API is in [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md). Sources:
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/netapp-volumes/add-remove-netapp-volumes
and https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/version-data-with-snapshots.

## NetApp Volumes vs Domino Datasets

| Feature | NetApp Volumes | Domino Datasets |
|---------|---------------|-----------------|
| Storage backend | NetApp ONTAP filesystem registered by an administrator (FSx for ONTAP, Google Cloud NetApp Volumes, Cloud ONTAP) | Domino-managed storage |
| Scope | Global; attach to any number of projects | Created in a project; shareable with other projects |
| Size limit | None from Domino; set by the ONTAP volume type (up to 300 TiB for a FlexVol) | Domino-managed |
| Snapshot time | About 3 seconds regardless of size | Seconds to hours as data grows |
| Snapshot storage | None at creation (redirect-on-write) | Duplicates the captured data |
| Commit message on snapshots | Yes | No (tags only) |
| New asset from a snapshot | No (volumes can be copied for Project Templates) | Yes, a new Dataset |
| Admin prerequisite | Registered ONTAP filesystem | None |
| REST API | `/remotefs/v1` | `/api/datasetrw/v1` and `/v2` |

## Mount paths

Paths mirror the Dataset scheme. Volumes are global, so there is no local/imported split.

| Project type | Read-write volume | Snapshots by number | Tagged snapshot |
|--------------|-------------------|---------------------|-----------------|
| DFS | `/domino/netapp-volumes/<name>` | `/domino/netapp-volumes/snapshots/<name>/<number>` | `/domino/netapp-volumes/snapshot-tags/<name>/<tag>` |
| Git-based | `/mnt/netapp-volumes/<name>` | `/mnt/netapp-volumes/snapshots/<name>/<number>` | `/mnt/netapp-volumes/snapshot-tags/<name>/<tag>` |

`<number>` is the snapshot's `version` from the API. Renaming a volume changes `<name>` and
therefore every path; update scripts after a rename.

### Permissions at mount time

- Volume Owners and Editors attach volumes read-write; Readers attach read-only.
- Apps mount read-write or read-only according to the App owner's role.
- You choose which attached volumes to mount when you launch the execution.

### Snapshot mounting

- By default an attached volume mounts its live data and all of its snapshots
  (`snapshots/<name>/<number>`).
- If a snapshot has a tag, Domino also mounts it under `snapshot-tags/<name>/<tag>`. If a
  snapshot carries several tags, only the most recently added tag is mounted. Tags can be
  moved to newer snapshots by Owners and Editors.
- **Pinning**: on the **Data Plane & Hardware** tab at launch you can pin a volume to one
  snapshot (`Snapshot #<version> - <date>`). The pinned snapshot then mounts read-only at
  the read-write path (`/domino/netapp-volumes/<name>` or `/mnt/netapp-volumes/<name>`),
  the read-write mount and the `snapshots/<name>` directory are disabled, and tag mounts
  stay. The pin applies to every restart of a Workspace, to a single one-off Job run, or
  to every run of a scheduled Job.

### Identify the project type

```python
import os

if os.path.isdir("/domino/netapp-volumes"):
    netapp_root = "/domino/netapp-volumes"      # DFS project
elif os.path.isdir("/mnt/netapp-volumes"):
    netapp_root = "/mnt/netapp-volumes"         # Git-based project
else:
    raise RuntimeError("No NetApp Volumes are mounted in this execution")
```

`DOMINO_IS_GIT_BASED` (injected into every execution) tells you the project type directly.

### Reading

```python
import pandas as pd

df = pd.read_parquet(f"{netapp_root}/large-training-data/features.parquet")                      # live data
df_v2 = pd.read_parquet(f"{netapp_root}/snapshot-tags/large-training-data/v2-0/features.parquet")  # tagged snapshot (tag names cannot contain dots)
df_n3 = pd.read_parquet(f"{netapp_root}/snapshots/large-training-data/3/features.parquet")        # snapshot number 3
```

### Writing

```python
import os
out_dir = f"{netapp_root}/large-training-data/processed"
os.makedirs(out_dir, exist_ok=True)
df.to_parquet(f"{out_dir}/output.parquet", index=False)
print(os.listdir(f"{netapp_root}/large-training-data"))
```

Writes need the Editor or Owner role; a pinned snapshot is read-only.

## Best practices

### Put the right data in the right place

| Data | Storage |
|------|---------|
| Large files or whole directory trees versioned as a unit, shared across projects | NetApp Volume |
| Project-scoped data that you want to clone into new editable versions | Domino Dataset |
| Small outputs (charts, reports, model files) | Project files / artifacts |
| Code | Git repository / project files |

### Snapshot before destructive changes

```python
requests.post(f"{remotefs_url}/remotefs/v1/snapshots", headers=remotefs_headers,
              json={"volumeId": volume_id, "description": "Pre-processing baseline",
                    "tagNames": ["pre-processing-2026-01"]})
process_data()
```

Setup for `remotefs_url` and `remotefs_headers`: [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#authentication-and-base-urls).
For Jobs, `snapshotNetAppVolumesOnCompletion: true` on `POST /api/jobs/v1/jobs` does
this automatically at the end of the run on deployments where an administrator has
enabled it (otherwise the job is rejected with 400; see
[API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#mount-volumes-in-a-job)).

### Reference tags, not numbers, in reproducible runs

```python
TRAINING_DATA = f"{netapp_root}/snapshot-tags/dataset/v2-0"     # tag names: letters, digits, _ and - only
df = pd.read_parquet(f"{TRAINING_DATA}/features.parquet")
```

Tag paths stay stable when you re-tag a newer snapshot; numbered paths identify one
specific snapshot forever. Or pin the snapshot at launch and keep reading the live path.

### Use columnar formats and lazy readers for large data

```python
df = pd.read_parquet(path, columns=["col1", "col2"])      # read only what you need

import dask.dataframe as dd
ddf = dd.read_parquet(f"{netapp_root}/dataset/large_data.parquet")
result = ddf.groupby("category").mean().compute()
```

### Organize the volume

```
/mnt/netapp-volumes/my-volume/
  raw/2026-Q1/  raw/2026-Q2/
  processed/features.parquet  processed/labels.parquet
  metadata/schema.json
```
