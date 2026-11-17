---
name: domino-apps
description: Publish, deploy, update, restart or stop a web application as a Domino App, and automate those steps over the Apps API or a CI/CD pipeline. Use whenever the user wants to publish, deploy, ship, launch, release or host an app (React/Vite, Streamlit, Dash, Flask, Shiny, Gradio, FastAPI, Rust) on Domino, make an existing app work behind Domino's reverse proxy (app.sh entry point, mandatory 0.0.0.0:8888, DOMINO_RUN_HOST_PATH, relative base, HashRouter, server-side model endpoint calls), create a new App version, stop an App or read its logs over /api/apps/beta, or set up GitHub Actions deployment to Domino. Not for scaffolding a brand-new app from scratch (domino-app-init) or for diagnosing 404s, blank pages or broken routing in an already published app (domino-debug-proxy); use it when those hand off to publishing.
compatibility: Domino 6.1. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY, outside a run a service account token or a user API key.
---

# Domino Apps

Applies to Domino 6.1.

A Domino App runs project code in a container behind Domino's reverse proxy. The proxy authenticates every request, strips the App's URL prefix, and forwards the viewer's username in the `domino-username` header; when the deployment setting `SecureIdentityPropagationToAppsEnabled` is on, it also forwards the viewer's token as `Authorization: Bearer`.

## Rules every App must satisfy

1. **Make the App idempotent.** It restarts at any time: startup changes nothing (migrate and seed in a Job before publishing), each write is an upsert or carries an idempotency key under a unique constraint, so a retry stores it once, and state lives in a Dataset or database, not in memory or on the App's disk ([details](./FRAMEWORKS.md#make-the-app-idempotent)).
2. **Serve on `0.0.0.0:8888`.** An App that does not expose a server on that address and port fails to start. Port 8888 is mandatory, not a default.
3. **The entry point is a launch file** in the project (`app.sh`, or a Python or R script). It is fixed for the life of the App; create a new App to change it.
4. **Read the URL prefix from `DOMINO_RUN_HOST_PATH`** wherever a framework needs its base path (Dash `requests_pathname_prefix`, Gradio `root_path`). Never assemble it from the project owner, name and run ID; the prefix is not derived from them.
5. **Use relative URLs** for assets and API calls (Vite `base: './'`, `new URL('api/', document.baseURI)`), never root-absolute `/assets/...` or `fetch('/api/...')`. They break when the App URL lacks its trailing slash; add it ([details](./FRAMEWORKS.md#behind-dominos-app-proxy)).
6. **Keep secrets on the server.** Model endpoint tokens live in project or user environment variables and are read by backend code. Anything in a `VITE_`-prefixed variable is compiled into the browser bundle.

## Quick start

| Framework | `app.sh` runs | Details |
|---|---|---|
| Vite + React | `node server.js` serving a build made once by `scripts/build-dist.sh`; never installs or builds | [REACT-VITE-GUIDE.md](./REACT-VITE-GUIDE.md) |
| Streamlit | `streamlit run app.py --server.port 8888 --server.address 0.0.0.0 --server.enableCORS false --server.enableXsrfProtection false` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Dash | `python app.py` with `Dash(__name__, routes_pathname_prefix='/', requests_pathname_prefix=os.environ.get('DOMINO_RUN_HOST_PATH'))` and `app.run(host='0.0.0.0', port=8888)` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Flask | `python -m flask run --host=0.0.0.0 --port=8888` or `gunicorn -w 4 -b 0.0.0.0:8888 app:app` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Shiny | `R -e 'shiny::runApp("./", port=8888, host="0.0.0.0")'` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Rust (axum) | the prebuilt binary; never compiles | [domino-rust-apps](../domino-rust-apps/SKILL.md) |

Vite: `base: './'` and `HashRouter`; `BrowserRouter` breaks nested routes.

## Lifecycle

Publishing is one step: in the project, **Deployments > Apps > Publish Domino App**, choose the launch file, Compute Environment, hardware tier and sharing, and publish; the App starts. To ship a change, sync it and publish the App again. Rolling back to an earlier version and autoscaling are not available on Domino 6.1: to go back, revert the code and publish again. Test behind the real proxy by publishing; a run in the Workspace checks only the build and the start command.

Check three things before publishing. **Builds**: Vite and Rust Apps start a build made once in a Workspace or Job, named by date, with the previous build kept and the label in Version Notes ([details](./FRAMEWORKS.md#build-once-and-version-builds)). **Files**: the App runs the project's committed files, so sync first (DFS Workspace: **File Changes > Sync to Domino**; Git-based: commit and push) or the start fails with `entry script 'app.sh' not found`. **Packages**: the App uses the project's Compute Environment, not what you `pip install` in a Workspace (`streamlit: not found`, exit 127); check with `python -c "import <framework>"` and fix it as [FRAMEWORKS.md](./FRAMEWORKS.md#dependencies) shows.

## Environment variables and headers

Injected at start: `DOMINO_RUN_HOST_PATH` (URL prefix, trailing `/`), the `DOMINO_PROJECT_*` and `DOMINO_RUN_ID` identifiers, `DOMINO_STARTING_USERNAME` (who started the run, not the viewer), `DOMINO_API_HOST` and `DOMINO_API_PROXY` (in-cluster API addresses; never in browser links), plus project and user environment variables ([full list](./FRAMEWORKS.md#environment-variables)). The viewer is the `domino-username` header; when the request carries a token, read its `preferred_username` claim instead.

## Calling Domino APIs and model endpoints from an App

- **As the publisher** (the user who started the App): `$DOMINO_API_PROXY/api/...` with no `Authorization` header; code that needs a bearer gets one per request from `$DOMINO_API_PROXY/access-token`.
- **As the viewer**: not available on Domino 6.1; Domino rejects the viewer's token on most routes, often with 500. Call as the publisher and scope per-viewer data in the App by the viewer's username ([details](./FRAMEWORKS.md#viewer-identity-and-domino-api-calls)).
- **Model endpoints**: from backend code only, with `MODEL_API_URL` and `MODEL_API_TOKEN` from Project environment variables; HTTP Basic with the token as username and password for synchronous endpoints, a bearer for asynchronous ones ([details](./FRAMEWORKS.md#calling-a-model-endpoint-from-any-framework)).

Auth: https://docs.dominodatalab.com/en/6.1/user_guide/40b91f/domino-api-authentication/ ; outside a run, a service account token as `Authorization: Bearer`, or a user API key in `X-Domino-Api-Key`.

## REST automation

`/api/apps/beta` for create, versions, reads, instance logs and stop (`DELETE .../instances/{instanceId}`). Starting an App: the UI, or python-domino `app_publish`. Routes and logs: [API-APPS.md](./API-APPS.md). CI/CD with GitHub Actions and a service account: [REACT-CICD.md](./REACT-CICD.md).

## Reference files

- [REACT-VITE-GUIDE.md](./REACT-VITE-GUIDE.md): Vite config, Node backend, HashRouter, testing in Domino
- [REACT-CICD.md](./REACT-CICD.md): GitHub Actions workflow and Public API deploy script
- [FRAMEWORKS.md](./FRAMEWORKS.md): Streamlit, Dash, Flask, Gradio, FastAPI, Shiny, dependencies, viewer identity, proxy behaviour and limits
- [API-APPS.md](./API-APPS.md): beta routes, starting and stopping, logs
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): symptoms, causes and fixes

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/apps

Related skills: `domino-app-init` (scaffold), `domino-debug-proxy` (diagnose), `domino-api-intro` (auth, hosts), `domino-ui-bootstrap` (design system SPA).
