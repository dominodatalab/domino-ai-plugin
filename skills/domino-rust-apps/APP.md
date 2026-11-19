# The axum App

The template in `assets/app/` is a small server-rendered App: axum 0.8 for routing, askama for HTML templates checked at compile time, tower-http for static files and request logs, sqlx for Postgres, reqwest for the Domino API and model endpoints, and tracing for logs. HTTP and Postgres share one TLS stack (rustls with the ring provider, no C toolchain beyond `cc`). Domino rules that apply to every framework (port, prefix, identity, sharing) are in [domino-apps](../domino-apps/SKILL.md); this file covers what they mean in Rust.

## Layout

| Path | Contents |
|---|---|
| `src/lib.rs` | `app()` router, handlers, `AppState`, `shutdown_signal()`, in-process tests |
| `src/domino.rs` | Domino API calls as the viewer or the publisher |
| `src/http.rs` | The two HTTP clients: in-cluster (never proxied) and external (proxy-aware) |
| `src/main.rs` | Logging setup, `PORT` (default 8888) on `0.0.0.0`, graceful shutdown |
| `templates/*.html` | askama templates; a field typo fails `cargo build` |
| `static/` | CSS and JavaScript served at `static/...` |

Routes: `/` (page), `healthz`, `api/whoami`, `api/me` and `api/projects` (Domino API as the publisher), `api/db` (Postgres check), `api/predict` (model endpoint), `refresh` (relative redirect). Delete the ones the App does not need, with their tests.

Add routes in `app()` with `/{id}` path parameters and a leading `/` (`.route("/items/{id}", get(item))`). The axum 0.7 forms `/:id` and `/*rest`, and a path without a leading `/`, panic when the router is built, so the App never reaches Running. The template's tests build the router, which catches this.

Pin `axum = "0.8.9"`: axum 0.9 changes `axum::serve` and middleware signatures. Older examples use `axum::Server` and `#[async_trait]`, which no longer exist.

## URLs behind Domino's proxy

The App is served under a prefix such as `/apps/<id>/`, and the server receives paths rooted at `/`. Every URL the browser follows must therefore be relative:

| Write | Not | Because |
|---|---|---|
| `href="static/app.css"`, `src="static/app.js"` | `href="/static/app.css"` | A leading `/` resolves against the Domino host, outside the App |
| `fetch("api/whoami")`, `<form action="refresh">` | `fetch("/api/whoami")` | Same |
| `Redirect::to("./")`, `Redirect::to("./items")` | `Redirect::to("/")` | `Location: /` sends the browser to Domino's home page |
| `ServeDir::new("static").redirect_to_trailing_slash(false)` | `ServeDir::new("static")` | ServeDir redirects a directory request to a root-absolute path |

Keep HTML pages one level deep and pass identifiers as query strings (`item?id=42`), so the same relative links work from every page. If a page must be nested, compute `../` per level from `axum::extract::OriginalUri`.

The App URL also answers without its trailing slash (`.../apps-internal/<id>`), and there every relative URL resolves one level too high and fails with 404. The template's `templates/index.html` starts with a one-line script that adds the slash; keep it at the top of every page that can be opened directly. The prefix differs by how the App is opened (`/apps-internal/<id>`, `/apps/<vanity>`, `/modelproducts/<id>`); `DOMINO_RUN_HOST_PATH` holds the current one with a trailing slash. Domino never sends `X-Script-Name`.

Domino's proxy inserts the deployment's branding into HTML responses: a `<title>` and a favicon link at the first literal `<head>` of each `text/html` response (not when the App compresses its responses). The inserted title comes first, so the browser tab shows it. The default favicon link, `/favicon.ico`, is root-absolute and answers 404 on the Apps host; the template's own `<link rel="icon" href="static/favicon.svg">` comes later in `<head>` and takes its place.

`DOMINO_RUN_HOST_PATH` holds the prefix. Use it only where a value must be absolute, such as a cookie `Path` (set it to the prefix without the trailing slash, give the cookie an App-specific name, and add `HttpOnly; Secure; SameSite=Lax`): every App on the deployment shares one origin, so cookies and `localStorage` are shared across Apps. Domino removes its own session cookies before requests reach the App. Some deployments only show Apps inside Domino's page; there, opening the App URL directly answers 400.

## Identity and Domino API calls

Domino authenticates every request before it reaches the App and passes the viewer's username in `domino-username` (`Anonymous` for anonymous viewers). When the deployment setting `SecureIdentityPropagationToAppsEnabled` is on, the request also carries `Authorization: Bearer <jwt>`, a short-lived token for the viewer.

`viewer_name()` in `src/domino.rs` reads the viewer from the token's `preferred_username` claim (`sub` is the Domino user id) and falls back to `domino-username` when no token arrived; `api/whoami` reports which source it used. Domino checked the token before forwarding the request. To rely on its claims inside the App, verify the RS256 signature against the Domino realm's keys and pin the issuer `https://<domino-domain>/auth/realms/DominoRealm`.

