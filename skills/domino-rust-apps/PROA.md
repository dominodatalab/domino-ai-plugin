# Proa sites as Domino Apps

Proa (https://proa.so) renders pages on the server with Axum and ships one release binary plus a `public/` folder. That fits the build-once model of this skill: build the binary in a Workspace or Job, and `app.sh` only starts it. Proa is pre-1.0 and changes between commits; everything below applies to Proa commit `7ab85e1447191325b46a07bc1353804bc2fcc676`.

## Which Proa

Behind Domino's App proxy a site needs Proa's runtime base path (`BasePath`, set from `PROA_BASE_PATH`). The crates.io releases `proa_framework_axum` 0.3.0 and `proa-cli` 0.1.3 do not have it, so take the CLI and every Proa crate from the commit above. The CLI and the crates must match: a crates.io 0.1.3 CLI cannot build a site that uses the commit's crates. When a crates.io release of `proa_core` documents `BasePath` (https://docs.rs/proa_core), use that release for both and delete the `[patch.crates-io]` block below.

## Install the CLI

Add to the Compute Environment's Dockerfile instructions, after the Rust toolchain ([ENVIRONMENT.md](./ENVIRONMENT.md#dockerfile-instructions)):

```dockerfile
USER root
RUN set -eux; \
    rev=7ab85e1447191325b46a07bc1353804bc2fcc676; \
    if [ "$(uname -m)" = x86_64 ]; then \
      f=proa-cli-0.1.3-main.$rev-x86_64-unknown-linux-gnu; cd /tmp; \
      curl -fsSLO https://github.com/Proa-Labs/proa/releases/download/proa-cli-v0.1.3-main.$rev/$f.tar.gz; \
      echo "7d46959428fdc8936d4a6deb1d1286e0a1a20a6f394b0757a235c0821c443944  $f.tar.gz" | sha256sum -c; \
      tar -xzf $f.tar.gz -C $CARGO_HOME/bin --strip-components=1 $f/proa $f/cargo-proa; rm -f $f.tar.gz; \
    else \
      cargo install --git https://github.com/Proa-Labs/proa --rev $rev --locked proa-cli; \
    fi; \
    proa --version
USER ubuntu
```

The prebuilt CLI runs on x86_64 Linux with glibc 2.34 or later; other architectures compile it, which takes a few minutes. Cargo fetches the Proa crates from github.com with `git`, not from a crates.io mirror; where Workspaces and Jobs cannot reach github.com, vendor them ([ENVIRONMENT.md](./ENVIRONMENT.md#no-mirror-vendor-the-dependencies)).

## Create the site

```bash
proa new site my-site --template minimal --database none --ui none --styling css --deploy none --no-git --no-vscode --yes
```

Use the `minimal` template. The default `app` template runs SQLite migrations at start and writes `data/<name>.db` into the project; App startup must not write, and App files are not saved ([domino-apps](../domino-apps/FRAMEWORKS.md#startup-must-not-change-state)). A site created by the crates.io 0.1.3 CLI does not read `PROA_BASE_PATH`: scaffold a new site with the CLI above and carry over its `src/config.rs`, `src/routes.rs` and `src/static_assets.rs` and the layout's `cx.request().url(...)` calls.

Then make the project follow this skill:

- The scaffold names crates.io versions of the Proa crates, which do not compile with the code it generates. Add this block to `Cargo.toml` to take all of them from the commit:

  ```toml
  [patch.crates-io]
  proa_core = { git = "https://github.com/Proa-Labs/proa", rev = "7ab85e1447191325b46a07bc1353804bc2fcc676" }
  proa_framework_axum = { git = "https://github.com/Proa-Labs/proa", rev = "7ab85e1447191325b46a07bc1353804bc2fcc676" }
  proa_macros = { git = "https://github.com/Proa-Labs/proa", rev = "7ab85e1447191325b46a07bc1353804bc2fcc676" }
  proa_stream = { git = "https://github.com/Proa-Labs/proa", rev = "7ab85e1447191325b46a07bc1353804bc2fcc676" }
  rsjs = { git = "https://github.com/Proa-Labs/proa", rev = "7ab85e1447191325b46a07bc1353804bc2fcc676" }
  ```

  A missing line puts crates.io and Git copies of Proa crates in one build, and `cargo tree -d` does not show it. After `cargo generate-lockfile`, `awk '/^name = "(proa|rsjs)/{p=1} p && /^source/{print $3; p=0}' Cargo.lock | sort -u` must print a single Git source.
- Set `channel` in `rust-toolchain.toml` to the environment's toolchain ([ENVIRONMENT.md](./ENVIRONMENT.md)); the scaffold pins its own.
- Add the `dist` profile from this skill's `Cargo.toml`, and copy `app.sh`, `scripts/build-dist.sh` and `scripts/stamp.sh` from `assets/app/`. Add `public`, `proa.config.json` and `proa.lock.json` to the optional inputs in `scripts/stamp.sh`: Proa serves `public/` from disk, so the build and the files it serves must match.

Proa uses Axum 0.7 (`/:param` routes) while this skill's template uses Axum 0.8 (`/{param}`). Copy patterns, not code, between them.

## Settings Domino needs

In `app.sh`, replace `export PORT=8888` with:

```bash
export PORT=8888 PROA_HOST=0.0.0.0 PROA_BASE_PATH="${DOMINO_RUN_HOST_PATH:-}" RUST_LOG="${RUST_LOG:-info}"
```

| Setting | Why |
|---|---|
| `PROA_HOST`, `PORT` | The scaffold reads these (not `HOST`) and defaults to `127.0.0.1:3000` |
| `PROA_BASE_PATH` | The App's URL prefix, read once at start; the trailing slash of `DOMINO_RUN_HOST_PATH` is accepted. Proa adds it to every URL it generates, so pages, assets, island scripts and redirects stay inside the App. Without it every asset and link returns 404 behind the proxy |
| `RUST_LOG` | Without it the scaffold logs nothing, not even the address it listens on |
| Working directory | Proa serves `public/` relative to the working directory; `app.sh` starts with `cd "$(dirname "$0")"`, the folder that holds `public/` |
| Request limits | Domino allows 25 MiB bodies and 300 s responses. The `minimal` scaffold applies Axum's 2 MB extractor limit and no request timeout; sites built on `FrameworkBuilder` default to 1 MiB and 30 s (408 after that), raised with `.with_body_limit(bytes)` and `.with_request_timeout(duration)` |
| Framing | Domino's App proxy adds `frame-ancestors` to App responses, and browsers then ignore Proa's default `X-Frame-Options: DENY`. If the App stays blank inside Domino and the browser console reports a refused frame, remove the header: add `.layer(SecurityHeadersLayer::new(SecurityHeadersConfig::new().with_frame_options(FrameOptions::Disabled)))` in `src/routes.rs`, with the three types imported from `proa_framework_axum` |

## URLs

Write every URL the site emits as a root-absolute path through Proa's helpers, never as a hand-written `/...` or relative path. The helpers return the full prefixed path, which resolves the same whether the App was opened with or without its trailing slash; a relative path does not.

- In components: `cx.request().url("/static/styles.css")`, `cx.request().url("/about")`, and the same for form `action`.
- In handlers: `Redirect::to(&proa_framework_axum::app_url("/").to_string())`. `app_url` reads the prefix from the request context that `RouteContextLayer` sets, so add routes above that layer in `src/routes.rs`; in a route added below it or in a spawned task, it returns URLs without the prefix.
- CSS and JavaScript files in `public/` are rewritten as they are served: `url()`, `@import`, module imports, `fetch`, `new URL`. Inline `<script>` and `<style>`, URLs inside data files and URLs that libraries such as htmx or axios build are not; pass those from the server with `cx.request().url(...)`.

## Interactive islands

Island scripts, their module preloads and the runtime's imports carry the prefix, so islands hydrate behind Domino's proxy. A site with an island builds only with `proa build` and runs only with `proa run`; plain `cargo build` and `cargo run` stop with a link error that says so. Beside the Workspace IDE, run it with `PORT=8501 proa run`.

## Build once

In `scripts/build-dist.sh`, replace the `cargo build --locked --profile dist` line and the `out=` line with:

```bash
proa build --locked --profile dist --artifact-out "target/proa-dist/$bin"
out="target/proa-dist/$bin"
```

`proa build` first checks the formatting of Proa's template macros and can stop on a difference, so run `proa fmt` and commit before building (`proa fmt --check` reports without writing). It then runs Cargo twice, so a cold build takes about twice as long as `cargo build`: over ten minutes for a small site on an 8-core hardware tier. Keep `--artifact-out` under `target/`: a path elsewhere in the project slows rebuilds. Publish and roll back as for any build in this skill ([APP.md](./APP.md#how-the-binary-is-shipped)).
