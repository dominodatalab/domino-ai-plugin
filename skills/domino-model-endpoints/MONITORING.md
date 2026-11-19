# Operational monitoring of Domino endpoints

Source: https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/monitor-model-endpoints. This file covers serving health (health checks, timeouts, status codes, logs). Drift and model-quality monitoring is the `domino-model-monitoring` skill.

## Where the metrics are

Domino 6.1 has no CPU, memory, traffic or status-code charts on the endpoint version page. Resource and latency metrics are in the platform's Grafana, which administrators reach under **Admin** > **Reports** > **Grafana**; non-admins ask an administrator for that data or for alerts. What every user can read: the version status, the **Logs** column and the **Tester** tab (below).

## What to watch

| Metric | Warning sign | Action |
|--------|--------------|--------|
| CPU | > 80% sustained, erratic spikes (20-60% is normal under steady load) | Vectorize, cache repeated computations, move up a tier or add instances |
| Memory | Keeps growing; > 1 GB for a simple model | Process in batches, free intermediates; growth after warm-up is a leak |
| 2xx share | < 99% | Investigate immediately |
| 4xx | > 1% | Client input or authentication problems (401: wrong auth mode or token) |
| 5xx | > 0.1% | Model errors or resource exhaustion; read the instance logs |
| 504 | Any | Requests exceed the request timeout; optimize or raise the timeout |

Suggested alert thresholds: CPU > 80% for 10 minutes, memory up by more than 1 GB in an hour, error rate > 2%.

## Health checks and timeouts

**Settings** > **Advanced**. Changing health-check fields restarts the endpoint; a changed request timeout also needs a restart (UI, or the internal stop and start routes in [domino-model-serving LIFECYCLE.md](../domino-model-serving/LIFECYCLE.md#update-replicas-tier-environment)).

| Setting | Meaning | Guidance |
|---------|---------|----------|
| Initial delay (s) | Wait before a new instance receives requests | 10-30 for simple models, 60-120 with large dependencies, 120+ when loading external resources |
| Health check period (s) | How often Domino probes | 10-15 for high availability, 30 standard, 60+ for heavy models |
| Health check timeout (s) | Probe counts as failed after | 2-3x the model's P95 response time, at least 5 |
| Failure threshold | Consecutive failures before the instance is restarted | 2-3 for critical production, 5+ while debugging |
| Override request timeout (s) | Request fails with 504 after | Default 60; 5-30 real-time, 60-300 batch-like, 300+ heavy analytics |

Constraint: health check period x failure threshold must exceed the request timeout, or a long request can get a healthy instance restarted.

## Logs

Open the **Logs** column for any version:

| Log | Contains | Use for |
|-----|----------|---------|
| Build | Image build steps, dependency installs | Missing packages, environment problems, the 500 MB size error |
| Export | Packaging of files into the endpoint image | Files missing from the image |
| Instance | stdout and stderr of each container (your `print` output and tracebacks) | Prediction errors, slow processing, memory warnings; filter by pod and container |
| Deployment | Kubernetes events, heartbeats, pod status | Pods not starting, resource allocation, health-check restarts |

Over the API: `GET /api/modelServing/v1/modelApis/{modelApiId}/versions/{modelApiVersionId}/buildLogs` (optional `buildId`, `sinceTimeNano`), `.../exportLogs`, `.../instanceLogs` (optional `podName`, `containerName`, `sinceTimeNano`, `tail`, `maxResults`). Each instance-log entry is `{timestamp, timeNano, log, streamType, tags[{key, value}]}`, and the pod has two containers: the model container (tag `kubernetes.container_name` starting with `model-`) and the `istio-proxy` sidecar.

```bash
TOKEN=$(curl -s http://localhost:8899/access-token)   # outside a run: a service-account token, or send X-Domino-Api-Key instead
curl -s -H "Authorization: Bearer $TOKEN" \
  "$DOMINO_API_HOST/api/modelServing/v1/modelApis/$MODEL_ID/versions/$VERSION_ID/instanceLogs?maxResults=3000"
```

Fetch **without** `tail` and with a large `maxResults`, then keep the model-container entries: the sidecar's hundreds of startup lines otherwise hide a crash. Healthy: `WSGI app 0 (mountpoint='') ready`; crash loop: `no app loaded. GAME OVER` after a `Traceback`; no model-container lines means nothing has been logged yet. The filtering snippet and the full procedure are under "Health check after publishing" in [DEPLOY-ENDPOINT.md](./DEPLOY-ENDPOINT.md#health-check-after-publishing). With `DOMINO_API_PROXY` set, call `$DOMINO_API_PROXY/api/...` without the header.

## Debugging workflow

1. Confirm the version is **Running** and stays there (Versions tab; start it from the Actions menu if stopped). A status that alternates between `Running` and `Starting`, or a 503 from the prediction URL, means the container crash-loops: read the instance logs for `Traceback` and `no app loaded`. The usual cause is a file the function loads that was not in the Project commit; sync or commit it and publish a new version ("Health check after publishing" in [DEPLOY-ENDPOINT.md](./DEPLOY-ENDPOINT.md)).
2. Reproduce with the **Tester** tab; a 400 usually means the request shape does not match the function signature (see "Request JSON" in [DEPLOY-ENDPOINT.md](./DEPLOY-ENDPOINT.md)).
3. Read the instance logs around the failure time for the traceback.
4. Ask an administrator for CPU and memory of this version against the previous one (Grafana); a regression after a release points at the new code or a larger model.
5. For slow requests: check whether the model loads inside the function (it should be module-level), the input size, and whether the tier is CPU-bound. Raising the request timeout is a stopgap, not a fix.
6. For memory growth: look for per-request caches or appended lists; `tracemalloc` snapshots printed periodically show current and peak usage in the instance logs.

## Request logging flags

On a version, `logHttpRequestResponse: true` (API field) makes Domino log HTTP requests and responses; `monitoringEnabled: true` enables monitoring for the version, which the data-capture client in `domino-model-monitoring` feeds.
