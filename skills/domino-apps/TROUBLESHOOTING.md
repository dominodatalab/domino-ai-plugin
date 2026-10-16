# Troubleshooting Domino App deployments

Start with the App logs: App details page, instance selector, or the beta logs route in [API-APPS.md](./API-APPS.md). Then match the symptom below. The `domino-debug-proxy` skill runs these checks against the project files.

## 1. App never reaches Running, or shows Error / Failed

**Cause:** nothing is listening on `0.0.0.0:8888`. Domino requires that address and port; an App that binds `localhost`, `127.0.0.1` or another port fails to start.

```bash
node server.js                       # Vite: server.js listens on 0.0.0.0:8888
streamlit run app.py --server.port 8888 --server.address 0.0.0.0
python -m flask run --host=0.0.0.0 --port=8888
```

Other causes, visible in the logs:

- `streamlit: not found` / `ModuleNotFoundError` / `exit code 127`: the framework is not in the Compute Environment. Packages pip-installed in a Workspace are not in the App. Use an environment that has it, a `requirements.txt` at the project root, or (prototype) `python -m pip install --user -q <pkg>` at the top of `app.sh`; see [FRAMEWORKS.md](./FRAMEWORKS.md), Dependencies.
- `entry script 'app.sh' not found in the root directory of your project`: the file was never synced or committed, or the version was created over the API right after the upload, before the DFS head included it, and resolved the previous head. DFS project: **File Changes > Sync to Domino**; Git-based: commit and push; over the API pin `content.dfsCommitId` to the uploaded commit (see [API-APPS.md](./API-APPS.md)). Then publish a new version.
- `Port 8888 is already in use` while testing in a Workspace: that port belongs to the IDE there. Test on another port in one command, since each tool call is a new shell: `streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true & pid=$!; sleep 8; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501/; kill $pid` (never `pkill -f`, which matches your own shell). Leave 8888 in `app.sh`, where the App's own container needs it.
- `app.sh: no build matches these sources`: the saved code changed after the last build, or the build was never saved. Run `scripts/build-dist.sh`, save (**Sync All Changes** or **Sync to Domino**), publish a new version ([FRAMEWORKS.md](./FRAMEWORKS.md#build-once-and-version-builds)).
- `npm: command not found` or a Vite error about the Node version while building: building needs Node 20.19 or later with npm; the App itself needs only `node` ([REACT-VITE-GUIDE.md](./REACT-VITE-GUIDE.md#build-once-serve-the-build)).
- `app.sh` not executable (`git update-index --chmod=+x app.sh`); wrong working directory (start `app.sh` with `cd "$(dirname "$0")"` so it runs next to `package.json` or `app.py`).

## 2. 404 on CSS and JS files

**Cause:** absolute asset paths. The browser asks for `/assets/index.js` at the deployment root instead of under the App's prefix.

```javascript
// vite.config.js
export default defineConfig({ base: './' })
```

Verify after `npm run build`: `grep -o 'src="[^"]*"' build/index.html` must show `./assets/...`, never `/assets/...`. For Flask, FastAPI and hand-written HTML use `href="static/style.css"`, not `/static/style.css`.

## 3. Blank page

1. Browser console: a JavaScript error, or assets loaded from the wrong path (see 2).
2. The App serves an older build than expected: `/healthz` and the App log (`app.sh: serving build <label>`) name the build. Rebuild and save, then publish a new version.
3. The App was not republished after the code change: publishing pins a commit, so edit, commit, publish a new version, deploy it.
4. The URL lacks its trailing slash (`.../apps/<vanity>`): relative assets resolve one level up. Add the trailing-slash script ([FRAMEWORKS.md](./FRAMEWORKS.md#behind-dominos-app-proxy)).

## 4. Deep links or page refresh return 404 (React Router)

**Cause:** routes in the URL path reach the server, which has no file for them.

- Preferred: `HashRouter`. Routes live after `#`, the server only ever sees `/`, and relative assets resolve correctly on every route.
- If `BrowserRouter` must stay: serve with an SPA fallback (the template's `server.js` has one; `npx serve` needs `-s`) and expect relative asset URLs to break on nested routes.

## 5. Dash or another Python app worked before and fails after a restart

**Cause:** the app builds its URL prefix from `DOMINO_PROJECT_OWNER`, `DOMINO_PROJECT_NAME` and `DOMINO_RUN_ID`. The prefix is not derived from them: App Preview (`/preview/<id>/`), deployed Apps (`/apps-internal/<id>/`, `/apps/<vanity>/`) and `/modelproducts/<id>/` differ, so a hand-built prefix breaks on the next restart or deploy. Symptoms: blank page, 404 or 502 after restart; Dash cannot load assets or callbacks.

```python
app = Dash(__name__, routes_pathname_prefix="/",
           requests_pathname_prefix=os.environ.get("DOMINO_RUN_HOST_PATH"))
```

Publish a new version with the change and deploy it. Reference: https://docs.domino.ai/cloud/platform-capabilities/features/apps/app-logs-and-versioning/app-configuration-settings

## 6. Model endpoint calls fail (401, 403, CORS)

- **401 from a synchronous endpoint:** the call used `Authorization: Bearer`, or a Domino user token instead of a Model Access Token. Synchronous endpoints need HTTP Basic with the Model Access Token as both username and password; only asynchronous endpoints take Bearer. Tokens are created per endpoint under **Settings > Invocation** (shown once) or by the agent ([Access tokens](../domino-model-endpoints/DEPLOY-ENDPOINT.md#access-tokens) in `domino-model-endpoints`); the public API lists token ids, never values.
- **404 when calling `$DOMINO_API_HOST/models/...` or `$DOMINO_API_PROXY/models/...` from inside Domino:** those hosts do not route `/models/`. Use the endpoint URL from its overview page (the deployment's external URL) in `MODEL_API_URL`.
- **CORS error in the browser:** the frontend calls the endpoint directly. Route the call through the App's backend (`server.js`, Flask, FastAPI); this also keeps the token out of the bundle.
- **`MODEL_API_URL` / `MODEL_API_TOKEN` undefined:** set them as project environment variables in Domino and restart the App; variables added after a start are not visible until the next start.
- **Token visible in the bundle:** a `VITE_MODEL_API_TOKEN` variable is inlined at build time. Remove it, rotate the token, and read it server-side.

## 7. `import.meta.env.VITE_*` is undefined

Vite exposes only variables prefixed `VITE_`, and only those present at **build** time, in the shell that runs `scripts/build-dist.sh`; the App's environment variables never reach a build made before publishing. Use the prefix for non-secret values only. Runtime values belong in the backend or in a small `GET /api/config` route.

## 8. Slow start

- `app.sh` installs or builds (`npm ci`, `npm run build`, `pip install`, `cargo build`): build once in a Workspace or Job and let `app.sh` only start the build ([FRAMEWORKS.md](./FRAMEWORKS.md#build-once-and-version-builds)). On an air-gapped site, build wherever npm or a mirror is reachable, such as CI ([REACT-CICD.md](./REACT-CICD.md)).
- Put Python packages in the Compute Environment, not in `app.sh`.

## 9. Streamlit websocket or "connection error"

```bash
streamlit run app.py --server.port 8888 --server.address 0.0.0.0 \
    --server.enableCORS false --server.enableXsrfProtection false
```

Domino's Streamlit example sets the same two options in `~/.streamlit/config.toml`.

## 10. Domino API calls from the App fail (401, 403, 500) or return the publisher's data

- **500 (or 401/403) on a viewer call:** without extended identity propagation the viewer's token works only for Dataset snapshot file reads and Data Source lookup by name. Publish with extended identity propagation (SysAdmin or CloudAdmin) or call as the publisher ([FRAMEWORKS.md](./FRAMEWORKS.md#viewer-identity-and-domino-api-calls)).
- **403 from `$DOMINO_API_HOST`:** the call sent a Domino CLI login token. Send the viewer's token, a Personal Access Token or a service account token.
- **The viewer sees the publisher's data:** the code called `$DOMINO_API_HOST` without `Authorization`, which runs as the publisher. Forward the viewer's token and return 401 when it is missing.
- **Publisher calls:** `$DOMINO_API_PROXY/...` with no header, or a bearer fetched per request from `$DOMINO_API_PROXY/access-token`.

## 11. Identity, consent, limits and streaming

- **Viewer name missing or `Anonymous`:** the App reads `domino-username`, which Apps with extended identity propagation do not receive. Read the token's `preferred_username` ([FRAMEWORKS.md](./FRAMEWORKS.md#viewer-identity-and-domino-api-calls)).
- **A script or `fetch` gets HTML or a 302:** a 302 to the sign-in page means no credentials; a 302 to `/app-consent?appId=...` means the user has not consented to an App with extended identity propagation. Consent once in a browser, then send a Personal Access Token.
- **413:** the request body exceeds 25 MiB (the default limit). Upload in parts.
- **No response after 300 s:** the proxy gives up on a response that sends nothing for 300 s. Run long work as a Job and poll for its result.
- **WebSocket or server-sent-events connection closes after 300 s idle:** send a heartbeat more often. **Server-sent events arrive all at once:** send `X-Accel-Buffering: no` on the response.
- **400 when opening the App URL directly:** the deployment shows Apps only inside Domino's iframe; open the App from Domino.
- **Cookies or `localStorage` values from another App:** every App shares one origin; use App-specific cookie names with `Path` set to the prefix, and prefixed `localStorage` keys.
- **`GET /favicon.ico` 404:** the proxy inserts the deployment's favicon link; add a relative `<link rel="icon">` later in `<head>`.

## Diagnostics

Logs over the API (instance reads are beta-only; in a run, no `Authorization` header on `$DOMINO_API_PROXY`; outside one, the deployment URL with a Personal Access Token):

```bash
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances"
curl -s "$DOMINO_API_PROXY/api/apps/beta/apps/$APP_ID/versions/$VERSION_ID/instances/$INSTANCE_ID/logs?logType=stderr"
```

`APP_ID` comes from `GET /api/apps/v1/apps?projectId=$DOMINO_PROJECT_ID&name=<app name>` (`items[].id`) and `VERSION_ID` from that record's `currentVersion.id`. The App details page offers the same logs and a support bundle (`execution.log`, `executor.log`, Kubernetes events, nginx logs).

Reproduce first with App Preview in a Workspace: it runs behind the real proxy with the identity headers. A local run only checks the build and the start command:

```bash
DIST_DIR=dist bash scripts/build-dist.sh && DIST_DIR=dist ./app.sh   # then open http://localhost:8888/healthz
```

## Quick reference

| Symptom | Fix |
|---|---|
| Never Running | Bind `0.0.0.0:8888` |
| 404 on assets | `base: './'`; relative `static/` paths |
| Deep links 404 | `HashRouter` |
| Broke after restart | `DOMINO_RUN_HOST_PATH` instead of a hand-built prefix |
| Model call 401 | Basic auth (sync) with the token as user and password; Bearer only for async |
| CORS on model call | Call from the backend, not the browser |
| Env var undefined | `VITE_` prefix for build-time values; project variables plus restart for runtime values |
| `no build matches these sources` | `scripts/build-dist.sh`, save, publish |
| Slow start | Build once; nothing installed or built in `app.sh`; packages in the environment |
| Viewer calls 500/403, or publisher data | Section 10 |
| Missing username, consent redirects, 413, timeouts, buffered streams | Section 11 |

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/apps/app-logs-and-versioning (logs and support bundle) and https://docs.domino.ai/cloud/platform-capabilities/features/apps/common-app-frameworks (minimal working examples).
