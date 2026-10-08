---
name: netapp-volumes
description: Work with Domino Volumes for NetApp ONTAP - enterprise-grade, multi-terabyte storage with near-instant snapshots. Covers volume creation, snapshot versioning with commit messages, cross-project sharing, mount paths (/mnt/netapp-volumes/ or /domino/netapp-volumes/), and the NetApp Volumes REST API. Use when managing large-scale data storage, needing fast no-copy snapshots, or integrating existing NetApp ONTAP infrastructure with Domino.
---

# Domino NetApp Volumes Skill

## Description
This skill helps users work with Domino Volumes for NetApp ONTAP — enterprise-grade storage that mounts NetApp ONTAP filesystems directly into Domino workloads, enabling multi-terabyte scale with near-instant snapshotting.

## Activation
Activate this skill when users want to:
- Create or manage NetApp Volumes in Domino
- Work with NetApp volume snapshots and versioning
- Share large-scale data across projects or teams
- Access existing NetApp ONTAP storage from Domino workspaces, jobs, or apps
- Use the NetApp Volumes REST API programmatically
- Understand mount paths for NetApp volumes
- Choose between NetApp Volumes and Domino Datasets

## NetApp Volumes or Domino Datasets?

Feature-by-feature comparison table: [DATA-ACCESS.md](./DATA-ACCESS.md).

**Use NetApp Volumes when:**
- Data exceeds ~1 TB
- Near-instant snapshotting is required
- Your organization already has NetApp ONTAP infrastructure
- You need snapshot commit messages for audit trails
- High-performance shared storage across many teams

**Use Domino Datasets when:**
- Data is Domino-managed with no external infrastructure dependency
- You need to create editable new versions from snapshots
- Data is under ~1 TB

## Prerequisites

An admin must register at least one NetApp filesystem (Kubernetes PVC with the `netapp-storage` label) before users can create volumes. Contact your Domino administrator if no filesystems are available.

## Creating a NetApp Volume

### From the Domino Home Page
1. Navigate to **Data > NetApp Volumes** in the toolbar
2. Click **Add NetApp Volume > Create Volume**
3. Fill in the form:
   - **Name**: Letters, numbers, underscores, hyphens only
   - **Description**: Brief overview of the data
   - **Data Plane**: Select from available options
   - **NetApp Filesystem**: Choose a registered filesystem
   - **Capacity**: Set maximum storage allocation
4. Click **Next** to configure permissions
5. Assign users with **Reader / Editor / Owner** roles
6. Click **Finish**
7. Manually add the volume to projects afterward

### From within a Project (recommended — auto-associates)
1. Open a project → **Data > NetApp Volumes** (left panel)
2. Click **Add NetApp Volume > Create Volume**
3. Fill in the same form fields as above
4. The volume is automatically associated with the current project on creation

REST API (`POST /remotefs/v1/volumes`, capacity in bytes, `grants` required): [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md).

## Adding a Volume to a Project

### Via Domino UI
1. Go to project → **Data > NetApp Volumes**
2. Click **Add NetApp Volume > Add Existing Volume**
3. Select the volume from the list
4. Configure access level for the project

REST API: `POST /remotefs/v1/rpc/attach-volume-to-project` — see [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md).

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

> **Important:** Each snapshot exposes only one tag path at a time — the most recently applied tag. Older tags on the same snapshot do not have accessible paths.

> **Important:** Renaming a volume changes its mount path. Update any hardcoded paths in your code after renaming.

Numbered snapshot paths appear immediately in a running workspace; tag paths need a workspace restart. Project-type detection, permissions, and read/write examples: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Snapshots and Versioning

### What is a Snapshot?
A snapshot is a read-only, immutable record of the volume's data at a specific point in time. NetApp snapshots use redirect-on-write — no additional storage is consumed at creation time.

### Create a Snapshot via UI
1. Go to project → **Data > NetApp Volumes**
2. Select the volume → click **Take Snapshot**
3. Add an optional **commit message** (e.g., "Added Q4 customer records")
4. Add an optional **tag name** (e.g., `v2.0`, `production`, `2024-Q4`)
5. Click **Confirm**

REST API (create with `tagNames`, add a tag, create from a run, restore): [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md).

## Roles and Permissions

| Role | API Value | Capabilities |
|------|-----------|-------------|
| **Reader** | `VolumeReader` | View files and snapshots; mount as read-only |
| **Editor** | `VolumeEditor` | All Reader capabilities + modify description, create/delete snapshots, manage shared access, manage users |
| **Owner** | `VolumeOwner` | All Editor capabilities + update volume grants, request deletion |

### Update Permissions via UI
1. Go to **Data > NetApp Volumes** → select volume
2. Click the three-dot menu → **Edit permissions**
3. Add/remove users and assign roles

## Using NetApp Volumes in Jobs

Set `snapshotNetAppVolumesOnCompletion: true` to automatically take a snapshot of all mounted NetApp volumes when the job completes. This is the recommended approach for training jobs — it captures the exact state of the volume at the end of the run without requiring a separate API call.

Job request body with `netAppVolumeIds`: [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md).

## Reference files

- [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md) — REST API: create/attach volumes, snapshots, grants, jobs, listing, swagger fetch, public doc links
- [DATA-ACCESS.md](./DATA-ACCESS.md) — comparison with Datasets, full mount-path section, snapshot path behavior, read/write examples, best practices
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — volume not found, permission denied, snapshot tag not mounted, no filesystems, slow reads

## Documentation Reference

Before writing or verifying any API call, use the cluster swagger to confirm current endpoint paths and field names. Use public docs for workflow context and field explanations.

**Get the cluster base URL:** `$DOMINO_API_HOST` (injected by Domino into every workspace, job, and app).

Swagger fetch script and public doc links: [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md).
