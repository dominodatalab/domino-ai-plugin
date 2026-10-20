# Rust in a Compute Environment

How to put a pinned Rust toolchain and its tools into a Domino Compute Environment. Creating environments and revisions: [domino-environments](../domino-environments/SKILL.md).

## Dockerfile instructions

Add one revision to the Project's environment (based on the Domino Standard Environment, which provides `curl`, `gcc`, `git` and VS Code) with these Dockerfile instructions. They install, in one layer:

- rustup (`rustup-init`, checked against its published SHA-256) and the toolchain pinned in `rust-toolchain.toml`, with Clippy, rustfmt, rust-analyzer and the standard library source;
- cargo-nextest and cargo-deny from their release archives, checked against the published SHA-256;
- the rust-analyzer VS Code extension.

```dockerfile
USER root
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
RUN set -eux; \
    arch=$(uname -m); cd /tmp; \
    r=https://static.rust-lang.org/rustup/dist/$arch-unknown-linux-gnu/rustup-init; \
    curl --proto '=https' --tlsv1.2 -fsSLO $r; curl --proto '=https' --tlsv1.2 -fsSLO $r.sha256; \
    sha256sum -c rustup-init.sha256; chmod +x rustup-init; \
    ./rustup-init -y --no-modify-path --profile minimal \
      --default-toolchain 1.99.1 --component clippy,rustfmt,rust-analyzer,rust-src; \
    rm -f rustup-init rustup-init.sha256; \
    nv=0.9.148; f=cargo-nextest-$nv-$arch-unknown-linux-gnu; \
    curl -fsSLO https://github.com/nextest-rs/nextest/releases/download/cargo-nextest-$nv/$f.tar.gz; \
    curl -fsSLO https://github.com/nextest-rs/nextest/releases/download/cargo-nextest-$nv/$f.sha256; \
    sha256sum -c $f.sha256; tar -xzf $f.tar.gz -C $CARGO_HOME/bin; \
    dv=0.20.2; d=cargo-deny-$dv-$arch-unknown-linux-musl; \
    curl -fsSLO https://github.com/EmbarkStudios/cargo-deny/releases/download/$dv/$d.tar.gz; \
    curl -fsSLO https://github.com/EmbarkStudios/cargo-deny/releases/download/$dv/$d.tar.gz.sha256; \
    echo "$(cut -d' ' -f1 $d.tar.gz.sha256)  $d.tar.gz" | sha256sum -c; \
    tar -xzf $d.tar.gz -C $CARGO_HOME/bin --strip-components=1 $d/cargo-deny; \
    rm -f /tmp/cargo-*; \
    if command -v code-server >/dev/null; then \
      code-server --install-extension rust-lang.rust-analyzer --extensions-dir /home/ubuntu/.local/share/code-server/extensions; \
      chown -R ubuntu:ubuntu /home/ubuntu/.local/share/code-server; \
    fi; \
    chown -R ubuntu:ubuntu $RUSTUP_HOME $CARGO_HOME; \
    rustc --version; cargo nextest --version; cargo deny --version
USER ubuntu
```

Why each part:

- `RUSTUP_HOME` and `CARGO_HOME` under `/usr/local` live in the image, so every Workspace, Job and App has the toolchain without reinstalling. `$HOME` (`/home/ubuntu`) is not kept between sessions unless Home Directory Persistence is on.
- `chown -R ubuntu:ubuntu` lets the run user (`ubuntu`) download crates into `CARGO_HOME`, add components, and let rustup install a toolchain that `rust-toolchain.toml` pins but the image lacks, without making the toolchain writable for every user.
- `--no-modify-path` skips shell profile edits; the `ENV PATH` line makes `cargo` visible to every process, including Apps and agents.
- `gcc` and `libc6-dev` must stay in the image: Rust uses `cc` to drive the linker even though LLD is the default linker on x86_64 Linux. cargo-deny calls `git` to fetch the RustSec advisory database.
- The VS Code extension bundles its own language server; listing `rust-analyzer` in `rust-toolchain.toml` components makes it use the toolchain's server instead.

