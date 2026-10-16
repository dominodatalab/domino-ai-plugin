---
type: llm
---

PASS if the reply tells the user (1) that the Rust toolchain must be in the Project's Compute Environment (or
gives the environment build steps), and (2) that the binary is built once in a Workspace or Job and saved,
after which the App (Preview and deployments) runs that prebuilt binary through app.sh without compiling.
FAIL if it tells the user to compile with cargo inside app.sh, or never mentions how the toolchain gets into
the environment.
