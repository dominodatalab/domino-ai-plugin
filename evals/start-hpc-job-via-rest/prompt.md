---
description: "HPC Slurm: start an HPC Job with POST /api/hpc/v1/jobs (filePath relative to the Project root, dataPlaneId, config.walltime), find it in the list, poll its status and page its logs; no standard Jobs route, no invented SDK method, no legacy API key."
tags: [trigger, domino-hpc-slurm, rest]
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

Our Domino admin enabled HPC Job submission. From Python running inside a Domino Workspace, start
the Slurm script `hpc/sweep.sh` that is committed in this Project as an HPC Job on data plane
`6a17175ab03cb818f0f9c25f` with 4 CPUs and a two-hour wall time, then show how to find the new
job, wait for it to finish, and print its logs. Use the REST API. Put the code in your reply, not
in files.
