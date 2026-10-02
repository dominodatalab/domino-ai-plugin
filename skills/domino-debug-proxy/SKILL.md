---
name: domino-debug-proxy
description: Diagnose and fix Domino reverse-proxy and routing problems in published web apps by checking vite.config.js, package.json, and app.sh for wrong ports, localhost binding, absolute base paths, missing SPA fallback, or missing build steps. Use when a Domino app shows connection refused, 404s on CSS/JS assets, a blank page, or broken deep links.
---

# Debug Domino App Proxy Issues

Find the configuration mistakes that break apps behind Domino's reverse proxy, report them, and
fix them with the user's agreement.

## Steps

1. Locate the app's config files: `vite.config.js`/`vite.config.ts`, `package.json`, `app.sh`,
   and any framework entry point (`app.py`, `server.js`).
2. Run every check below and record each result as pass or fail.
3. Print a report in the format shown under "Report format".
4. List the recommended fixes and ask whether to apply them. Apply only what the user approves.
5. For anything you can't fix from config, give the manual investigation steps.

## Checks

| # | Check | Pass condition |
|---|---|---|
| 1 | Port | The server listens on `8888`; Vite also sets `strictPort: true` |
| 2 | Base path | Vite sets `base: './'`; other frameworks use relative asset paths |
| 3 | Host binding | The server binds to `0.0.0.0`, not `localhost` or `127.0.0.1` |
| 4 | `app.sh` | It `cd`s to the code directory, runs the build, and then serves the output |
| 5 | SPA fallback | Static serving uses `npx serve -s dist` (the `-s` flag) |
| 6 | Asset references | No hardcoded root-absolute paths such as `/assets/...` or `fetch('/api/...')` |

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| Connection refused | Wrong port, for example 3000 | `server: { port: 8888, strictPort: true }` |
| 404 on CSS/JS files | `base` is `/` or missing | `base: './'` in `defineConfig` |
| App unreachable from the browser | Bound to localhost | `server: { host: '0.0.0.0' }` |
| Deep links return 404 | `serve` without `-s` | `npx serve -s dist -l 8888` |
| Blank page or stale content | `app.sh` has no build step | Add `npm run build` before `serve` |

A corrected `app.sh` for a Vite app:

```bash
#!/bin/bash
set -e
cd /mnt/code
npm ci
npm run build
npx serve -s dist -l 8888
```

## Report format

```
Domino Proxy Debug Report
=========================

Checking: vite.config.js
✅ Port: 8888
✅ Base path: './'
✅ Host: 0.0.0.0

Checking: app.sh
✅ Working directory: /mnt/code
✅ Build command: npm run build
❌ Serve command missing -s flag

Summary: 1 issue found

Recommended fixes:
1. Update the app.sh serve command:
   - Current: npx serve dist -l 8888
   + Fixed:   npx serve -s dist -l 8888
```

## Manual investigation

If the config is correct but the app still fails:

1. Open the browser developer tools console and look for failed module or asset loads.
2. In the Network tab, check whether failing requests drop the app's proxy URL prefix (the part
   of the path before the app's own routes).
3. Check the app logs on the app's page in Domino.
4. Confirm the app was republished after the last code change.

For general deployment guidance, use the `domino-apps` skill.
