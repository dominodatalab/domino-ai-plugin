---
type: llm
---

PASS if the reply identifies all of these problems in the user's config and gives a fix for each:
1. Vite has no relative base path; it needs `base: './'`.
2. The app uses port 3000 instead of 8888.
3. The server binds to localhost instead of 0.0.0.0.
4. app.sh serves `dist/` but no build exists: nothing ever runs the Vite build. Either fix counts: build once in a Workspace or Job and have app.sh serve that build (the recommended form, which also drops `npm ci` from app.sh), or run `npm run build` in app.sh before serving.
5. `serve` is missing the `-s` (single-page app fallback) flag, or an equivalent SPA fallback such as a server that returns `index.html` for extension-less paths.
Fixes shown as diffs or code blocks, or an offer to apply them, are proposals and are fine.
FAIL if any of the five is missing, or if the reply claims it already changed a file.
