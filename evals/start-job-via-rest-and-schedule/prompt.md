---
description: "Jobs: POST /api/jobs/v1/jobs with runCommand, poll GET /api/jobs/beta/jobs/{jobId}; scheduled jobs have no public route, only the labelled internal /v4 scheduledjobs route or the UI."
tags: [trigger, domino-jobs, jobs]
max_turns: 12
allowed_tools: [Read, Glob, Grep, Skill]
---

From inside my Domino workspace, write Python that starts a job running `python train.py --epochs 5`
in the current project through the REST API and polls until it finishes. Then: can I also create the
nightly schedule for it through the public API? Put the code in your reply, not in files.
