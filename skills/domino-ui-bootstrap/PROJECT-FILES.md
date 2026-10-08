# Project files: instructions file and .gitignore (Steps 10–11)

Step 10 (write or merge the agent instructions file at the project root) and Step 11 (`.gitignore` entries for the app folder).

## Step 10 — Write or update the instructions file

The **project root** (from Step 1 — not the app folder if those are different paths) should have an instructions file (`CLAUDE.md` or `AGENTS.md`; see "Host-specific files") that tells future assistant sessions four things:

1. The npm package is `@dominodatalab/extensions-tools`. All imports in this project use that name.
2. Storybook code snippets (and the `node_modules/@dominodatalab/extensions-tools/README.md`) import from `@domino/base-components` — that's a Storybook alias. Rewrite to `@dominodatalab/extensions-tools` before pasting.
3. Component APIs come from the Storybook MCP. Don't invent props.
4. **URLs must be proxy-aware (assets and API).** When deployed, this app is served under a proxy prefix (e.g. `/preview/<appId>/`). Two things keep URLs working (see Step 8): `base: './'` in `vite.config.ts`, and an `apiBase` resolved against `document.baseURI`. Root-absolute URLs (`fetch('/api/…')`) bypass the proxy and 404.
   ```ts
   const apiBase = new URL('api', document.baseURI).href
   fetch(`${apiBase}/projects`)
   ```

It should also describe the MCP lookup workflow (`list-all-documentation` → `get-documentation` → `get-documentation-for-story`), note that React 18 / react-router 5 versions are pinned for peer-dep reasons, and remind that all backend URLs route through `apiBase` (not root-absolute paths).

If the instructions file already exists at the project root, **merge** rather than overwrite — preserve whatever project-specific guidance is there, and add a Domino section. The user's existing file may have important info about their codebase that you'd erase by replacing it. If the project already has the other host's instructions file (for example `CLAUDE.md` when you are writing `AGENTS.md`), mention it so the user can keep the two in sync. If no instructions file exists at the project root, create one there — never inside the app folder, even when the app folder is a subdirectory of the project root.

---

## Step 11 — Update `.gitignore`

The **app folder** (the target path from Step 1) needs a `.gitignore` that excludes the things this skill (and a normal Vite + Domino workflow) generates but that shouldn't be committed. Make sure the following entries are present:

- `node_modules/` — npm install output.
- `dist/` and `build/` — Vite production builds.
- `.vite/` — Vite's dev cache.
- `*.log`, `npm-debug.log*`, `yarn-debug.log*`, `yarn-error.log*` — package manager logs.
- `.DS_Store`, `Thumbs.db` — OS junk.
- `.env`, `.env.local`, `.env.*.local` — local environment files. Keep `.env.example` if the project has one.
- **Claude Code only:** `.claude/settings.local.json` — this is the per-user MCP/permissions file. It can leak machine-specific paths and personal preferences. `.mcp.json` **should** be committed (it's shared project config); `.claude/settings.local.json` should not. Codex's `.codex/config.toml` from Step 6 is shared project config and needs no entry. Only add this entry when the project root equals the app folder — when they differ, `.claude/settings.local.json` lives at the project root (Step 6), so it belongs in *that* directory's `.gitignore`. Don't create or modify a project-root `.gitignore` for this; surface the missing entry to the user and let them decide.

**How to handle the file itself:**

- If `.gitignore` doesn't exist, create it with the entries above.
- If it already exists (Vite's scaffold writes one), read it first and **append only the entries that aren't already covered**. Don't duplicate lines and don't reorder what's there. A grep-and-append per missing entry is fine.
- Preserve any project-specific patterns the user already has (their own ignored directories, secrets paths, build artifacts from other tools, etc.).
- If the user has committed something this skill is now telling git to ignore (e.g., they checked in `node_modules` once by accident, or the MCP enablement file is already tracked), don't run `git rm` on their behalf — surface it and let them decide.
