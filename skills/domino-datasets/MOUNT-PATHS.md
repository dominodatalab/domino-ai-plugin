# Dataset mount paths

Full mount trees and path tables for local and shared datasets and their snapshots in DFS and Git-based projects, how to detect the project type, permissions, and read examples.

## Dataset Paths

Dataset paths differ based on your **project type**. Domino has two project types with different mount structures.

### DFS (Domino File System) Projects

DFS projects use `/domino` as the root:

```
/domino
   |--/datasets
      |--/local               <== Local datasets and snapshots
         |--/clapton          <== Read-write dataset for owner and editor, read-only for reader
         |--/mingus           <== Read-write dataset for owner and editor, read-only for reader
         |--/snapshots        <== Snapshot folder organized by dataset
            |--/clapton       <== Read-write for owner and editor, read-only for reader
               |--/tag1          <== Mounted under latest tag
               |--/1             <== Always mounted under the snapshot number
               |--/2
            |--/mingus
               |--/tag2
               |--/1
               |--/2
      |--/ella                <== Read-write shared dataset for owner and editor, Read-only for reader
      |--/davis               <== Read-write shared dataset for owner and editor, Read-only for reader
      |--/snapshots           <== Shared datasets snapshots organized by dataset
         |--/ella             <== Read-write for owner and editor, read-only for reader
            |--/tag3          <== Mounted under latest tag
            |--/1             <== Always mounted under the snapshot number
            |--/2
         |--/davis
            |--/tag4
            |--/1
            |--/2
```

| Dataset Type | Path |
|-------------|------|
| Local datasets | `/domino/datasets/local/{dataset-name}/` |
| Local snapshots | `/domino/datasets/local/snapshots/{dataset-name}/{tag-or-number}/` |
| Shared datasets | `/domino/datasets/{dataset-name}/` |
| Shared snapshots | `/domino/datasets/snapshots/{dataset-name}/{tag-or-number}/` |

### Git-Based Projects

Git-based projects use `/mnt` as the root:

```
/mnt
   |--/data                  <== Local datasets and snapshots
     |--/clapton             <== Read-write dataset for owner and editor, read-only for reader
     |--/mingus              <== Read-write dataset for owner and editor, read-only for reader
     |--/snapshots           <== Snapshot folder organized by dataset
        |--/clapton          <== Read-write for owner and editor, read-only for reader
           |--/tag1          <== Mounted under latest tag
           |--/1             <== Always mounted under the snapshot number
           |--/2
        |--/mingus
           |--/tag2
           |--/1
           |--/2
   |--/imported
     |--/data
        |--/ella             <== Read-write shared dataset for owner and editor, read-only for reader
        |--/davis            <== Read-write shared dataset for owner and editor, read-only for reader
        |--/snapshots        <== Shared dataset snapshots organized by dataset
           |--/ella          <== Read-write for owner and editor, read-only for reader
              |--/tag3       <== Mounted under latest tag
              |--/1          <== Always mounted under the snapshot number
              |--/2
           |--/davis
              |--/tag4
              |--/1
              |--/2
```

| Dataset Type | Path |
|-------------|------|
| Local datasets | `/mnt/data/{dataset-name}/` |
| Local snapshots | `/mnt/data/snapshots/{dataset-name}/{tag-or-number}/` |
| Shared datasets | `/mnt/imported/data/{dataset-name}/` |
| Shared snapshots | `/mnt/imported/data/snapshots/{dataset-name}/{tag-or-number}/` |

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

### Example: Reading Data

```python
import pandas as pd

# Git-Based Project
df = pd.read_csv("/mnt/data/training-data/customers.csv")

# DFS Project
df = pd.read_csv("/domino/datasets/local/training-data/customers.csv")

# List files
import os
files = os.listdir("/mnt/data/training-data/")  # Git-Based
files = os.listdir("/domino/datasets/local/training-data/")  # DFS
```
