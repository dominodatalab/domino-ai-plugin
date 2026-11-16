# SDK and skill map

Where to go after [SKILL.md](./SKILL.md).

## API surface to skill

All Public API families below are served on the same base URL: `$DOMINO_API_PROXY` or
`$DOMINO_API_HOST` inside a run, the deployment URL outside ([HOSTS.md](./HOSTS.md)).

| Surface | Routes | Plugin skill / reference |
|---------|--------|---------------------------|
| REST overview and python-domino | `/api/...` | [domino-python-sdk](../domino-python-sdk/SKILL.md), [API-REFERENCE](../domino-python-sdk/API-REFERENCE.md) |
| Jobs | `/api/jobs/v1`, `/api/jobs/beta` | [domino-jobs](../domino-jobs/SKILL.md), [API-JOBS](../domino-python-sdk/API-JOBS.md) |
| Jobs started from Apache Airflow or Kubeflow Pipelines | the Jobs routes, called from the orchestrator's workers with a service account token or user API key | [domino-airflow-kubeflow](../domino-airflow-kubeflow/SKILL.md) |
| Projects, collaborators, git repos, goals | `/api/projects/v1`, `/api/projects/beta`, `/api/projects/v2` | [domino-projects](../domino-projects/SKILL.md), [API-PROJECTS](../domino-python-sdk/API-PROJECTS.md) |
| Datasets and snapshots | `/api/datasetrw/v1`, `/api/datasetrw/v2` | [domino-datasets](../domino-datasets/SKILL.md), [API-DATASETS](../domino-python-sdk/API-DATASETS.md) |
| Data sources and their audit | `/api/datasource/v1` | [domino-data-connectivity](../domino-data-connectivity/SKILL.md), [API-ADMIN](../domino-python-sdk/API-ADMIN.md) |
| Data access from code (SQL, object storage, dataset files) | Domino Data API (`dominodatalab-data`) | [domino-data-sdk](../domino-data-sdk/SKILL.md) |
| NetApp Volumes | `/remotefs/v1` | [netapp-volumes](../netapp-volumes/SKILL.md) |
| Apps | `/api/apps/beta` | [domino-apps](../domino-apps/SKILL.md), [API-APPS](../domino-apps/API-APPS.md) |
| Model APIs, registry | `/api/modelServing/v1` (except `modelDeployments`, which is SageMaker: next row), `/api/registeredmodels/v1` | [domino-model-serving](../domino-model-serving/SKILL.md), [domino-model-endpoints](../domino-model-endpoints/SKILL.md), [API-MODELS](../domino-python-sdk/API-MODELS.md) |
| Model export out of Domino (registry, NVIDIA Fleet Command, Snowflake), SageMaker external endpoints (deployment targets), batch scoring Jobs | `/v4/models/...` (non-public route; may change in a future Domino version, see [route types](./SKILL.md#route-types)), `/api/admin/v1/deploymentTargets`, `/api/modelServing/v1/modelDeployments`, the Jobs routes | [domino-model-delivery](../domino-model-delivery/SKILL.md) |
| Workspaces | `/api/projects/v1/.../workspaces/{id}/sessions` | [domino-workspaces](../domino-workspaces/SKILL.md) |
| Environments | `/api/environments/beta`, `/v1` | [domino-environments](../domino-environments/SKILL.md), [API-ENVIRONMENTS](../domino-python-sdk/API-ENVIRONMENTS.md) |
| Users, orgs, service accounts, hardware tiers, cost, audit trail | `/api/users/v1`, `/api/organizations/v1`, `/api/serviceAccounts/v1`, `/api/hardwaretiers/v1`, `/api/cost/v1`, `/api/audittrail/v1` | [API-ADMIN](../domino-python-sdk/API-ADMIN.md) |

## Outside the REST API

The Domino CLI (`domino login`, `get`, `sync`, `run`, `upload-dataset`, ...) syncs project files,
starts Jobs and uploads to Datasets from a laptop without writing API calls or handling tokens;
it signs in with a code from the deployment's `/authorizeCli` page. The R package wraps its file and run commands:
[domino-cli](../domino-cli/SKILL.md).

## LLM access

| Need | Skill |
|------|-------|
| Call an LLM from code: the AI Gateway (`/api/aigateway/v1`), or an external provider with a key in a Domino environment variable | [domino-llm-access](../domino-llm-access/SKILL.md) |

## Discovery for agents

| Resource | Purpose |
|----------|---------|
| [API-SPECS.md](./API-SPECS.md) | The Domino 6.1 API reference and the deployment's own OpenAPI files |
| https://docs.domino.ai/llms.txt | Index of the Domino 6.3 and Cloud docs (append `.md` to read a page); can describe features Domino 6.1 lacks |
