# NetApp Volumes troubleshooting

Symptoms and fixes for missing mounts, permission errors, snapshot paths, missing
filesystems, full filesystems and slow reads. Mount path rules: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Volume not found at the mount path

- Confirm the volume is attached to the project (**Data > NetApp Volumes** in the project,
  or `GET /remotefs/v1/volumes?project_id=<id>`).
- Confirm it was selected for this execution: volumes are chosen at launch. Start a new
  Workspace or Job, or restart the Workspace, after attaching a volume.
- Check the project type: DFS projects mount under `/domino/netapp-volumes/`, Git-based
  projects under `/mnt/netapp-volumes/` (`DOMINO_IS_GIT_BASED`).
- The path uses the volume's current `name`; a rename changes it.

## Permission denied on write

- Readers mount read-only; writing needs the Editor or Owner role (`grants` on the volume).
- A volume pinned to a snapshot at launch is read-only at the read-write path; launch
  again with **All snapshots** to write.
- Snapshot paths (`snapshots/...`, `snapshot-tags/...`) are always read-only.

## A tag path is missing

- Only the most recently added tag on a snapshot is mounted; earlier tags on the same
  snapshot have no path. Move the tag or use the numbered path
  `snapshots/<name>/<version>`.
- A pinned Dataset gets no tag mount; a pinned NetApp Volume keeps its tag mounts.

## No NetApp filesystems available

Volumes are created inside an administrator-registered ONTAP filesystem.
`GET /remotefs/v1/filesystems` returning an empty `data` array means none is registered
for your data plane; ask your Domino administrator
(https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes).

## 409 filesystem full

Domino 6.4 caps volumes per filesystem (`maxVolumes` on the filesystem record, 490 by
default; `numVolumes` is the current count).

- `POST /remotefs/v1/volumes` with a `filesystemId` returns
  `409 filesystem has reached its maximum number of volumes`: pick another filesystem on
  the same data plane, or omit `filesystemId` and send `dataPlaneId` so the service
  places the volume automatically.
- `409 no filesystem on the data plane has capacity for another volume` from automatic
  placement: every filesystem on that data plane is full; an administrator registers
  another one or raises `maxVolumes` with `PUT /remotefs/v1/filesystems/{id}`.
- `bulk-copy-volumes-to-project` reports a full `targetFilesystemId` as `status: 409` on
  that item only; drop `targetFilesystemId` to let the copy fall back to an automatically
  selected filesystem.
- `400 filesystem does not belong to the specified data plane`: `filesystemId` and
  `dataPlaneId` disagree; send one of them, or matching values.
- In the UI (Create Volume, Create Template Data step, Create Project from a template)
  the filesystem is chosen automatically. A **NetApp Filesystem** picker (default
  **Automatic**, full filesystems listed as "(full)" and disabled, Create blocked while a
  template copy points at a full one) appears only after an administrator sets the
  Central Config key `com.cerebro.domino.netApp.manualFilesystemSelection.enabled` to
  `true` and restarts nucleus.

## Take Snapshot is unavailable

- The volume has reached its `maxSnapshots` (`numSnapshots` on the volume record); delete
  old snapshots first.
- Taking snapshots needs the Editor or Owner role.

## 404 or `{"message": ...}` from the API

- Inside a run, volume, filesystem and snapshot operations work only on
  `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` with the `localhost:8899` access token as a
  bearer: `$DOMINO_API_PROXY` and the in-run `$DOMINO_API_HOST` return 404 for
  `/remotefs/v1/*`, and the hostport without the header returns 401. Outside Domino use the deployment URL with a PAT or service account
  token. File operations need the `/webvfs` prefix outside Domino or the
  `data-webvfs-service.domino-compute:80` host inside a run
  ([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#files)).
- Snapshot list filters are snake_case (`volume_id`), and `grants` on create is required.

## Slow reads

- Prefer Parquet or Feather over CSV; read only needed columns.
- Use Dask or chunked reads for files larger than memory.
- Choose a hardware tier on the same data plane as the filesystem (`dataPlaneId` on the
  volume and filesystem records).
