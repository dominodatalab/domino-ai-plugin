---
name: domino-hpc-slurm
description: Run Slurm HPC batch workloads on Domino - a Slurm cluster attached to a Workspace (sbatch, squeue, sacct, scancel, array and dependent jobs, a Dataset as the shared file system) and HPC Jobs over /api/hpc/v1/jobs (start, list, details, logs, cancel). Covers the Slurm-enabled data plane, client and worker environments, worker tiers, finding them by API, submit-supported, output paths, limits and troubleshooting. Use for existing sbatch scripts, parameter sweeps, simulations and ensembles on Domino; Spark, Ray, Dask and Open MPI clusters are domino-distributed-computing.
compatibility: Domino 6.3 and Domino Cloud. Requires DOMINO_API_HOST; in a run use DOMINO_API_PROXY or the localhost:8899 access-token endpoint, outside a run a Personal Access Token.
---

# Domino HPC with Slurm

Applies to Domino 6.3 and Domino Cloud.

A Slurm-enabled data plane runs one persistent Slurm cluster shared by all users; workers are provisioned per Workspace, from zero, and autoscaled with the queue. A Workspace with a Slurm cluster attached is the login node, with the Slurm CLI configured, so existing `sbatch` scripts run unchanged. Spark, Ray, Dask and MPI get an ephemeral cluster per execution instead ([domino-distributed-computing](../domino-distributed-computing/SKILL.md)). Pick Slurm for batch work already written as Slurm scripts or that fits the batch model (simulations, ensembles, sweeps, R `mirai` or `clustermq`).

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/compute-clusters-hpc/slurm and `/cloud/admin/infrastructure-and-compute/administer-slurm` (same paths under `/6.3/`).

## Prerequisites

1. A data plane with Slurm installed; the administrator enables it when the data plane is deployed, never afterwards.
2. Two environments the administrator creates ([domino-environments](../domino-environments/SKILL.md)): the **Workspace environment** with the Slurm CLI (`quay.io/domino/domino-slurm-environment:<tag>`, Supported Clusters none) and the **cluster environment** for the workers (`quay.io/domino/slurm-cluster-environment:<tag>`, Supported Clusters **Slurm**).
3. A worker hardware tier on that data plane (one per workload profile: CPU, big memory, GPU).
4. A Dataset on that data plane ([domino-datasets](../domino-datasets/SKILL.md)): the shared file system for scripts, inputs and outputs, since Slurm copies no files between the Workspace and the workers (`/domino/datasets/local/<name>` in a DFS Project, `/mnt/data/<name>` in a Git-based one).

Usernames become Slurm users and have to be valid Linux usernames (`^[a-z_][a-z0-9_-]{0,31}`, not `root`, `daemon`, `nobody`), or the launch fails for that user.

