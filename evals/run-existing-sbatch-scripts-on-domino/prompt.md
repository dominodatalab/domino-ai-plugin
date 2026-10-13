---
description: "Disambiguation: a pile of existing sbatch scripts from a university HPC cluster is a domino-hpc-slurm request; domino-distributed-computing (Spark, Ray, Dask, MPI) must not fire."
tags: [disambiguation, domino-hpc-slurm, domino-distributed-computing]
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

Our group has a pile of sbatch scripts from the university HPC cluster: parameter sweeps and a
few Monte Carlo ensembles, nothing MPI. We now have Domino. What do we need in place, and how do
we run those scripts on Domino with as little change as possible? Keep it to the essentials.
