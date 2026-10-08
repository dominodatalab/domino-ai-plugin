# Mount paths and data access

Where NetApp volumes and their snapshots appear inside a workspace, job, or app (Git-based vs DFS projects), snapshot path behavior, read/write examples, and file-handling best practices, preceded by the NetApp Volumes vs. Domino Datasets comparison. The REST API is in [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md).

## What is a Domino NetApp Volume?

A Domino NetApp Volume is:
- **Enterprise-grade storage**: Backed by NetApp ONTAP via Kubernetes PVCs with the `netapp-storage` storage class
- **Multi-terabyte scale**: No practical upper limit — suitable for very large datasets
- **Near-instant snapshots**: ~3 seconds even for 100+ GB volumes using redirect-on-write (no extra storage consumed at snapshot time)
- **Versioned with commit messages**: Snapshots support human-readable tags and commit messages, unlike Datasets
- **Shareable**: Attach a single volume to multiple projects and teams
- **Persistent**: Data persists across executions

### NetApp Volumes vs. Domino Datasets

| Feature | NetApp Volumes | Domino Datasets |
|---------|---------------|-----------------|
| Storage backend | External NetApp ONTAP | Domino-managed NFS/EFS |
| Data scale | Multi-terabyte and beyond | Up to ~1 TB |
| Snapshot speed | ~3 seconds (any size) | Scales with data size |
| Snapshot storage cost | No extra space (redirect-on-write) | Duplicates physical data |
| Commit messages on snapshots | Supported | Not supported |
| Create new volume from snapshot | Read-only clones | Can create editable dataset |
| Cross-project sharing | Yes | Yes |
| Admin prerequisite | Admin must register filesystems | None |
| REST API | Full dedicated API | Via Domino Python SDK |

**Advantages over Domino Dataset snapshots:**

- Near-instant for any volume size (~3 seconds)
- Support commit messages for documentation and audit trails
- No storage overhead at creation time

## Mount Paths

Mount paths depend on your **project type**. Check which exists in your execution to determine your project type.

### Git-Based Projects

| Volume Type | Mount Path |
|-------------|-----------|
| Live volume | `/mnt/netapp-volumes/<volume-name>/` |
| Snapshot by number | `/mnt/netapp-volumes/snapshots/<volume-name>/<snapshot-number>/` |
| Snapshot by tag | `/mnt/netapp-volumes/snapshot-tags/<volume-name>/<tag-name>/` |

### DFS (Domino File System) Projects

| Volume Type | Mount Path |
|-------------|-----------|
| Live volume | `/domino/netapp-volumes/<volume-name>/` |
| Snapshot by number | `/domino/netapp-volumes/snapshots/<volume-name>/<snapshot-number>/` |
| Snapshot by tag | `/domino/netapp-volumes/snapshot-tags/<volume-name>/<tag-name>/` |

### Snapshot Access Behavior

There are two ways to access snapshots, with an important behavioral difference:

- **`/snapshots/<volume-name>/<number>/`** — Accessed by snapshot number. When a new snapshot is taken while a workspace is running, the new numbered directory appears **immediately** in that workspace without a restart.
- **`/snapshot-tags/<volume-name>/<tag-name>/`** — Accessed by tag name. Each snapshot has at most one active tag path — a symlink to its numbered snapshot directory. If you apply multiple tags to the same snapshot, only the most recently applied tag creates a path; earlier tags for that snapshot are not accessible by path. Tag paths for new snapshots are also **not** visible in a running workspace — you must **restart the workspace** for them to appear.

Use the numbered path when you need to access a fresh snapshot from within a live workspace. Use the tagged path for stable, named references in reproducible runs.

> **Important:** Each snapshot exposes only one tag path at a time — the most recently applied tag. Older tags on the same snapshot do not have accessible paths.

> **Important:** Renaming a volume changes its mount path. Update any hardcoded paths in your code after renaming.

### Identify Your Project Type

```python
import os

if os.path.exists("/domino/netapp-volumes"):
    print("DFS Project")
    netapp_root = "/domino/netapp-volumes"
elif os.path.exists("/mnt/netapp-volumes"):
    print("Git-Based Project")
    netapp_root = "/mnt/netapp-volumes"
```

### Permissions

- **Owners/Editors**: Read-write access to the live volume
- **Readers**: Read-only access

### Example: Reading Data

```python
import pandas as pd

# Git-Based Project
df = pd.read_parquet("/mnt/netapp-volumes/large-training-data/features.parquet")

# DFS Project
df = pd.read_parquet("/domino/netapp-volumes/large-training-data/features.parquet")

# Read from a specific snapshot tag
df = pd.read_parquet("/mnt/netapp-volumes/snapshot-tags/large-training-data/v2.0/features.parquet")
```

### Example: Writing Data

```python
# Write directly to the live volume
df.to_parquet("/mnt/netapp-volumes/large-training-data/processed/output.parquet", index=False)

# List files
import os
files = os.listdir("/mnt/netapp-volumes/large-training-data/")
```

## Best Practices

### 1. Use Appropriate Storage
| Data Type | Storage |
|-----------|---------|
| Large data of any file type where the entire filesystem should be versioned as a unit, with intentional snapshots | NetApp Volume |
| Small output files — charts, reports, model binaries | Artifacts / DFS (auto-versioned per file, not suitable for large files) |
| Code | Git / Project files |

### 2. Snapshot Before Changes
```python
# Always snapshot before modifying large volumes
requests.post(
    f"{remotefs_url}/remotefs/v1/snapshots",
    headers=headers,
    json={
        "volumeId": "<volume-id>",
        "description": "Pre-processing baseline snapshot",
        "tagNames": ["pre-processing-2024-01"]
    }
)

# Then run your data transformation
process_data()
```

### 3. Use Efficient File Formats
```python
# Parquet for tabular data (faster reads, smaller storage)
df.to_parquet("/mnt/netapp-volumes/dataset/data.parquet")

# Feather for fast pandas I/O
df.to_feather("/mnt/netapp-volumes/dataset/data.feather")

# HDF5 for large numerical arrays
import h5py
with h5py.File("/mnt/netapp-volumes/dataset/arrays.h5", "w") as f:
    f.create_dataset("features", data=features_array)
```

### 4. Organize Data
```
/mnt/netapp-volumes/my-volume/
├── raw/
│   ├── 2024-Q1/
│   └── 2024-Q2/
├── processed/
│   ├── features.parquet
│   └── labels.parquet
└── metadata/
    └── schema.json
```

### 5. Use Snapshot Tags for Reproducibility
Reference snapshot tags (not snapshot IDs) in your training scripts so that tagged paths remain stable across runs:
```python
# Reproducible reference using a tag
TRAINING_DATA = "/mnt/netapp-volumes/snapshot-tags/dataset/v2.0/"
df = pd.read_parquet(f"{TRAINING_DATA}/features.parquet")
```

### 6. Reading Large Volumes Efficiently
```python
import dask.dataframe as dd

# Lazy read — no data loaded until .compute()
df = dd.read_parquet("/mnt/netapp-volumes/dataset/large_data.parquet")
result = df.groupby("category").mean().compute()
```
