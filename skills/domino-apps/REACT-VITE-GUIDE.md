# React + Vite on Domino

How a Vite-built React app is served behind Domino's reverse proxy, and how it calls a model endpoint without exposing the token.

## What the proxy does

```
Viewer opens:  the App's `url` field (an apps hostname or an /apps/<vanity>/ path; both end in a prefix)
Proxy:         authenticates the viewer, strips the prefix, forwards to the container on port 8888,
               adds `Authorization: Bearer <viewer token>` (secure identity propagation, the default) and,
               except for Apps with extended identity propagation, a `domino-username` copy of the name
Container:     GET /              -> index.html
               GET /assets/x.js   -> served from the build app.sh selected
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
  build:  { outDir: 'build', assetsDir: 'assets' },   // scratch output; dated builds go to dist/
})
```

`server` matters only for `npm run dev` on a laptop. Neither the dev server nor `vite preview` is a way to serve the App on Domino: Vite ignores a relative `base` in dev mode and its host check rejects proxied hostnames, so a published App serves a build as described below and in-Domino testing goes through App Preview. `outDir` is `build/` because `npm run build` empties its output folder, and the dated builds in `dist/` must survive it.

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

The App URL also answers without its trailing slash, where `./assets/...` resolves one level up. Make this the first line of `<head>` in `index.html`:

```html
<script>if (!location.pathname.endsWith('/')) location.replace(location.pathname + '/' + location.search + location.hash)</script>
```

## Build once, serve the build

`app.sh` never installs or builds. Build in a Workspace or a Job with `scripts/build-dist.sh`, save the build, then publish. Dated builds, the previous build kept for rollbacks, and how `app.sh` picks one: [FRAMEWORKS.md](./FRAMEWORKS.md#build-once-and-version-builds). Copy `app.sh`, `server.js`, `scripts/build-dist.sh` and `scripts/stamp.sh` from the `domino-app-init` template ([assets/vite-react](../domino-app-init/assets/vite-react/server.js)).

- **Node.** Building needs Node 20.19 or later with npm (Vite 8). The App needs only `node` 18 or later, because `server.js` uses Node built-ins and the App never runs npm. A Compute Environment can ship an older Node without npm: check `node -v` and `npm -v` in the Workspace, and if either is missing or older, add Node 24 (LTS) to the environment, or install it for your user with nvm v0.40.8: `git clone --depth 1 --branch v0.40.8 https://github.com/nvm-sh/nvm.git ~/.nvm`, then `export NVM_DIR=~/.nvm && . ~/.nvm/nvm.sh && nvm install 24` (repeat the `export` and `.` in each new shell).
- **Build.** `bash scripts/build-dist.sh` runs `npm ci` and `npm run build` (Vite writes `build/`), then copies `build/` into a dated folder under `/mnt/artifacts/dist/<package name>/` in a Git-based Project, or `dist/` with `DIST_DIR=dist` in a DFS Project. Registry access (or a mirror in `.npmrc`) is needed only here. `VITE_` variables come from the shell that runs the build, not from the App.
- **Save.** Git-based: commit and push the code, and **File Changes > Sync All Changes** saves the build. DFS: **Sync to Domino**, with `node_modules/` and `build/` listed in the `.dominoignore` at the Project root (Domino reads only that file; a folder pattern matches at any depth).
- **Serve.** `app.sh` hashes the committed build inputs (`index.html`, `package.json`, `package-lock.json`, `src/`, `public/`, Vite and TypeScript config), picks the newest build whose stamp matches, and runs `node server.js` with `BUILD_DIR` and `APP_BUILD` set. It never falls back to an older or newer build.

`server.js` serves the build with an SPA fallback for extension-less paths (a missing asset stays 404), answers `healthz` with the build label, calls the model endpoint server-side (`POST api/predict`), and calls the Domino API as the viewer by forwarding the request's `Authorization` header (`GET api/projects`); without the header it answers 401 instead of calling without one, because `$DOMINO_API_HOST` runs header-less calls as the publisher. Calls as the publisher go to `$DOMINO_API_PROXY` with no header. Which routes accept the viewer's token: [FRAMEWORKS.md](./FRAMEWORKS.md#viewer-identity-and-domino-api-calls).

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
| `MODEL_API_TOKEN` | Same; never in the repository | A Model Access Token: the user's (created under **Settings > Invocation > Add Model Access Token**, shown once) or one the agent creates and stores ([Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens) in `domino-model-endpoints`) |

The URL has to come from a person with access to the endpoint's page; the token can be created by the agent.

A changed variable takes effect on the next start of the App. `.env.example` documents the names; `.env` files stay out of git. For a local run, `node --env-file=.env server.js`.

## Developing in a Domino Workspace

Use **App Preview**: open the App Preview tab in the workspace, set the App file (`app.sh`), Compute Environment and Hardware Tier, and start it. Preview runs the saved code in a real App pod on port 8888 with the production proxy, `DOMINO_RUN_HOST_PATH` and identity headers, at `/preview/<draftAppId>` (author only). After a code change, run `scripts/build-dist.sh` and save before Preview restarts: `app.sh` serves only a build of the saved code and otherwise stops with `no build matches these sources`. Publish from the same workspace with **Publish App**.

Do not try to run the Vite dev server inside the workspace instead: the workspace IDE owns port 8888, Vite serves `/@vite/client` and `/src/main.jsx` from the domain root in dev mode (it ignores a relative `base`), and its host check rejects proxied hostnames, so the page comes up blank behind Jupyter Server Proxy. Keep `npm run dev` for a laptop and App Preview for Domino.

## Project layout

```
my-react-app/
  src/
    api/modelApi.js
    App.jsx
    main.jsx
  public/
  scripts/
    build-dist.sh    # npm ci, npm run build, copy into a dated build, keep the previous one
    stamp.sh         # hash of the committed build inputs
  build/             # Vite's scratch output; git- and Domino-ignored
  dist/              # dated builds in a DFS Project (Git-based: /mnt/artifacts/dist/<package name>/)
  vite.config.js     # base './', outDir 'build'
  package.json       # "type": "module"; no runtime dependencies are needed by server.js
  server.js          # Node built-ins only
  app.sh             # starts with cd "$(dirname "$0")", so the folder can sit anywhere in the repo
  .env.example
  .gitignore         # node_modules/, build/, dist/, .env
```

The `domino-app-init` skill writes these files; `domino-debug-proxy` checks them.