Acting for viewers is not available on Domino 6.1: the viewer's token identifies the viewer, and Domino API routes reject it, often with a 500. Call the Domino API as the publisher, the user the App was started as:

| Identity | How the template calls | Use on Domino 6.1 |
|---|---|---|
| Publisher (the template's default) | `$DOMINO_API_PROXY` with no `Authorization` header; the proxy adds the publisher's token | Every Domino API call. Where data is per viewer, filter it in the App by the viewer's username |
| Viewer (`?as=viewer`) | `$DOMINO_API_HOST` + the viewer's bearer token | Rejected by Domino; the template passes Domino's status through and turns a missing token into a 401 |

`/api/me` (`GET /api/users/v1/self`) and `/api/projects` (`GET /api/projects/beta/projects`) call as the publisher. `?as=viewer` remains for testing and gets Domino's rejection back.

`DOMINO_API_HOST` runs a request that has no `Authorization` header as the publisher. Never build links for the browser from `DOMINO_API_HOST` or `DOMINO_USER_HOST`; either can be an address inside the pod. `localhost:8899` is the default behind `DOMINO_API_PROXY`, not a fixed address: use the variable. A request to the App without browser credentials gets a 302 to the sign-in page. Never log or return a token; `TraceLayer` does not log headers. Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/apps/identity

## Streaming, WebSockets and limits

- Request bodies above 25 MiB are rejected with 413 by default, and the proxy gives up on a response that sends nothing for 300 seconds.
- WebSockets work through the proxy. Idle WebSocket and server-sent-event connections close after 300 seconds, so send a heartbeat (axum: `Sse::new(stream).keep_alive(KeepAlive::default())`).
- For server-sent events, set the response header `X-Accel-Buffering: no`, or the proxy buffers the stream and the browser receives events in bursts.

## Secrets and model endpoints

- Configuration comes from environment variables read once in `AppState::from_env()`. Set secrets as Project environment variables, never in files; user variables come from whoever starts the App.
- `/api/predict` shows a synchronous model endpoint call: HTTP Basic auth with the token as both username and password, body `{"data": ...}`, from the server only. Endpoint URL and token: [domino-model-endpoints](../domino-model-endpoints/SKILL.md).

## Postgres

- `DATABASE_URL`, a Project environment variable, holds the connection string (user variables come from whoever starts the App, so they vanish when someone else deploys it), for example `postgres://app_user:<password>@db.example.internal:5432/appdb?sslmode=verify-full`. Without it, `/api/db` answers 503 and the rest of the App works.
- The pool is created with `connect_lazy`: startup parses the URL and connects to nothing, so the App starts while the database is down, and each request waits at most 5 seconds for a connection.
- TLS: `sslmode=verify-full` checks the server's certificate chain and host name against the OS certificate store; `sslrootcert=/path/ca.pem` in the URL adds a CA for a database with a private one. `require` encrypts without checking the certificate. The `PGSSLMODE` and `PGSSLROOTCERT` environment variables work too. Postgres connections never use an HTTP proxy.
- Pass values as bind parameters (`sqlx::query("SELECT name FROM items WHERE id = $1").bind(id)`), never by formatting SQL strings. The template uses the runtime query API; sqlx's `query!` macros check SQL at compile time but need a database or committed `.sqlx` query data during every build, so add them only with that in place.
- Create tables and load data with a Job before publishing, never at App start ([domino-apps](../domino-apps/FRAMEWORKS.md#make-the-app-idempotent)).

## Outbound TLS and HTTP proxies

Write every outbound call anticipating that the trust store holds the organization's own root certificates and that external requests pass through a TLS-inspecting corporate proxy:

- Trust the OS certificate store. reqwest and sqlx in the template do (`/etc/ssl/certs`, maintained by `update-ca-certificates`), so custom roots work without code. Libraries or features that ship only a bundled root set (webpki-roots), and certificate pinning, fail behind an inspecting proxy.
- Honour `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` and `NO_PROXY`. The external client in `src/http.rs` does, in upper or lower case; `NO_PROXY` matches host names and domain suffixes, not ports, and `localhost` is not exempt unless listed.
- Keep in-cluster calls off the proxy. The in-cluster client for `DOMINO_API_HOST` and `DOMINO_API_PROXY` never uses one; send any other in-cluster service through it too.
- When a certificate error persists, point the client at the right roots (a complete PEM bundle through reqwest's `tls_certs_merge`, `sslrootcert=` for Postgres, `CARGO_HTTP_CAINFO` for Cargo) rather than turning verification off: disabling it silences the proxy's errors and removes the protection with them.
- `http::install_crypto_provider()` installs rustls's ring provider before any client or pool is built; reqwest panics without one.

## Startup and shutdown

- `main` reads configuration, binds `0.0.0.0:$PORT` and serves. It writes nothing: no migrations, no seeding, no files. Every restart and publish runs it again.
- `app.sh` starts the binary with `exec`. `shutdown_signal()` resolves on SIGTERM or Ctrl-C, and axum then finishes in-flight requests, which matters for local runs and Jobs. When Domino stops an App it ends the container, and the server may not get to run its shutdown path, so never rely on shutdown to save state: write anything durable when it happens.
- Logs go to stdout, which the App's **Logs** tab shows. `RUST_LOG` (an environment variable) sets the level, for example `RUST_LOG=info,domino_rust_app=debug`. ANSI colours are on only when stdout is a terminal.

## How the binary is shipped

`scripts/build-dist.sh` runs `cargo build --locked --profile dist` and stores `target/dist/<name>` as a dated build: `<root>/<label>/<name>` with `<root>/<label>.stamp` beside it, where `<root>` is `$DIST_DIR` (default `/mnt/artifacts/dist/<name>`, one folder per App) and `<label>` is the UTC date (`2026.10.15`, then `2026.10.15.2` for a later build that day). It keeps the previous build, so a reverted commit starts again without a rebuild; build labels and going back: [domino-apps FRAMEWORKS.md](../domino-apps/FRAMEWORKS.md#build-once-and-version-builds). Stamp line 1 is the hash `scripts/stamp.sh` computes over `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `src/` and, if present, `build.rs`, `.cargo/`, `templates/`, `static/`, `migrations/` and `pgo/`; then `build=`, `commit=`, `rustc --version`, `RUSTFLAGS=` and `arch=` (the build node's `uname -m`). `KEEP_BUILDS` changes how many builds stay (default 2) and `BUILD_LABEL` sets the label (CI).

At start, `app.sh` recomputes the hash over the App's files and runs the newest build, in `/mnt/artifacts/dist/<name>` (or `$DIST_DIR`) and then `./dist`, whose stamp matches it and whose `arch=` matches the node. It copies that binary to a temporary directory, marks it executable, exports the label as `APP_BUILD` (logged, and reported by `/healthz`) and `exec`s it. With no match it prints which step to repeat and exits, and the App shows as failed in its logs. It never compiles.

Hardware tiers can run on different node types: amd64 or arm64, and different CPU generations within one architecture. Build the binary on the App's own environment and hardware tier; a Job with that tier is the reliable way when the Workspace uses another. A binary for the wrong architecture cannot run at all; one built with `-C target-cpu` for a newer CPU crashes on older ones ([TOOLING.md](./TOOLING.md#target-cpu)).

`app.sh` always runs the build that matches the source the App started from. Add any other build input (an `include_str!` file outside `src/`) to the list in `scripts/stamp.sh`.

Where the binary lives:

| Project | Location | Saved by |
|---|---|---|
| Git-based (default) | `/mnt/artifacts/dist/<name>/` | **File Changes > Sync All Changes** (artifacts go to Domino storage, code to Git) |
| Git-based, binary in Git | `dist/` in the repository (`DIST_DIR=dist`) | Commit and push the new `dist/<label>/` and its stamp, only for builds you publish |
| DFS | `dist/` in the Project (`DIST_DIR=dist`) | **File Changes > Sync to Domino** |

A binary kept in Git stays in history and in every clone (Domino does not support Git LFS), so commit only builds you publish and keep `strip = true`.

A Job builds the same way and saves artifacts when it finishes: run `bash scripts/build-dist.sh` as the Job command on the App's environment and hardware tier. Use a Job when you want the binary built from the committed code rather than from a Workspace's working tree.

## Other UI approaches

- **Vite + React frontend** for heavy client-side interaction or the Domino design system ([domino-ui-bootstrap](../domino-ui-bootstrap/SKILL.md)): build it with `base: './'` and `HashRouter`, serve `dist/` from axum with `.fallback_service(ServeDir::new("frontend/dist").redirect_to_trailing_slash(false))`, and keep JSON routes under `api/`. Add the frontend's `dist/` to `scripts/stamp.sh` inputs.
- **Proa** for server-rendered pages and interactive islands written in Rust: the same build-once binary, built with `proa build` and kept under the App's URL prefix by `PROA_BASE_PATH` ([PROA.md](./PROA.md)).
- **htmx** for partial page updates: copy `htmx.min.js` into `static/` instead of loading it from a CDN (the App's content security policy can block external scripts), and keep `hx-get="api/..."` URLs relative.
- **Leptos or Dioxus** (Rust compiled to WebAssembly) only when the browser must run Rust. They need the `wasm32-unknown-unknown` target and their own build CLIs, compile twice, and default to root-absolute asset paths; Dioxus fixes its base path at build time.
