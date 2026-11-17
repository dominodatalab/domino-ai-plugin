---
name: netapp-volumes
description: Work with Domino Volumes for NetApp ONTAP (NetApp Volumes) - shared, multi-terabyte storage with near-instant snapshots. Covers creating volumes, attaching them to projects, mount paths (/mnt/netapp-volumes/ or /domino/netapp-volumes/), snapshots, roles, deletion, mounting volumes in jobs, and the NetApp Volumes REST API. Use when managing large-scale shared data, taking fast no-copy snapshots, or integrating NetApp ONTAP storage with Domino.
compatibility: Domino 6.1. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a service-account token (or a user API key). An administrator must have registered a NetApp ONTAP filesystem.
---

# Domino NetApp Volumes

Applies to Domino 6.1.

Domino Volumes for NetApp ONTAP mount NetApp ONTAP filesystems directly into Domino
Workspaces, Jobs, Apps and Launchers. They are global entities (not scoped to a project)
that you attach to any project that needs them. Product docs:
https://docs.dominodatalab.com/en/6.1/user_guide/06da1b/work-with-netapp-volumes/.
Auth: [domino-api-intro](../domino-api-intro/SKILL.md#authentication); in a run the
volume routes answer on `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` with a bearer
([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#authentication-and-base-urls)). The API base
path is `/remotefs/v1` or `/domino-netapp-volumes/v1` depending on the deployment; confirm it
and the request bodies in the deployment's `/docs` (`/docs/openapi/openapi-public.json`)
before scripting ([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#base-path)). Routes below are
relative to that base.

## NetApp Volumes or Domino Datasets?

NetApp Volumes cover nearly the same ground as Datasets and are recommended wherever the
organization runs ONTAP. Differences:

- Snapshots are near-instant regardless of size (about 3 seconds) and use
  redirect-on-write, so they consume no extra storage at creation; a Dataset snapshot
  duplicates the data.
- Datasets can be cloned from a snapshot into a new Dataset; a NetApp Volume snapshot
  cannot be cloned into a new volume.
- NetApp Volumes need ONTAP infrastructure and an administrator-registered filesystem;
  Domino sets no volume size limit (the ONTAP volume type does). There are limits on
  snapshots per volume and volumes per filesystem.

Comparison and examples: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Prerequisites

An administrator registers an ONTAP filesystem (data plane, storage class, root PVC) before
anyone can create volumes: https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes.
List registered filesystems with `GET /filesystems`
([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#filesystems)).

## Create a volume

From Domino (then add it to projects manually) or from inside a project (auto-attached):

1. **Data > NetApp Volumes** (toolbar, or a project's left panel).
2. **Add NetApp Volume > Create Volume**.
3. **Name** (letters, numbers, underscores, hyphens), **Description**, **Data Plane**,
   **NetApp Filesystem**, **Capacity**. Click **Next**.
4. Add users or organizations with a **Reader**, **Editor** or **Owner** role. **Finish**.

REST: `POST /volumes` with `name`, `filesystemId`, `capacity` (bytes) and optional
`projectId` ([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#create-a-volume)).

## Attach, detach, delete

- **Attach**: **Data > NetApp Volumes**, three-dot menu on the volume, **Add to project**.
  REST: `POST /rpc/attach-volume-to-project`.
- **Detach**: in the project, **Data > NetApp Volumes**, **Remove from project**. Only the
  attachment goes; data and other projects are unaffected. REST:
  `POST /rpc/detach-volume-from-project`.
- **Delete**: **Delete Volume** (if your admin enabled it for your role) or **Mark for
  deletion** (requests that an admin delete it). Deletion is permanent. REST:
  `POST /rpc/delete-volume` (no need to mark first) or
  `/rpc/mark-volume-for-deletion` (undo: `/rpc/restore-volume`).

## Mount paths

Paths mirror the Dataset scheme; volumes are global, so there is no local/imported split.

| Project type | Read-write volume | Snapshot by number |
|--------------|-------------------|--------------------|
| DFS | `/domino/netapp-volumes/<name>` | `/domino/netapp-volumes/snapshots/<name>/<number>` |
| Git-based | `/mnt/netapp-volumes/<name>` | `/mnt/netapp-volumes/snapshots/<name>/<number>` |

`<number>` is the snapshot's `version` from the API. Owners and Editors mount read-write;
Readers mount read-only; Apps mount with the App owner's permission. Renaming a volume
changes its mount path. Details: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Snapshots

Owners and Editors snapshot the whole volume: **Data > NetApp Volumes**, click the volume,
**Take Snapshot** near the top of the Details view. Expand the **Latest data** menu to list
snapshots. Owners and Editors delete a snapshot permanently (**Delete Snapshot**); Readers can
only **Mark Snapshot for Deletion**. Snapshots carry no tags or commit messages on Domino 6.1,
and an execution cannot be pinned to one snapshot at launch.

REST: `POST /snapshots` (`volumeId`, `name`), `PUT /snapshots/{id}` (rename),
`/rpc/restore-snapshot`, `/rpc/delete-snapshot`
([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#snapshots)). To snapshot at the end of a
job, call `POST /snapshots` from the job's last step.

## Roles

| Role | Capabilities |
|------|---------------------|
| Reader | Read data and view snapshots; attach to projects read-only; can only mark a snapshot for deletion |
| Editor | Reader plus write data, edit the description, take and delete snapshots, mount, mark for deletion or restore |
| Owner | Editor plus change who has access and their roles (grants), request volume deletion |

Edit permissions: three-dot menu on the volume, **Edit permissions**. REST:
`PUT /volumes/{id}/grants`; copy the grant field values from `GET /volumes/{id}/grants`
([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#grants)).

## Volumes in Jobs

`POST /api/jobs/v1/jobs` takes `netAppVolumeIds` (volume ids to mount). Body: [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#mount-volumes-in-a-job).

## Reference files

- [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md): base path, REST API with request bodies (volumes, filesystems, attach/detach, snapshots, grants, deletion, listing, jobs)
- [DATA-ACCESS.md](./DATA-ACCESS.md): comparison with Datasets, mount paths, snapshot mounting, read/write examples, best practices
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): missing mounts, permission errors, no filesystems, API errors, slow reads

## Documentation

- https://docs.dominodatalab.com/en/6.1/user_guide/06da1b/work-with-netapp-volumes/ (overview, create, add/remove, view/edit)
- https://docs.dominodatalab.com/en/6.1/api_guide/b3b2a1/domino-netapp-volumes-api/
- https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes (administrator setup)
- Specs: [API-SPECS.md](../domino-api-intro/API-SPECS.md); per-deployment service document `/docs/openapi/data_remotefs_service-swagger.json`
