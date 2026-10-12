# AWS identity for Domino workloads: credential propagation, IRSA and Pod Identity

Three ways to give code in a Workspace or Job an AWS identity without long-lived keys, from the
documented product feature to the Professional Services blueprints. All three are self-managed
(Domino 6.3) procedures that need AWS and cluster administration; on Domino Cloud, ask Domino
Support for the equivalent.

First check whether a Data Source fits: an S3, Redshift, MySQL or PostgreSQL Data Source
(`domino-data-sdk`) needs none of this and is the default. Use an option below when access must be
attributable to the user in CloudTrail, or the code needs an AWS service no connector covers.

| Option | Identity | Workload types | Where documented |
|---|---|---|---|
| AWS credential propagation (SAML) | The user's own IAM roles, chosen by the identity provider | Workspaces and Jobs started by the user | https://docs.domino.ai/6.3/admin/identity-and-access/authentication/sso/aws-credential-propagation |
| IAM-authenticated Data Sources | The user's SAML-propagated AWS role, read from `AWS_SHARED_CREDENTIALS_FILE` (requires credential propagation; 6.3 admins add `AWSIAMRole` to `com.cerebro.domino.datasource.<Type>Config.enabledAuthTypes`, Cloud asks Domino Support) | Workspaces and Jobs (not scheduled Jobs or endpoints) | https://docs.domino.ai/6.3/admin/data-administration/external-data#iam-authentication-for-aws-data-sources |
| IRSA through Domsed (blueprint) | A Kubernetes service account mapped per Domino user, trusted by IAM roles in any account | Workspace, Batch (Job), Scheduled; selectable by label | https://domino.ai/resources/blueprints/aws-irsa, code in https://github.com/dominodatalab/domino-blueprints (IRSA-README.md, advanced-credential-propagation/irsa) |
| EKS Pod Identity (blueprint) | A static service account mapped per Domino service account | Same as IRSA; EKS only | https://domino.ai/resources/blueprints/advanced-credential-propagation-aws-eks, code in advanced-credential-propagation/eks-pod-identity |

## 1. AWS credential propagation (documented)

With SSO enabled, Domino exchanges the user's SAML assertion for temporary role credentials
(`sts:AssumeRoleWithSAML`) and refreshes them during the session.

Follow the docs page end to end; its key steps are:

1. Federate the AWS account with the identity provider; create a SAML identity provider in IAM.
2. Create each role with `SAML 2.0 federation` as the trusted entity, then edit its trust policy
   to allow both `sts:AssumeRoleWithSAML` from the provider and `sts:AssumeRole` from the role's
   own ARN (Domino refreshes credentials mid-session, so the role must be able to assume itself).
3. Create a permissions policy allowing `sts:AssumeRole` and `sts:AssumeRoleWithSAML` on the
   role's ARN and attach it to the role.
4. Have the identity provider emit `https://aws.amazon.com/SAML/Attributes/Role`
   (`<provider-arn>,<role-arn>`, multi-valued), `.../RoleSessionName` and `.../SessionDuration`.
