# Azure Entra ID user-token propagation (blueprint)

Gives code running in a user's Workspace, Job or scheduled Job an OAuth access token for that
user's Entra ID (formerly Azure AD) identity, so Azure Storage, ADLS Gen2, Databricks, Azure SQL
and other Entra-protected services authorise and audit the individual user. There is no
product-side configuration file for this: it is a Keycloak configuration plus a small Python
package, published as a Professional Services blueprint.

- Blueprint: https://domino.ai/resources/blueprints/domino-azure-credential-propagation
- Code and setup guide: https://github.com/dominodatalab/domino-blueprints
  (`AD-User-README.md`, `advanced-credential-propagation/azure-ad-user-tokens/README.md`)
- Blueprints index on docs.domino.ai: https://docs.domino.ai/cloud/examples/blueprints

Applies to self-managed Domino 6.3, where your team administers Keycloak at
`https://<domino-domain>/auth/`. On Domino Cloud, request it through Domino Support. For
service (non-user) identities, the companion "Azure authorization" blueprint
(https://domino.ai/resources/blueprints/azure-authorization, code in
`advanced-credential-propagation/azure-ad-advanced-auth`) maps Domino users or service
accounts to Azure Workload Identity through a Domsed `Mutation` with
`cloudWorkloadIdentity: cloud_type: azure`; code then uses Azure's own
`WorkloadIdentityCredential`. This file covers the user-token path only.

Two properties of the `domino_aad` package (0.0.4) shape everything below:

- **One token per identity provider.** `DominoCredential("<alias>").get_token(...)` ignores the
  scopes it is given and returns the token Keycloak exchanged for that alias. An Entra access
  token has one audience, so each Azure resource (Storage, SQL, Databricks) needs its own
  Keycloak identity provider with its own Default Scopes and its own alias.
- **No refresh after the first hour.** The credential caches the token it obtained at
  construction with a 3600-second expiry; when that passes it re-requests but discards the
  result, so calls keep presenting the stale token. Construct a new `DominoCredential` for each
  unit of work and never keep one for longer than an hour. Consent prompts use `input()`, so a Job whose user has not consented fails with `EOFError`;
  consent once from a Workspace first.

Prefer the documented alternatives when they fit: an Azure Blob, ADLS or Databricks **Data
Source** (https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/data-source-connectors)
keeps the key or service principal with the Data Source, managed by Domino, and needs no
Keycloak work.

## How it works

