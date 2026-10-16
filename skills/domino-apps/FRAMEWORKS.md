# Framework configurations for Domino Apps

Every framework must bind `0.0.0.0:8888`; an App that does not fails to start. Where a framework needs its URL prefix, read `DOMINO_RUN_HOST_PATH`. Domino's own minimal examples: https://docs.domino.ai/cloud/platform-capabilities/features/apps/common-app-frameworks (same content under `/6.3/`).

## Calling a model endpoint from any framework

Read the endpoint URL and a Model Access Token from Project (or user) environment variables, set in the UI or through the API ([domino-api-intro](../domino-api-intro/SKILL.md#environment-variables-as-the-secret-store)); never hardcode them. The URL is on the endpoint's overview page (the deployment's external URL, `https://<domino-domain>/models/<id>/latest/model`; `$DOMINO_API_HOST` and `$DOMINO_API_PROXY` do not route `/models/...`), so ask for it. The token is the user's, or one you create and store as a Project variable without printing it ([Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens) in `domino-model-endpoints`); a Domino bearer token is rejected with 401. Synchronous endpoints use HTTP Basic auth with the token as both username and password; asynchronous endpoints use `Authorization: Bearer <token>` (https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/domino-endpoint-authorization).

```python
# predict.py: shared helper for the Python examples below
import os
import requests


def predict(features: dict) -> dict:
    url = os.environ.get("MODEL_API_URL")
    token = os.environ.get("MODEL_API_TOKEN")
    if not url or not token:
        raise RuntimeError("Set MODEL_API_URL and MODEL_API_TOKEN in the project environment variables")
    response = requests.post(url, auth=(token, token), json={"data": features}, timeout=60)
    response.raise_for_status()
    return response.json()
```

## Streamlit

Streamlit defaults to port 8501; pass the port and address explicitly in `app.sh`. Domino's published example also writes a `config.toml` that sets `enableCORS = false` and `enableXsrfProtection = false`; keep those unless the deployment is known to work with the defaults (XSRF protection off weakens file-upload protection).

```bash
#!/bin/bash
# app.sh
set -e
cd "$(dirname "$0")"
mkdir -p ~/.streamlit
cat > ~/.streamlit/config.toml << 'EOF'
[server]
port = 8888
address = "0.0.0.0"
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF
streamlit run app.py --server.port 8888 --server.address 0.0.0.0
```

The equivalent one-liner without a config file: `streamlit run app.py --server.port 8888 --server.address 0.0.0.0 --server.headless true --server.enableCORS false --server.enableXsrfProtection false`.

To check that the app starts in a Workspace before publishing, use another port, because 8888 is the IDE's port there (code-server or Jupyter), and start, check and stop in one command: each tool call is a new shell, so a `kill $!` in a later call finds nothing and the test server keeps running.

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true & pid=$!; sleep 8; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501/; kill $pid
```

`--server.headless true` stops Streamlit's first-run prompt from blocking. Do not `pkill -f "streamlit run"`: the pattern matches the calling shell and kills it. Keep 8888 in `app.sh`; the App gets that port in its own container. The same one-command pattern applies to every framework below (`python app.py` with the port taken from an environment variable, `uvicorn --port 8501`, and so on).

```python
# app.py
import os
import streamlit as st
from predict import predict

st.set_page_config(page_title="ML Dashboard", layout="wide")
st.title("ML Model Dashboard")
st.caption(f"Project: {os.environ.get('DOMINO_PROJECT_NAME', 'n/a')}")

feature1 = st.number_input("Feature 1", value=0.0)
feature2 = st.number_input("Feature 2", value=0.0)
if st.button("Predict"):
    try:
        st.json(predict({"feature1": feature1, "feature2": feature2}))
    except Exception as exc:
        st.error(f"Prediction failed: {exc}")
```

Streamlit's frontend uses relative URLs, so no base path setting is needed. `[theme]` entries in the same `config.toml` restyle the app.

## Dash

Dash needs both prefixes: routes are served at `/` inside the container (the proxy strips the prefix) and the browser requests them under `DOMINO_RUN_HOST_PATH`. `app.run_server` was removed in Dash 3; use `app.run`.

```python
# app.py
import os
from dash import Dash, Input, Output, State, callback, dcc, html
from predict import predict

app = Dash(
    __name__,
    routes_pathname_prefix="/",
    requests_pathname_prefix=os.environ.get("DOMINO_RUN_HOST_PATH"),
)

app.layout = html.Div([
    html.H1("ML Model Dashboard"),
    html.Label("Feature 1"), dcc.Input(id="feature1", type="number", value=0),
    html.Label("Feature 2"), dcc.Input(id="feature2", type="number", value=0),
    html.Button("Predict", id="predict-btn", n_clicks=0),
    html.Div(id="prediction-output"),
    html.P(f"Project: {os.environ.get('DOMINO_PROJECT_NAME', 'n/a')}", style={"color": "gray"}),
])


@callback(
    Output("prediction-output", "children"),
    Input("predict-btn", "n_clicks"),      # only the button triggers the endpoint call
    State("feature1", "value"),            # State: read on click, no call on every keystroke
    State("feature2", "value"),
    prevent_initial_call=True,
)
def run_prediction(n_clicks, feature1, feature2):
    try:
        return html.Pre(str(predict({"feature1": feature1, "feature2": feature2})))
    except Exception as exc:
        return html.P(f"Prediction failed: {exc}", style={"color": "red"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=False)
```

`app.sh` is `cd "$(dirname "$0")" && python app.py`. Files in `assets/` are served automatically under the same prefix. Dash callbacks read the viewer with `viewer_name(flask.request.headers)` ([Viewer identity](#viewer-identity-and-domino-api-calls)).

## Flask

```python
# app.py
import os
from flask import Flask, jsonify, request
from predict import predict
from viewer import viewer_name   # viewer.py: see Viewer identity below

app = Flask(__name__)


@app.route("/")
def index():
    return f"Hello {viewer_name(request.headers) or 'viewer'} from {os.environ.get('DOMINO_PROJECT_NAME', 'n/a')}"


@app.route("/predict", methods=["POST"])
def predict_route():
    try:
        return jsonify(predict(request.get_json(force=True)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/health")
def health():
    return jsonify({"status": "ok"})
```

```bash
#!/bin/bash
# app.sh (development server)
set -e
export FLASK_APP=app.py
python -m flask run --host=0.0.0.0 --port=8888
```

For more than a handful of concurrent users serve with gunicorn (Domino's performance guidance): `gunicorn -w 4 -b 0.0.0.0:8888 app:app`. Use relative URLs in templates (`href="static/style.css"`, `fetch("predict")`), not `/static/...`. Domino sends no `X-Script-Name` header, so middleware that reads it does nothing. Where Flask must generate absolute URLs (`url_for`), set `SCRIPT_NAME` from the prefix:

```python
prefix = os.environ.get("DOMINO_RUN_HOST_PATH", "/").rstrip("/")
wsgi_app = app.wsgi_app
def with_prefix(environ, start_response):
    environ["SCRIPT_NAME"] = prefix          # the proxy already removed it from PATH_INFO
    return wsgi_app(environ, start_response)
app.wsgi_app = with_prefix
```

## Gradio

Gradio serves assets under its `root_path`; set it from `DOMINO_RUN_HOST_PATH`, as Gradio documents for apps behind a reverse proxy.

```python
# app.py
import os
import gradio as gr
from predict import predict


def run(feature1, feature2):
    try:
        return str(predict({"feature1": feature1, "feature2": feature2}))
    except Exception as exc:
        return f"Prediction failed: {exc}"


demo = gr.Interface(
    fn=run,
    inputs=[gr.Number(label="Feature 1"), gr.Number(label="Feature 2")],
    outputs=gr.Textbox(label="Prediction"),
    title="ML Model Interface",
)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=8888,
        root_path=os.environ.get("DOMINO_RUN_HOST_PATH", ""),
        share=False,
    )
```

`app.sh` is `python app.py`.

## FastAPI

```bash
#!/bin/bash
# app.sh
set -e
uvicorn app:app --host 0.0.0.0 --port 8888
```

```python
# app.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from predict import predict
from viewer import viewer_name   # viewer.py: see Viewer identity below

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "project": os.environ.get("DOMINO_PROJECT_NAME", "n/a"),
        "user": viewer_name(request.headers) or "viewer",
    })


@app.post("/predict")
async def predict_route(features: dict):
    return predict(features)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

Reference static files and API routes relatively in `index.html` (`static/app.js`, `fetch("predict")`).

## Shiny (R)

Two-file apps (`ui.R`, `server.R`) are launched by an `app.R` or `app.sh` that Domino runs as the entry point:

```r
# app.R
shiny::runApp("./", port = 8888, host = "0.0.0.0")
```

```bash
#!/bin/bash
# app.sh alternative
set -e
R -e 'shiny::runApp("./", port=8888, host="0.0.0.0")'
```

Model call from `server.R` (synchronous endpoint, Basic auth):

```r
library(httr)
result <- POST(
  Sys.getenv("MODEL_API_URL"),
  authenticate(Sys.getenv("MODEL_API_TOKEN"), Sys.getenv("MODEL_API_TOKEN")),
  body = list(data = list(feature1 = input$feature1, feature2 = input$feature2)),
  encode = "json"
)
output$result <- renderText(content(result, "text"))
```

Identity headers reach Shiny only under Shiny Server Pro. R is single-process, so Shiny Apps serve a handful of concurrent users; see https://docs.domino.ai/cloud/platform-capabilities/features/apps/app-logs-and-versioning/app-scalability-performance .

## Dependencies

The App runs in the project's default Compute Environment (or the one chosen at publish time). Packages you `pip install` in a Workspace are not in it; an App published that way dies at start with `streamlit: not found` (exit 127). Before publishing, run `python -c "import <framework>"` in the Workspace (`node -v` for Vite); if it fails, do one of:

1. **Put the package in the environment** (best): pick an environment that has it when publishing (`GET /api/environments/beta/environments` lists them), or build one from the Domino Standard Environment with Dockerfile lines `USER root`, `RUN pip install dash`, `USER ubuntu`. Fast starts, no egress needed.
2. **`requirements.txt`** at the project root (Git-based projects: the code folder, `/mnt/code`). Domino installs it at the start of every execution, Apps included; slower starts and PyPI egress (https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/add-packages-to-environments/use-requirements-txt).
3. **Install at start in `app.sh`** for a prototype: `python -m pip install --user -q streamlit && exec python -m streamlit run app.py --server.port 8888 --server.address 0.0.0.0`. Same trade-offs as `requirements.txt`; the `python -m` form avoids depending on `~/.local/bin` being on `PATH`.

Versions that match the code above. A package the Domino Standard Environment ships is pinned at or below the DSE's version (`pip show <pkg>` reports it; a newer one can break ranges its preinstalled MLflow declares, such as `gunicorn<24`); a package it does not ship takes its newest release:

| Framework | Packages |
|---|---|
| Streamlit | `streamlit>=1.65` (not in the DSE), `requests` |
| Dash | `dash>=4` (not in the DSE; `run_server` was removed in 3.0), `plotly<=6.9.0` (the DSE's version), `requests` |
| Flask | ships in the DSE: `flask<=3.1.3`, `gunicorn<=23.0.0`, `requests` |
| Gradio | `gradio>=6` (not in the DSE), `requests` |
| FastAPI | ships in the DSE: `fastapi<=0.136.3`, `uvicorn<=0.52.4`, `jinja2`, `requests` |

## Viewer identity and Domino API calls

Domino authenticates every request before it reaches the App. With secure identity propagation (the default) the request carries the viewer's token in `Authorization: Bearer <jwt>`: its `preferred_username` claim is the viewer's username and `sub` their Domino user id. The `domino-username` header is a convenience copy. Apps with extended identity propagation do not receive it, and there a client can send its own, so read the token whenever one is present. Only with secure identity propagation turned off does the App get `domino-username` (`Anonymous` for anonymous viewers) and no token.

| App | Viewer token | Accepted by |
|---|---|---|
| Default | Short-lived (valid for about 5 minutes), audience `apps` | Dataset snapshot file reads and Data Source lookup by name only; other routes reject it, often with HTTP 500 |
| Extended identity propagation: a SysAdmin or CloudAdmin publishes the version with **Allow App to act for viewers in Domino** (`extendedIdentityPropagationToAppsEnabled: true` over the API); it cannot be turned off for that App | The viewer's own credential: their browser session token, or the Personal Access Token a script sent | Every route the viewer may call. Each viewer consents once per App; consent lasts 8 hours by default, up to 30 days |

- **As the viewer**: send the viewer's token to `$DOMINO_API_HOST`. If the request carries none, return 401. Never retry without the header: `$DOMINO_API_HOST` runs a request without `Authorization` as the publisher, so the viewer would silently see the publisher's data.
- **As the publisher** (the user the App run was started as, `DOMINO_STARTING_USERNAME`): `$DOMINO_API_PROXY/...` with no `Authorization` header. Code that needs a bearer token gets one per request from `$DOMINO_API_PROXY/access-token`; `localhost:8899` is only its default address.
- Inside an App, `$DOMINO_API_HOST` can be a gateway inside the App's own container (for example `http://127.0.0.1:8763`). It accepts browser-session, service account and Personal Access Token credentials and rejects a token from the Domino CLI login with 403. Never build browser links from `DOMINO_API_HOST` or `DOMINO_USER_HOST`; use relative URLs or the App's `url`.

```python
# viewer.py: who is viewing the App, and Domino API calls as the viewer or the publisher.
import base64
import json
import os

import requests


def viewer_token(headers):
    """The bearer token Domino forwards with each request, or None (also for an empty one)."""
    auth = headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    return token or None


def viewer_name(headers):
    """For display only: the token's preferred_username claim, or the domino-username header when
    the request carries no token. Not verified here; for access decisions verify the token
    (verified_claims below) or, on an App with extended identity propagation, call Domino as the
    viewer."""
    token = viewer_token(headers)
    if token is None:
        return headers.get("domino-username")
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["preferred_username"]
    except (IndexError, KeyError, TypeError, ValueError):
        return None  # not a JWT (a Personal Access Token): GET /api/users/v1/self as the viewer


def domino_get(path, headers=None):
    """GET a Domino API path as the viewer (pass the request's headers) or as the publisher (None)."""
    if headers is None:
        return requests.get(os.environ["DOMINO_API_PROXY"] + path, timeout=30)
    token = viewer_token(headers)
    if token is None:
        # Never retry without the header: DOMINO_API_HOST runs header-less calls as the publisher.
        raise PermissionError("no viewer token")
    return requests.get(os.environ["DOMINO_API_HOST"] + path,
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
```

`headers` is Flask's or Dash's `request.headers`, FastAPI's `request.headers`, or Streamlit's `st.context.headers`.

To trust the token's claims without calling Domino (for example to gate a page on the viewer's email), verify it. Pin the issuer, `https://<domino-domain>/auth/realms/DominoRealm`, stored as a Project environment variable; do not require audience `apps`, which tokens on Apps with extended identity propagation do not carry. If the App cannot reach the deployment's URL to fetch the keys and has extended identity propagation, call `GET /api/users/v1/self` as the viewer instead; without it Domino rejects the viewer's token there, so verifying is the only option.

```python
import os

import jwt  # pip install "pyjwt[crypto]"

ISSUER = os.environ["DOMINO_TOKEN_ISSUER"].rstrip("/")  # https://<domino-domain>/auth/realms/DominoRealm
JWKS = jwt.PyJWKClient(ISSUER + "/protocol/openid-connect/certs")


def verified_claims(token):
    """Claims of a token Domino issued; raises jwt.PyJWTError for any other token."""
    key = JWKS.get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["RS256"], issuer=ISSUER,
                      options={"verify_aud": False, "require": ["exp", "iss"]})
```

## Behind Domino's App proxy

- **Prefix and trailing slash.** The proxy strips the App's prefix: `<prefix>` and `<prefix>/` both reach the App as `/`, with no redirect. Opened without the slash, every relative URL resolves one level too high and returns 404. Make this the first line of `<head>` in every page that can be opened directly:
  `<script>if (!location.pathname.endsWith('/')) location.replace(location.pathname + '/' + location.search + location.hash)</script>`
  A server-rendered page can instead emit `<base href="...">` with the value of `DOMINO_RUN_HOST_PATH`. The prefix differs between App Preview (`/preview/<id>/`), deployed Apps (`/apps-internal/<id>/`, `/apps/<vanity>/`) and `/modelproducts/<id>/`; `DOMINO_RUN_HOST_PATH` always holds the current one, with a trailing slash. Domino sends no `X-Script-Name` header, so middleware that reads it does nothing.
- **Title and icon.** In `text/html` responses the proxy inserts the deployment's `<title>` and a favicon link right after the first literal `<head>`, unless the App compresses its responses. The inserted title comes first, so the browser tab shows it; set `document.title` from script for an App-specific title. The inserted icon link points at `/favicon.ico`, which returns 404 on the Apps host; add a relative `<link rel="icon" href="static/favicon.svg">` later in `<head>`.
- **Limits.** Request bodies up to 25 MiB by default (413 above that); the proxy waits up to 300 s for a response, so run longer work as a Job and poll for its result. WebSockets work. An idle WebSocket or server-sent-events connection is closed after 300 s: send a heartbeat more often (a ping frame, or an SSE comment line `:` followed by a blank line). Send `X-Accel-Buffering: no` on SSE responses, or the proxy buffers the stream.
- **One origin for every App.** All Apps share the Apps host, so cookies and `localStorage` are visible to every other App. Give cookies an App-specific name and `Path=` set to `DOMINO_RUN_HOST_PATH` without its trailing slash (with `HttpOnly; Secure; SameSite=Lax`), prefix `localStorage` keys, and keep secrets out of both. Domino removes its own session cookies before a request reaches the App.
- **Iframe-only deployments.** Some deployments serve Apps only inside Domino's iframe; opening the App URL directly then returns 400. Open the App from its page in Domino.
- **Scripts and other non-browser clients.** A request without credentials gets a 302 to the sign-in page. On an App with extended identity propagation, a script sends a Personal Access Token as `Authorization: Bearer`, and its user must have consented to the App once in a browser: without consent every request, JSON included, gets a 302 to `/app-consent?appId=...&callback=...`. Do not follow redirects (`curl` without `-L`, `requests` with `allow_redirects=False`) and treat a 302 as "sign in or consent first".

## Startup must not change state

Domino runs the entry point again on every restart, App Preview live sync, deployment and rollback, and once per replica when autoscaling; replicas share the App's disk and can start together. Startup that writes (creates tables, seeds rows, fills a Dataset, downloads into the project) races with itself or repeats work.

1. **Make startup read-only.** Read configuration, open connections, load models, serve. Run schema migrations, seeding and Dataset preparation as a Job (or a Flow step) before you publish, and pin the Job's outputs as the App's inputs.
2. **If startup must write, make it idempotent and safe to run concurrently.** Idempotent alone is not enough: "check whether the table exists, then create it" still races between two replicas. Use operations that are atomic on their own: `CREATE TABLE IF NOT EXISTS`, upserts on a unique key, a database advisory lock around migrations, or write to a temporary file and `rename` it into place.
3. **Writes while serving** (user uploads, results, logs of user actions) follow https://docs.domino.ai/cloud/platform-capabilities/features/apps/persist-data-in-apps : Datasets, databases or object storage, never the project's files, with concurrent writers in mind.

## Build once and version builds

Apps with a build step (Vite, Rust) build in a Workspace or Job, never in `app.sh`. A build at start repeats on every restart, live sync, deployment and replica, needs the build toolchain and package-registry access in the App's environment, and can fail where nobody watches. `app.sh` only picks a finished build and starts it, so the App starts in seconds.

- **Where builds live.** Git-based Project: `/mnt/artifacts/dist/<name>/`, one folder per App so Apps in one Project never prune each other's builds, saved by **File Changes > Sync All Changes**; each App version pins the Domino files commit together with the Git commit. DFS Project: `dist/` in the Project (`DIST_DIR=dist`), saved by **Sync to Domino**. CI or air-gapped sites: `dist/` committed on a commit tagged `build-<label>`.
- **One folder per build, named by its UTC date.** `2026.10.15`; a later build that day adds `.2`, `.3` past the highest suffix in use, so a label is never reused and `sort -V` orders builds by time. Next to each folder, `<label>.stamp`: line 1 is a hash over every committed build input, then `build=`, `commit=` and the toolchain (plus `arch=` for native binaries).
- **Keep the previous build.** After a build, delete an older build of the same sources, then keep the two newest (`KEEP_BUILDS`).
- **`app.sh` runs the build that matches the code.** It hashes the App's committed inputs and starts the newest build whose stamp matches; when none does it exits with a message to run the build. It exports the label as `APP_BUILD` and logs it; `/healthz` reports it.
- **Name the build in the App version.** Domino numbers versions v1, v2 and so on; put the label in the version's **Version Notes** (`description` on `POST /api/apps/v1/apps/{appId}/versions`, `createAndStart`, or `PATCH .../versions/{versionId}`) so each version says which build it runs.

| To roll back | Do | Why it works |
|---|---|---|
| To an earlier release | Start that App version (App page, or `POST /api/apps/v1/apps/{appId}/versions/{versionId}/start` with `{}`) | The version pins its commits, so its own build comes back with it |
| A code change | Revert the commit, save, publish a new version | The previous build is still in the folder and matches the reverted code; no rebuild |
| Further back than the previous build | Rebuild from that commit | Only two builds are kept |

Scripts: `scripts/build-dist.sh`, `scripts/stamp.sh` and `app.sh` in the `domino-app-init` Vite template ([build-dist.sh](../domino-app-init/assets/vite-react/scripts/build-dist.sh)) and in `domino-rust-apps` ([APP.md](../domino-rust-apps/APP.md#how-the-binary-is-shipped)).

## Environment variables

Injected by Domino: `DOMINO_RUN_HOST_PATH` (the current URL prefix, with a trailing slash), `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_NAME`, `DOMINO_PROJECT_OWNER`, `DOMINO_RUN_ID`, `DOMINO_STARTING_USERNAME` (the publisher), `DOMINO_WORKING_DIR`, `DOMINO_API_HOST` and `DOMINO_API_PROXY` (in-cluster addresses for API calls; never use them in browser links) (full glossary: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/manage-compute-environments/manage-environment-variables/5-glossary-default-variables). Set by you as Project or user environment variables (UI or API: [domino-api-intro](../domino-api-intro/SKILL.md#environment-variables-as-the-secret-store)): `MODEL_API_URL`, `MODEL_API_TOKEN`.
