# External Data Volumes (EDVs)

An EDV mounts a network filesystem that Domino does not own into executions. A Kubernetes admin
creates a labelled PersistentVolumeClaim, a Domino admin registers it, and users add it to
Projects. Domino does not propagate the user's identity to the underlying filesystem; access is
whatever the PVC and the storage grant.

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/external-volumes
(users), https://docs.domino.ai/cloud/admin/data-administration/external-data/external-data-volumes
(admins), https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/sharing-and-security/share-edv
(access control). Replace `/cloud/` with `/6.3/` for the self-managed pages.

**Domino Cloud**: EDVs require a remote Data Plane. **Domino 6.3**: available on the local Data
Plane too.

## Mount path and usage

Every EDV added to a Project mounts at `/domino/edv/<name>`, where `<name>` is the **Relative
Mount Path** the admin chose at registration (defaults to the PVC name, unique across EDVs). The
Project's **Data > External Data Volumes** page lists Name, Type (NFS, EFS, SMB or Generic),
Description and Mount Path for each volume.

```python
import json
import pandas as pd

with open("/domino/edv/finance-share/config.json") as f:
    config = json.load(f)
df = pd.read_parquet("/domino/edv/finance-share/datasets/sales.parquet")
```

Read-only or read-write is set per EDV at registration. Read-write is enforced at the Domino
layer only: a read-only PVC access mode or filesystem permission wins regardless.

## Add an EDV to a Project (user)

1. In the Project, **Data > External data volumes > Add External Volume**.
2. Pick the volume and click **Add**. If none is listed, the admin has not given you **Volume
   Access**; ask them.
3. By default every EDV added to the Project (that you can access) mounts in each execution. On
   the Workspace or Job launch form you can restrict which EDVs mount for that execution.
4. Every EDV an execution uses must bind successfully during startup; if any binding fails the
   execution does not start. Each EDV also adds startup latency, so select only the volumes
   the task needs.

Remove it from **Data > External data volumes** with the three-dot menu. The same add, list and
remove operations exist as `POST`, `GET` and `DELETE /v4/datamount/projects/{projectId}`
(non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types); see "Non-public routes" below).

## Register an EDV (admin)

### 1. Create the PV and PVC (Kubernetes admin)

A PVC is eligible when all three hold:

- label key `dominodatalab.com/external-data-volume` is present;
- its value is the storage type: `NFS`, `SMB`, `EFS` or `Generic`;
- it lives in the Domino compute namespace (`domino-compute` by default).

NFS example from the admin docs (adjust namespace, names, server and path):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-nfs
  namespace: domino-compute
  labels:
    "dominodatalab.com/external-data-volume": "NFS"
spec:
  storageClassName: ""
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 30Gi
  volumeName: pv-nfs
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-nfs
spec:
  storageClassName: ""
  accessModes:
    - ReadWriteMany
  capacity:
    storage: 30Gi
  claimRef:
    apiVersion: v1
    kind: PersistentVolumeClaim
    name: pvc-nfs
    namespace: domino-compute
  persistentVolumeReclaimPolicy: Retain
  nfs:
    path: /mnt/export
    server: 10.0.0.26
