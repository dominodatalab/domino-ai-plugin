# Setup steps (1–7)

Steps 1–7 of the Domino UI bootstrap workflow: elicit project info, survey the target directory, scaffold, align `package.json`, install, register the Storybook MCP, and wire the React entry point. Read [SKILL.md](./SKILL.md) first for the invariants and the host-specific file names.

## Step 1 — Elicit project info

Ask the user, in a single turn, for:

1. **Target path** — the absolute or workspace-relative path where the Vite + React app will live ("the app folder"). Ask this as a plain chat question, not a multiple-choice picker, because paths are free-form.
2. **Project root path** — where shared project config (the instructions file, MCP config, and MCP enablement file) should live. Default to the target path; set this to a parent directory when the target is a subfolder of a larger repo (monorepos, an existing project with apps under `apps/`, etc.) — those files belong at the repo root, not nested inside the app folder. Ask explicitly; don't assume. If the user doesn't volunteer one, propose the target path and confirm.
3. **Display name** — free-form, any string. Used in the instructions file, UI titles, and the hand-off message. Example: `Domino Frontend`.
4. **Package name** — the value that goes in `package.json`'s `name` field. npm requires lowercase, no spaces, no leading dot or underscore, URL-safe. Default to the kebab-case-lowercase of the display name (e.g. `Domino Frontend` → `domino-frontend`) and confirm. If retrofitting, default to whatever the existing `package.json` says and confirm.
5. **What to do if the path has unexpected content** — present this as a short list of choices once you've inspected the directory (Step 2). The options depend on what you find; see Step 2.

If the user has already given any of these in the conversation, skip the corresponding question. If they give only one name, treat it as the display name and derive the package name from it — don't ask twice for the same information, just confirm the normalized package name. Throughout the rest of this skill, "project root" means the path from question 2 (equal to the target path unless the user said otherwise) and "app folder" means the target path from question 1.

---

## Step 2 — Survey the target directory

Before changing anything, find out what's there. This determines which branch of the skill you take.

Look for:

- Does the path exist? Is it empty?
- Is there a `package.json`? If so:
  - Is `react` already a dependency? At what major version?
  - Is `vite` a devDependency? Some other bundler (`webpack`, `next`, `parcel`, `cra`)?
  - Does `@dominodatalab/extensions-tools` already appear (any version)?
- Is there a `src/` directory with `main.tsx` / `main.jsx` / `index.tsx` / `index.jsx`?
- At the **project root** (from Step 1 — may equal the app folder, may not): is there an existing instructions file, MCP config, or MCP enablement file (see "Host-specific files")? These live at the project root, not the app folder, so check there even when the app folder is a fresh empty subdirectory.

Classify the directory into one of these states, then ask the user how to proceed if needed:

| State | What you found | What to do |
|---|---|---|
| **Empty / nonexistent** | No files, or directory doesn't exist | Go to Step 3 (scaffold from scratch). |
| **Vite + React already** | `package.json` lists `vite` and `react` | Skip scaffolding. Go to Step 4 (align deps), then continue. |
| **React but not Vite** | React present, bundler is webpack/CRA/Next/etc. | Stop and ask the user: do they want to migrate to Vite, or keep their bundler and just add the Domino library? The skill is Vite-shaped; if they keep their bundler, the version pinning and theme-provider wiring still apply, but the scaffolding steps don't. |
| **Unrelated content** | Files exist but no `package.json`, or a non-React `package.json` | Ask the user: overwrite (delete and scaffold fresh), bootstrap in place (let Vite prompt), or pick a different path. |
| **Already partially Domino-wired** | `@dominodatalab/extensions-tools` already in deps | Treat as a verification/repair job: check each invariant below and only touch what's actually wrong. |

Run `node -v` and `npm -v`. Stop if Node is older than 20.

---

## Step 3 — Scaffold (only if empty / nonexistent / overwrite chosen)

From the target directory:

```bash
npm create vite@latest . -- --template react-ts
```

