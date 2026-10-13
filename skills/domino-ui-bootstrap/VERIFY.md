# Verify and hand off (Steps 12–13)

Step 12 (the `npm run build` gate, the `dist/index.html` URL check, and what each build failure means) and Step 13 (what to tell the user at hand-off).

## Step 12 — Verify

The most reliable verification is a clean production build:

```bash
npm run build
```

**`npm install` is not a sufficient check.** It can succeed while the toolchain is broken in ways that only surface at build time (see the rolldown failure below). Always run `npm run build` before reporting success.

This catches version mismatches deterministically. If it passes, the pinning and the entry-point wiring are correct.

`npm run dev` is a softer check — it'll start even with some misconfigurations. Run it if the user wants to eyeball the result, but `npm run build` is the one that gates "done".

**`npm run build` does NOT catch the proxy-URL bug from Step 8** — that's a runtime/deploy failure, not a compile one. After a successful build, also confirm the URL wiring by inspecting the built `dist/index.html`:

- Asset tags are **relative** (`src="./assets/…"`, `href="./assets/…"`) — not `/assets/…`. If they're root-absolute, `base: './'` is missing (Step 8a).
- API calls use `new URL('api', document.baseURI)` (Step 8b). `grep -rn "pathname.replace" src/` should return nothing — any hit is a pathname-based URL builder to replace.

Expected, not a failure: Vite will emit a warning that some chunks are larger than 500 KB. The Domino library bundles a lot — this is normal for Domino apps and doesn't need chasing.

If `build` fails:

- **Rolldown native binding error** (`Cannot find module @rolldown/binding-*` or similar) → the Vite toolchain in `package.json` requires Node `^20.19.0 || >=22.12.0` but the workspace is on an older Node. Go back to Step 4's Node-version branch: install a newer Node or apply the Vite 5 set.
- JSX runtime or React typing errors → React or `@types/react` versions don't match. Recheck Step 4.
- TypeScript errors about `erasableSyntaxOnly` or missing `composite` → leftover from a TS-6 scaffold on a downgraded TS. Recheck the Node-version branch in Step 4 (TypeScript `~5.8.3` keeps the flag; add `composite: true` if `tsc -b` asks for it).
- Missing modules from `@dominodatalab/extensions-tools` → install didn't complete. Check `node_modules/@dominodatalab/extensions-tools/dist`.
- TypeScript errors in the user's existing code (only relevant on retrofits) → don't try to fix them as part of this skill. Surface them to the user and let them decide.

If the build is green but **assets or API calls 404 after deploy**:

- **Cause:** root-absolute URLs (asset tags pointing to `/assets/…`, or `fetch('/api/…')`) bypass the proxy.
- **Fix:** apply both parts of Step 8 — `base: './'` (8a) and `apiBase` via `document.baseURI` (8b).
- Verify the running app is on the latest commit and was re-published — a stale publish serves the old build regardless of code changes.

---

## Step 13 — Hand off

Tell the user:

- Where the project lives.
- How to start the dev server.
- That future component additions should go through the Storybook MCP (which the instructions file you wrote will remind the next session about).
- Anything that changed in their existing code (downgraded versions, swapped router, edited entry point) so they're not surprised.
- The `>500 KB chunk` build warning is expected (Step 12).
- **Port 8888 means two different things.** A published Domino App must listen on `0.0.0.0:8888`; inside a Domino workspace that port belongs to the IDE, so test there with **App Preview** and keep `npm run dev` for a laptop ([domino-apps/REACT-VITE-GUIDE.md](../domino-apps/REACT-VITE-GUIDE.md#developing-in-a-domino-workspace)).
- **Next step toward a deployable app:** suggest that the user create an `app.sh` launch script that runs `npm ci`, `npm run build`, and then serves `dist/` on `0.0.0.0:8888` (`npx serve -s dist -l 8888`, or an Express server when the app calls a model endpoint or the Domino API, so tokens stay server-side). `npm run build` alone does not serve anything. Point them at the `domino-apps` skill for the full deploy shape.
