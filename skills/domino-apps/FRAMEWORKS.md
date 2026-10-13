# Framework configurations for Domino Apps

Every framework must bind `0.0.0.0:8888`; an App that does not fails to start. Where a framework needs its URL prefix, read `DOMINO_RUN_HOST_PATH`. Domino's own minimal examples: https://docs.domino.ai/cloud/platform-capabilities/features/apps/common-app-frameworks (same content under `/6.3/`).

## Calling a model endpoint from any framework

Read the endpoint URL and a Model Access Token from environment variables set in the project (or user) settings; never hardcode them. Both values must come from the user: the URL is on the endpoint's overview page (the deployment's external URL, `https://<domino-domain>/models/<id>/latest/model`; `$DOMINO_API_HOST` and `$DOMINO_API_PROXY` do not route `/models/...`), and the token is created and shown once under **Settings > Invocation > Add Model Access Token**. No API returns or mints that token, and a Domino bearer token is rejected with 401, so ask for both before writing the call. Synchronous endpoints use HTTP Basic auth with the token as both username and password; asynchronous endpoints use `Authorization: Bearer <token>` (https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/domino-endpoint-authorization).

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

To smoke-test in a Workspace before publishing, use another port, because 8888 is the IDE's port there (code-server or Jupyter), and start, check and stop in one command: each tool call is a new shell, so a `kill $!` in a later call finds nothing and the test server keeps running.

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

Streamlit's frontend uses relative URLs, so no base path setting is needed. `[theme]` entries in the same `config.toml` restyle the app (see the `domino-ui-design` skill for Domino's tokens).

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

`app.sh` is `cd "$(dirname "$0")" && python app.py`. Files in `assets/` are served automatically under the same prefix. Dash receives the `domino-username` header through Flask's `request.headers`.

## Flask

```python
# app.py
import os
from flask import Flask, jsonify, request
from predict import predict

app = Flask(__name__)


@app.route("/")
def index():
    return f"Hello {request.headers.get('domino-username', 'Anonymous')} from {os.environ.get('DOMINO_PROJECT_NAME', 'n/a')}"


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

For more than a handful of concurrent users serve with gunicorn (Domino's performance guidance): `gunicorn -w 4 -b 0.0.0.0:8888 app:app`. Use relative URLs in templates (`href="static/style.css"`, `fetch("predict")`), not `/static/...`. If the app must generate absolute URLs, Domino's Flask example wraps `app.wsgi_app` in a `ReverseProxied` middleware that copies `HTTP_X_SCRIPT_NAME` into `SCRIPT_NAME`; see https://docs.domino.ai/cloud/platform-capabilities/features/apps/common-app-frameworks/flask-app .

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

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "project": os.environ.get("DOMINO_PROJECT_NAME", "n/a"),
        "user": request.headers.get("domino-username", "Anonymous"),
    })


@app.post("/predict")
async def predict_route(features: dict):
    return predict(features)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

Reference static files and API routes relatively in `index.html` (`static/app.js`, `fetch("predict")`). The `domino-ui-design` skill builds on this layout with Ant Design.

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

1. **Put the package in the environment** (best): pick an environment that has it when publishing (`GET /api/environments/beta/environments` lists them), or build one from the Domino Standard Environment with Dockerfile lines `USER root`, `RUN pip install dash`, `USER ubuntu` (Domino's Dash guide does exactly this). Fast starts, no egress needed.
2. **`requirements.txt`** at the project root (Git-based projects: inside the Artifacts folder). Domino installs it at the start of every execution, Apps included; slower starts and PyPI egress (https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/add-packages-to-environments/use-requirements-txt).
3. **Install at start in `app.sh`** for a prototype: `python -m pip install --user -q streamlit && exec python -m streamlit run app.py --server.port 8888 --server.address 0.0.0.0`. Same trade-offs as `requirements.txt`; the `python -m` form avoids depending on `~/.local/bin` being on `PATH`.

Floors that match the code above:

| Framework | Packages |
|---|---|
| Streamlit | `streamlit>=1.65`, `requests` |
| Dash | `dash>=4` (3.0 removed `run_server`; the code above runs on 4.4), `plotly`, `requests` |
| Flask | `flask>=3.1`, `gunicorn>=26`, `requests` |
| Gradio | `gradio>=6`, `requests` |
| FastAPI | `fastapi>=0.143`, `uvicorn>=0.54`, `jinja2`, `requests` |

## Environment variables

Injected by Domino: `DOMINO_RUN_HOST_PATH`, `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_NAME`, `DOMINO_PROJECT_OWNER`, `DOMINO_RUN_ID`, `DOMINO_STARTING_USERNAME`, `DOMINO_WORKING_DIR`, `DOMINO_API_HOST` (full glossary: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/manage-compute-environments/manage-environment-variables/5-glossary-default-variables). Set by you in project or user settings: `MODEL_API_URL`, `MODEL_API_TOKEN`.
