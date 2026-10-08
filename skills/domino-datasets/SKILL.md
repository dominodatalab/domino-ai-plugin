---
name: domino-datasets
description: Work with Domino Datasets - high-performance, versioned filesystem storage. Covers dataset creation, snapshots for versioning, sharing across projects, mounting paths (/domino/datasets/), and performance optimization. Use when managing data storage, creating reproducible data versions, or sharing data between projects.
---

# Domino Datasets Skill

## Description
This skill helps users work with Domino Datasets - high-performance, versioned filesystem storage for data science projects.

## Activation
Activate this skill when users want to:
- Create or manage Domino Datasets
- Work with dataset snapshots and versioning
- Share data between projects
- Access large datasets efficiently
- Understand dataset paths and mounting

## What is a Domino Dataset?

A Domino Dataset is:
- **High-performance storage**: Network filesystem optimized for data science
- **Versioned**: Create snapshots for reproducibility
- **Shareable**: Access across projects
- **Scalable**: No file size or count limits
- **Persistent**: Data persists across executions

## Creating a Dataset

### Via Domino UI
1. Navigate to your project
2. Go to **Data** > **Domino Datasets**
3. Click **Create New Dataset**
4. Enter:
   - **Name**: Dataset name (e.g., `training-data`)
   - **Description**: What the dataset contains
5. Click **Create**

### Via Python SDK
```python
from domino import Domino

domino = Domino("project-owner/project-name")

# Create a new dataset
dataset = domino.datasets_create(
    name="training-data",
    description="Training data for classification model"
)
```

## Dataset Paths

Dataset paths differ based on your **project type**. Domino has two project types with different mount structures.

### DFS (Domino File System) Projects

| Dataset Type | Path |
|-------------|------|
| Local datasets | `/domino/datasets/local/{dataset-name}/` |
| Local snapshots | `/domino/datasets/local/snapshots/{dataset-name}/{tag-or-number}/` |
| Shared datasets | `/domino/datasets/{dataset-name}/` |
| Shared snapshots | `/domino/datasets/snapshots/{dataset-name}/{tag-or-number}/` |

### Git-Based Projects

| Dataset Type | Path |
|-------------|------|
| Local datasets | `/mnt/data/{dataset-name}/` |
| Local snapshots | `/mnt/data/snapshots/{dataset-name}/{tag-or-number}/` |
| Shared datasets | `/mnt/imported/data/{dataset-name}/` |
| Shared snapshots | `/mnt/imported/data/snapshots/{dataset-name}/{tag-or-number}/` |

Full mount trees (local vs shared, snapshot tags vs numbers) and read examples: [MOUNT-PATHS.md](./MOUNT-PATHS.md).

### How to Identify Your Project Type

Check which paths exist in your execution:
```python
import os

if os.path.exists("/domino/datasets"):
    print("DFS Project")
    dataset_root = "/domino/datasets/local"
elif os.path.exists("/mnt/data"):
    print("Git-Based Project")
    dataset_root = "/mnt/data"
```

### Permissions

Both project types follow the same permission model:
- **Owners/Editors**: Read-write access to datasets
- **Readers**: Read-only access

## Uploading Data

### Via Domino UI
1. Go to dataset page
2. Click **Upload**
3. Select files (up to 50GB or 50,000 files via UI)
4. Click **Upload**

### Via Domino CLI (Large Uploads)
```bash
# For large uploads, use CLI
domino upload /local/path/to/data /mnt/data/training-data/
```

### Via Code in Workspace
```python
import shutil

# Copy from local to dataset
shutil.copy("local_file.csv", "/mnt/data/training-data/")

# Write directly
df.to_csv("/mnt/data/training-data/processed.csv", index=False)
```

## Snapshots

### What is a Snapshot?
A snapshot is a read-only, immutable version of your dataset at a point in time. Use snapshots for:
- Reproducibility
- Versioning training data
- Rolling back to previous states

### Create a Snapshot
```python
# Via Python SDK
snapshot = domino.datasets_snapshot(
    dataset_name="training-data",
    tag="v1.0"
)
```

Or via UI:
1. Go to dataset page
2. Click **Create Snapshot**
3. Add optional tag (e.g., `v1.0`, `production`)

### Access Snapshots
```python
# Latest snapshot
df = pd.read_csv("/mnt/data/training-data/data.csv")

# Specific tagged snapshot
df = pd.read_csv("/mnt/data/training-data@v1.0/data.csv")
```

### Snapshot Limits
- Default limit: 20 snapshots per dataset
- Configurable by admins
- Oldest snapshots auto-deleted when limit reached

## Tags

### What are Tags?
Tags provide friendly names for snapshots:
- `production`: Current production data
- `v1.0`, `v2.0`: Version numbers
- `2024-01-15`: Date-based tags

### Move Tags
Tags can be moved to different snapshots:
```python
# Move 'production' tag to latest snapshot
domino.datasets_tag(
    dataset_name="training-data",
    snapshot_id="snapshot-123",
    tag="production"
)
```

## Sharing Datasets

### Within Organization
1. Go to dataset settings
2. Set visibility to **Organization**
3. Other projects can mount the dataset

### Cross-Project Access
```python
# Import dataset from another project
# Configured in project settings
df = pd.read_csv("/mnt/data/shared-dataset/data.csv")
```

## Troubleshooting

### Dataset Not Found
- Verify dataset name is correct
- Check dataset is mounted to project
- Confirm you have access permissions

### Permission Denied
- Check project role (need Contributor+)
- Verify dataset sharing settings
- Contact dataset owner

### Slow Performance
- Use efficient file formats (Parquet > CSV)
- Read only needed columns
- Use chunked/lazy loading for large files

### Snapshot Failed
- Check disk quota
- Verify no files are open/locked
- Check snapshot limit not reached

## Reference files

- [MOUNT-PATHS.md](./MOUNT-PATHS.md) — full DFS and Git-based mount trees, path tables, project-type detection, permissions, read examples
- [BEST-PRACTICES.md](./BEST-PRACTICES.md) — storage selection, layout, file formats, metadata, snapshot-before-change, chunked/Dask/memmap reading

## Documentation Reference
- [Create and manage Datasets](https://docs.dominodatalab.com/en/latest/user_guide/0a8d11/create-and-manage-datasets/)
- [Version data with Snapshots](https://docs.dominodatalab.com/en/cloud/user_guide/dbdbff/version-data-with-snapshots/)
- [Datasets best practices](https://archive.docs.dominodatalab.com/en/4.4/user_guide/a222c9/datasets-best-practices/)
