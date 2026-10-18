---
description: "Proa on Domino: a site from the Proa CLI is made ready to publish: Proa crates pinned to one commit, PROA_BASE_PATH from DOMINO_RUN_HOST_PATH in app.sh, built once with proa build."
tags: [trigger, domino-rust-apps, apps, rust, proa]
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

I made this website with Proa (https://proa.so), using `proa new` with the minimal template. I want to run it
as a Domino App in our Git-based Project. Make the changes the project needs, including the App's `app.sh`, and
tell me how to build it and publish it.
