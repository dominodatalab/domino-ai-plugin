---
type: llm
---

PASS if the reply tells the user (1) to build the site once with `proa build` in a Workspace or Job, directly or
through a build script that runs it (not with plain `cargo build`), (2) that the Proa CLI used for that build comes from the same Proa commit or release as the Proa
crates in `Cargo.toml`, and (3) that the App then runs the prebuilt binary through `app.sh` without compiling.
FAIL if it tells the user to compile in `app.sh`, or says the crates.io 0.3.0 Proa crates the scaffold names work as
they are.
