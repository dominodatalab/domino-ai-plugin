---
description: "Rust Apps: a new Rust web service is scaffolded with a pinned toolchain, strict lints and an app.sh that runs a prebuilt binary instead of compiling."
tags: [trigger, domino-rust-apps, apps, rust]
max_turns: 40
timeout_seconds: 600   # without a shell the model writes each template file itself
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

Set up a new Rust web service in this folder that I can publish as a Domino App. It should show a simple
status page and a JSON health check. We care a lot about correctness here, so use strict linting and a
pinned toolchain. Tell me what I need to do in Domino before I can publish it.
