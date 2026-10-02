---
name: domino-app-init
description: Scaffold a new Domino-ready web application (Vite + React, Streamlit, Dash, Flask, or Gradio) with proxy-compatible settings, port 8888 binding, and an app.sh entry point. Use when the user wants to start, initialize, or scaffold a new app to publish on Domino, or asks for a starter app.sh for a web framework.
---

# Initialize a Domino App

Create a web application that works behind Domino's reverse proxy on the first publish.

## Inputs

Collect these before writing files. Skip any the user has already given.

1. **Framework**: `vite-react` (default), `streamlit`, `dash`, `flask`, or `gradio`.
2. **Project name**: name for the app folder and `package.json` (React only).
3. **Model API integration**: whether the app calls a Domino model endpoint, and if so its URL.

If the target directory already contains an app, stop and ask before overwriting anything.

## Steps

1. Copy the matching template from this skill's `assets/` folder into the project:

   | Framework | Files to copy |
   |---|---|
   | `vite-react` | `assets/vite-react/vite.config.js`, `assets/vite-react/app.sh`, `assets/vite-react/.env.example` |
   | `streamlit` | `assets/streamlit/app.sh` |
   | `dash` | `assets/dash/app.sh`, and `assets/dash/app.py.template` saved as `app.py` |
   | `flask`, `gradio` | No template; write the files from the snippets below |

2. Make `app.sh` executable (`chmod +x app.sh`).
3. Keep these invariants in every generated file:
   - Bind to `0.0.0.0`, never `localhost` or `127.0.0.1`.
   - Listen on port `8888` unless the user asks for another port.
   - For Vite, set `base: './'` so assets resolve under the proxy prefix.
4. If the user wants Model API integration, add the endpoint URL and token as environment
   variables (see `.env.example`) and never hardcode credentials.
5. Finish with the post-initialization checklist below.

## Reference snippets

### React / Vite: `vite.config.js`

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: { host: '0.0.0.0', port: 8888, strictPort: true },
  preview: { host: '0.0.0.0', port: 8888, strictPort: true },
  build: { outDir: 'dist', assetsDir: 'assets' }
})
```

### React / Vite: `app.sh`

```bash
#!/bin/bash
set -e
cd /mnt/code
npm ci
npm run build
npx serve -s dist -l 8888 --no-clipboard
```

### Streamlit: `app.sh`

```bash
#!/bin/bash
set -e
streamlit run app.py \
    --server.port 8888 \
    --server.address 0.0.0.0 \
    --server.headless true
```

### Dash: `app.py`

```python
import os
from dash import Dash, html

app = Dash(__name__)
app.layout = html.Div([html.H1("Domino Dash App")])

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8888, debug=False)
```

### Flask: `app.py` and `app.sh`

```python
import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Domino Flask App"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=False)
```

```bash
#!/bin/bash
set -e
python app.py
```

### Gradio: `app.py` (use the Flask `app.sh` above)

```python
import gradio as gr

demo = gr.Interface(fn=lambda text: text, inputs="text", outputs="text")

if __name__ == '__main__':
    demo.launch(server_name='0.0.0.0', server_port=8888)
```

## Post-initialization checklist

Tell the user to:

1. Configure environment variables in the Domino project settings.
2. Set `app.sh` as the app entry point when publishing the app.
3. Test locally with `./app.sh` before deploying.
4. Confirm the app listens on port 8888.

For deployment details, CI/CD, and proxy troubleshooting, use the `domino-apps` skill. If the app
shows 404s or blank pages after publishing, use the `domino-debug-proxy` skill.