1. Keycloak (Domino's identity broker) is given an OIDC identity provider that points at an
   Entra application with the API permissions you want to delegate.
2. The first time a user asks for a token in a Workspace, the `domino_aad` package prints an
   Entra consent URL. After consent, Entra returns an access token and an offline refresh token;
   Keycloak stores the refresh token and the user never sees it.
3. Each new `DominoCredential` performs a Keycloak internal-to-external token exchange
   (`$DOMINO_API_PROXY/exchange-token?external_idp=<alias>`) and gets a current access token.
   Consent lasts as long as the refresh token, which the tenant controls; when it expires the
   user is prompted again.

## Setup (Keycloak and Entra admins)

### Entra application

Register (or reuse the SSO) application in the tenant. Under **API permissions**, add the
delegated permissions for each target service, for example `user_impersonation` on Azure
Storage (`https://storage.azure.com/`). Under **Authentication**, add the redirect URI that
Keycloak displays for the identity provider you create below.

### Keycloak identity provider

In the Keycloak admin console (**Domino Realm > Identity providers > Add provider > OpenID
Connect v1.0**):

1. In Entra, copy the application's **OpenID Connect metadata document** URL
   (**Overview > Endpoints**) and import it into the new provider.
2. Set **Client ID** and **Client secret** from the application. Store the secret in the
   Keycloak form only; never in code, notebooks or chat.
3. Enable **Store Tokens** and **Stored Tokens Readable**; set **First Login Flow** to
   `Domino First Broker Login`; turn **Account Linking Only** and **Disable user info** on.
4. Under **Mappers**, add an `Attribute Importer` mapping claim `email` to user attribute
   `email`.
5. Under **Default Scopes**, enter the scopes to request, for example
   `offline_access https://storage.azure.com/user_impersonation`. The resource scope must match
   the API permission you granted. One resource per provider: for Azure SQL create a second
   provider (alias `azsql`, say) with `offline_access https://database.windows.net/user_impersonation`,
   and so on for each resource.

### Token exchange permission

Follow the Keycloak token-exchange guide (https://www.keycloak.org/securing-apps/token-exchange)
to allow the `domino-play` client to exchange tokens with each new identity provider; in the
client-policy step, `domino-play` is the client. Internal-to-external exchange is part of
Keycloak's legacy token exchange (V1), which Keycloak marks deprecated and does not enable by
default; Domino's bundled Keycloak exposes it through `$DOMINO_API_PROXY/exchange-token`, so
confirm with Domino before relying on it.

### Workload package

Install the exchange helper in the compute environment (Dockerfile) or the Workspace. The
blueprint distributes it as a wheel; take the current URL from the blueprint README:

```dockerfile
USER root
RUN python -m pip install https://mirrors.domino.tech/domino_aad-0.0.4-py3-none-any.whl
USER ubuntu
```

## Using it in a workload

`DominoCredential("<idp-alias>")` is an Azure `TokenCredential`; pass it wherever an Azure SDK
client takes `credential=`. The alias is the Keycloak identity-provider alias (`azstorage` in
the blueprint), and it decides which resource the token is for; the scope the Azure SDK asks
for is ignored. On the first call it prints a consent URL; open it, grant access, return to the
Workspace and press Enter. Create the credential inside the function that uses it rather than
once per process (no refresh after an hour, see above).

```python
from domino_aad import DominoCredential
from azure.storage.blob import BlobServiceClient

creds = DominoCredential("azstorage")
blob = BlobServiceClient("https://mystorageaccount.blob.core.windows.net", credential=creds)
for container in blob.list_containers(include_metadata=True):
    print(container["name"])
```

ADLS Gen2 and a pandas read:

```python
from io import StringIO
import pandas as pd
from azure.storage.filedatalake import DataLakeServiceClient

dl = DataLakeServiceClient("https://mystorageaccount.dfs.core.windows.net", credential=creds)
fs = dl.get_file_system_client("lake")
content = fs.get_file_client("sales/2026/sales.csv").download_file().readall().decode()
df = pd.read_csv(StringIO(content))
```

Azure SQL through pyodbc needs a token whose audience is the database service, so it comes from
a separate identity provider configured with the `https://database.windows.net/user_impersonation`
scope (alias `azsql` here); `get_token()` takes no scope because the alias already fixes it:

```python
import struct
import pyodbc

sql_creds = DominoCredential("azsql")
token = sql_creds.get_token().token.encode("utf-16-le")
token_struct = struct.pack(f"<I{len(token)}s", len(token), token)
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};SERVER=myserver.database.windows.net;DATABASE=mydb;",
    attrs_before={1256: token_struct},   # SQL_COPT_SS_ACCESS_TOKEN
)
```

`DefaultAzureCredential` does not find Domino-propagated tokens; use `DominoCredential`.

## Azure RBAC

Access on the Azure side is the user's own RBAC. Minimal roles for storage:

| Role | Permissions |
|---|---|
| Storage Blob Data Reader | Read blobs |
| Storage Blob Data Contributor | Read, write, delete blobs |
| Storage Blob Data Owner | Full access including POSIX ACLs |

```bash
az role assignment create \
  --role "Storage Blob Data Reader" \
  --assignee user@example.com \
  --scope /subscriptions/SUB_ID/resourceGroups/RG/providers/Microsoft.Storage/storageAccounts/ACCOUNT
```

Scope assignments to the storage account or container, enable Azure Monitor diagnostic
settings for audit, keep client-secret lifetimes short and apply Conditional Access policies.

## Troubleshooting

| Symptom | Check |
|---|---|
| Consent URL appears on every call | **Store Tokens** / **Stored Tokens Readable** off, or `offline_access` missing from the provider's default scopes |
| `EOFError` in a Job | The user has not consented for this alias; run the code once in a Workspace and complete the consent URL |
| Token exchange denied | The `domino-play` client lacks the token-exchange permission for this provider, or legacy token exchange is not enabled in Keycloak |
| `AuthorizationPermissionMismatch` | The user's Azure RBAC role or scope; role propagation can take a few minutes |
| Azure rejects the token's audience (`InvalidAuthenticationToken`, `AADSTS500011`-style errors) | The alias points at a provider for a different resource; one provider per resource, matching the application's API permissions |
| Token expired after about an hour of use | `DominoCredential` does not refresh; construct a new one. If a fresh one also fails, the refresh token expired in the tenant and the user consents again |