5. In Keycloak, on the SAML identity provider turn **Store Tokens** and **Store Tokens
   Readable** on (Domino needs the users' SAML assertions), and add `Attribute Importer` mappers
   for the three attributes to user attributes `aws-roles`, `aws-role-session-name` and
   `aws-session-duration`.
6. On the `domino-play` client add a mapper named `identity-provider-mapper` of type
   User Session Note, note `identity_provider`, token claim `idpbroker`.
7. In **Admin > Platform Settings > Configuration Records** set
   `com.cerebro.domino.auth.aws.sts.enabled=true`, `com.cerebro.domino.auth.aws.sts.region`
   (for example `us-west-2`) and `com.cerebro.domino.auth.aws.sts.defaultSessionDuration`
   (for example `1h`), then restart services. Users log out and in again.

What the user sees: `AWS_SHARED_CREDENTIALS_FILE` points at
`/var/lib/domino/home/.aws/credentials`, one profile per role. boto3, the AWS CLI and the
Data API pick it up without code changes:

```python
import boto3

session = boto3.Session(profile_name="DataScientist-dev")   # omit for the default profile
for obj in session.resource("s3").Bucket("my-bucket").objects.filter(Prefix="raw/"):
    print(obj.key)
```

## 2. IRSA through Domsed (blueprint)

IAM Roles for Service Accounts lets a pod call `sts:AssumeRoleWithWebIdentity` with a JWT that
the EKS cluster's OIDC provider issues for the pod's Kubernetes service account. Domino's
adaptation uses Domsed, a Domino-aware mutating webhook
(https://github.com/dominodatalab/domino-field-solutions-installations/tree/main/domsed), to
swap the workload's generated service account for one mapped to the Domino user and to project
the token into the pod. It works across AWS accounts and for scheduled Jobs, which SAML
propagation does not cover.

Prerequisites (from the blueprint): Domsed installed; one Kubernetes service account per mapped
user in `domino-compute`; agreement with Domino Professional Services, because this changes how
Domino manages pod identity.

### Steps

1. Create a service account per user:

   ```bash
   kubectl -n domino-compute create sa sa-jane-doe
   ```

2. In every AWS account whose roles the workloads will assume, register the EKS cluster's OIDC
   provider as an IAM identity provider. Its ARN has the form
   `arn:aws:iam::<TARGET_ACCOUNT>:oidc-provider/oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>`
   (`eksctl utils associate-iam-oidc-provider --cluster <name> --approve` creates it in the
   cluster's own account).

3. Trust the service accounts in each role's trust policy:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {
         "Federated": "arn:aws:iam::<TARGET_ACCOUNT>:oidc-provider/oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>"
       },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringLike": {
           "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>:sub": [
             "system:serviceaccount:domino-compute:sa-jane-doe"
           ]
         }
       }
     }]
   }
   ```

   Attach a least-privilege permissions policy to the role (named buckets and prefixes; no
   `*` resources). Hardening beyond the blueprint, per AWS's IRSA
   guidance: use `StringEquals` on `sub` and add
   `"oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>:aud": "sts.amazonaws.com"` so only tokens
   minted for STS can assume the role.

4. Apply the Domsed mutation in `domino-platform`. This is the blueprint's
   `user-identity-based-irsa.yaml`, with the user mappings and region edited:

   ```yaml
   apiVersion: apps.dominodatalab.com/v1alpha1
   kind: Mutation
   metadata:
     name: user-identity-based-irsa
     namespace: domino-platform
   rules:
   - labelSelectors:
     - dominodatalab.com/workload-type in (Workspace,Batch,Scheduled)
     cloudWorkloadIdentity:
       cloud_type: aws
       default_sa: ""
       assume_sa_mapping: false
       user_mappings:
         jane-doe: sa-jane-doe
         john-doe: sa-john-doe
     insertVolumes:
     - name: aws-user-token
       projected:
         defaultMode: 422
         sources:
         - serviceAccountToken:
             audience: sts.amazonaws.com
             expirationSeconds: 86400
             path: token
     insertVolumeMounts:
       volumeMounts:
         - mountPath: /var/run/secrets/eks.amazonaws.com/serviceaccount/
           name: aws-user-token
     modifyEnv:
       env:
       - name: AWS_WEB_IDENTITY_TOKEN_FILE
         value: /var/run/secrets/eks.amazonaws.com/serviceaccount/token
       - name: AWS_DEFAULT_REGION
         value: us-west-2
       - name: AWS_REGION
         value: us-west-2
       - name: AWS_STS_REGIONAL_ENDPOINTS
         value: regional
     modifySecurityContext:
       context:
         fsGroup: 12574
   ```

   `user_mappings` keys are Domino usernames; `default_sa` is the service account for unmapped
   users (empty keeps Domino's generated one); `labelSelectors` matches the pod label
   `dominodatalab.com/workload-type`. The projected token is a JWT whose `sub` is
   `system:serviceaccount:domino-compute:<sa>`, issued by the EKS OIDC provider, with `exp` set.

### Using it from a workload

Set the role to assume, then let boto3 do the exchange:

```python
import os
import boto3

