# Dataset mount paths

Where Domino mounts Datasets and snapshots in DFS and Git-based Projects, how to detect which
layout applies, what is read-write, and how pinned snapshots and tags change the tree.

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/use-datasets-and-snapshots
(section "Understand Dataset paths") and
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/version-data-with-snapshots.

## Detect the layout

Domino injects these into every execution
(https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/manage-compute-environments/manage-environment-variables/5-glossary-default-variables):

| Variable | Value |
|---|---|
| `DOMINO_DATASETS_DIR` | `/mnt/data` in a Git-based Project, `/domino/datasets` in a DFS Project |
| `DOMINO_IS_GIT_BASED` | `true` or `false` |
| `DOMINO_PROJECT_NAME` | Also the name of the Project's default Dataset |

```python
import os

root = os.environ["DOMINO_DATASETS_DIR"]
git_based = os.environ.get("DOMINO_IS_GIT_BASED") == "true"
local_root = root if git_based else f"{root}/local"                       # this Project's Datasets
# shared Datasets: /mnt/imported/data beside /mnt/data, or the DFS root itself
imported_root = os.path.join(os.path.dirname(root), "imported", "data") if git_based else root
default_dataset = f"{local_root}/{os.environ['DOMINO_PROJECT_NAME']}"
```

The roots are deployment settings (`/mnt` and `/domino/datasets` by default), which is why the
code derives them from `DOMINO_DATASETS_DIR` instead of hardcoding.

A Git-based Project `my-project` has
`DOMINO_DATASETS_DIR=/mnt/data` and its default Dataset at `/mnt/data/my-project`; a DFS Project
has `DOMINO_DATASETS_DIR=/domino/datasets` and the Dataset at `/domino/datasets/local/my-project`.

## DFS Projects

```
/domino
   |--/datasets
      |--/local               <== this Project's Datasets and their snapshots
         |--/clapton          <== read-write for Dataset Owners and Editors, read-only for Readers
         |--/mingus
         |--/snapshots        <== snapshots organised by Dataset, always read-only
            |--/clapton
               |--/tag1       <== mounted under the most recently added tag
               |--/1          <== always mounted under the snapshot number
               |--/2
            |--/mingus
               |--/tag2
               |--/1
               |--/2
      |--/ella                <== Dataset shared from another Project
      |--/davis
      |--/snapshots           <== shared Datasets' snapshots organised by Dataset
         |--/ella
            |--/tag3
            |--/1
            |--/2
         |--/davis
            |--/tag4
            |--/1
            |--/2
```

| Dataset | Path |
|---|---|
| Of this Project | `/domino/datasets/local/<name>` |
| Its snapshots | `/domino/datasets/local/snapshots/<name>/<n>`, `/domino/datasets/local/snapshots/<name>/<tag>` |
| Shared from another Project | `/domino/datasets/<name>` |
| Its snapshots | `/domino/datasets/snapshots/<name>/<n>`, `/domino/datasets/snapshots/<name>/<tag>` |

## Git-based Projects

```
/mnt
   |--/data                  <== this Project's Datasets and their snapshots
     |--/clapton             <== read-write for Dataset Owners and Editors, read-only for Readers
     |--/mingus
     |--/snapshots           <== snapshots organised by Dataset, always read-only
        |--/clapton
           |--/tag1          <== mounted under the most recently added tag
           |--/1             <== always mounted under the snapshot number
           |--/2
        |--/mingus
           |--/tag2
           |--/1
           |--/2
   |--/imported
     |--/data
        |--/ella             <== Dataset shared from another Project
        |--/davis
        |--/snapshots        <== shared Datasets' snapshots organised by Dataset
           |--/ella
              |--/tag3
              |--/1
              |--/2
           |--/davis
              |--/tag4
              |--/1
              |--/2
```

| Dataset | Path |
|---|---|
| Of this Project | `/mnt/data/<name>` |
| Its snapshots | `/mnt/data/snapshots/<name>/<n>`, `/mnt/data/snapshots/<name>/<tag>` |
| Shared from another Project | `/mnt/imported/data/<name>` |
| Its snapshots | `/mnt/imported/data/snapshots/<name>/<n>`, `/mnt/imported/data/snapshots/<name>/<tag>` |

Git-based Projects also mount code at `/mnt/code` and artifacts at `/mnt/artifacts`
(https://docs.domino.ai/cloud/platform-capabilities/core-concepts/projects/files-artifacts-and-results);
neither is a Dataset.

## When snapshot directories appear

Snapshot mounts are set up when an execution starts. A snapshot taken during a Workspace or
Job is therefore **not** visible in that execution: there is no `snapshots/<name>/<n>` entry for
it, and a Workspace that has taken its Dataset's first snapshots has no `snapshots/` directory
at all. Executions started after the snapshot became `active` mount it. Snapshot 0 (the empty
initial snapshot every Dataset starts with) and snapshots whose status is `failed` are not
mounted.

To read a snapshot from the execution that took it, use the internal file route through the
proxy or `DatasetClient` with `DatasetConfig(snapshot_id=...)`, both in [API.md](./API.md)
and the domino-data-sdk skill, or start a Job that mounts it.

## Read-write or read-only

- Live Dataset directories follow the user's Dataset role: Owner and Editor read-write, Reader
  read-only. Roles are granted per Dataset, independently of Project roles. A Dataset shared
  from another Project may mount read-only regardless of role; check before writing:
  `os.access(path, os.W_OK)`.
- Every snapshot directory (numbered or tagged) is read-only.
- An execution pinned to one snapshot mounts that snapshot read-only at the live path
  (`/mnt/data/<name>` or `/domino/datasets/local/<name>`) and mounts nothing under
  `snapshots/<name>/` for that Dataset. Pinning is chosen per Dataset on the **Data Plane &
  Hardware** tab when launching a Workspace or Job or defining a scheduled Job.

## Tags

A snapshot with a tag is mounted under `snapshots/<name>/<tag>`; if a snapshot has several
tags, only the most recently added one is mounted. Tags move: re-tagging a newer snapshot with
the same name moves the path to it, so code that reads `snapshots/<name>/production` follows
the tag while `snapshots/<name>/3` stays fixed.

## Reading data

```python
import os
import pandas as pd

root = os.environ["DOMINO_DATASETS_DIR"]
git_based = os.environ.get("DOMINO_IS_GIT_BASED") == "true"
local_root = root if git_based else f"{root}/local"

live = f"{local_root}/training-data/customers.csv"                     # current data
pinned = f"{local_root}/snapshots/training-data/production/customers.csv"   # follows the tag
fixed = f"{local_root}/snapshots/training-data/3/customers.csv"        # snapshot number 3

df = pd.read_csv(live)
files = os.listdir(f"{local_root}/training-data")
```

The UI shows the resolved paths: **Data > Datasets** inside a running Workspace, **Workspaces >
Settings** before launch, and **Details > Data** on a Job.