Do not run `npm install` immediately afterward. The next step rewrites `package.json` so the install picks up the right versions in one pass.

If the directory had existing content and the user chose "overwrite", clear it first (`rm -rf` the contents, not the directory itself).

---

## Step 4 — Align `package.json` to the Domino invariants

You're enforcing constraints, not writing a fixed file. View the current `package.json` and make sure it satisfies these:

**Required `dependencies`** (add or pin to these exact versions):

- `@dominodatalab/extensions-tools` — `latest` is fine for fresh projects; use a specific version if the user gave one or if one is already pinned in the existing `package.json`. (See the post-install pin step at the end of this section.)
- `react` — `18.2.0`
- `react-dom` — `18.2.0`
- `react-router` — `5.3.4`
- `react-router-dom` — `5.3.4`

**Required `devDependencies`** (the React typings must match React 18):

- `@types/react` — `18.2.0`
- `@types/react-dom` — `18.2.0`
- `@types/react-router` — `5.1.20`
- `@types/react-router-dom` — `^5.3.3`

**Node-version branch — check this BEFORE leaving the scaffold's toolchain alone.**

Run `node -v`. The current `npm create vite@latest` scaffold writes Vite 9 / TypeScript 6 / ESLint 10 / `@types/node` 24, all of which require Node ≥ 20.19. The Domino default workspace image ships Node 20.18.3, so the scaffold's defaults will fail `npm run build` (rolldown native binding error) and TS will error on `erasableSyntaxOnly` (a 5.6+ flag) and on missing `composite: true` for `tsc -b`.

- **If Node ≥ 20.19:** the scaffold's defaults are fine. Skip to "Leave alone" below.
- **If Node < 20.19:** pin the toolchain to a Node-20.18-compatible set before installing:
  - `vite` — `^5.4.0`
  - `@vitejs/plugin-react` — `^4.3.4`
  - `typescript` — `~5.5.4` (or `~5.6` if you keep `erasableSyntaxOnly` — but the simpler path is to drop the flag)
  - `@types/node` — `^20.12.0`
  - Remove the `eslint`, `@eslint/js`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `typescript-eslint`, and `globals` entries from `devDependencies`. The Vite-9 scaffold's ESLint pins all require Node ≥ 20.19 — easier to drop them than to find a compatible set.
  - Strip the `erasableSyntaxOnly` line from `tsconfig.app.json` and `tsconfig.node.json` (TS 5.6+ only).
  - Add `"composite": true` to both `tsconfig.app.json` and `tsconfig.node.json` (required when `build` runs `tsc -b`).
  - Delete `eslint.config.js` since ESLint was removed.

**Leave alone:**

- Vite, ESLint, TypeScript, `@vitejs/plugin-react`, and any other tooling already in the file — assuming the Node-version branch above didn't tell you to touch them. Whatever versions are there are fine if they work on the user's Node.
- Any scripts, fields, or sections you don't have a specific reason to change. In particular, don't rewrite `scripts` if the existing ones work; only add `dev`/`build`/`preview` if they're missing.
- Any project-specific dependencies the user already has (state libraries, icon packs, data-fetching libs, etc.). The skill is additive.

**Remove or downgrade:**

- If `react` or `react-dom` is at 19+, downgrade to `18.2.0`. Same for the `@types/*`.
- If `react-router-dom` is at 6+, downgrade to `5.3.4`. Warn the user — their existing routes use v6 syntax (`<Routes>` / `element={}`) and will need to be rewritten to v5 (`<Switch>` / `component={}` or `render={}`). Don't silently rewrite their routes; tell them what needs to change.

**After install — pin the resolved `@dominodatalab/extensions-tools` version.**

Once Step 5 has run cleanly and `latest` was used, resolve the floating tag to a concrete version and rewrite `package.json`:

```bash
npm view @dominodatalab/extensions-tools version
```