```

- **EFS**: same shape with `csi.driver: efs.csi.aws.com` and `volumeHandle: <fs-id>:/<path>`;
  label value `EFS`.
- **SMB**: `csi.driver: smb.csi.k8s.io`, a `nodeStageSecretRef` for the share credentials and
  `mountOptions` such as `dir_mode=0777`, `file_mode=0777`, `vers=3.0`; label value `SMB`. The
  SMB driver is off by default; on 6.3 enable it in the installer configuration with
  `release_overrides: csi-driver-smb: installed: true` and re-run the installer.
- **Generic**: any PV you provision yourself (for example a Mountpoint for Amazon S3 volume, see
  [S3-MOUNTPOINT.md](./S3-MOUNTPOINT.md)); label value `Generic`.

### 2. Register it (Domino admin)

**Admin > Manage resources > External Data Volumes > Register External Volume**:

| Step | Fields |
|---|---|
| Volume | Storage type and the backing PVC from **Available Volumes**. In a hybrid deployment Domino also lists the Data Planes where a PVC of that name exists |
| Configuration | **Name** (defaults to the PVC name), **Relative Mount Path** (defaults to the PVC name; becomes `/domino/edv/<path>`), **Mount as read-only**, **Description** |
| Access | **Volume Access**: **Everyone** or **Specific users or organizations** |

Admins can always access any EDV. Users without access either see nothing about the volume
("full censorship") or see its name and description so they can request access ("inactive
censorship", the default). On 6.3 this is the `ShortLived.ExternalDataVolumesFullCensor`
feature flag; on Cloud ask Domino Support.

Edit, unregister, and add or remove Data Planes from the same page (three-dot menu > **Edit**;
a PVC with the same name in another Data Plane shows up as an addition).

## Non-public routes

The Public API has no EDV routes. The Domino Internal API has the full set; every route here is
**non-public route; may change in a future Domino version**, as documented in the 6.4.0 internal
reference (`/docs`, `openapi-internal.json`); if a call answers 404 or 400, confirm the route and
body in your deployment's `/docs`. Registration, update and unregistration
are admin operations: document them, never run them from a user context.

| Call (non-public route; may change in a future Domino version) | Notes |
|---|---|
| `GET /v4/datamount/all` | Every registered EDV (`DataMountDto`: `id`, `name`, `volumeType`, `pvcName`, `mountPath`, `readOnly`, `isPublic`, `users`, `projects`, `status`, `dataPlanes`). Returned `[]` on the test deployment |
| `GET /v4/datamount/pvcs/available?volumeType=Nfs` (`Smb`, `Efs`, `Generic`) | Labelled PVCs not yet registered |
| `GET /v4/datamount/isMountPathValid?mountPath=<name>` | Whether a Relative Mount Path is unique and free of reserved words |
| `POST /v4/datamount` (admin) | Register. Body `{"name", "volumeType": "Nfs" / "Smb" / "Efs" / "Generic", "pvcName", "mountPath", "users": [<user ids>], "readOnly", "isPublic", "dataPlaneIds": [], "description", "pvId"}`; `name`, `volumeType`, `pvcName`, `mountPath`, `users`, `readOnly`, `isPublic`, `dataPlaneIds` required. `isPublic: true` is **Everyone**; otherwise list the users |
| `POST /v4/datamount/{datamountId}` (admin) | Update: same fields plus `id`, `projects`, `isRegistered`, `status` |
| `DELETE /v4/datamount/{datamountId}` (admin) | Unregister |
| `GET /v4/datamount/projects/{projectId}` | EDVs added to a Project (what **Data > External data volumes** shows) |
| `POST /v4/datamount/projects/{projectId}?datamountIds=<id>&datamountIds=<id>` | Add EDVs to a Project (the **Add External Volume** button); needs Volume Access to each |
| `DELETE /v4/datamount/projects/{projectId}?datamountId=<id>` | Remove an EDV from a Project |
| `GET /v4/datamount/projects/inaccessible/{projectId}` | EDVs on the Project the caller cannot access |

Mount path in executions stays `/domino/edv/<mountPath>` whichever way the EDV was added.

## Troubleshooting

| Symptom | Check |
|---|---|
| PVC not listed under **Available Volumes** | Label key and value, namespace, and that the PVC is `Bound` (`kubectl get pvc -n domino-compute -l dominodatalab.com/external-data-volume`) |
| User cannot see or add the EDV | **Volume Access** on the EDV; collaborators on a Project do not inherit each other's access |
| Writes fail on a read-write EDV | PVC access mode and filesystem permissions override the Domino setting; check `uid`/`gid` on the share |
| Execution fails to start after adding an EDV | The volume could not bind; check the PV/PVC status and the storage backend, or exclude the EDV on the launch form |
| EDV missing on Domino Cloud | EDVs need a remote Data Plane; see https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data-plane |

General data-access diagnosis (network routes, Data Plane locality):
https://docs.domino.ai/cloud/admin/data-administration/troubleshoot-data
