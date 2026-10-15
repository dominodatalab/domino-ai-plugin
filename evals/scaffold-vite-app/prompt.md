---
description: "Vite Apps: an existing Vite React app is made publishable with an app.sh that serves a build made once, never installing or building at start."
tags: [trigger, domino-app-init, domino-apps, apps, vite]
max_turns: 40
timeout_seconds: 600   # without a shell the model writes each template file itself
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

This folder has a React dashboard I made with Vite. Get it ready to publish as a Domino App in our Git-based
Project. It will call one of our model endpoints, so give it a small backend route for that. Tell me what I need
to do in Domino before I publish it, and how I'd roll back if a release goes wrong.
