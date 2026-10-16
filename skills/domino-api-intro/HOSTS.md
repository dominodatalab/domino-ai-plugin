# Which base URL for which API

Base URL and credential for each place code runs: [SKILL.md](./SKILL.md#authentication).

Do not derive the deployment URL from a JWT claim, and do not copy hostnames out of one
execution into another. For API calls, read `DOMINO_API_HOST` or `DOMINO_API_PROXY` where the
call runs. For links a user opens, use a URL an API response returns or the deployment URL the
user gives you: inside a run `DOMINO_API_HOST` and `DOMINO_USER_HOST` can be in-cluster or
in-pod addresses.

## One base for the Public API

The Public API has a single server, the deployment hostname. From outside
Domino the `/api/...`, `/remotefs/v1` and `/model-monitor/...` paths are served on that
base (for example `GET /api/users/v1/self`, `/api/jobs/beta/jobs`, `/api/taxonomy/v1/config`
and `/remotefs/v1/volumes`), with the
documented exception that NetApp file operations under `/remotefs/v1/.../files/*` take a
`/webvfs` prefix. The dataset files service is different: from outside,
the spec's `/datasetrw/...` snapshot-file routes return 404 (HTML), and only the
`/v4/datasetrw/...` form answers (non-public route; may change in a future Domino version, see [route types](./SKILL.md#route-types)).
Inside a run `$DOMINO_API_PROXY` or
`$DOMINO_API_HOST` stands in for the base for the platform `/api/...` routes, but not for
`/remotefs/v1` (NetApp Volumes, below).

## Inside an App

An App serves many viewers but runs as one user, the publisher (the user the App run was
started as). Which identity a call carries:

| Call | Acts as |
|---|---|
| `$DOMINO_API_PROXY/<path>` with no `Authorization` header, or a bearer from `$DOMINO_API_PROXY/access-token` | The publisher, for every viewer |
| `$DOMINO_API_HOST/<path>` with the viewer's `Authorization` header forwarded unchanged | The viewer |
| `$DOMINO_API_HOST/<path>` with no `Authorization` header | The publisher |

- Domino authenticates each request before it reaches the App and, with secure identity
  propagation on (the default), sends the viewer's token as `Authorization: Bearer <jwt>`.
  Without extended identity propagation that token lasts about 5 minutes, has audience `apps`,
  and only Dataset snapshot file reads and Data Source lookup by name accept it; other routes
  reject it, often with HTTP 500. With extended identity propagation (turned on for the App
  version by a SysAdmin or CloudAdmin, and permanent for that App) and the viewer's consent, it
  is the viewer's own credential with the viewer's permissions.
- When the App means to act as the viewer and no token arrived, answer 401. Never retry
  without the header: on the in-App `DOMINO_API_HOST` that runs as the publisher.
- `DOMINO_API_HOST` can be a gateway inside the App's pod (`http://127.0.0.1:<port>`). It
  accepts browser-session, service-account and Personal Access Token bearers and answers 403 to
  tokens from the Domino CLI login.
- `localhost:8899` is the default address behind `DOMINO_API_PROXY`, not a fixed one; read the
  variable.
- Reading the viewer's name, verifying the token, consent redirects and the URL prefix:
  [domino-apps](../domino-apps/SKILL.md).

## NetApp Volumes (`/remotefs/v1`)

Reference: https://docs.domino.ai/cloud/reference/api/domino-volumes-api (file-operation
hosts are spelled out on the 6.3 page,
https://docs.domino.ai/6.3/reference/api/domino-volumes-api).

| Operation | Inside a run | Outside Domino |
|-----------|--------------|----------------|
| Volume and filesystem CRUD, snapshots, grants, transfers | `$DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` **only**, always with `Authorization: Bearer` from `http://localhost:8899/access-token` (also served at `$DOMINO_API_PROXY/access-token`). `$DOMINO_API_PROXY` and the in-run `$DOMINO_API_HOST` return 404 for `/remotefs/v1/*`, and the hostport without a header returns 401 | deployment URL with a PAT or service account token |
| File operations under `/remotefs/v1/volumes/{id}/files/*` and `/remotefs/v1/snapshots/{id}/files/*` | `http://data-webvfs-service.domino-compute:80` with the path as shown in the reference; send the same access-token bearer as for the other remotefs routes | deployment URL with `/webvfs` prefixed to the path |

Details: [netapp-volumes](../netapp-volumes/API-NETAPP-VOLUMES.md).

## Model API invocation

Management calls (`/api/modelServing/v1/...`, `/api/registeredmodels/...`) use the Public
API base. Prediction requests go to the Model API's own URL shown on its page in Domino,
with the endpoint's access token, not a platform token:

- Restricted **synchronous** endpoints: HTTP Basic with the access token as both username
  and password.
- Restricted **asynchronous** endpoints (`/api/modelApis/async/v1/{asyncModelId}`):
  `Authorization: Bearer <access token>`.
- Unrestricted endpoints: no token.

Source: https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/domino-endpoint-authorization.
Workflow: [domino-model-endpoints](../domino-model-endpoints/SKILL.md).

## Governance

Governance routes use the suffix `/api/governance/v1` on the same base. The
[domino-governance](../domino-governance/SKILL.md) skill owns base resolution: try
`$DOMINO_API_PROXY`, then `$DOMINO_API_HOST` with an access token, and on a 404 fall back
to the deployment URL with a PAT or service account token. Use that skill's procedure
rather than restating it.

## 404 on the in-run base

If an `/api/...` route returns 404 on `$DOMINO_API_PROXY` or `$DOMINO_API_HOST` inside a
run, confirm the path against [API-SPECS.md](./API-SPECS.md), then retry on the deployment
URL with a PAT or service account token. Whether the in-run gateway routes a service is a
deployment setting, not something the caller can change.

## Related

- [LIMITS.md](./LIMITS.md) pagination and deprecated credentials
- [ERRORS.md](./ERRORS.md) status codes and retries
- [API-SPECS.md](./API-SPECS.md) OpenAPI files and route discovery