Replace `"latest"` in `dependencies` with the exact version string this returns. Skip if a specific version was already pinned (the user explicitly chose one, or you retrofitted). This keeps future installs reproducible — `latest` drifts.

---

## Step 5 — Install

```bash
npm install
```

Likely failures:

- **Peer-dep error about React 19** → Step 4 didn't take. Re-check `package.json`. Don't use `--legacy-peer-deps`.
- **404 / E401 / EAUTH on `@dominodatalab/extensions-tools`** → the user needs to authenticate to a private npm registry. Stop and ask how they normally authenticate. Don't switch to a tarball or alternative source on your own.

---

## Step 6 — Register the Storybook MCP

The Storybook MCP is what lets future assistant sessions look up real component props instead of guessing. Register a server named `storybook` at the **project root** (from Step 1 — not the app folder if those are different paths) that points at the Domino library's live Storybook:

- URL: `https://main--60c0de3f60dd96003bdcb1a1.chromatic.com/mcp`
- Transport: HTTP (streamable HTTP)

These rules apply on every host:

- If the MCP config already exists at the project root (with other MCP servers, or from a prior bootstrap), merge — don't overwrite. Add the `storybook` entry alongside whatever's there.
- If a `storybook` server is already registered at a different URL, ask the user before changing it.
- If no MCP config exists at the project root, create one there — never inside the app folder.

### Claude Code

**`.mcp.json`** registers the server with transport `http` and the URL above.

**`.claude/settings.local.json`** must:

- Pre-allow tools under the `mcp__storybook` namespace.
- Enable project-level MCP servers (`enableAllProjectMcpServers: true`).
- List `storybook` in the enabled servers.

Both files must sit in the same directory: if they get split across folders, Claude Code won't apply the allow-list to the registered MCP and the server stays disabled. If `.claude/settings.local.json` already exists, merge the relevant fields and preserve any other permissions or settings.

### Codex

**`.codex/config.toml`** registers the server:

```toml
[mcp_servers.storybook]
url = "https://main--60c0de3f60dd96003bdcb1a1.chromatic.com/mcp"
```

Codex loads project `.codex/config.toml` only for trusted projects. Tell the user to trust the project if Codex hasn't asked yet. If the file already exists, add the table without touching other settings.

---

## Step 7 — Wire up the React entry point

The project's React entry (`src/main.tsx` for a fresh scaffold, but it might be `src/index.tsx` or similar in an existing project) needs to satisfy these invariants:

- `DominoThemeProviderDecorator` from `@dominodatalab/extensions-tools` wraps the entire app tree. It must be an ancestor of every Domino component that gets rendered.
- A `HashRouter` from `react-router-dom` (v5) wraps the app inside the theme provider. Not `BrowserRouter`, not v6.
- The app component is rendered via `createRoot` from `react-dom/client` (React 18 idiom).
- `StrictMode` is fine to keep if Vite added it; not required.

For a fresh scaffold, write a clean `main.tsx` from scratch. For an existing project:

- If the entry already wraps the app in some other provider (Redux store, React Query client, custom theme), keep those wrappers and insert `DominoThemeProviderDecorator` so it's an ancestor of any Domino components. The usual place is outermost or just inside `StrictMode`, but the user's existing structure may dictate otherwise — don't blindly reorder providers that have ordering requirements (e.g., Redux usually goes outermost; auth providers often need to be high up).
- If the project already has a router, check which one. If it's `BrowserRouter` from v5, swap to `HashRouter`. If it's any router from v6, you'll need to convert routes too (see Step 4's note) — flag this to the user before doing it.
- Don't remove existing CSS imports. The theme provider injects its own styles, so a separate Domino CSS import isn't needed, but the user's app CSS should stay.

A heads-up worth passing to the user: in a standalone (non-Domino-backend) environment, `DominoThemeProviderDecorator` will try to fetch user / white-label data and fail silently. The UI still renders with defaults. If they want to suppress those requests, point them at `node_modules/@dominodatalab/extensions-tools/README.md` for the static `useStoreHook` prop.
