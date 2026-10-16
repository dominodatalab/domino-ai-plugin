# Rust tooling: checks, build profiles, editors and agents

## Lints and formatting

`Cargo.toml` carries the lint policy, so every tool (cargo, rust-analyzer, CI, agents) applies the same rules:

```toml
[lints.rust]
unsafe_code = "forbid"

[lints.clippy]
pedantic = { level = "warn", priority = -1 }
```

- `priority = -1` puts the group below single-lint overrides; without it Clippy's `lint_groups_priority` lint fails the build. To silence one pedantic lint, add it at default priority: `module_name_repetitions = "allow"`.
- In a Cargo workspace, put the tables under `[workspace.lints.*]` and add `[lints] workspace = true` to each member.
- If a dependency's macro emits `#[allow(unsafe_code)]` and the build fails under `forbid`, use `"deny"`.
- `scripts/check.sh` runs Clippy with `-D warnings`, so pedantic warnings fail the gate. Fix them or allow the specific lint with a reason; do not lower the group.
- `rustfmt.toml` sets `style_edition = "2024"`. `cargo fmt` infers it from `Cargo.toml`, but editors run bare `rustfmt`, which defaults to 2015.

## Tests

- `cargo nextest run` runs unit and integration tests in parallel processes. It does not run doctests; `cargo test --doc` covers them, and needs a library target, which is why the template keeps the router in `src/lib.rs`.
- `cargo nextest run --profile ci` keeps going after failures and writes `target/nextest/ci/junit.xml`.
- Test routes in-process with `tower::ServiceExt::oneshot` (see `src/lib.rs`); no port is bound, so tests run beside the IDE and in Jobs.

## Dependency policy (cargo-deny)

`cargo deny check` runs four checks: `advisories` (RustSec vulnerabilities, unmaintained and unsound crates, yanked versions), `licenses`, `bans` (duplicates, wildcard versions) and `sources` (crates.io only). It covers what cargo-audit checks, so one tool is enough.

