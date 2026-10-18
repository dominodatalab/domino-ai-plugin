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

Routes: `/` (page), `healthz`, `api/whoami`, `api/me` and `api/projects` (Domino API as viewer or publisher), `api/db` (Postgres check), `api/predict` (model endpoint), `refresh` (relative redirect). Delete the ones the App does not need, with their tests.

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

The App URL also answers without its trailing slash (`.../apps-internal/<id>`), and there every relative URL resolves one level too high and fails with 404. The template's `templates/index.html` starts with a one-line script that adds the slash; keep it at the top of every page that can be opened directly. The prefix differs by how the App is opened (`/preview/<id>` in App Preview, `/apps-internal/<id>`, `/apps/<vanity>`, `/modelproducts/<id>`); `DOMINO_RUN_HOST_PATH` holds the current one with a trailing slash. Domino never sends `X-Script-Name`.

Domino's proxy inserts the deployment's branding into HTML responses: a `<title>` and a favicon link at the first literal `<head>` of each `text/html` response (not when the App compresses its responses). The inserted title comes first, so the browser tab shows it. The default favicon link, `/favicon.ico`, is root-absolute and answers 404 on the Apps host; the template's own `<link rel="icon" href="static/favicon.svg">` comes later in `<head>` and takes its place.

`DOMINO_RUN_HOST_PATH` holds the prefix. Use it only where a value must be absolute, such as a cookie `Path` (set it to the prefix without the trailing slash, give the cookie an App-specific name, and add `HttpOnly; Secure; SameSite=Lax`): every App on the deployment shares one origin, so cookies and `localStorage` are shared across Apps. Domino removes its own session cookies before requests reach the App. Some deployments only show Apps inside Domino's page; there, opening the App URL directly answers 400.

## Identity: acting as the viewer or the publisher

Domino authenticates every request before it reaches the App. What the App receives depends on its identity mode:

| Mode | When | The App receives | Viewer calls to the Domino API |
|---|---|---|---|
| Default | Every App, unless set otherwise | `Authorization: Bearer <jwt>`: a short-lived token issued for Apps (audience `apps`), plus `domino-username` copied from it | Most routes reject the token, often with a 500; a few data-access routes accept it (Dataset snapshot file reads, Data Source lookup by name) |
| Extended identity propagation | The App version has it on, and the viewer consented | `Authorization: Bearer <jwt>` with the viewer's own credential; no `domino-username`, and a client-supplied one passes through | Any route the viewer may use |
| Secure identity propagation off | Deployment setting | `domino-username` only | None |

`viewer_name()` in `src/domino.rs` reads the viewer from the token's `preferred_username` claim (`sub` is the Domino user id) and falls back to `domino-username` only when no token arrived; `api/whoami` reports which source it used. Never read `domino-username` while a token is present. Domino checked the token before forwarding the request. To rely on its claims inside the App, verify the RS256 signature against the Domino realm's keys and pin the issuer `https://<domino-domain>/auth/realms/DominoRealm`; do not require audience `apps`, which extended-mode tokens lack. For decisions that grant access, verify the token, or, on an App with extended identity propagation, call the Domino API as the viewer; without it Domino rejects the viewer's token on most routes.

`src/domino.rs` calls the Domino API with either identity, chosen per call:

| Identity | How the template calls | Token scope |
|---|---|---|
| Viewer (default) | `$DOMINO_API_HOST` + the viewer's bearer token | Identifies the viewer only, unless the App has extended identity propagation and the viewer consented; then the viewer's full Domino permissions |
| Publisher (`?as=publisher`) | `$DOMINO_API_PROXY` with no `Authorization` header; the proxy adds the publisher's token | The publisher's permissions |

With extended identity propagation, `/api/me` (`GET /api/users/v1/self`) and `/api/projects` (`GET /api/projects/beta/projects`) show the difference: the viewer and the publisher see different users and project lists. Without it the viewer calls fail, often with a 500, and only `?as=publisher` answers. Use the viewer's identity whenever the App reads or changes data on someone's behalf, so Domino enforces that person's permissions; use the publisher's only for the App's own shared resources. "Publisher" is the user the App was started as.