By API ([API.md](./API.md#find-the-data-plane-environments-and-tiers)): environments carry `supportedClusters` (`Slurm` on the worker one), hardware tiers `dataPlaneName` and `computeClusterRestrictions.restrictToSlurm`, data planes (internal list) `status.supportsSlurm`; `GET /api/hpc/v1/jobs/submit-supported?projectId=&dataPlaneId=` says whether API submission works.

## Path 1: a Slurm cluster attached to a Workspace

**Workspaces > + Create New Workspace** ([domino-workspaces](../domino-workspaces/SKILL.md)): the Slurm Workspace environment, a tier on the Slurm-enabled data plane (the Dataset shows under **Datasets available**), then **Compute Cluster** = **Slurm** with **Worker Hardware Tier**, **Max Number of Workers** (the partition ceiling) and **Cluster Compute Environment**. By API: `computeClusterConfig` with `"clusterType": "Slurm"`, no master tier ([domino-workspaces API.md](../domino-workspaces/API.md#attach-a-cluster)).

In the Workspace terminal:

| Command | Purpose |
|---|---|
| `sinfo` | partitions and nodes; zero nodes when idle is normal |
| `sbatch job.sh` | submit; prints `Submitted batch job <id>` |
| `squeue -j <id>` | `PD` pending (workers provisioning), `R` running; empty = done |
| `scontrol show job <id>`, `sacct -j <id>` | details while queued or running; accounting after completion (filter by job, user or time, never `sacct -a`) |
| `scancel <id>` | cancel |

Resource requests go in `#SBATCH` header lines or as `sbatch` options, which override the header (`sbatch --time=00:10:00 --cpus-per-task=4 --mem=4G job.sh`). Arrays: `--array=0-9` plus `$SLURM_ARRAY_TASK_ID` in each task's output path. Dependencies: `--dependency=afterok:<id>` (`afterany`, `afternotok`). Domino overrides `--output` and `--error` to collect the logs, so redirect inside the script to the Dataset; workers neither read nor write the Workspace files, so code and inputs live in the Dataset too.

```bash
#!/bin/bash
#SBATCH --job-name=sweep
#SBATCH --array=1-3
umask 077        # workers and their Unix group are shared between users
D=/domino/datasets/local/<dataset>
{ echo "task $SLURM_ARRAY_TASK_ID on $(hostname)"; python3 "$D/run.py" "$SLURM_ARRAY_TASK_ID"; } > "$D/sweep_$SLURM_ARRAY_TASK_ID.txt" 2>&1
```

Stopping the Workspace releases its workers; the accounting record outlives both.

## Path 2: HPC Jobs through the API

The **HPC** tab on the Project's Jobs page lists every HPC Job, however submitted. Its **Run** button and the API below need the `ShortLived.EnableHPCJobs` feature flag, set by the administrator; `sbatch` in a Workspace needs no flag.

| Route | Notes |
|---|---|
| `POST /api/hpc/v1/jobs` | `projectId`, `filePath`, `dataPlaneId`; optional `title`, `mainRepoGitRef`, `config` (`cpu`, `gpu`, `memory`, `nodes`, `ntasks`, `walltime` `HH:MM:SS`); 202, no body |
| `GET /api/hpc/v1/jobs?projectId=` | `offset`, `limit`, `sortBy`, `ascending`, `statusFilter` |
| `GET /api/hpc/v1/jobs/{jobId}` | `status` (`Submitted`, `Running`, `Completed`, `Failed`, `Cancelled`, `TimedOut`), `requestedResources`, `usage`, `stageTime`, `script` |
| `GET /api/hpc/v1/jobs/{jobId}/logs` | `limit`, `latestTimeNano`, `logType`; page until `logset.isComplete` |
| `POST /api/hpc/v1/jobs/cancel` | `{"jobId"}`; 204 |

`filePath` is relative to the Project root and runs from the latest commit (or `mainRepoGitRef`), never from a Dataset; a path missing from that commit is refused with 403. The partition is chosen for you. The start response carries no id: list with `sortBy=number&limit=1` for the new Job. `python-domino` has no HPC methods. Code and error shapes: [API.md](./API.md#start-poll-read-logs-cancel).

```python
import os, requests
base = os.environ["DOMINO_API_PROXY"]
body = {"projectId": os.environ["DOMINO_PROJECT_ID"], "filePath": "hpc/sweep.sh",
        "dataPlaneId": "<data plane id>", "config": {"cpu": 4, "walltime": "02:00:00"}}
requests.post(f"{base}/api/hpc/v1/jobs", json=body).raise_for_status()
```

## Limitations

- The cluster attaches at Workspace launch; a standard Job cannot carry a Slurm cluster (ignore `slurm` in the Jobs API's `clusterType` enum); submit through `/api/hpc/v1/jobs`.
- Workers reach Datasets only: no Data Sources, no NetApp Volumes.
- No interactive or scheduled Slurm jobs; no external, customer-managed Slurm clusters.
- Jobs of different users share worker nodes and one Unix group, unsandboxed: `umask 077` for sensitive output.

## Troubleshooting

- **Slurm option disabled in the launcher**: no environment with Supported Clusters **Slurm** is visible to you, or the chosen tier's data plane has no Slurm; standard Jobs never offer it.
- **Output files missing**: `--output` and `--error` are overridden; redirect inside the script to a Dataset path that exists on the workers.
- **Jobs stay `PD`**: a cold cluster is provisioning; if nothing ever dispatches, the request exceeds the worker tier or **Max Number of Workers**, or a Slurm scheduling limit applies (ask the administrator).

## Reference files

- [API.md](./API.md): discovery, start, poll, logs, cancel, errors, the Workspace cluster body.
- [EXAMPLES.md](./EXAMPLES.md): array, sweep, SMP, GPU and dependency scripts.
