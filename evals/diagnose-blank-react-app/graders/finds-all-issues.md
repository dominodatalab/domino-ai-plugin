---
type: llm
---

PASS if the reply identifies all of these problems in the user's config and gives a fix for each:
1. Vite has no relative base path; it needs `base: './'`.
2. The app uses port 3000 instead of 8888.
3. The server binds to localhost instead of 0.0.0.0.
4. app.sh never runs the build (`npm run build`) before serving.
5. `serve` is missing the `-s` (single-page app fallback) flag.
FAIL if any of the five is missing, or if the reply says it edited files.
