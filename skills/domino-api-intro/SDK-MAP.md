# SDK and skill map

Where to go after [SKILL.md](./SKILL.md).

## API surface to skill

All Public API families below are served on the same base URL: `$DOMINO_API_PROXY` or
`$DOMINO_API_HOST` inside a run, the deployment URL outside ([HOSTS.md](./HOSTS.md)).

| Surface | Routes | Plugin skill / reference |
|---------|--------|---------------------------|
| REST overview and python-domino | `/api/...` | [domino-python-sdk](../domino-python-sdk/SKILL.md), [API-REFERENCE](../domino-python-sdk/API-REFERENCE.md) |
| Jobs | `/api/jobs/v1`, `/api/jobs/beta` | [domino-jobs](../domino-jobs/SKILL.md), [API-JOBS](../domino-python-sdk/API-JOBS.md) |
| Jobs started from Apache Airflow or Kubeflow Pipelines | the Jobs routes, called from the orchestrator's workers with a PAT or service-account token | [domino-airflow-kubeflow](../domino-airflow-kubeflow/SKILL.md) |
| Projects, collaborators, git repos, goals | `/api/projects/v1`, `/api/projects/beta`, `/api/projects/v2` | [domino-projects](../domino-projects/SKILL.md), [API-PROJECTS](../domino-python-sdk/API-PROJECTS.md) |
| Datasets and snapshots | `/api/datasetrw/v1`, `/api/datasetrw/v2` | [domino-datasets](../domino-datasets/SKILL.md), [API-DATASETS](../domino-python-sdk/API-DATASETS.md) |
| Data sources and their audit | `/api/datasource/v1` | [domino-data-connectivity](../domino-data-connectivity/SKILL.md), [API-ADMIN](../domino-python-sdk/API-ADMIN.md) |
| Data access from code (SQL, object storage, dataset files) | Domino Data API (`dominodatalab-data`) | [domino-data-sdk](../domino-data-sdk/SKILL.md) |
| NetApp Volumes | `/remotefs/v1` | [netapp-volumes](../netapp-volumes/SKILL.md) |
| Tags and properties | `/api/taxonomy/v1` | [tags-and-properties](../tags-and-properties/SKILL.md) |
| Apps | `/api/apps/v1`, `/api/apps/beta` | [domino-apps](../domino-apps/SKILL.md), [API-APPS](../domino-apps/API-APPS.md) |
| Model APIs, registry | `/api/modelServing/v1` (except `modelDeployments`, which is SageMaker: next row), `/api/registeredmodels/v1`, `/v2` | [domino-model-serving](../domino-model-serving/SKILL.md), [domino-model-endpoints](../domino-model-endpoints/SKILL.md), [API-MODELS](../domino-python-sdk/API-MODELS.md) |
| Model export out of Domino (registry, NVIDIA Fleet Command, Snowflake), SageMaker external endpoints (deployment targets), batch scoring Jobs | `/v4/models/...` (non-public route; may change in a future Domino version, see [route types](./SKILL.md#route-types)), `/api/admin/v1/deploymentTargets`, `/api/modelServing/v1/modelDeployments`, the Jobs routes | [domino-model-delivery](../domino-model-delivery/SKILL.md) |
| Governance | `/api/governance/v1` | [domino-governance](../domino-governance/SKILL.md) |
| Extensions | `/api/extensions/beta` | [domino-extensions](../domino-extensions/SKILL.md) |
| Workspaces | `/api/projects/v1/.../workspaces/{id}/sessions`; `/api/workspace/v1` (Cloud only) | [domino-workspaces](../domino-workspaces/SKILL.md) |
| Environments | `/api/environments/beta`, `/v1`, `/v2` (Cloud) | [domino-environments](../domino-environments/SKILL.md), [API-ENVIRONMENTS](../domino-python-sdk/API-ENVIRONMENTS.md) |
| Users, orgs, service accounts, PATs, hardware tiers, cost, audit trail | `/api/users/v1`, `/api/organizations/v1`, `/api/serviceAccounts/v1`, `/api/pat/v1`, `/api/hardwaretiers/v1`, `/api/cost/v1`, `/api/audittrail/v1` | [API-ADMIN](../domino-python-sdk/API-ADMIN.md) |

## Outside the REST API

The Domino CLI (`domino login`, `get`, `sync`, `run`, `upload-dataset`, ...) syncs project files,
starts Jobs and uploads to Datasets from a laptop without writing API calls or handling tokens;
it signs in through the browser or a device code. The R package wraps its file and run commands:
[domino-cli](../domino-cli/SKILL.md).

## LLM access

| Need | Skill |
|------|-------|
| LLM Gateway 2.0, the first choice where an administrator has deployed it (calling models through the gateway, coding assistants, admin setup) | [domino-llm-gateway](../domino-llm-gateway/SKILL.md) |
| Call an LLM from code without a gateway: a Domino-hosted model endpoint, an external provider with a key in a Domino environment variable, or the legacy AI Gateway on 6.3 | [domino-llm-access](../domino-llm-access/SKILL.md) |
| Host an LLM endpoint and manage it over `/api/gen-ai/beta/endpoints` (6.3 and Cloud) | [domino-llm-access/HOST-AN-LLM-API.md](../domino-llm-access/HOST-AN-LLM-API.md) |

The legacy AI Gateway routes (`/api/aigateway/v1/*`) exist only in the 6.3 spec; Domino
Cloud has removed them, so nothing under `/api/aigateway` is callable there.

## Discovery for agents

| Resource | Purpose |
|----------|---------|
| https://docs.domino.ai/llms.txt | Index of every docs page (append `.md` to read one) |
| https://docs.domino.ai/llms-full.txt | Expanded index with page summaries |
| [API-SPECS.md](./API-SPECS.md) | OpenAPI files, published and per deployment |
