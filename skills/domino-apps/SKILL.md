---
name: domino-apps
description: Publish, deploy, update, restart, stop or roll back a web application as a Domino App, and automate those steps over the Apps API or a CI/CD pipeline. Use whenever the user wants to publish, deploy, ship, launch, release or host an app (React/Vite, Streamlit, Dash, Flask, Shiny, Gradio, FastAPI) on Domino, make an existing app work behind Domino's reverse proxy (app.sh entry point, mandatory 0.0.0.0:8888, DOMINO_RUN_HOST_PATH, relative base, HashRouter, server-side model endpoint calls), create a new App version, deploy an older version, start or stop an App over /api/apps/v1, or set up GitHub Actions deployment to Domino. Not for scaffolding a brand-new app from scratch (domino-app-init) or for diagnosing 404s, blank pages or broken routing in an already published app (domino-debug-proxy); use it when those hand off to publishing.
compatibility: Domino 6.3 and Domino Cloud. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a Personal Access Token or service account token.
---

# Domino Apps

Applies to Domino 6.3 and Domino Cloud.

A Domino App runs project code in a container behind Domino's reverse proxy. The proxy authenticates the viewer, strips the App's URL prefix before forwarding the request, and adds the `domino-username` header (plus an `Authorization` JWT when secure identity propagation is on, the default on 6.3 and Cloud).

## Rules every App must satisfy

1. **Serve on `0.0.0.0:8888`.** An App that does not expose a server on that address and port fails to start. Port 8888 is mandatory, not a default.
2. **The entry point is a launch file** in the project (`app.sh`, or a Python or R script). It is fixed for the life of the App; create a new App to change it.
3. **Read the URL prefix from `DOMINO_RUN_HOST_PATH`** wherever a framework needs its base path (Dash `requests_pathname_prefix`, Gradio `root_path`). Never assemble it from the project owner, name and run ID; that layout no longer matches.
4. **Use relative URLs** for assets and API calls (Vite `base: './'`, `new URL('api/', document.baseURI)`), never root-absolute `/assets/...` or `fetch('/api/...')`.
5. **Keep secrets on the server.** Model endpoint tokens live in project or user environment variables and are read by backend code. Anything in a `VITE_`-prefixed variable is compiled into the browser bundle.

## Quick start

| Framework | `app.sh` runs | Details |
|---|---|---|
| Vite + React | `npm ci && npm run build && node server.js` (Express serves `dist/` and proxies model calls), or `npx serve -s dist -l 8888` when the app calls nothing | [REACT-VITE-GUIDE.md](./REACT-VITE-GUIDE.md) |
| Streamlit | `streamlit run app.py --server.port 8888 --server.address 0.0.0.0 --server.enableCORS false --server.enableXsrfProtection false` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Dash | `python app.py` with `Dash(__name__, routes_pathname_prefix='/', requests_pathname_prefix=os.environ.get('DOMINO_RUN_HOST_PATH'))` and `app.run(host='0.0.0.0', port=8888)` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Flask | `python -m flask run --host=0.0.0.0 --port=8888` or `gunicorn -w 4 -b 0.0.0.0:8888 app:app` | [FRAMEWORKS.md](./FRAMEWORKS.md) |
| Shiny | `R -e 'shiny::runApp("./", port=8888, host="0.0.0.0")'` | [FRAMEWORKS.md](./FRAMEWORKS.md) |

Vite: set `base: './'` in `vite.config.js` (relative asset URLs in the build) and use `HashRouter` for client-side routes: they live after `#`, so they never reach the server and relative asset URLs resolve from the App root on every route. `BrowserRouter` with a basename derived from `window.location.pathname` breaks on nested routes.

## Lifecycle

Create, publish and deploy are separate steps. Publishing records an immutable version (code commit, environment revision, mounts, identity propagation); deploying starts it. Hardware tier, autoscaling, vanity URL and iframe settings are deployment settings: changing them restarts the instance without creating a version. Develop in a workspace with **App Preview** (a real App runtime on port 8888, author-only at `/preview/<draftAppId>`), then **Publish App**, then **Deploy** the version from the App details page.