`DOMINO_API_HOST` can be a local API gateway inside the App's pod (`http://127.0.0.1:<port>`). It accepts browser-session, service-account and Personal Access Token credentials, and runs a request that has no `Authorization` header as the publisher. Never drop the viewer's token and retry without it: that silently changes whose permissions apply. Never build links for the browser from `DOMINO_API_HOST` or `DOMINO_USER_HOST`; either can be an address inside the pod. `localhost:8899` is the default behind `DOMINO_API_PROXY`, not a fixed address: use the variable.

Extended identity propagation:

- It is part of the App version: **Allow App to act for viewers in Domino** in the App's sharing settings, or `"extendedIdentityPropagationToAppsEnabled": true` in the version's `content` ([domino-apps API-APPS.md](../domino-apps/API-APPS.md)). Changing it creates a version. Only a SysAdmin or CloudAdmin can publish an App with it on, and it cannot be turned off for that App afterwards.
- The deployment-wide setting `com.cerebro.domino.apps.extendedIdentityPropagationToAppsEnabled` must be on (it is by default).
- Each viewer sees a consent prompt; consent lasts 8 hours by default and up to 30 days. Until a viewer consents, every request to the App, JSON routes included, redirects to Domino's `/app-consent?appId=<id>&callback=<url>` page, so scripts and `curl` get HTML instead of the App's response. Open the App in a browser and consent first.
- Without it, Domino rejects the viewer's token on most routes, often with a 500; the template passes Domino's status through and turns a missing token into a 401 that says which setting to check.
- Scripts and other non-browser clients call the App with a Personal Access Token as the bearer; the App receives that token and acts with it. Consent must already exist for that user (granted once in a browser): until then every request, JSON included, gets a 302 to `/app-consent`, and a request with no credentials gets a 302 to the sign-in page. Tokens from the Domino CLI login are refused where `DOMINO_API_HOST` is the local gateway (403).
- Never log or return the token. `TraceLayer` does not log headers.
- Docs: https://docs.domino.ai/cloud/platform-capabilities/features/apps/authentication-and-identity/app-security

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
- Create tables and load data with a Job before publishing, never at App start ([domino-apps](../domino-apps/FRAMEWORKS.md#startup-must-not-change-state)).

## Outbound TLS and HTTP proxies

Write every outbound call anticipating that the trust store holds the organization's own root certificates and that external requests pass through a TLS-inspecting corporate proxy:

- Trust the OS certificate store. reqwest and sqlx in the template do (`/etc/ssl/certs`, maintained by `update-ca-certificates`), so custom roots work without code. Libraries or features that ship only a bundled root set (webpki-roots), and certificate pinning, fail behind an inspecting proxy.
- Honour `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` and `NO_PROXY`. The external client in `src/http.rs` does, in upper or lower case; `NO_PROXY` matches host names and domain suffixes, not ports, and `localhost` is not exempt unless listed.
- Keep in-cluster calls off the proxy. The in-cluster client for `DOMINO_API_HOST` and `DOMINO_API_PROXY` never uses one; send any other in-cluster service through it too.
- When a certificate error persists, point the client at the right roots (a complete PEM bundle through reqwest's `tls_certs_merge`, `sslrootcert=` for Postgres, `CARGO_HTTP_CAINFO` for Cargo) rather than turning verification off: disabling it silences the proxy's errors and removes the protection with them.
- `http::install_crypto_provider()` installs rustls's ring provider before any client or pool is built; reqwest panics without one.

## Startup and shutdown

- `main` reads configuration, binds `0.0.0.0:$PORT` and serves. It writes nothing: no migrations, no seeding, no files. Restarts, live sync and autoscaled replicas all run it again, often at the same time.
- `app.sh` starts the binary with `exec`. `shutdown_signal()` resolves on SIGTERM or Ctrl-C, and axum then finishes in-flight requests, which matters for local runs and Jobs. When Domino stops an App it ends the container, and the server may not get to run its shutdown path, so never rely on shutdown to save state: write anything durable when it happens.
- Logs go to stdout, which the App's **Logs** tab shows. `RUST_LOG` (an environment variable) sets the level, for example `RUST_LOG=info,domino_rust_app=debug`. ANSI colours are on only when stdout is a terminal.

## How the binary is shipped

`scripts/build-dist.sh` runs `cargo build --locked --profile dist` and stores `target/dist/<name>` as a dated build: `<root>/<label>/<name>` with `<root>/<label>.stamp` beside it, where `<root>` is `$DIST_DIR` (default `/mnt/artifacts/dist/<name>`, one folder per App) and `<label>` is the UTC date (`2026.10.15`, then `2026.10.15.2` for a later build that day). It keeps the previous build, so a reverted commit starts again without a rebuild; labels, Version Notes and rollback: [domino-apps FRAMEWORKS.md](../domino-apps/FRAMEWORKS.md#build-once-and-version-builds). Stamp line 1 is the hash `scripts/stamp.sh` computes over `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `src/` and, if present, `build.rs`, `.cargo/`, `templates/`, `static/`, `migrations/` and `pgo/`; then `build=`, `commit=`, `rustc --version`, `RUSTFLAGS=` and `arch=` (the build node's `uname -m`). `KEEP_BUILDS` changes how many builds stay (default 2) and `BUILD_LABEL` sets the label (CI).

At start, `app.sh` recomputes the hash over the App's files and runs the newest build, in `/mnt/artifacts/dist/<name>` (or `$DIST_DIR`) and then `./dist`, whose stamp matches it and whose `arch=` matches the node. It copies that binary to a temporary directory, marks it executable, exports the label as `APP_BUILD` (logged, and reported by `/healthz`) and `exec`s it. With no match it prints which step to repeat and exits, and the App shows as failed in its logs. It never compiles.

Hardware tiers can run on different node types: amd64 or arm64, and different CPU generations within one architecture. Build the binary on the App's own environment and hardware tier; a Job with that tier is the reliable way when the Workspace uses another. A binary for the wrong architecture cannot run at all; one built with `-C target-cpu` for a newer CPU crashes on older ones ([TOOLING.md](./TOOLING.md#target-cpu)).

An App version pins the Git commit and the artifacts commit together, so App Preview, deployment and starting an older version all run the build that matches their source. Add any other build input (an `include_str!` file outside `src/`) to the list in `scripts/stamp.sh`.

Where the binary lives:

| Project | Location | Saved by |
|---|---|---|
| Git-based (default) | `/mnt/artifacts/dist/<name>/` | **File Changes > Sync All Changes** (artifacts go to Domino storage, code to Git) |
| Git-based, binary in Git | `dist/` in the repository (`DIST_DIR=dist`) | Commit and push the new `dist/<label>/` and its stamp, only for builds you publish |
| DFS | `dist/` in the Project (`DIST_DIR=dist`) | **File Changes > Sync to Domino** |

A Job builds the same way and saves artifacts when it finishes: run `bash scripts/build-dist.sh` as the Job command on the App's environment and hardware tier. Use a Job when you want the binary built from the committed code rather than from a Workspace's working tree.

## Other UI approaches

- **Vite + React frontend** for heavy client-side interaction or the Domino design system ([domino-ui-bootstrap](../domino-ui-bootstrap/SKILL.md)): build it with `base: './'` and `HashRouter`, serve `dist/` from axum with `.fallback_service(ServeDir::new("frontend/dist").redirect_to_trailing_slash(false))`, and keep JSON routes under `api/`. Add the frontend's `dist/` to `scripts/stamp.sh` inputs.
- **Proa** for server-rendered pages and interactive islands written in Rust: the same build-once binary, built with `proa build` and kept under the App's URL prefix by `PROA_BASE_PATH` ([PROA.md](./PROA.md)).
- **htmx** for partial page updates: copy `htmx.min.js` into `static/` instead of loading it from a CDN (the App's content security policy can block external scripts), and keep `hx-get="api/..."` URLs relative.
- **Leptos or Dioxus** (Rust compiled to WebAssembly) only when the browser must run Rust. They need the `wasm32-unknown-unknown` target and their own build CLIs, compile twice, and default to root-absolute asset paths; Dioxus fixes its base path at build time.