- It fetches the RustSec database with `git` on each run (offline: [ENVIRONMENT.md](./ENVIRONMENT.md#offline-and-mirrors)).
- A licence failure names the crate and licence. Add the licence to `allow` in `deny.toml` if your organisation accepts it; do not delete the check.
- `cargo deny init` generates an empty licence allowlist that fails immediately; start from the template's `deny.toml` instead.

## Build profiles

| Profile | Command | Use |
|---|---|---|
| dev | `cargo build`, `cargo run`, `cargo check` | Editing and tests: fast incremental builds, debug assertions, overflow checks |
| release | `cargo build --release` | Local performance checks |
| dist | `cargo build --locked --profile dist` (via `scripts/build-dist.sh`) | The binary the App runs |

`dist` inherits `release` (`opt-level = 3`, `panic = "unwind"`) and adds `lto = "fat"`, `codegen-units = 1` and `strip = true`: whole-program optimization and the smallest binary. For the template, a clean `dist` build costs about the same as a plain release build, because compiling dependencies dominates, and fits a 1-core, 4 GiB hardware tier; the binary is about a third smaller. A clean dev build costs about half as much, and later builds are incremental.

- **`panic = "abort"` does not belong in a web server.** With unwinding, a panic in one handler ends that request's task and the server keeps serving; with abort, the process exits and every viewer loses the App until Domino restarts it.
- **Fat LTO's cost grows with the App's own code.** If `dist` builds become slow or run out of memory on the Workspace's hardware tier, switch to `lto = "thin"`, which keeps most of the gain.
- **`strip = true`** removes symbols. Panic messages keep their file and line; backtraces (`RUST_BACKTRACE=1`) show addresses instead of function names. Use `strip = "debuginfo"` (the release default) if you need named frames.
- **`opt-level = 3`** is already the release default.

## CPU-specific builds and PGO (opt-in)

Both help only when profiling shows the App's CPU time in your Rust code (parsing, scoring, serialization), not in waiting on the network or a database. An I/O-bound App gains about nothing. Measure first.

### target-cpu

By default Rust compiles for the baseline of the build node's architecture (x86-64 or aarch64), which every node of that architecture runs. `-C target-cpu` adds newer instructions, and a binary that uses one the App's CPU lacks dies at start with `Illegal instruction` (exit code 132), often before `main` runs. Administrators map hardware tiers to node pools, so tiers can differ in architecture (amd64 or arm64) and in CPU generation, and one tier can mix instance types; the Workspace or Job that builds and the App that runs may land on different ones.

- Never use `native`: it targets the build node's CPU, not the App's.
- Never use `x86-64-v4` (AVX-512): AMD Zen 3 and older nodes, common in GPU node pools, lack it.
- Use `x86-64-v3` (AVX2, FMA, BMI) only when every node in the App's hardware tier supports AVX2 (Intel Haswell or later, any AMD EPYC). Expect 0 to 1 percent for typical web code; TLS and crypto libraries already choose AVX paths at run time.
- On arm64 (AWS Graviton) the ceiling for mixed node generations is `neoverse-n1`.

Build with an explicit target, so build scripts and proc macros stay generic and `build-dist.sh` finds the output under `target/<triple>/`:

```bash
CARGO_BUILD_TARGET=x86_64-unknown-linux-gnu RUSTFLAGS="-C target-cpu=x86-64-v3" bash scripts/build-dist.sh
```

`RUSTFLAGS` replaces any `rustflags` in `.cargo/config.toml` rather than adding to them. The stamp records the flags. A check inside the binary cannot protect it (`is_x86_feature_detected!` is always true for features enabled at compile time, and the crash can come first), so add this guard to `app.sh`, before the `exec`:

```bash
if [ "$(uname -m)" = x86_64 ]; then
  flags=" $(grep -m1 '^flags' /proc/cpuinfo | cut -d: -f2) "
  for f in avx avx2 bmi1 bmi2 f16c fma abm movbe xsave; do
    case $flags in *" $f "*) ;; *) echo "app.sh: this CPU lacks $f; rebuild without -C target-cpu" >&2; exit 1 ;; esac
  done
fi
```

### Profile-guided optimization (PGO)

PGO compiles an instrumented binary, records which code real traffic exercises, and recompiles using that profile. On the template it cut user CPU per request by about a fifth (total CPU about 7 percent, since most time is in the kernel) at roughly twice the build time; request throughput did not change measurably. Use it when the App is CPU-bound in Rust code.

- Requires Rust 1.100 or later on x86_64 Linux: on 1.99 merging the profile fails (rust-lang/rust#163616). Upgrade the environment and `rust-toolchain.toml` first.
- If the dependency tree compiles C (aws-lc-sys and ring do), run `cargo update -p cc` so the `cc` crate is 1.8.0 or later; older versions pass PGO flags to the C compiler and the instrumented binary can crash.

Steps, in a Workspace on the App's environment:

1. `rustup component add llvm-tools` and `cargo install --locked cargo-pgo`.
2. `cargo pgo build -- --locked --profile dist` builds `target/x86_64-unknown-linux-gnu/dist/<name>` with instrumentation.
3. Run it beside the IDE (`PORT=8711 target/x86_64-unknown-linux-gnu/dist/<name>`), send it traffic shaped like production (real routes and payloads, production `RUST_LOG`), then stop it with Ctrl-C or SIGTERM. SIGKILL leaves an empty profile.
4. `cargo pgo optimize build -- --locked --profile dist` merges the profile into `target/pgo-profiles/merged-<hash>.profdata` and builds with it. Copy that file to `pgo/merged.profdata` and commit it (a few MB); `scripts/stamp.sh` includes `pgo/`.
5. Build the shipping binary from the committed profile:

   ```bash
   CARGO_BUILD_TARGET=x86_64-unknown-linux-gnu \
   RUSTFLAGS="-Cprofile-use=$PWD/pgo/merged.profdata -Cllvm-args=-pgo-warn-missing-function" \
   bash scripts/build-dist.sh
   ```

Regenerate the profile after every toolchain upgrade (the profile format follows the toolchain's LLVM), after dependency updates and after changes to hot code. rustc warns `function control flow change detected` for stale functions in your crate but stays silent about dependencies. A missing profile file fails the build.

## target/ and disk

- One project's `target/` reaches 0.5 to 1 GB after dev, Clippy and dist builds. Workspace volumes default to 10 GiB and Job volumes can be smaller; run `cargo clean` when space runs low, or `cargo clean --profile dist` to drop only the shipping build.
- The template keeps full debug info for your crate and drops it for dependencies (`[profile.dev.package."*"] debug = false`), which cuts `target/` by about a third while keeping your code debuggable.
- `target/` stays in the project directory, which persists across Workspace restarts, so incremental builds survive. Never point `CARGO_TARGET_DIR` at a Dataset: builds on network storage are slow and the build lock is unreliable there.
- `.gitignore` excludes `target/`; in DFS Projects `.dominoignore` must too. `.vscode/settings.json` excludes it from the file watcher, which otherwise exhausts the Workspace's watcher limit.

## Editors

| Editor | Rust language server |
|---|---|
| VS Code in a Workspace | The `rust-lang.rust-analyzer` extension from Open VSX (the environment installs it; [ENVIRONMENT.md](./ENVIRONMENT.md)). `.vscode/settings.json` runs Clippy on save and formats on save |
| VS Code, Cursor or Zed over SSH | Runs on the Workspace; needs the toolchain and `rust-analyzer` there. Connect with the Domino CLI ([domino-workspaces](../domino-workspaces/SKILL.md)) |
| RustRover over SSH | Uses its own engine; needs the toolchain on the Workspace |
| JupyterLab, RStudio | No practical Rust support; use a VS Code Workspace |

rust-analyzer finds `Cargo.toml` in the opened folder or one level below. If the crate sits deeper, set `"rust-analyzer.linkedProjects": ["path/to/Cargo.toml"]`.

## Coding agents

| Agent | Language server | Checks after edits and at the end of a turn |
|---|---|---|
| Claude Code | Install the `rust-analyzer-lsp` plugin from the `claude-plugins-official` marketplace (`claude plugin install rust-analyzer-lsp@claude-plugins-official`); it starts `rust-analyzer` from `PATH` and reports diagnostics after each edit | `.claude/settings.json` hooks (below) |
| Cursor | The editor's rust-analyzer; the agent reads its diagnostics | Reads `.claude/settings.json` hooks, or `.cursor/hooks.json` (use one, not both) |
| GitHub Copilot CLI | `.github/lsp.json` with `{"lspServers": {"rust-analyzer": {"command": "rust-analyzer", "fileExtensions": {".rs": "rust"}}}}` (navigation only) | Reads `.claude/settings.json` hooks |
| Codex | No language server support; read `cargo clippy` output | `.codex/hooks.json` (the project must be trusted and each hook approved in `/hooks`) |
| Gemini CLI | No language server support; read `cargo clippy` output | `.gemini/settings.json`, timeouts in milliseconds |
| OpenCode | Set `"lsp": true` in `opencode.json`; it uses `rust-analyzer` from `PATH` | No end-of-turn hook; rely on Git hooks |

## Hooks

`scripts/agent-hooks/rust_fmt.py` formats after an agent edits a `.rs` file; `scripts/agent-hooks/rust_gate.py` runs Clippy and the tests when the agent ends its turn and sends it back once if they fail. Both need only `python3` and `cargo`. Set a timeout on every hook: some agents treat a timed-out hook as passed.

`.claude/settings.json` (Claude Code; Cursor and Copilot CLI read it too):

```json
{
  "hooks": {
    "PostToolUse": [{ "matcher": "Edit|Write", "hooks": [{ "type": "command", "timeout": 120,
      "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/agent-hooks/rust_fmt.py\"" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "timeout": 900,
      "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/agent-hooks/rust_gate.py\"" }] }]
  }
}
```

`.codex/hooks.json` (Codex):

```json
{
  "hooks": {
    "PostToolUse": [{ "matcher": "^apply_patch$", "hooks": [{ "type": "command", "timeout": 120,
      "command": "python3 \"$(git rev-parse --show-toplevel)/scripts/agent-hooks/rust_fmt.py\"" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "timeout": 900,
      "command": "python3 \"$(git rev-parse --show-toplevel)/scripts/agent-hooks/rust_gate.py\"" }] }]
  }
}
```

`.gemini/settings.json` (Gemini CLI; write it by hand, because `gemini hooks migrate` copies second-based timeouts into a millisecond field):

```json
{
  "hooks": {
    "AfterTool": [{ "matcher": "write_file|replace", "hooks": [{ "name": "rust-fmt", "type": "command", "timeout": 120000,
      "command": "python3 \"$GEMINI_PROJECT_DIR/scripts/agent-hooks/rust_fmt.py\"" }] }],
    "AfterAgent": [{ "hooks": [{ "name": "rust-gate", "type": "command", "timeout": 900000,
      "command": "python3 \"$GEMINI_PROJECT_DIR/scripts/agent-hooks/rust_gate.py\"" }] }]
  }
}
```

Git hook (Git-based Projects; once per clone): `git config core.hooksPath .githooks`. `.githooks/pre-commit` runs fmt, Clippy and nextest. A new Workspace clones the repository again, so run the `git config` line in each new Workspace. Agents can bypass Git hooks with `--no-verify`; treat them as a backstop behind the agent hooks.
