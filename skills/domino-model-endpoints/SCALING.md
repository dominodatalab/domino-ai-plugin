# Scaling and routing Domino endpoints

Sources: https://docs.domino.ai/cloud/platform-capabilities/features/model-deployment/scale and https://docs.domino.ai/cloud/admin/platform-configuration/manage-model-deployments.

Domino endpoints scale by a **fixed number of instances** and a **hardware tier per instance**. There is no autoscaling policy, target-utilization setting or scale-to-zero for endpoints; size for peak load, and restart the endpoint after changing scale settings (from the UI, or stop and start the version with the internal routes in [domino-model-serving LIFECYCLE.md](../domino-model-serving/LIFECYCLE.md#update-replicas-tier-environment); non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types)).

## Horizontal: number of instances

- Set the instance count when you publish, or later under **Endpoints** > endpoint > **Settings** > **Deployment**. Domino load-balances requests across instances.
- The default is two instances (high availability); the maximum is 32. Admins change the default with the `com.cerebro.domino.modelmanager.instances.defaultNumber` configuration record.
- Instances are scheduled on separate nodes and availability zones when possible. To require separate nodes, create the endpoint with `strictNodeAntiAffinity: true` (API, at creation).
- Add instances for throughput-bound endpoints (many concurrent callers, queues building up in downstream applications).

Via the API, `PUT /api/modelServing/v1/modelApis/{modelApiId}` takes `name`, `description`, `replicas` and `environmentId` (all required) plus optional `hardwareTierId` and `resourceQuotaId`; `GET` the current object first and send the unchanged values back.

## Vertical: endpoint hardware tiers

- Endpoints use a separate class of hardware tier. A tier is usable by endpoints only when an admin marked it **Is Domino endpoint Tier** (Admin > **Advanced** > **Hardware Tiers**), or set the same flag with the public `PUT /api/hardwaretiers/v1/hardwaretiers`: the body is the full `HardwareTierV1` record (read it with the `GET` below) with `flags.isModelApiTier: true` and, for the default endpoint tier, `flags.isDefaultForModelApi: true`. That route needs `ManageHardwareTiers` and changes the platform for every project. Workspace and Job tiers do not appear in the endpoint form.
- List what exists: `GET $DOMINO_API_HOST/api/hardwaretiers/v1/hardwaretiers?limit=100` (needs `ViewHardwareTiers`). Endpoint tiers have `flags.isModelApiTier: true`; `flags.isDefaultForModelApi` marks the default. Names and IDs are deployment-specific; never copy a tier name from another deployment.
- When creating by API, pass `hardwareTierId` explicitly: on Domino Cloud a create without it lands on `small-k8s`, not the tier flagged `isDefaultForModelApi`.
- GPU tiers exist only if the administrator configured GPUs in the node pool. Check in code (`torch.cuda.is_available()`) rather than assuming.
- Move up a tier for resource-bound endpoints (long per-request compute, large models in memory).

## Python worker parallelism

Each Python endpoint instance runs uWSGI with one worker by default. An administrator raises `com.cerebro.domino.modelmanager.uWsgi.workerCount` under **Admin** > **Platform settings** > **Configuration records** and restarts services. The setting is deployment-wide and applies to synchronous endpoints only. The same records are reachable through the internal `/v4/admin/centralConfigSettings` routes ([API-ADMIN.md](../domino-python-sdk/API-ADMIN.md); non-public route; may change in a future Domino version, requires `EditCentralConfig`); on Domino Cloud only Domino holds that permission, so for Cloud the UI instruction is the path, and self-managed admins can use either. More workers means more concurrent requests per instance and proportionally more memory, since each worker loads the model.

## Routing modes

| Mode | Routes | Behaviour |
|------|--------|-----------|
| Basic (default) | `/models/<modelId>/latest/model` | Always the newest successful version; the old version shuts down once the new one is up |
| Advanced | `/models/<modelId>/latest/model` and `/models/<modelId>/labels/prod/model` | A promoted version serves production while you test the latest; promote without downtime |

Change the mode under **Settings** > **Deployment**.

## Timeouts and health checks

The request timeout (default 60 s; 504 when exceeded) and the health-check period, timeout, failure threshold and initial delay are under **Settings** > **Advanced**; the endpoint restarts when health-check settings change. Tuning guidance is in [MONITORING.md](./MONITORING.md).

## Asynchronous endpoints

Async endpoints trade latency for long-running work: payloads are limited to 10 KB (pass data by reference), a picked-up request lives 30 minutes, and the function must be idempotent. Capacity planning for async endpoints is an admin topic: https://docs.domino.ai/cloud/admin/architecture-and-deployment/sizing-the-infrastructure/size-async-domino-endpoint.

## Cost

- Start with the smallest endpoint tier that fits the model in memory, watch CPU and memory on the version page, then move up a tier or add instances.
- Spot node pools cut cost; if a spot instance is interrupted the endpoint degrades or stops until capacity returns, and the remedy is switching to a non-spot tier.
- Lower the instance count for low-traffic endpoints (one instance is allowed; two is the high-availability default).
- If you need elastic autoscaling, export the model to Amazon SageMaker: https://docs.domino.ai/cloud/platform-capabilities/features/models/deploy-sagemaker. Deployment targets, the legacy image export and the other export targets: [domino-model-delivery](../domino-model-delivery/EXPORT-TARGETS.md#amazon-sagemaker).

## GPU inference

Endpoints have no NVIDIA Triton integration; an endpoint runs your Python or R function on the selected hardware tier. For GPU serving, pick a GPU endpoint tier, load the model onto the device at module level, and batch inside the function when callers can send several rows per request. To serve an LLM with an OpenAI-compatible API, use the hosted LLM feature instead: https://docs.domino.ai/cloud/platform-capabilities/features/llms/host-an-llm.
