# Apache Airflow and Domino Jobs

Use this when an existing Airflow deployment owns the schedule. Otherwise orchestrate inside
Domino: [domino-flows](../domino-flows/SKILL.md) for multi-step pipelines, a scheduled Job
([domino-jobs](../domino-jobs/SKILL.md)) for one recurring script.

Sources: https://docs.domino.ai/cloud/platform-capabilities/features/integrations (Airflow tab),
python-domino `domino/airflow/_operator.py`, `domino/authentication.py`, `domino/routes.py`,
`setup.py`, `README.md` and `examples/example_airflow_dag.py` at `Release-2.2.0` / `master`
(https://github.com/dominodatalab/python-domino), Airflow constraint files 3.3.2 and 2.11.2.
Parameter names below are exact.

## Credentials on a worker

Outside Domino there is no API proxy and no access-token sidecar. The worker needs:

| Variable | Value |
|---|---|
| `DOMINO_API_HOST` | the deployment URL users open in a browser (python-domino reads the same variable) |
| `DOMINO_TOKEN_FILE` | path to a file whose first line is a Personal Access Token or service-account token created in Domino; the worker mounts it from Airflow's own secret mechanism, since Domino Project and user environment variables are not readable outside Domino |

Airflow Variables are fine for the host; keep the token out of Variables unless the Variable is
backed by a secrets backend. Legacy API keys (`DOMINO_USER_API_KEY`, `X-Domino-Api-Key`) are
deprecated even though python-domino's `example_airflow_dag.py` still uses one.

## Recommended: a task on the Public Jobs API

Needs only `requests` (already an Airflow dependency), honours Airflow's constraints, runs on
Airflow 2 and 3, and fails the task on every outcome other than `Succeeded`.

```python
from datetime import datetime
from airflow import DAG
from airflow.decorators import task

@task
def run_domino_job(run_command: str, project_id: str, title: str = "airflow") -> str:
    import os, time, requests
    base = os.environ["DOMINO_API_HOST"].rstrip("/")
    headers = {"Authorization": "Bearer " + open(os.environ["DOMINO_TOKEN_FILE"]).readline().strip()}
    body = {"projectId": project_id, "runCommand": run_command, "title": title}
    # optional: "environmentId", "hardwareTier" (tier id, e.g. small-k8s), "mainRepoGitRef", "computeCluster"
    r = requests.post(f"{base}/api/jobs/v1/jobs", headers=headers, json=body, timeout=60)
    r.raise_for_status()
    job = r.json()["job"]
    while not job["status"]["isCompleted"]:
        time.sleep(30)
        job = requests.get(f"{base}/api/jobs/beta/jobs/{job['id']}", headers=headers, timeout=60).json()["job"]
    state = job["status"]["executionStatus"]                     # Succeeded | Failed | Error | Stopped
    if state != "Succeeded":
        logs = requests.get(f"{base}/api/jobs/beta/jobs/{job['id']}/logs", headers=headers,
                            params={"logType": "stdErr", "limit": 200}, timeout=60).json()
        raise RuntimeError(f"Domino job {job['id']} ended {state}: {logs['logs']['logContent'][-20:]}")
    return job["commitDetails"]["outputCommitId"]

with DAG("churn_pipeline", start_date=datetime(2026, 1, 1), schedule="0 2 * * *", catchup=False):
    prepared = run_domino_job.override(task_id="prepare_data")("python prepare.py {{ ds }}", "<project id>")
    trained = run_domino_job.override(task_id="train")("python train.py {{ ds }}", "<project id>")
    prepared >> trained
```

The return value (the Job's output commit id) is the task's XCom; a downstream task can pass it
as `commitId` on a DFS project or read a result file with
`GET /api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content`. `{{ ds }}` is
rendered because `op_args` of a `@task` are templated. Polling, logs and result hand-off:
[JOBS-API-PATTERN.md](./JOBS-API-PATTERN.md).

## python-domino operators

The product page documents both integrations through python-domino, so the operators are the
documented route; they come with the constraints below.

### Install

`dominodatalab` 2.2.0 (`setup.py`) pins `packaging==23.2`, `python-dateutil~=2.8.2`,
`typing-extensions~=4.13`, `beautifulsoup4~=4.11`, `polling2~=0.5.0`, `frozendict~=2.3`,
`retry==0.9.2`. Airflow's constraint files pin `packaging==26.3` and `python-dateutil==2.9.0.post0`
(3.3.2; `packaging==26.0` in 2.11.2); their `typing_extensions` 4.16.0 and 4.15.0 satisfy
`~=4.13`, so `packaging` and `python-dateutil` are the conflicts. Consequences:

- `pip install -c constraints-<version>.txt dominodatalab`, the install method Airflow documents
  and managed Airflow services enforce, does not resolve.
- `pip install dominodatalab` without constraints downgrades `packaging` and `python-dateutil`
  under a running Airflow.

Options, in order of preference: the Public API task above (no python-domino); a worker image
with its own virtual environment where Airflow was installed without constraints and these
pins are accepted; `PythonVirtualenvOperator` with `requirements=["dominodatalab"]` to call the
python-domino client in an isolated environment per task (client usage:
[domino-python-sdk](../domino-python-sdk/SKILL.md)). Never use the `dominodatalab[airflow]`
extra on an existing Airflow: it pins `apache-airflow==2.2.4`.

Both operators import `airflow.utils.decorators.apply_defaults`, a deprecated no-op in Airflow 2
that Airflow 3.0 removed, so `from domino.airflow import DominoOperator` raises `ImportError`
on Airflow 3.

### Auth precedence (`domino/authentication.py`)

`api_proxy` > `auth_token` > `domino_token_file` > `api_key` > env `DOMINO_API_PROXY` > env
`DOMINO_TOKEN_FILE` > env `DOMINO_USER_API_KEY`. The host comes from `host` or env
`DOMINO_API_HOST`. The operators expose `host`, `api_key` and `domino_token_file` only, so a
token goes in through `domino_token_file` (the client re-reads the file on every request, so
rotating the token in place needs no restart) or the `DOMINO_TOKEN_FILE` environment variable.

### `DominoOperator`

```python
from domino.airflow import DominoOperator
```

Runs through `runs_start_blocking` on the **legacy v1 Runs API** (`/v1/projects/{owner}/{project}/runs`,
`/v1/projects/{owner}/{project}/run/{id}/stdout`; not in the Public API, absent from the
cluster's internal reference too; non-public route, may change in a future Domino version). python-domino's README:
"Use `job_start` for all new development. `runs_start` is retained for backwards compatibility."

| Parameter | Type / default | Meaning |
|---|---|---|
| `project` | `str`, required | `owner/project-name` |
| `command` | `List[str]`, required | file to run first, then arguments; templated |
| `host` | `str`, `None` | deployment URL; else env `DOMINO_API_HOST` |
| `api_key` | `str`, `None` | legacy API key; do not use |
| `domino_token_file` | `str`, `None` | path to a file holding a Bearer token |
| `isDirect` | `bool`, `None` | run `command[0]` as a shell command; must then be a single element |
| `commitId` | `str`, `None` | DFS commit to run from (not a git SHA on a Git-based project) |
| `title` | `str`, `None` | Job title; templated |
| `tier` | `str`, `None` | hardware tier **name**; checked against `hardware_tiers_list()` (`/v4/projects/{id}/hardwareTiers`, non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types)) before start |
| `publishApiEndpoint` | `bool`, `None` | republish the project's endpoint after the Job |
| `poll_freq` | `int`, `5` | seconds between status polls |
| `max_poll_time` | `int`, `6000` | seconds before the task fails (the Job keeps running) |
| `startup_delay` | `int`, `10` | seconds to sleep before starting |
| `include_setup_log` | `bool`, `True` | prefix the replayed log with the Job's setup log |

Behaviour (`execute`): builds `Domino(project, api_key, host, domino_token_file)` (which calls
`/version`), validates `tier`, sleeps `startup_delay`, calls `runs_start_blocking(...)`, then
`get_run_log(run_id, include_setup_log)` and `process_log(log)` into the task log. Returns the
start response (a dict with `runId`) as the XCom value. `runs_start_blocking` waits for an
output commit and then raises `RunFailedException` unless the run `status` is `Succeeded`;
exceeding `max_poll_time` raises too. So this operator fails on any non-success.

### `DominoSparkOperator`

```python
from domino.airflow import DominoSparkOperator
```

Runs through `job_start_blocking` on the v4 Jobs API (`/v4/jobs/start`, `/v4/jobs/{id}`;
**non-public route; may change in a future Domino version**). Despite the name it is the operator for
**any** Job that needs an explicit environment or a compute cluster.

Same `project`, `host`, `api_key`, `domino_token_file`, `poll_freq`, `max_poll_time`,
`startup_delay`, plus:

| Parameter | Type / default | Meaning |
|---|---|---|
| `command` | `str`, required | one string, for example `"main.py arg1 arg2"`; templated |
| `commit_id` | `str`, `None` | as above |
| `hardware_tier_name` | `str`, `None` | hardware tier name (python-domino resolves it to an id) |
| `environment_id` | `str`, `None` | environment id; default is the project's |
| `compute_cluster_properties` | `dict`, `None` | `{"clusterType": "Spark" \| "Ray" \| "Dask" \| "MPI", "computeEnvironmentId", "computeEnvironmentRevisionSpec"?, "masterHardwareTierId" (not for MPI), "workerCount", "workerHardwareTierId", "workerStorage"?: {"value", "unit": "GiB" \| "MB"}, "maxWorkerCount"?}`; cluster environments and sizing: [domino-distributed-computing](../domino-distributed-computing/SKILL.md) |
| `on_demand_spark_cluster_properties` | `dict`, `None` | deprecated; ignored when `compute_cluster_properties` is set |

Behaviour: returns the final Job object (`id`, `statuses.executionStatus`, `statuses.isCompleted`,
`commitDetails`, ...). **It raises `RunFailedException` only when `executionStatus` is `Failed`**
(`domino.py`, `job_start_blocking`). The completed-status values are `Succeeded`, `Failed`,
`Error` and `Stopped`, so a Job that ended `Error` (a setup failure, for example) or was stopped
returns normally and the Airflow task succeeds. Subclass it:

```python
from airflow.exceptions import AirflowException
from domino.airflow import DominoSparkOperator

class StrictDominoSparkOperator(DominoSparkOperator):
    """Fail on Error and Stopped too; DominoSparkOperator raises only on Failed."""
    def execute(self, context):
        job = super().execute(context)
        state = job["statuses"]["executionStatus"]
        if state != "Succeeded":
            raise AirflowException(f"Domino job {job['id']} ended {state}")
        return job
```

### DAG with the operators

```python
from datetime import datetime
from airflow import DAG
from airflow.models import Variable
from domino.airflow import DominoOperator

HOST = Variable.get("DOMINO_API_HOST")           # https://<deployment>
TOKEN_FILE = "/var/run/secrets/domino/token"     # mounted secret, first line = PAT or SA token

with DAG("churn_pipeline", start_date=datetime(2026, 1, 1), schedule="0 2 * * *", catchup=False) as dag:
    prepare = DominoOperator(
        task_id="prepare_data",
        project="acme/churn",
        host=HOST, domino_token_file=TOKEN_FILE,
        command=["prepare.py", "{{ ds }}"],
        tier="Small",
        max_poll_time=3600,
    )
    train = StrictDominoSparkOperator(            # the subclass above
        task_id="train_on_spark",
        project="acme/churn",
        host=HOST, domino_token_file=TOKEN_FILE,
        command="train.py {{ ds }}",
        environment_id="<spark-enabled environment id>",
        hardware_tier_name="Medium",
        compute_cluster_properties={
            "clusterType": "Spark",
            "computeEnvironmentId": "<spark cluster environment id>",
            "masterHardwareTierId": "<tier id>",
            "workerHardwareTierId": "<tier id>",
            "workerCount": 4,
        },
        max_poll_time=4 * 3600,
    )
    prepare >> train
```

`{{ ds }}` renders because `command` and `title` are template fields. Data moves between the
two Jobs through the Domino project (results committed by the first Job are the input commit of
the second) or through a Dataset.

## Result delivery

Domino delivers results itself, so start there: the Job's success email carries the last lines of
output and up to ten result files (`.dominoresults` and `email.html` shape them; a scheduled Job's
**Notify emails** field lists the recipients), and the scoring Job can write straight to the
warehouse or bucket through a Data Source (`domino-data-sdk`). Add an Airflow delivery task only
when Airflow already owns the downstream load.

Airflow can also run **after** a Domino scheduled Job finished elsewhere: a sensor-style task
lists Jobs (`GET /api/jobs/beta/jobs?projectId=...&statusFilter=completed`), downloads the newest
result file with the files route above, then delivers it (email, S3, a warehouse load). The
batch-scoring page on docs.domino.ai names this as the way to automate result delivery; the
scoring Job itself, its schedule and its result files:
[domino-model-delivery](../domino-model-delivery/BATCH-SCORING.md).