Check in a new Workspace on the revision: `rustc --version` prints the pinned version, `rust-analyzer --version` prints a version (not `Unknown binary`), and `cargo nextest --version` and `cargo deny --version` succeed. If the build fails on a download, read the build log ([domino-environments API.md](../domino-environments/API.md#build-logs)); the builder may lack internet access (see "Offline and mirrors").

## Upgrading Rust

1. Change `--default-toolchain` in the Dockerfile instructions and build a new revision.
2. Change `channel` in `rust-toolchain.toml` to the same version, run `bash scripts/check.sh`, fix new Clippy findings, and commit.
3. Rebuild the binary (`bash scripts/build-dist.sh`) and publish a new App version on the new revision.

Do steps 1 and 2 together. If the project pins a version the image lacks, rustup downloads it on the first `cargo` call in every new Workspace (several hundred MB, and it fails without internet access or a mirror). Set `RUSTUP_AUTO_INSTALL=0` as an environment variable to make that an error instead of a download.

To move to the latest stable release, read its version (`rustup check`, or the release notes at https://blog.rust-lang.org) and use it in both places; pin an exact version rather than `stable`, so every build uses the same compiler.

Nightly: use a dated channel (`nightly-2026-10-14`) in both places, never bare `nightly`, so the build is reproducible.

## Package registry mirrors

Many organizations serve crates.io and the Rust toolchain through a repository manager, JFrog Artifactory or Sonatype Nexus Repository, instead of letting builds reach the internet. Use it whenever one exists, and always on air-gapped deployments. Ask the user or the Domino administrator for the mirror URLs; never guess them. GitLab's package registry does not support Cargo and cannot proxy crates.io.

| Repository manager | Cargo index URL (proxy of `https://index.crates.io`) | Token value |
|---|---|---|
| JFrog Artifactory 7.46.3 or later (remote Cargo repository with sparse index enabled) | `sparse+https://<host>/artifactory/api/cargo/<repo-key>/index/` | `Bearer <identity or access token>` |
| Sonatype Nexus Repository 3.77 or later (Cargo proxy repository; Pro from 3.73) | `sparse+https://<host>/repository/<repo-name>/` | `Basic <base64 of a user token, or of username:password>` |

### Point Cargo at the mirror

Write the configuration once into the environment, so every Workspace, Job and user gets it: in the Dockerfile instructions, after the toolchain install, create `$CARGO_HOME/config.toml` (`/usr/local/cargo/config.toml`). A project can instead commit `.cargo/config.toml`; the project file overrides the environment's.

```toml
[source.crates-io]
replace-with = "mirror"

[registries.mirror]
index = "sparse+https://<host>/artifactory/api/cargo/<repo-key>/index/"
```

Keep the `sparse+` prefix and the trailing slash. `Cargo.lock` still names crates.io, so one lockfile works with and without the mirror. `[source]` settings have no environment-variable form.

### Mirrors that require a token

1. Add the token provider to the same `config.toml`; without it Cargo refuses authenticated registries:

   ```toml
   [registry]
   global-credential-providers = ["cargo:token"]
   ```

2. Store the token as a Domino user environment variable named `CARGO_REGISTRIES_MIRROR_TOKEN` (the registry name in capitals, dashes as underscores), never in a file. Include the scheme from the table: Cargo sends the value unchanged as the `Authorization` header.
3. Declare an authenticated mirror under `[registries.mirror]` as above; a `[source.mirror] registry = ...` entry never receives a token. On Nexus Repository, turn on "Restrict repository content to authenticated users" for the Cargo proxy repository, or Cargo never sends the token.

| Error | Fix |
|---|---|
| `authenticated registries require a credential-provider to be configured` | Add the `[registry]` block |
| `token rejected` ... `the token does not include an authentication scheme` | Start the value with `Bearer ` or `Basic ` |
| `no token found for 'mirror'` | Declare the mirror under `[registries]`, or match the variable name to the registry name |

### The toolchain through the mirror

Proxy `https://static.rust-lang.org` with an anonymously readable generic remote repository (Artifactory) or raw proxy repository (Nexus Repository), and set, in the Dockerfile instructions and as environment variables on the environment:

```dockerfile
ENV RUSTUP_DIST_SERVER=https://<host>/artifactory/<generic-repo-key> \
    RUSTUP_UPDATE_ROOT=https://<host>/artifactory/<generic-repo-key>/rustup
```

No trailing slash on `RUSTUP_DIST_SERVER`; the mirror must use HTTPS. Download `rustup-init` and `rustup-init.sha256` from `$RUSTUP_UPDATE_ROOT/dist/<arch>-unknown-linux-gnu/` instead of `static.rust-lang.org`. The pinned toolchain version also keeps the mirror's cache valid: a version's manifest never changes, while `stable` does. Mirror the nextest and cargo-deny release archives the same way, or install them with `cargo install --locked cargo-nextest cargo-deny` through the Cargo mirror (slower: it compiles them).

### TLS inspection and HTTP proxies

Organizations may add their own root certificates to the system trust store and send outbound traffic through a TLS-inspecting corporate proxy. curl, git, rustup and Cargo read the system store and `HTTPS_PROXY`/`NO_PROXY`, so they work unchanged. Where a tool still reports certificate errors, point it at a complete PEM bundle that includes the organization's root (`CARGO_HTTP_CAINFO`, `GIT_SSL_CAINFO`, `SSL_CERT_FILE` for rustup) rather than turning verification off. `NO_PROXY` must keep in-cluster addresses (`localhost`, `127.0.0.1`, the hosts in `DOMINO_API_HOST` and `DOMINO_API_PROXY`) off the proxy. For git dependencies set `CARGO_NET_GIT_FETCH_WITH_CLI=true`, so git's own proxy and certificate settings apply.

### No mirror: vendor the dependencies

`cargo vendor --locked --respect-source-config` copies every dependency into `vendor/` (tens of MB) and prints the `[source]` lines; save them as the project's `.cargo/config.toml`, commit both, and build with `cargo build --frozen`. Keep any mirror configuration in `$CARGO_HOME/config.toml`, since one file cannot hold two `[source.crates-io]` tables.

### cargo-deny's advisory database

`cargo deny check` clones `https://github.com/rustsec/advisory-db` with git. Point `[advisories] db-urls` in `deny.toml` at an internal mirror of that repository, or run `cargo deny --offline check` against a copy fetched earlier.
