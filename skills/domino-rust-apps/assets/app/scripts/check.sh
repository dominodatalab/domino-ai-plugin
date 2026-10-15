#!/usr/bin/env bash
# Every gate, in the order that fails fastest. Run it before each commit and before build-dist.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
cargo fmt --all --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo nextest run --locked --all-features
cargo test --locked --doc --all-features   # nextest does not run doctests
cargo deny check                           # fetches the RustSec advisory database; add --offline to use the cached copy
