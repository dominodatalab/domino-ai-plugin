# App source: proxy-aware URLs and starter screen (Steps 8–9)

Step 8 (make asset and API URLs survive the Domino proxy prefix) and Step 9 (the starter screen for fresh scaffolds, the CSS reset, and the table of components safe to use without an MCP query).

## Step 8 — Make URLs proxy-aware (assets AND API calls)

When this app runs inside Domino it's served under a proxy prefix (e.g. `https://<host>/preview/<appId>/`). Root-absolute URLs bypass the proxy and 404 — both asset tags emitted as `/assets/index-*.js` and user-written `fetch('/api/…')` calls.

Two things to get right:

### 8a. `base: './'` in `vite.config.ts` (the scaffold does NOT set this)

The `npm create vite` scaffold leaves `base` at its default `/`, which emits root-absolute asset URLs (`/assets/…`) that bypass the proxy. Set it explicitly so emitted assets are document-relative:

```ts
export default defineConfig({
  base: './',
  plugins: [react()],
})
```

### 8b. `apiBase` resolved against `document.baseURI`

Build API URLs off `document.baseURI` so they resolve against the proxied path:

```ts
const apiBase = new URL('api', document.baseURI).href
fetch(`${apiBase}/projects`)
```

Don't construct API URLs from `window.location.pathname` (`pathname.replace(/[^/]*$/, '') + 'api'` etc.) — those either bypass the proxy or break under deeper routes. Use `document.baseURI`.

### 8c. Add the trailing slash in `index.html`

Domino serves the App at `<prefix>` and `<prefix>/` alike, without a redirect. Opened without the slash, `./assets/...` and `new URL('api', document.baseURI)` resolve one level too high and 404. Make this the first element inside `<head>` in `index.html` (Vite leaves inline scripts without `type="module"` as written):

```html
<script>if (!location.pathname.endsWith('/')) location.replace(location.pathname + '/' + location.search + location.hash)</script>
```

Keep `location.search` and `location.hash`: `HashRouter` routes and Extension context live there.

### 8d. Title, icon and storage

- Domino inserts the deployment's `<title>` and a `/favicon.ico` link at the start of `<head>` in every HTML response. The inserted title wins, so set `document.title` in `main.tsx` when the tab must show the App's name. `/favicon.ico` answers 404 on the Apps host; keep a relative icon link in `index.html` (`<link rel="icon" href="./favicon.svg">`, file in `public/`).
- Every App on the deployment shares one browser origin. Prefix `localStorage` keys with an App-specific name and keep viewer data out of it.
- WebSockets: `const u = new URL('ws', document.baseURI); u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'`.

### 8e. Identity and Domino calls come from the backend

The page has no Domino token: Domino adds the viewer's token to each request on its way to the App's backend. Get the viewer's name and any Domino data from the App's own backend (`fetch(new URL('api/whoami', document.baseURI))`), which reads the `preferred_username` claim of the `Authorization` token and calls Domino as the viewer or the publisher ([domino-apps](../domino-apps/SKILL.md)). Never call Domino APIs from the browser, and never build links from `DOMINO_API_HOST`.

**When to apply this:**

- **Fresh scaffolds / starter screens you're generating:** write 8a to 8e in from the start. If the starter screen calls a backend, route it through `apiBase`.
- **Retrofits:** add 8a if `base` is missing/`/`, and 8c if `index.html` lacks the slash script. For API calls, scan for `fetch('/`, `axios.get('/`, `new WebSocket('ws`, and any `pathname`-based URL construction. Surface root-absolute or pathname-based URLs and recommend the `document.baseURI` form — **don't silently rewrite their fetches** (some may intentionally target another host).

This overlaps with the `domino-apps` skill, which covers the full deploy shape (launch script, port binding, build output location). Point the user there for an actual app publish.

---

## Step 9 — Starter screen (only for fresh scaffolds)

Skip this step for retrofits — don't overwrite the user's existing `App.tsx` and don't touch their existing CSS.

For a fresh scaffold, replace Vite's default `App.tsx` with something that exercises a few real Domino components, to prove the install works. The minimum it should demonstrate:

- An import from `@dominodatalab/extensions-tools` (so the install path is verified).
- At least one component that depends on the theme provider (e.g., `Button`, `Card`, `Typography`) — this proves Step 7 is wired correctly.
- Optionally, `IconResolver` to demonstrate the icon system.

### Replace `src/index.css` (fresh scaffolds only)

Vite's template `src/index.css` conflicts with `DominoThemeProviderDecorator`'s tokens; on a fresh scaffold replace it:

- Overwrite `src/index.css` with a minimal reset:

  ```css
  body { margin: 0; }
  #root { min-height: 100svh; }
  ```

- Delete `src/App.css` if `App.tsx` no longer imports it.

On retrofits leave existing CSS alone (Step 7).

### Components safe to use without an MCP query

Components and prop shapes safe to use without an MCP query. For anything beyond this set, query the Storybook MCP first (see the instructions-file workflow in Step 10) — don't guess.

| Component | Safe usage |
|---|---|
| `Button` | `type='primary' \| 'secondary' \| 'tertiary'`, `onClick`, children. |
| `Card` | `title`, `extra`, `helpMessage`, `noPadding`, children. **No `size` prop.** |
| `Row` / `Col` / `Space` | Ant-style. `Space` takes `direction`, `size`. |
| `Tag` | `type` (**not `color`**). Values: `user-generated`, `success`, `danger`, `warning`. |
| `Typography` | **Namespace, not a wrapper.** Render `Typography.H1` / `.H2` / `.H3` / `.Text`. Never `<Typography>…</Typography>` — it'll throw React error #130 at runtime. |
| `Typography.Text` | Optional `type='BodyDefault' \| 'BodyDefaultStrong' \| 'BodySmall' \| 'BodySmallStrong' \| 'BodyCode'`. |
| `SpinnerWrapper` | Loading wrapper. |

`node_modules/@dominodatalab/extensions-tools/README.md` also imports from the Storybook alias `@domino/base-components`; every import in this project uses `@dominodatalab/extensions-tools` ([SKILL.md](./SKILL.md#why-this-exists)).
