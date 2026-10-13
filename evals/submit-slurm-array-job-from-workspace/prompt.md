---
description: "HPC Slurm: a parameter sweep as a Slurm array job from a Domino Workspace with a Slurm cluster attached; output goes to the Dataset, submit and monitor with sbatch, squeue and sacct."
tags: [trigger, domino-hpc-slurm, clusters]
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

I have a Domino Workspace with a Slurm cluster attached. Write me a job script that runs
`python3 simulate.py --seed N` for N = 1 to 10 as a Slurm array job on Domino and keeps each
task's output where I can read it afterwards from the Workspace, then tell me how to submit it and
how to check on it while it runs and after it finishes. Put the script and the commands in your
reply, not in files.
