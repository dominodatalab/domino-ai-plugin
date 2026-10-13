# React + Vite on Domino

How a Vite-built React app is served behind Domino's reverse proxy, and how it calls a model endpoint without exposing the token.

## What the proxy does

```
Viewer opens:  the App's `url` field (an apps hostname or an /apps/<vanity>/ path; both end in a prefix)
Proxy:         authenticates the viewer, strips the prefix, forwards to the container on port 8888,
               adds the `domino-username` header (and `Authorization` when identity propagation is on)
Container:     GET /              -> index.html
               GET /assets/x.js   -> served from dist/
```

Two consequences for a single-page app:

1. **Assets must be referenced relatively.** Vite's default `base: '/'` emits `/assets/index.js`; the browser requests that from the deployment root, outside the prefix, and gets a 404. `base: './'` emits `./assets/index.js`, which resolves under the prefix.
2. **Client-side routes must not need the server.** `HashRouter` keeps routes after `#`, so every request the server sees is `/` or an asset, and relative asset URLs resolve from the App root on every route. `BrowserRouter` with a basename derived from `window.location.pathname` breaks on nested routes (`./assets/...` then resolves under `/reports/2024/`) and needs an SPA fallback on the server. Use `HashRouter`; it is also what `@dominodatalab/extensions-tools` expects (see the `domino-ui-bootstrap` skill).

## vite.config.js

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',                       // relative asset URLs in the build; required behind the proxy
  server: { host: '0.0.0.0', port: 8888, strictPort: true },   // laptop development only
  build:  { outDir: 'dist', assetsDir: 'assets' },
})
```

`server` matters only for `npm run dev` on a laptop. Neither the dev server nor `vite preview` is a way to serve the App on Domino: Vite ignores a relative `base` in dev mode and its host check rejects proxied hostnames, so a published App serves `dist/` as described below and in-Domino testing goes through App Preview.

## Router

```jsx
// src/main.jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <HashRouter>
    <App />
  </HashRouter>
)
```

Routes appear as `.../apps/<vanity>/#/dashboard`.

## Serving the build

### Static only (the app calls nothing)

```bash
#!/bin/bash
# app.sh
set -e
cd "$(dirname "$0")"       # run next to package.json, wherever app.sh lives in the repo
npm ci
npm run build
npx serve -s dist -l 8888 --no-clipboard
```

Add `serve` to `devDependencies` so `npm ci` installs it and `npx` needs no network access at start. `-s` rewrites unknown paths to `index.html`: harmless with `HashRouter`, required with `BrowserRouter`. `npm ci` itself needs egress to the npm registry or a private mirror (`.npmrc`); on an air-gapped site commit `dist/` on a deploy branch and reduce `app.sh` to the serve step.

### Static build plus a backend (the app calls a model endpoint or the Domino API)

The token must never reach the browser, so a small Express server serves `dist/` and makes the call. `app.sh` ends with `node server.js` instead of `npx serve`; add `express` to `dependencies` (`package.json` from the Vite scaffold already has `"type": "module"`).

```javascript
// server.js
import express from 'express'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist')
const app = express()
app.use(express.json())

// Server-side call to a synchronous Domino endpoint: HTTP Basic with the token as user and password.
// Asynchronous endpoints take "Authorization: Bearer <token>" instead.
app.post('/api/predict', async (req, res) => {
  const url = process.env.MODEL_API_URL
  const token = process.env.MODEL_API_TOKEN
  if (!url || !token) return res.status(500).json({ error: 'MODEL_API_URL or MODEL_API_TOKEN is not set' })
  const basic = Buffer.from(token + ':' + token).toString('base64')
  try {
    const upstream = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Basic ' + basic },
      body: JSON.stringify({ data: req.body }),
    })
    res.status(upstream.status).type('application/json').send(await upstream.text())
  } catch (err) {
    console.error('model endpoint call failed:', err)
    res.status(502).json({ error: 'model endpoint call failed' })
  }
})

app.use(express.static(dist))
app.use((req, res) => {                       // SPA fallback for extension-less paths only
  if (path.extname(req.path)) return res.status(404).end()   // a missing asset stays a 404
  res.sendFile(path.join(dist, 'index.html'))
})

app.listen(8888, '0.0.0.0', () => console.log('listening on 0.0.0.0:8888'))
```

The same server can call the Domino platform API as the publisher (`DOMINO_API_PROXY` with no header, or a bearer from `http://localhost:8899/access-token` on `DOMINO_API_HOST`) or as the viewer by forwarding the incoming `Authorization` header when extended identity propagation is enabled for the App.

### Frontend call

```javascript
// src/api/modelApi.js
const apiBase = new URL('api/', document.baseURI).href   // resolves under the proxy prefix

export async function predict(input) {
  const response = await fetch(apiBase + 'predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) throw new Error('API error: ' + response.status)
  return response.json()
}
```

Never read a token from `import.meta.env`: Vite inlines every `VITE_` variable into the bundle at build time, so it would ship to every viewer. `VITE_` variables are fine for non-secret build-time values (titles, feature flags).

### Configuration

| Variable | Where to set it | Value |
|---|---|---|
| `MODEL_API_URL` | Project environment variables (project **Settings**, or the API in [domino-api-intro](../domino-api-intro/SKILL.md#environment-variables-as-the-secret-store)) or user environment variables | The endpoint's URL from its overview page (the deployment's external URL; `$DOMINO_API_HOST` does not route `/models/`) |
| `MODEL_API_TOKEN` | Same; never in the repository | A Model Access Token created on the endpoint under **Settings > Invocation > Add Model Access Token**, shown once; no API returns it |

Both values have to come from a person with access to the endpoint's page; an agent cannot look them up.

A changed variable takes effect on the next start of the App. `.env.example` documents the names; `.env` files stay out of git. For a local run, `node --env-file=.env server.js`.

## Developing in a Domino Workspace

Use **App Preview**: open the App Preview tab in the workspace, set the App file (`app.sh`), Compute Environment and Hardware Tier, and start it. Preview runs the committed code in a real App pod on port 8888 with the production proxy, `DOMINO_RUN_HOST_PATH` and identity headers, at `/preview/<draftAppId>` (author only). Commit, and live sync restarts the container with the new commit. Publish from the same workspace with **Publish App**.

Do not try to run the Vite dev server inside the workspace instead: the workspace IDE owns port 8888, Vite serves `/@vite/client` and `/src/main.jsx` from the domain root in dev mode (it ignores a relative `base`), and its host check rejects proxied hostnames, so the page comes up blank behind Jupyter Server Proxy. Keep `npm run dev` for a laptop and App Preview for Domino.

## Project layout

```
my-react-app/
  src/
    api/modelApi.js
    App.jsx
    main.jsx
  public/
  dist/              # build output, git-ignored
  vite.config.js
  package.json       # "type": "module"; express in dependencies; serve in devDependencies if used
  server.js
  app.sh             # starts with cd "$(dirname "$0")", so the folder can sit anywhere in the repo
  .env.example
  .gitignore
```

The `domino-app-init` skill writes these files; `domino-debug-proxy` checks them.
