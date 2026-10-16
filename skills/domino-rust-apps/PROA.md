# Proa sites as Domino Apps

Proa (https://proa.so) renders pages on the server with Axum and ships one release binary plus a `public/` folder. That fits the build-once model of this skill: build the binary in a Workspace or Job, and `app.sh` only starts it. Proa is pre-1.0 and changes between minor versions; the settings below apply to `proa-cli` 0.1 and `proa_framework_axum` 0.3.

## Create the site

Install the CLI where you develop (`cargo install proa-cli --version 0.1.3 --locked`), then scaffold without a database or UI kit:

```bash
proa new site my-site --template minimal --database none --ui none --styling css --deploy none --no-git --yes
```

Then make the project follow this skill:

- Set `channel` in `rust-toolchain.toml` to the environment's toolchain ([ENVIRONMENT.md](./ENVIRONMENT.md)); the scaffold pins its own.
- Add the `dist` profile from this skill's `Cargo.toml`, and copy `app.sh`, `scripts/build-dist.sh` and `scripts/stamp.sh` from `assets/app/`.
- Add `public`, `proa.config.json` and `proa.lock.json` to the optional inputs in `scripts/stamp.sh`: Proa serves `public/` from disk, so the build and the files it serves must match.
- Use the `minimal` template. The default `app` template runs SQLite migrations at start and writes `data/<name>.db` into the project; App startup must not write, and App files are not saved ([domino-apps](../domino-apps/FRAMEWORKS.md#startup-must-not-change-state)).

Proa 0.3 uses Axum 0.7 (`/:param` routes) while this skill's template uses Axum 0.8 (`/{param}`). Copy patterns, not code, between them.

## Settings Domino needs

| Requirement | Proa |
|---|---|
| Listen on `0.0.0.0:8888` | Scaffolded sites read `PROA_HOST` and `PORT` (not `HOST`), default `127.0.0.1:3000`. In `app.sh`: `export PROA_HOST=0.0.0.0 PORT=8888` |
| Relative URLs | The scaffold's root layout links `/static/styles.css` and `/static/favicon.svg`. Write `static/...`, relative `href` and form `action`, and `Redirect::to("./...")`; Proa has no base-path setting. Put the trailing-slash script first in `<head>` on the root page ([details](../domino-apps/FRAMEWORKS.md#behind-dominos-app-proxy)) |
| Working directory | Proa serves `public/` relative to the working directory; `app.sh` starts with `cd "$(dirname "$0")"`, the folder that holds `public/` |
| Request limits | Domino allows 25 MiB bodies and 300 s responses. Proa's `FrameworkBuilder` defaults to 1 MiB and 30 s (408 after that); raise them with `.with_body_limit(bytes)` and `.with_request_timeout(duration)`, or per route with `DefaultBodyLimit::max(...)`. Without the builder, Axum's own 2 MB extractor limit applies |
| Framing | No change: Domino's proxy sets the App's `frame-ancestors`, and browsers then ignore Proa's default `X-Frame-Options: DENY` |

## Interactive islands

Island scripts load from fixed root paths (`/rsjs-runtime.js`, `/rsjs/island/<id>.js`) that no Proa setting moves under a prefix, so behind Domino's proxy they return 404 and the islands never hydrate; the server-rendered HTML still shows. Build pages without islands, or add client behaviour with a small script in `public/` loaded by a relative URL. Base-path support is requested upstream in https://github.com/Proa-Labs/proa/issues/36 and https://github.com/Proa-Labs/proa/issues/37.

## Build once

- **Without islands:** `bash scripts/build-dist.sh` as in this skill. `cargo build --locked --profile dist` builds the site.
- **With islands:** `cargo build` fails at link time; the build needs `proa build --locked --artifact-out <path>`, and the environment needs `proa-cli` (`RUN cargo install proa-cli --version 0.1.3 --locked` in the Dockerfile, several minutes). In `scripts/build-dist.sh`, replace the `cargo build` line with `proa build --locked --artifact-out "target/proa-dist/$bin"` and set `out` to that path.

Publish and roll back as for any build in this skill ([APP.md](./APP.md#how-the-binary-is-shipped)).
