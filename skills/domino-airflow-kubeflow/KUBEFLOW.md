# Kubeflow Pipelines and Domino Jobs

Sources: https://docs.domino.ai/cloud/platform-capabilities/features/integrations (Kubeflow tab),
KFP v2 component documentation on kubeflow.org, the `kfp-kubernetes` README. Domino ships no
Kubeflow-specific package; the integration is "install a client in the component and call the
Domino API", which is what the product page describes (it names `dominodatalab`; `requests`
alone is enough for the Public API and is what the examples below use).

## Architecture

Kubeflow Pipelines runs in its own Kubernetes cluster, separate from Domino. Each pipeline step
that needs Domino runs as a pod that must reach the Domino deployment URL over the network and
present a Bearer token. The step's code is thin: start a Job, wait, return what the next step
needs. The real work is the Domino Job, versioned in the Domino project.

## Credentials

Create a Kubernetes Secret in the namespace where the pipeline's pods run (in multi-user KFP
that is the user's profile namespace, not `kubeflow`) holding a Personal Access Token or a
service-account token, not a legacy API key (the product page still mentions one). The token is
created in Domino; the Secret is the pipeline's own copy, because its pods cannot read Domino
Project or user environment variables:

```bash
kubectl -n <pipeline namespace> create secret generic domino-token --from-literal=token='<PAT or service-account token>'
```

Expose it to the task as an environment variable with `kfp-kubernetes`:

```bash
pip install "kfp[kubernetes]"
```

```python
from kfp import kubernetes
kubernetes.use_secret_as_env(task, secret_name="domino-token", secret_key_to_env={"token": "DOMINO_TOKEN"})
```

## Components on the Public API

```python
from kfp import dsl, kubernetes

@dsl.component(base_image="python:3.11", packages_to_install=["requests"])
def run_domino_job(domino_url: str, project_id: str, run_command: str,
                   environment_id: str = "", hardware_tier: str = "") -> str:
    """Start a Domino Job, wait for it, return the output commit id. Fails on Failed, Error, Stopped."""
    import os, time, requests
    headers = {"Authorization": f"Bearer {os.environ['DOMINO_TOKEN']}"}
    body = {"projectId": project_id, "runCommand": run_command, "title": "kubeflow"}
    if environment_id:
        body["environmentId"] = environment_id
    if hardware_tier:
        body["hardwareTier"] = hardware_tier          # hardware tier id, e.g. small-k8s
    r = requests.post(f"{domino_url}/api/jobs/v1/jobs", headers=headers, json=body, timeout=60)
    r.raise_for_status()
    job_id = r.json()["job"]["id"]
    print(f"Domino job {job_id} started")           # visible in the KFP UI; open it in Domino from there
    while True:
        job = requests.get(f"{domino_url}/api/jobs/beta/jobs/{job_id}", headers=headers, timeout=60).json()["job"]
        if job["status"]["isCompleted"]:
            break
        time.sleep(30)
    state = job["status"]["executionStatus"]
    if state != "Succeeded":
        logs = requests.get(f"{domino_url}/api/jobs/beta/jobs/{job_id}/logs", headers=headers,
                            params={"logType": "stdErr", "limit": 200}, timeout=60).json()
        for line in logs["logs"]["logContent"][-50:]:
            print(line["log"])
        raise RuntimeError(f"Domino job {job_id} ended {state}")
    return job["commitDetails"]["outputCommitId"]


@dsl.component(base_image="python:3.11", packages_to_install=["requests"])
def fetch_result(domino_url: str, project_id: str, commit_id: str, path: str, out: dsl.OutputPath(str)):
    """Copy one result file from the Job's output commit into a KFP artifact."""
    import os, urllib.parse, requests
    headers = {"Authorization": f"Bearer {os.environ['DOMINO_TOKEN']}"}
    url = f"{domino_url}/api/projects/v1/projects/{project_id}/files/{commit_id}/{urllib.parse.quote(path, safe='')}/content"
    r = requests.get(url, headers=headers, timeout=300)
    r.raise_for_status()
    with open(out, "wb") as f:
        f.write(r.content)


@dsl.pipeline(name="domino-train-and-collect")
def pipeline(domino_url: str, project_id: str):
    train = run_domino_job(domino_url=domino_url, project_id=project_id, run_command="python train.py")
    kubernetes.use_secret_as_env(train, secret_name="domino-token", secret_key_to_env={"token": "DOMINO_TOKEN"})

    collect = fetch_result(domino_url=domino_url, project_id=project_id,
                           commit_id=train.output, path="results/metrics.json")
    kubernetes.use_secret_as_env(collect, secret_name="domino-token", secret_key_to_env={"token": "DOMINO_TOKEN"})
```

`train.output` is the output commit id; passing it to the next component makes the dependency
explicit and gives the second step a pinned view of the first step's results. The Domino routes
are Public API in both published specs:

```text
POST /api/jobs/v1/jobs
GET  /api/jobs/beta/jobs/{jobId}
GET  /api/jobs/beta/jobs/{jobId}/logs?logType=stdErr
GET  /api/projects/v1/projects/{projectId}/files/{commitId}/{path}/content
```

Chaining Jobs that must run on the previous step's results **inside Domino** (same project):
pass `train.output` as the next Job's `commitId` on a DFS project, or let the next Job read from
the Dataset the first one wrote to.

Prefer this over a python-domino client inside the component: `job_start_blocking` raises only
on `Failed` (not on `Error` or `Stopped`) and depends on the v4 Jobs API, which is internal. If
you still want the client, see [domino-python-sdk](../domino-python-sdk/SKILL.md).

## Operational notes

- Set `timeout`s on every request and keep the poll interval at 30 s or more; a pipeline with
  many parallel steps otherwise turns into a steady stream of status calls.
- A KFP retry re-submits the Job; make Jobs idempotent (overwrite the day's partition) or guard
  with a check on the latest completed Job (`GET /api/jobs/beta/jobs?projectId=...&statusFilter=completed`).
- Logs stay in Domino; the component prints the Job id and, on failure, the tail of `stdErr`.
- `hardwareTier` in the Public body is the tier **id** (the spec example is `small-k8s`), not the
  display name python-domino's `hardware_tier_name` takes.
