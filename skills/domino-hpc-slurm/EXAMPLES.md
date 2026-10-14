# Slurm job scripts on Domino

Applies to Domino 6.3 and Domino Cloud. Submit each script from the terminal of a Workspace with a Slurm cluster attached ([SKILL.md](./SKILL.md#path-1-a-slurm-cluster-attached-to-a-workspace)), or commit it to the Project and start it as an HPC Job ([API.md](./API.md#start-poll-read-logs-cancel)).

Two rules shape every script here:

- Domino sets `--output` and `--error` on every job to collect the logs into the Job record, so a `#SBATCH --output=` line has no effect. To keep your own copy, redirect inside the script to the shared Dataset. Any other path fails: workers cannot write to the Workspace file system.
- Workers are shared between users and all Domino users are in one Unix group there. `umask 077` at the top of the script keeps output private.

The scripts below use a Dataset named `my-dataset`, at `/domino/datasets/local/my-dataset` in a DFS Project and `/mnt/data/my-dataset` in a Git-based one ([domino-datasets](../domino-datasets/SKILL.md#paths)). Write the real name of a Dataset of the Project instead: `ls $DOMINO_DATASETS_DIR` lists them (`/domino/datasets`, with the Project's own under `local/`, in a DFS Project; `/mnt/data` in a Git-based one). With several Datasets, use the one that holds the inputs or the Project's default (named after the Project), and say which you chose. Never leave `<...>` in a script: unquoted angle brackets are shell redirections, so the file does not parse. Zero nodes in `sinfo` and `PD` in `squeue` on a fresh cluster are normal: Domino provisions workers when jobs enter the queue.

## Array job with one output file per task

```bash
#!/bin/bash
#SBATCH --job-name=hello-cluster
#SBATCH --array=1-3
#SBATCH --nodes=1
#SBATCH --ntasks=1

umask 077
OUTDIR=/domino/datasets/local/my-dataset
OUTFILE="$OUTDIR/output_task_$SLURM_ARRAY_TASK_ID.txt"

{
  echo "Job ID:        $SLURM_JOB_ID"
  echo "Array Job ID:  $SLURM_ARRAY_JOB_ID"
  echo "Array Task ID: $SLURM_ARRAY_TASK_ID"
  echo "Node:          $(hostname)"
  echo "CPUs:          $(nproc)"
  free -h
  df -h "$OUTDIR"                      # proves the Dataset is mounted on the worker
  python3 -c "
import math, time
t = time.time()
print('sum of sqrts', sum(math.sqrt(i) for i in range(1, 10_000_000)))
print('elapsed', round(time.time() - t, 3), 's')
"
} > "$OUTFILE" 2>&1

echo "Task $SLURM_ARRAY_TASK_ID wrote $OUTFILE"   # this line lands in the Domino-collected log
```

```bash
sbatch sample-job.sh            # Submitted batch job 1
squeue                          # 1_[1-3] ... PD (PartitionConfig) while workers come up, then R
sinfo                           # nodes appear as the partition scales
sacct -j 1                      # accounting once the tasks finish
ls /domino/datasets/local/my-dataset/
```

Short jobs can finish before `squeue` shows them running; append `sleep 180` to watch the lifecycle, or submit several times to see jobs queue and dispatch as workers arrive.

## Parameter sweep driven by the task id

```bash
#!/bin/bash
#SBATCH --job-name=sweep
#SBATCH --array=0-9
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00

umask 077
DATA=/domino/datasets/local/my-dataset
read -r LR DEPTH < <(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$DATA/params.txt")   # one "lr depth" line per task
python3 "$DATA/code/train.py" --lr "$LR" --depth "$DEPTH" \
    --out "$DATA/results/run_$SLURM_ARRAY_TASK_ID" > "$DATA/results/run_$SLURM_ARRAY_TASK_ID.log" 2>&1
```

Put the code and the inputs in the Dataset as well: the script runs on a worker, which does not see the Project files of the Workspace. Limit concurrency with `--array=0-99%10` when the sweep is larger than the worker ceiling.

## SMP: one node, several cores

```bash
#!/bin/bash
#SBATCH --job-name=smp
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00

umask 077
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
./simulate --threads "$SLURM_CPUS_PER_TASK" > /domino/datasets/local/my-dataset/smp.log 2>&1
```

`--cpus-per-task` sets cores per task, `--mem` memory per node. The request has to fit inside one worker of the **Worker Hardware Tier** chosen for the cluster; a request larger than the tier never dispatches.

## GPU job

Run the cluster with a GPU worker tier, then request the GPUs in Slurm terms:

```bash
#!/bin/bash
#SBATCH --job-name=gpu-train
#SBATCH --gpus=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00

umask 077
nvidia-smi > /domino/datasets/local/my-dataset/gpu-train.log 2>&1
python3 /domino/datasets/local/my-dataset/code/train.py >> /domino/datasets/local/my-dataset/gpu-train.log 2>&1
```

Through the API the same request is `"config": {"gpu": 1, "cpu": 4, "memory": "32Gi", "walltime": "04:00:00"}` on `POST /api/hpc/v1/jobs`.

## Dependent jobs

```bash
PREP=$(sbatch --parsable prepare.sh)
SWEEP=$(sbatch --parsable --dependency=afterok:$PREP sweep.sh)
sbatch --dependency=afterany:$SWEEP collect.sh
```

`afterok` waits for success, `afterany` for completion in any state, `afternotok` for failure. `--parsable` prints the bare job id, which makes chaining in a shell script safe.

## Command-line options instead of a header

Options on the command line override `#SBATCH` lines in the script, which is the way to reuse one script with different sizes:

```bash
sbatch --job-name=hello_job --time=00:01:00 --cpus-per-task=1 --mem=256M job.sh
```

## Watching and cleaning up

```bash
JOBID=42                                 # from "Submitted batch job 42"
squeue --me                              # your queued and running jobs
scontrol show job "$JOBID"               # the full record while queued or running
sacct -j "$JOBID" --format=JobID,State,Elapsed,MaxRSS,AllocCPUS
sacct --starttime=today                  # your jobs since midnight; broad queries such as sacct -a load the Slurm REST service
scancel "$JOBID"                         # one job
```

Stopping the Workspace releases the worker nodes; the accounting record and the Project's **HPC** tab keep the job history.