Check two things before publishing. **Files**: the App runs the project's committed files, so sync first (DFS Workspace: **File Changes > Sync to Domino**; Git-based: commit and push) or the start fails with `entry script 'app.sh' not found`. **Packages**: the App uses the project's Compute Environment; `pip install` in a Workspace does not reach it (`streamlit: not found`, exit 127). Run `python -c "import <framework>"` in the Workspace; if it fails, publish with an environment that has the package, add `requirements.txt` at the project root, or for a prototype install at the top of `app.sh` (slower start, needs egress). See [FRAMEWORKS.md](./FRAMEWORKS.md), Dependencies.

## Environment variables and headers

Injected at start: `DOMINO_RUN_HOST_PATH` (URL prefix), `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_NAME`, `DOMINO_PROJECT_OWNER`, `DOMINO_RUN_ID`, `DOMINO_STARTING_USERNAME` (who started the run, not the viewer), `DOMINO_API_HOST` (platform API base), plus project and user environment variables. Request headers: `domino-username` (viewer; `Anonymous` when anonymous access is on) and `Authorization` (viewer JWT; full user scope only with extended identity propagation and consent).

## Calling Domino APIs and model endpoints from an App

- **Platform API as the publisher**: `$DOMINO_API_PROXY/api/...` with no `Authorization` header, or a bearer from `http://localhost:8899/access-token` on `$DOMINO_API_HOST`. Fetch the token per request; it is short-lived.
- **Platform API as the viewer**: with extended identity propagation enabled by a SysAdmin or CloudAdmin and consent granted, forward the viewer's `Authorization` header.
- **Model endpoints**: read `MODEL_API_URL` and `MODEL_API_TOKEN` from Project environment variables (API: `domino-api-intro`). Both come from the user: the URL is on the endpoint's overview page (`$DOMINO_API_HOST` and `$DOMINO_API_PROXY` do not route `/models/`), and the token is created and shown once under **Settings > Invocation > Add Model Access Token**; no API returns it. Synchronous endpoints take HTTP Basic auth with the token as both username and password (`auth=(token, token)`); asynchronous endpoints take `Authorization: Bearer <token>`. Call them from backend code, never from the browser.

Authentication reference: https://docs.domino.ai/cloud/reference/api/domino-api-authentication . Legacy API keys (`DOMINO_USER_API_KEY`, `X-Domino-Api-Key`) are deprecated; do not use them.

## REST automation

`/api/apps/v1` for create, versions, publish (drafts), start and stop; `/api/apps/beta` only for instance reads (list instances, logs, real-time logs, views). The create body requires `name`, `projectId` and `visibility`. Full chain, bodies and the logs route: [API-APPS.md](./API-APPS.md). CI/CD with GitHub Actions and a service account: [REACT-CICD.md](./REACT-CICD.md).

## Reference files

- [REACT-VITE-GUIDE.md](./REACT-VITE-GUIDE.md): Vite config, Express backend, HashRouter, App Preview
- [REACT-CICD.md](./REACT-CICD.md): GitHub Actions workflow and Public API deploy script
- [FRAMEWORKS.md](./FRAMEWORKS.md): Streamlit, Dash, Flask, Gradio, FastAPI, Shiny, dependencies
- [API-APPS.md](./API-APPS.md): v1 vs beta routes, publish chain, logs
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): symptoms, causes and fixes

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/apps (same under `/6.3/`). Specs: https://docs.domino.ai/api-specs/cloud/public-api.json and https://docs.domino.ai/api-specs/6.3/public-api.json . Related skills: `domino-app-init` (scaffold), `domino-debug-proxy` (diagnose), `domino-api-intro` (auth, hosts), `domino-ui-bootstrap` (design system SPA), `domino-ui-design` (FastAPI + Ant Design), `domino-extensions` (mount an App in the Domino UI).
