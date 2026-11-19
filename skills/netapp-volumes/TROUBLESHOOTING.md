# NetApp Volumes troubleshooting

Symptoms and fixes for missing mounts, permission errors, snapshot paths, missing
filesystems and slow reads. Mount path rules: [DATA-ACCESS.md](./DATA-ACCESS.md).

## Volume not found at the mount path

- Confirm the volume is attached to the project (**Data > NetApp Volumes** in the project,
  or `GET <base>/volumes?project_id=<id>`; base path in
  [API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#base-path-and-shapes)).
- Confirm it was selected for this execution: volumes are chosen at launch. Start a new
  Workspace or Job, or restart the Workspace, after attaching a volume.
- Check the project type: DFS projects mount under `/domino/netapp-volumes/`, Git-based
  projects under `/mnt/netapp-volumes/` (`DOMINO_IS_GIT_BASED`).
- The path uses the volume's current `name`; a rename changes it.

## Permission denied on write

- Readers mount read-only; writing needs the Editor or Owner role (`grants` on the volume).
- Snapshot paths (`snapshots/...`) are always read-only.

## No NetApp filesystems available

Volumes are created inside an administrator-registered ONTAP filesystem.
`GET <base>/filesystems` returning an empty `items` array means none is registered
for your data plane; ask your Domino administrator
(https://docs.domino.ai/cloud/admin/data-administration/netapp-volumes).

## Take Snapshot is unavailable

- The volume has reached its maximum snapshot count; delete old snapshots first.
- Taking snapshots needs the Editor or Owner role.

## 404 or `{"message": ...}` from the API

- Check the base path: the service answers on `/remotefs/v1`, not the
  `/domino-netapp-volumes/v1` the 6.1 API page lists
  ([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md#base-path-and-shapes)).
- Inside a run, volume, filesystem and snapshot operations work on
  `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` with the `localhost:8899` access token as a
  bearer; `$DOMINO_API_PROXY` and the in-run `$DOMINO_API_HOST` can return 404 for them, and
  the hostport without the header returns 401. Outside Domino use the deployment URL with a
  service-account token (or a user API key in `X-Domino-Api-Key`).
- Snapshot list filters are snake_case (`volume_id`).
- A 400 on create, grants or snapshots usually means a body taken from the 6.1 API page:
  create needs `grants`, the grants `PUT` takes a bare array of `{"targetId", "targetRole"}`,
  and snapshots take `description`, not `name`
  ([API-NETAPP-VOLUMES.md](./API-NETAPP-VOLUMES.md)).

## Slow reads

- Prefer Parquet or Feather over CSV; read only needed columns.
- Use Dask or chunked reads for files larger than memory.
- Choose a hardware tier on the same data plane as the filesystem (`dataPlaneId` on the
  volume and filesystem records).
