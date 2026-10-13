# Mount an S3 bucket as a filesystem: Mountpoint for Amazon S3 as a Generic EDV (blueprint)

Mountpoint for Amazon S3's CSI driver mounts a bucket on the compute node; Domino exposes it to
Projects as a **Generic External Data Volume**, so Workspaces, Jobs and Apps browse the bucket
at `/domino/edv/<name>` without FUSE privileges in the container.

- Blueprint: https://domino.ai/resources/blueprints/transforming-s3-into-local-storage, code in
  https://github.com/dominodatalab/domino-blueprints/tree/main/mountpoint-s3
- Driver: https://github.com/awslabs/mountpoint-s3-csi-driver. The blueprint pins no version;
  the manifests here (`uid`, `gid`, `allow-other`) are for the v1 driver (1.15.0, the last v1
  release). The v2 line changes the architecture and is not validated on Domino; see "Driver
  v2" below before choosing it.
- EDV registration (product docs): https://docs.domino.ai/cloud/admin/data-administration/external-data/external-data-volumes
- Mountpoint semantics and limits: https://docs.aws.amazon.com/AmazonS3/latest/userguide/mountpoint.html

Self-managed Domino 6.3 on EKS. On Domino Cloud, ask Domino Support; an S3 **Data Source**
(https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/data-source-connectors/connect-to-amazon-s3)
gives the same bucket through the Data API without any cluster change and is the default
choice on either target. Azure Blob and GCS equivalents are a separate blueprint
(https://domino.ai/resources/blueprints/turn-cloud-object-storage-into-local-filesystems).

Use Mountpoint for large, read-mostly data that tools expect as files. Not for write-heavy or
random-write workloads: Mountpoint supports sequential writes to new objects, no edits in place,
and the AWS page lists the rest.

## Setup (AWS, Kubernetes and Domino admins)

Prerequisites: AWS account rights for IAM, `kubectl` and `helm` against the Domino EKS cluster,
and Domino admin rights.

### 1. IAM policy and role for the driver

Policy scoped to the bucket (add more buckets as separate resources):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::my-bucket"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
```

Drop `s3:PutObject` and `s3:DeleteObject` for a read-only mount. Create the role only; the Helm
chart creates and annotates the service account in the namespace where you install the driver
(the blueprint uses `domino-platform`, the upstream docs `kube-system`):

```bash
eksctl create iamserviceaccount \
  --name s3-csi-driver-sa \
  --namespace domino-platform \
  --cluster CLUSTER_NAME \
  --attach-policy-arn arn:aws:iam::ACCOUNT_ID:policy/MountpointS3Policy \
  --role-name MountpointS3Role \
  --region REGION \
  --role-only \
  --approve
```

### 2. Install the CSI driver

Install from the Helm repository (installing from a GitHub branch is unsupported upstream) and
pin the chart version you reviewed:

```bash
helm repo add aws-mountpoint-s3-csi-driver https://awslabs.github.io/mountpoint-s3-csi-driver
helm repo update
helm upgrade --install aws-mountpoint-s3-csi-driver \
  aws-mountpoint-s3-csi-driver/aws-mountpoint-s3-csi-driver \
  --version 1.15.0 \
  --namespace domino-platform \
  --set node.serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=arn:aws:iam::ACCOUNT_ID:role/MountpointS3Role
```

**Driver v2** runs Mountpoint in separate pods in the `mount-s3` namespace with a preempting
priority class (conflicts with Karpenter and Cluster Autoscaler) and sets `fsGroup` and
`mountOptions` itself, so the `uid`/`gid`/`allow-other` flags below may be redundant. Test v2 on
a non-production Domino cluster first.

### 3. PersistentVolume and labelled PersistentVolumeClaim

The PVC must carry the EDV label with value `Generic` and live in the compute namespace
(blueprint YAML; `volumeHandle` must be unique per bucket):

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: mountpoints3-pv
spec:
  capacity:
    storage: 10Gi                 # ignored by the driver, required by Kubernetes
  accessModes:
    - ReadWriteMany               # or ReadOnlyMany
  storageClassName: ""            # static provisioning
  claimRef:
    namespace: domino-compute
    name: mountpoints3-pvc
  mountOptions:
    - uid=12574                   # Domino's container user
    - gid=12574
    - allow-other
    - allow-overwrite
    - allow-delete
    - region us-west-2
    # - prefix datasets/sales/    # mount one prefix only
    # - read-only
  csi:
    driver: s3.csi.aws.com
    volumeHandle: s3-csi-driver-my-bucket
    volumeAttributes:
      bucketName: my-bucket
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mountpoints3-pvc
  namespace: domino-compute
  labels:
    dominodatalab.com/external-data-volume: Generic
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  resources:
    requests:
      storage: 10Gi
  volumeName: mountpoints3-pv
```

`mountOptions` are Mountpoint command-line flags
(https://github.com/awslabs/mountpoint-s3/blob/main/doc/CONFIGURATION.md): `region`, `prefix`,
`read-only`, `allow-delete`, `allow-overwrite`, `allow-other`, `uid`, `gid`, `cache <dir>`.

### 4. Register the EDV in Domino

**Admin > Manage resources > External Data Volumes > Register External Volume**: type
**Generic**, pick `mountpoints3-pvc`, set the **Name** and **Relative Mount Path** (the
mount becomes `/domino/edv/<path>`), tick **Mount as read-only** unless writes are intended, and
set **Volume Access**. Details in [EXTERNAL-DATA-VOLUMES.md](./EXTERNAL-DATA-VOLUMES.md).

## Using it

Users add the EDV under **Data > External data volumes** in the Project and read it as files:

```python
import os
import pandas as pd

root = "/domino/edv/s3-data"
print(os.listdir(f"{root}/datasets"))
df = pd.read_parquet(f"{root}/datasets/large_dataset.parquet")
df.to_parquet(f"{root}/outputs/results.parquet")     # new object; Mountpoint cannot edit in place
```

Spark reads the mount like any local path (`spark.read.parquet("/domino/edv/s3-data/datasets/")`).

Performance: first access of an object is slower than later reads; sequential reads beat
random reads; prefer Parquet and files of 100 MB to 1 GB over many small files; writes upload
on close. Keep the bucket in the cluster's region.

## Troubleshooting

```bash
kubectl get pods -n domino-platform -l app=s3-csi-node          # one per node, Running
kubectl logs -n domino-platform -l app=s3-csi-node --tail=200   # v1: Mountpoint logs are here
kubectl logs -n domino-platform -l app=s3-csi-controller --tail=200
kubectl get pods -n mount-s3                                     # v2 only: one Mountpoint pod per volume
kubectl logs -n mount-s3 -l s3.csi.aws.com/volume-name=mountpoints3-pv --tail=200   # v2 only
kubectl get pv mountpoints3-pv; kubectl get pvc -n domino-compute mountpoints3-pvc   # both Bound
```

| Symptom | Check |
|---|---|
| PVC not offered at registration | Label `dominodatalab.com/external-data-volume: Generic`, namespace `domino-compute`, PVC `Bound` |
| `Access Denied` in the mount | Policy actions and bucket ARN; `eks.amazonaws.com/role-arn` annotation on the node service account; bucket region matches `region` |
| Files owned by another uid, writes fail | `uid=12574`, `gid=12574`, `allow-other`; `read-only` not set |
| Execution stuck at start | Node driver pods not Running; multiple S3 volumes in one pod need distinct `volumeHandle` values |
| Slow reads | Cross-region bucket; many small files; consider `cache <dir>` for repeated reads |

Security: keep the IAM policy bucket-scoped, add a bucket policy that allows only the driver
role's ARN, and register the EDV read-only unless a workflow needs to write.