os.environ["AWS_ROLE_ARN"] = "arn:aws:iam::<TARGET_ACCOUNT>:role/my-irsa-test-role"
print(boto3.client("sts").get_caller_identity()["Arn"])
# arn:aws:sts::<TARGET_ACCOUNT>:assumed-role/my-irsa-test-role/botocore-session-...
```

Several roles at once: declare profiles in `~/.aws/config` (or the file named by
`AWS_CONFIG_FILE`) using the standard AWS SDK `web_identity_token_file` and `source_profile`
settings (https://docs.aws.amazon.com/sdkref/latest/guide/feature-assume-role-credentials.html);
no keys appear anywhere.

```ini
[profile domino-irsa]
role_arn = arn:aws:iam::<TARGET_ACCOUNT>:role/DominoWorkloadRole
web_identity_token_file = /var/run/secrets/eks.amazonaws.com/serviceaccount/token

[profile data-account]
role_arn = arn:aws:iam::<OTHER_ACCOUNT>:role/DataAccessRole
source_profile = domino-irsa
role_session_name = domino-workload
```

```python
s3 = boto3.Session(profile_name="data-account").client("s3")
```

The second role's trust policy names the first role's ARN as principal for `sts:AssumeRole`.

## 3. EKS Pod Identity (blueprint)

Same Domsed mechanism, but the identity comes from EKS Pod Identity associations instead of
OIDC federation, so it is EKS-only and keyed on Domino service accounts rather than users:

1. Install the **EKS Pod Identity Agent** add-on on the cluster and give the node role
   `eks-auth:AssumeRoleForPodIdentity` (AWS prerequisites, called out in the blueprint).
2. Create Domino service accounts (https://docs.domino.ai/6.3/admin/identity-and-access/manage-users/service-accounts)
   and one static Kubernetes service account each in `domino-compute`.
3. Create Pod Identity associations from each Kubernetes service account to its IAM role; the
   role trusts `pods.eks.amazonaws.com` for `sts:AssumeRole` and `sts:TagSession`.
4. Apply a `Mutation` with the same `labelSelectors` and a `cloudWorkloadIdentity` block whose
   `user_mappings` map Domino service-account names to the Kubernetes service accounts. No
   projected volume or environment variables are needed; the Pod Identity agent injects them.

## Troubleshooting

| Symptom | Check |
|---|---|
| `AWS_WEB_IDENTITY_TOKEN_FILE` unset or file missing | The pod did not match the mutation: `kubectl describe pod <pod> -n domino-compute` and compare labels with `labelSelectors`; confirm Domsed is running in `domino-platform` |
| Pod runs as Domino's generated service account | The username is not in `user_mappings` and `default_sa` is empty |
| `AccessDenied` on `AssumeRoleWithWebIdentity` | Trust policy `sub` condition versus `system:serviceaccount:domino-compute:<sa>`; OIDC provider registered in the target account; `AWS_ROLE_ARN` spelled correctly |
| Credentials expire mid-run | `expirationSeconds` on the projected token (86400 in the blueprint); STS session duration on the role |
| Wrong identity | `boto3.client("sts").get_caller_identity()` shows the assumed role; check profiles in `~/.aws/config` |

Inspect without entering the pod:

```bash
kubectl get serviceaccount sa-jane-doe -n domino-compute -o yaml
kubectl describe pod <pod> -n domino-compute | grep -A3 -E "AWS_WEB_IDENTITY_TOKEN_FILE|aws-user-token"
```
