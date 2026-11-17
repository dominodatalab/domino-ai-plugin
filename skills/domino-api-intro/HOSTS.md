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
base (for example `GET /api/users/v1/self`, `/api/jobs/beta/jobs` and
`/remotefs/v1/volumes`). The dataset files service is different: from outside,
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
| `$DOMINO_API_HOST/<path>` with no `Authorization` header | The publisher |

- Domino authenticates each request before it reaches the App and sends the viewer's
  username in the `domino-username` header; when the administrator setting
  `SecureIdentityPropagationToAppsEnabled` is on, it also sends the viewer's token as
  `Authorization: Bearer <jwt>`. Use them to identify the viewer, not to call Domino APIs: an
  App cannot act as the viewer on Domino 6.1, so filter what each viewer sees in the App
  itself.
- `DOMINO_API_HOST` can be a gateway inside the App's pod (`http://127.0.0.1:<port>`). It
  accepts browser-session and service-account bearers and answers 403 to tokens from the
  Domino CLI login.
- `localhost:8899` is the default address behind `DOMINO_API_PROXY`, not a fixed one; read the
  variable.
- Reading the viewer's name and the URL prefix:
  [domino-apps](../domino-apps/SKILL.md).

## NetApp Volumes (`/remotefs/v1`)

Reference: https://docs.dominodatalab.com/en/6.1/api_guide/b3b2a1/domino-netapp-volumes-api/. Confirm the base
path (`/remotefs/v1` or `/domino-netapp-volumes/v1`) in your deployment's `/docs`.

| Operation | Inside a run | Outside Domino |
|-----------|--------------|----------------|
| Volume and filesystem CRUD, snapshots, grants | `$DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` **only**, always with `Authorization: Bearer` from `http://localhost:8899/access-token` (also served at `$DOMINO_API_PROXY/access-token`). `$DOMINO_API_PROXY` and the in-run `$DOMINO_API_HOST` return 404 for `/remotefs/v1/*`, and the hostport without a header returns 401 | deployment URL with a service account token or user API key |

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

Source: https://docs.dominodatalab.com/en/6.1/user_guide/e038f2/select-domino-endpoint-authorization-mode/.
Workflow: [domino-model-endpoints](../domino-model-endpoints/SKILL.md).

## 404 on the in-run base

If an `/api/...` route returns 404 on `$DOMINO_API_PROXY` or `$DOMINO_API_HOST` inside a
run, confirm the path against [API-SPECS.md](./API-SPECS.md), then retry on the deployment
URL with a service account token or user API key. Whether the in-run gateway routes a service is a
deployment setting, not something the caller can change.

## Related

- [LIMITS.md](./LIMITS.md) pagination and unsupported credential patterns
- [ERRORS.md](./ERRORS.md) status codes and retries
- [API-SPECS.md](./API-SPECS.md) OpenAPI files and route discovery
