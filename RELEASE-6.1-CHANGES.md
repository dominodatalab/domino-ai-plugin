# Release 6.1 change log

Changes made on branch `release-6.1` to make the plugin correct for **self-managed Domino 6.1 only**,
applying the Domino skills 6.1 compatibility review (the compat doc, `domino-skills-6_1-compatability.md`,
kept outside the repository).
Version `2026.603.10` → `2026.601.11`.

## Summary

| Area | Result |
|---|---|
| Skills | 35 → 28: 7 removed, 28 adapted (every `compatibility:` and opening line now says Domino 6.1) |
| Plugin-level files | `rules/domino.md`, README, AGENTS.md, the 3 agent routers, all 4 manifests |
| MCP server | user API key fallback (`X-Domino-Api-Key`); `commits/latest` 404 fallback; README; tests |
| Evals | 15 cases/scenarios removed, 12 rewritten for 6.1 rules, HPC dryrun cases removed |
| Repo mechanics | version bump, `check-version.sh` exception for a release branch leaving main's line |

## Checks run on the final tree

- `scripts/lint-skills.py`: ok, 28 skills, 0 errors, 0 warnings
- `scripts/sync-manifests.py --check`: in sync at 2026.601.11
- `scripts/check-codeowners.py`: ok, 28 skills
- `claude plugin validate .claude-plugin/plugin.json` and `claude plugin validate .`: passed
- `scripts/check-version.sh origin/release-6.1`: ok (re-run after commit)
- MCP server `pytest`: 125 passed
- `evals/e2e/tools/dryrun_checks.py`: 22/22
- Not run: `claude plugin eval` (model calls) and the live end-to-end round on a 6.1 Workspace.
  AGENTS.md requires the live round before shipping write-path changes; none exists for 6.1 yet.

## Branch-wide decisions

- **A. Auth outside a run:** service-account token (`Authorization: Bearer`) first, user API key
  (`X-Domino-Api-Key`, `DOMINO_USER_API_KEY`, python-domino `api_key=`) as the fallback. All
  Personal Access Token wording and `/api/pat/v1/*` routes removed; API keys are not called deprecated.
  In-run auth unchanged.
- **B. Version checks:** `GET /version` 6.1.x takes the self-managed path. Where a "Which path applies"
  section only contrasted 6.3 with Cloud (domino-projects, domino-model-serving), it was removed.
- **C. Doc links (deviation from the compat doc):** docs.domino.ai links in skills were left as they are;
  6.1 URLs contain page ids that cannot be derived, and the compat doc rates this change cosmetic.
  Instead `rules/domino.md` states the target is 6.1, points to `docs.dominodatalab.com/en/6.1`, and
  warns that `domino_docs` / docs.domino.ai describe 6.3 and Cloud. Exceptions: domino-api-intro and
  domino-python-sdk spec links point to the 6.1 Platform API reference; the MCP server, README and
  manifests point to the 6.1 auth page.
- **Removed features are removed,** not labelled "6.2+", unless a user would plausibly ask for them; then
  one line says they are not available on Domino 6.1.

## Delisted skills (removed)

`domino-hpc-slurm`, `tags-and-properties`, `domino-extensions`, `domino-llm-gateway`,
`domino-genai-tracing`, `domino-trace-setup`, `domino-governance` (compat doc "Delist on 6.1"; for
governance the recommended option, delist, was taken).

- Folders deleted; names added to `scripts/removed-skills.txt` so lint rule L16 fails on any reference.
- `.github/CODEOWNERS`: their 7 lines removed. `scripts/claude-mentions.allow`: their 3 entries removed.
- `agents/_domino-setup.md`: `domino-trace-setup` preload and the tracing row removed (tracing now says
  "requires Domino 6.2 or later"); LLM row routes to `domino-llm-access` only; description trimmed.
- `agents/_domino-debug.md`: Slurm troubleshooting row removed.
- `AGENTS.md`, `evals/README.md`, `evals/e2e/README.md`: references removed or replaced.

## Plugin-level files (compat doc section D)

- `rules/domino.md`: outside-Domino auth is service-account token, fallback user API key; "deprecated"
  removed; "LLM Gateway if present" → "AI Gateway"; "run as several replicas" removed (autoscaling is
  6.2+); docs line per decision C. Lead section 971 bytes (limit 990), file 2,669 chars (limit 2,700).
- `README.md`: feature list, token table, troubleshooting rows, prerequisites, Cursor and Gemini
  sections, MCP section, skill table (28) and agent table updated; Compatibility section replaced with a
  6.1 support statement pointing to the compat doc and this log.
- `.claude-plugin/plugin.json` (source of truth), synced to `plugin.json`, `.cursor-plugin/plugin.json`,
  `gemini-extension.json`: version 2026.601.11; description drops GenAI tracing and governance and says
  "for Domino 6.1"; `genai-tracing` keyword removed; OpenAI `longDescription` drops tracing, governance,
  tags and properties; token setting retitled "Domino service account token" (Claude Code and Gemini).
- Agent routers (`_domino-setup`, `_domino-deploy`, `_domino-debug`): auth sentence per change A.

## MCP server (`mcp-servers/domino_mcp_server`)

- `_get_auth_headers`: `DOMINO_TOKEN` → `Authorization: Bearer`; else `DOMINO_API_KEY` →
  `X-Domino-Api-Key` (was rejected). `_auth_mode` reports `api_key`; `_redact` also removes the key;
  `get_domino_environment_info` checks the connection in either mode and reports `DOMINO_API_KEY` in
  `credential_sources`; the start-up "not supported" warning removed; help and 401/403 text drop PAT.
- `_latest_commit_id`: on 404 from `GET /api/projects/beta/projects/{id}/commits/latest`, falls back to
  `GET /v1/projects/{owner}/{project}/commits` and takes the first commit id (newest first, as the
  domino-python-sdk skill documents for `commits_list()`); object entries with commit times are ordered
  by time. Callers pass owner and project name.
- `tests/test_server.py`: 5 tests updated for the new auth behaviour; 4 added (API key header, token wins
  over key, commit fallback by time, commit fallback first id).
- `README.md`: `DOMINO_TOKEN` row, API key paragraph, and the `download_file_from_domino_project` route row.

## Evals

- Removed (compat doc "Branch packaging"): `start-hpc-job-via-rest`, `run-existing-sbatch-scripts-on-domino`,
  `submit-slurm-array-job-from-workspace`, `create-extension-rest`, `create-governance-bundle-rest`,
  `tag-project-via-taxonomy-api`, `call-llm-through-gateway`, `add-genai-tracing`,
  `add-evaluator-to-traced-agent`, `instrument-agent-from-scratch`, `trace-deployed-app-performance-tab`,
  `call-llm-from-domino-cloud`; e2e scenarios `s08`, `s11`, `s12`, `s13-dfs`, `s13-git`;
  `evals/e2e/tools/probe_hpc.py`; the s11–s13 cases and HPC fixtures in `dryrun_checks.py`.
- Kept: `s14-mpi-disambiguation` (MPI is right and Slurm wrong on 6.1 too).
- Rewritten for 6.1: `call-llm-on-domino-6-3` → `call-llm-on-domino-6-1` (AI Gateway is standard;
  no Gateway 2.0 or hosted LLMs); `apps-cicd-github-actions` (`/api/apps/beta` or python-domino
  `app_publish`, never `/api/apps/v1`); `cli-headless-login-run-download` (`/authorizeCli` code, no
  `--device`); auth graders in `authenticate-in-run-and-ci`, `api-token-rule-for-ci`,
  `automate-model-api-version-rest`, `export-model-image-from-ci`, `kubeflow-component-runs-domino-job`,
  `airflow-dag-runs-domino-job`, `mcp-server-from-laptop` (service-account token first, API key allowed,
  PAT fails; the `no-api-key` regex graders removed).
- Not changed: `evals/e2e/config.example.yaml` still describes PAT auth for the harness itself.

## Repo mechanics

- `scripts/check-version.sh`: a `release-X.Y` base that still carries main's newer line may move to
  line X.Y once (N must still increase). Without this no version could pass on this branch: rule 4
  requires line 601 and rule 5 forbids the line going backwards from the base's 603.

## Open items to confirm on a live 6.1 instance

From the compat doc, still open:
- 6.1 request bodies for `/api/apps/beta`, and whether any public route starts an App version.
- `POST /api/registeredmodels/v1` body (documented from the 6.3 spec's v1 schema with "check `/docs`").
- NetApp Volumes base path (`/remotefs/v1` vs `/domino-netapp-volumes/v1`); the skill tells the
  reader to probe it.
- Whether `localhost:8899/access-token` works on 6.1 (kept, with a fallback to `$DOMINO_API_PROXY`;
  the 6.1 auth page documents only the proxy).
- `/api/governance/v1` on 6.1 (moot while governance is delisted).

Raised during the work:
- Sort order of `GET /v1/projects/{owner}/{project}/commits` (MCP fallback, domino-jobs,
  domino-projects and domino-python-sdk assume newest first).
- python-domino `app_publish` with a commit only a tag reaches (the domino-apps CI flow).
- Whether `SecureIdentityPropagationToAppsEnabled` is on by default; the app templates still forward
  the viewer's token on their example Domino API call (comments updated, code unchanged).
- NetApp grant `entityType`/`accessLevel` values, `netAppVolumeIds` on Jobs.
- Whether launcher web routes accept `X-Domino-Api-Key`; Bedrock `AWS_PROFILE` propagation; exact
  6.1 MPI image tags; MLflow alias support; the admin Grafana menu path.
- The domino-cli skill still links docs.domino.ai pages that describe the device flow; the 6.1 CLI
  install page is
  `https://docs.dominodatalab.com/en/6.1/user_guide/e21e55/install-the-domino-command-line-interface-cli/`.

## Round 2: product-team feedback

Both docs were revised first (compat doc changelog "second revision"; instructions doc items 10–12
and "Carry doc changes into the release-6.1 branch"), then these approved branch changes:

- **Item 11, AI Gateway wording:** `skills/domino-llm-access/LEGACY-AI-GATEWAY.md` opening and
  `SKILL.md` "Which path applies" item 1 no longer call the gateway "standard on 6.1"; they say it is
  usable once an administrator has created endpoints, to fall back to Option A when Gateway LLMs is
  missing or empty, and never to enable it. `evals/call-llm-on-domino-6-1` grader updated to match.
- **Item 10, `rules/domino.md`:** no branch change; README, AGENTS.md and the MCP README already
  describe it as the always-on rule file whose lead section the MCP server sends as instructions.
- **Item 12, `s14-mpi-disambiguation`:** no branch change; it was already kept.
- **Leftovers from the earlier eval cleanup:** `evals/e2e/README.md` no longer lists the deleted
  `s08`, `s11`, `s12`, `s13` scenarios or `tools/probe_hpc.py`; its run and format examples use `s05`
  and `s14`.

## Skill changes, per file

The per-skill logs below were written while each group of skills was edited.

### Change log: auth group (6.1 branch)

#### domino-api-intro
- SKILL.md — description drops PAT, extension, governance; `compatibility:` and opening line set to Domino 6.1 (version labels).
- SKILL.md — auth table outside-Domino row: service account token (Bearer) first, user API key (`X-Domino-Api-Key`, `DOMINO_USER_API_KEY`, `api_key=`) fallback; `POST /api/pat/v1/tokens` and the "API keys are deprecated, never use" paragraph removed (global A, api-intro row).
- SKILL.md — auth reference link set to the 6.1 auth page; curl and Python setup blocks use `SA_TOKEN` then `X-Domino-Api-Key` fallback (global A).
- SKILL.md — one line: if `localhost:8899/access-token` does not answer, use `$DOMINO_API_PROXY` (Items to confirm: access-token).
- SKILL.md — App note: an App acts only as the publisher on 6.1 (api-intro row, viewer identity 6.2+); "on 6.3 confirm" relabelled; delisted-skill names removed from Next steps.
- HOSTS.md — "Inside an App" rewritten: publisher-only, `domino-username` header, JWT only with `SecureIdentityPropagationToAppsEnabled`, no extended identity/consent; PAT removed from in-pod gateway list (api-intro row, debug-proxy row).
- HOSTS.md — taxonomy example and `/webvfs` NetApp file-ops exception and row removed; NetApp base-path check (`/remotefs/v1` vs `/domino-netapp-volumes/v1`) added (netapp row, Items to confirm).
- HOSTS.md — Governance section removed (delisted); 404 fallback now "service account token or user API key", not PAT (api-intro row).
- ERRORS.md — taxonomy error-body rows, governance large-read bullet, governance 404 bullet, consent-redirect and extended-identity guidance removed; CLI-login 403 now points to proxy or service account token; "never escalate to a legacy API key" replaced by a permission-problem rule (global A, delisted skills).
- LIMITS.md — "Deprecated credentials" table becomes "Credential patterns to avoid": API key row removed (it is the fallback), `EnableLegacyJwtTooling` no longer labelled 6.3; legacy-API-key link removed; taxonomy pagination row removed; NetApp list shape `items`/`totalCount` with confirm-in-/docs; registry pagination v1 only (api-intro row, netapp row, model-serving row).
- API-SPECS.md — rewritten around the 6.1 Platform API reference plus the deployment's `/docs` as authoritative; docs.domino.ai specs described as 6.3/Cloud; taxonomy and governance service docs and Tags/Governance links removed; 404 guidance for `/docs/configuration.json` (api-intro row, global C exception).
- SDK-MAP.md — rows for tags-and-properties, governance, extensions removed; Apps beta only; registry v1 only; Workspaces `/api/workspace/v1` and environments v2 removed; PAT/`/api/pat/v1` removed; Airflow credential wording; CLI sign-in via `/authorizeCli`; LLM rows reduced to domino-llm-access with AI Gateway (gateway 2.0 and gen-ai rows dropped); llms.txt labelled 6.3/Cloud (api-intro row, delisted skills).

#### domino-python-sdk
- SKILL.md — `compatibility:`/opening line 6.1; outside-Domino auth: service account `auth_token` first, `api_key=` fallback (example added); "deprecated" API key wording removed; PAT/taxonomy/governance removed from the REST-surface row and the API-ADMIN row; route-verification rule points at 6.1 reference or `/docs`; auth doc link to 6.1 page (python-sdk row, global A).
- API-ADMIN.md — Personal Access Tokens section and PAT intro/admin-page mention removed; "Unlike a PAT" wording removed; role example `Librarian` (6.3 role) changed to `Practitioner`; "On Domino 6.3 confirm" relabelled (python-sdk row).
- API-REFERENCE.md — intro points at the 6.1 Platform API reference, `/docs` authoritative; PAT, commits/latest, HPC, gen-ai, registry v2, apps v1, extensions, governance, taxonomy rows removed; Cloud-only rows removed from the index; `/api/aigateway/v1` no longer labelled 6.3; taxonomy response-code/error/pagination text removed; doc links to 6.1 reference and auth page (python-sdk row, model-serving row, projects row, jobs row).
- API-APPS.md — "prefer v1 routes" and v1 chain removed; `tagIds`, `taxonomyTags`, Cloud-only params, `configurationType`, `autoscalingSpecification`, `bundleId`, `extendedIdentityPropagationToAppsEnabled` removed; beta `start`/`stop` removed: start via UI or python-domino `app_publish(app_id=...)`, stop via `DELETE .../instances/{id}` or `app_unpublish`; roles route note relabelled; workflow example rewritten (python-sdk row, apps row).
- API-MODELS.md — registry section rewritten for v1 only (`POST /api/registeredmodels/v1` with `modelName`, `experimentRunId`, `discoverable`; `POST .../{modelName}/versions` with `experimentRunId`, `artifact`, `description`), Hugging Face source and MLflow 3 `loggedModelId` removed, confirm-in-/docs guidance (model-serving row).
- API-MODEL-SERVING.md — v1/v2 table replaced with v1-only table, "deprecated" label on v1 versions POST removed, Cloud-only collaborator bullet and governance attachments removed, GenAI endpoints section removed (model-serving row, gen-ai drop).
- API-ENVIRONMENTS.md — "6.3" path relabelled 6.1 (`6.1.x`), `slurm` removed from `supportedClusters`, "tags deprecated in favour of taxonomy" removed (environments row, global B).
- API-JOBS.md — `slurm` removed from `clusterType`; job-defaults note relabelled 6.1 (distributed-computing/jobs rows).
- API-PROJECTS.md — `commits/latest` removed; DFS head via python-domino `commits_list()[0]` (non-public `/v1/projects/{owner}/{project}/commits`); "on Domino 6.3 confirm" relabelled (projects row).
- SDK-EXAMPLES.md — "Never pass api_key=" replaced with SA-token-first/API-key-fallback; tags-and-properties link removed; `create_environment` 6.3 label relabelled; `app_publish`/`app_unpublish` row now the way to start/stop Apps on 6.1 (python-sdk row, apps row).

#### domino-airflow-kubeflow
- SKILL.md — description and `compatibility:` no longer say "PAT ... never an API key"; opening line 6.1; credential step rewritten (service account token first, user API key fallback via `X-Domino-Api-Key`/`api_key`/`DOMINO_USER_API_KEY`); "deprecated" API key text removed; API-key header fallback comment in the task example; operator and env-var pitfalls reworded; auth link to 6.1 page (airflow row).
- AIRFLOW.md — `DOMINO_TOKEN_FILE` is a service account token; `DOMINO_USER_API_KEY` row added as fallback; `api_key` parameter no longer "legacy; do not use"; auth-precedence note covers API key; DAG comment (airflow row).
- KUBEFLOW.md — Secret holds a service account token or API key fallback (`X-Domino-Api-Key`) (airflow row).
- JOBS-API-PATTERN.md — AUTH comment SA token + API-key fallback; `GET /api/pat/v1/tokens` tip replaced by `GET /api/users/v1/self` credential check (airflow row).

#### domino-cli
- SKILL.md — description drops device-code; `compatibility:` 6.1 and no "older than 6.2.3" note; opening line 6.1; sign-in steps replaced with `domino login <url>` + `<url>/authorizeCli` code paste; `--device`, browser auto-auth and 6.2.3 note removed; "(6.3 same content)" note removed (cli row).
- CLI-INSTALL.md — sign-in section rewritten for the `/authorizeCli` code flow; `--device` and the 6.2.3 note removed; "6.3 pages identical" removed (cli row).
- R-PACKAGE.md — sign-in via `/authorizeCli`; `httr` example uses `SA_TOKEN` (Bearer) then `X-Domino-Api-Key` fallback; auth link to 6.1 page; "6.3 page identical" removed (cli row).
- CLI-REFERENCE.md — "6.3 pages identical" removed.

#### domino-modeling-assistant
- SKILL.md — `compatibility:`/opening line 6.1; Workspace use needs a custom Compute Environment with assistant, plugin and `uv`; outside Domino `DOMINO_TOKEN` = service account token, `DOMINO_API_KEY` = user API key fallback (matches the modified MCP server and manifests in the working tree); "API keys deprecated and not accepted" removed; 6.3/Cloud modeling-assistant doc link removed (modeling-assistant row, MCP row).
- SETUP.md — "Create a Personal Access Token" replaced with "Get a credential" (SA token first, API key fallback); variables table adds `DOMINO_API_KEY`; env-file note for API key; troubleshooting no longer references PAT status; Step 4 rewritten: the 6.1 DSE has no assistant/skills/`uv`, build a custom environment (points to `domino-environments`); coding-assistants doc links (6.3/Cloud-only) removed (modeling-assistant row).

#### Deviations / skipped
- Global C: docs.domino.ai links left as-is except the two exceptions, per instructions. I fetched and confirmed real 6.1 CLI URLs (install: https://docs.dominodatalab.com/en/6.1/user_guide/e21e55/install-the-domino-command-line-interface-cli/, proxy: .../0da1e9/use-the-domino-cli-behind-a-proxy/, reference: .../9355a5/domino-cli-reference/, download files: .../8ec1ce/download-files-with-the-cli/) but did not substitute them; domino-cli still cites docs.domino.ai/cloud pages, whose install page describes the device flow.
- API-SPECS.md also links the 6.1 user guide index (https://docs.dominodatalab.com/en/6.1/user_guide/1a73c8/user-guide/), taken from the compat doc's Sources.
- python-sdk per-area files (API-ENVIRONMENTS, API-MODELS, API-PROJECTS, API-ADMIN, API-JOBS) keep their existing **Cloud**-labelled routes; only API-REFERENCE's route index dropped Cloud-only rows. Labelled Cloud content does not claim 6.1 availability, so I left it to keep edits surgical.
- python-sdk API-APPS.md went beyond the python-sdk row (which only asked to drop "prefer v1" and `tagIds`): also removed beta `start`/`stop`, autoscaling, extended identity and `bundleId`, applying the domino-apps row so the two skills agree.
- python-sdk registry files rewritten to v1 per the domino-model-serving row (the python-sdk row did not list them).
- api-intro ERRORS.md: the "never escalate to a legacy API key" rule became "a 403 is a permission problem; do not switch credentials", since the API key is a valid fallback on 6.1.
- API-ADMIN.md: example role `Librarian` (a 6.3 taxonomy role) changed to `Practitioner`.

#### Uncertain
- `http://localhost:8899/access-token` is not documented on the 6.1 auth page (only `DOMINO_API_PROXY` is). Kept, with one line: if it does not answer, use `$DOMINO_API_PROXY`. Same pattern remains in HOSTS.md (NetApp in-run row), python-sdk SKILL.md and R-PACKAGE.md.
- `/api/apps/beta` body shapes on 6.1 (`configurationType` removed on judgement; `netAppVolumeIds`, `vanityUrl`, `tags` kept). Text tells the reader to confirm in `/docs`.
- `POST /api/registeredmodels/v1` and `.../versions` bodies come from the 6.3 spec's v1 schemas (`NewRegisteredModelV1`, `NewRegisteredModelVersionV1`); 6.1 not verified. Text has confirm-in-/docs guidance.
- NetApp list envelope (`items`/`totalCount`) taken from the compat doc; confirm-in-/docs guidance added.
- HOSTS.md in-App gateway (`DOMINO_API_HOST` as `127.0.0.1:<port>`, 403 for CLI-login tokens) kept without PAT; not confirmed for 6.1.
- `commits_list()[0]` as DFS head relies on the legacy route returning newest first (python-domino docs and SDK-EXAMPLES say so; the compat doc asks to confirm the sort order on 6.1).
- Whether a deployment's `/docs` (configuration.json, per-service OpenAPI) is served on 6.1; API-SPECS gives a 404 fallback to the 6.1 reference.
- Service-account token default four-month expiry (API-ADMIN.md) left unchanged; not checked for 6.1.
- `/authorizeCli` "any device" wording: the 6.1 page has you paste the code by hand, so the browser can be anywhere; inferred, not stated by the docs.

### 6.1 change log: app skills

#### domino-apps
- SKILL.md: description drops roll back, "deploy an older version" and start/stop over /api/apps/v1, and adds stop/logs over /api/apps/beta. compatibility and opening line set to 6.1. Identity is now `domino-username` always, with a JWT only when `SecureIdentityPropagationToAppsEnabled` is on. "Several replicas" is gone. Lifecycle is a one-step publish (Deployments > Apps > Publish Domino App), with rollback and autoscaling stated as not available. Viewer API calls are stated as not available (call as the publisher). The auth line puts the service account first and the user API key as fallback, without "deprecated". REST automation covers beta plus `app_publish`. Removed the `domino-extensions` pointer and the "/6.3/" note. (domino-apps row; A)
- API-APPS.md: rewritten for `/api/apps/beta` only. Includes a route table from the 6.3 spec's beta paths, minus start/stop. Stopping is `DELETE …/instances/{id}`. Starting goes through the UI or python-domino `app_publish`/`app_get_status`/`app_unpublish`, whose signatures I checked against python-domino master; it uses /v4/modelProducts and is labelled non-public. Removed: v1 routes, drafts, publish, createAndStart, liveSync, `extendedIdentityPropagationToAppsEnabled`, `autoscalingSpecification`, the governance-blocked row, the /v4 visibility routes, the Cloud roles route and the commits/latest guidance. No JSON request bodies; readers go to the deployment's `/docs`. Auth examples use a service account Bearer or `X-Domino-Api-Key`. (domino-apps row; A; Items to confirm)
- REACT-CICD.md: identity is a service account first, user API key as fallback. Removed the PAT minting route (`/api/pat/v1/tokens`) and the API-ADMIN pointer. The App is published once in the UI (new setup step 6) and CI stores `APP_ID`. `deploy_app.py` is now python-domino `app_publish(app_id, commit_id=BUILD_SHA, …)`, polls `app_get_status`, and reads `url` from `GET /api/apps/beta/apps/{id}`. The workflow exports `BUILD_SHA` and installs `dominodatalab`. Rollback section replaced by "revert and push". (domino-apps row: REACT-CICD; A)
- FRAMEWORKS.md: viewer identity section rewritten for 6.1. `domino-username` is always sent, the JWT only with the setting on, and acting for viewers is not available. `viewer.py` `domino_get` is publisher-only. Removed the extended-identity table, consent and the PAT script text. Removed `/preview/` from the prefix list. Idempotency text no longer mentions replicas, live sync or rollback. Version-notes bullet points to beta with a check-/docs note. Rollback table replaced by "revert and publish again". Dropped "(same content under /6.3/)". (domino-apps row)
- TROUBLESHOOTING.md: "publish a new version / deploy it" is now "publish again". Removed the `dfsCommitId` API pointer, the App Preview prefix, the extended-identity, consent and PAT bullets (section 10/11 rewritten) and the support bundle mentions. Logs auth is a service account or API key, and the APP_ID lookup uses beta. Reproduce by publishing. (domino-apps row; A)
- REACT-VITE-GUIDE.md: proxy diagram matches 6.1 identity. App Preview section replaced by test-by-publishing. The server.js paragraph says Domino 6.1 rejects the viewer token and recommends publisher calls. "kept for rollbacks" removed. (domino-apps row)

#### domino-app-init
- SKILL.md: compatibility and opening line set to 6.1. Replicas removed. The identity invariant is now token-when-present, else `domino-username`. Removed the `content.dfsCommitId` API pointer. Steps 5–6 (Preview, Publish, Deploy) merged into a one-step publish via Deployments > Apps > Publish Domino App. (app-init row)
- assets/vite-react/vite.config.js: comment changed from App Preview to "test the published App". (app-init row)
- assets/vite-react/server.js: the comment on `api/projects` now says the token arrives only with `SecureIdentityPropagationToAppsEnabled` on, 6.1 rejects it on API routes, and real data should use `$DOMINO_API_PROXY` scoped by `domino-username`. Comments only; code unchanged. (app-init row)

#### domino-debug-proxy
- SKILL.md: compatibility and opening line set to 6.1, with service account / API key for the log check. The intro says the JWT is sent only with `SecureIdentityPropagationToAppsEnabled` on. Check 9 makes publisher calls the rule. Common-issues row reworded. Manual steps: support bundle and PAT removed, "version pins a commit" and App Preview replaced by test-the-published-App. (debug-proxy row; A)
- RUNTIME.md: identity table replaced by setting on/off. Extended-identity and consent rows and the consent section removed; a short sign-in redirects section added. `/preview/<id>` prefix row reworded. PAT and CLI-token rows removed. (debug-proxy row)

#### domino-rust-apps
- SKILL.md: description drops "as the viewer with extended identity propagation" and App Preview. compatibility and opening line set to 6.1. Replicas, Preview and live sync removed. Step 5 is a one-step publish. The "Act as the viewer" rule is replaced by "Call Domino as the publisher" (`?as=publisher`), with the anchor updated. (rust-apps row)
- APP.md: identity section rewritten as "Identity and Domino API calls". Extended identity, consent, PAT script access and the deployment flag are removed (not on 6.1) and the docs link is kept. Replicas, live sync, rollback, Version Notes and App Preview wording removed. (rust-apps row: APP.md)
- PROA.md: "Publish and roll back" is now "Publish". (remove rollback)
- assets/app/src/domino.rs: module and item doc comments rewritten for 6.1. `VIEWER_REJECTED` message now tells the reader to call as the publisher. (rust-apps row: domino.rs)
- assets/app/src/lib.rs: the test asserting the old message is renamed to `rejected_viewer_call_suggests_the_publisher` and asserts `"as the publisher"`. Two doc comments reworded (rollback, extended identity). No logic change.
- assets/app/templates/index.html: the link text says the viewer call is rejected on Domino 6.1.

#### domino-ui-bootstrap
- SKILL.md: removed "or extension" from the description scope and from the trigger list. compatibility and opening line set to 6.1. The prefix example `/preview/<appId>/` is now `/apps-internal/<appId>/`. (ui-bootstrap row)
- APP-SOURCE.md: same prefix example change. "Extension context" removed. Section 8e says the backend reads `domino-username` or the token and calls as the publisher. (ui-bootstrap row)
- PROJECT-FILES.md: prefix example change, and the identity line is now publisher calls. (ui-bootstrap row)
- VERIFY.md: the App Preview step is now "test in Domino by publishing", and the server.js description no longer claims viewer calls. (ui-bootstrap row)

#### Deviations / skipped
- REACT-CICD.md `deploy_app.py`: the compat doc says to switch to beta create/versions. I used python-domino `app_publish` on a UI-created App (`APP_ID`) instead, for two reasons. The 6.1 beta create/version bodies are unconfirmed (compat doc: Medium), and whether any public route starts a version is unconfirmed. `app_publish` is the start path the compat doc names. Beta is still used to read the App URL.
- API-APPS.md: lists beta routes from the 6.3 spec (minus start/stop) without request bodies. Readers are sent to the deployment's `/docs` for the AppCreationRequest and AppVersionCreationRequest shapes.
- server.js `api/projects` and the Rust template's default `Identity::Viewer` were left as code, with only comments and text changed as the compat doc asks. On 6.1 both example viewer routes return 401 or a Domino error. The docs tell readers to use publisher calls (`?as=publisher` in Rust).
- domino-rust-apps APP.md: the compat doc says "mark extended identity, consent, PAT, autoscaled replicas as 6.2+". Per the branch decision I removed them and stated in one line that acting for viewers is not available on 6.1.
- Kept existing docs.domino.ai `/cloud/` links (global change C). Removed only "(same under /6.3/)" notes.
- Also removed the App support-bundle mentions (domino-apps TROUBLESHOOTING, debug-proxy SKILL), because I could not confirm it exists on 6.1.

#### Uncertain
- Whether python-domino `app_publish(commit_id=…)` works on 6.1 (`/v4/modelProducts/{id}/start` with `mainRepoGitRef`), and whether Domino's clone can check out a commit reachable only through a tag (the CI build commit).
- Whether `app_get_status` statuses on 6.1 include "Error" (the script also accepts "Failed").
- Whether 6.1 beta responses carry `url`, `currentVersion.id` and `currentInstance.status` as in the 6.3 spec, and whether beta `versions` and `DELETE …/instances/{id}` behave the same.
- Whether `SecureIdentityPropagationToAppsEnabled` is on by default on 6.1, and whether `domino-username` is always sent alongside the JWT.
- The example prefix `/apps-internal/<appId>/` in ui-bootstrap is taken from the existing prefix list, not from 6.1 docs.
- Rust template changes were not compiled (no cargo in this environment). The edits are a string constant, a test name and assertion, and comments. server.js was not syntax-checked (no node); the change there is comment-only.

### Change log: model and experiment skills (Domino 6.1)

#### domino-model-serving
- SKILL.md — compatibility/body relabelled to Domino 6.1; outside-run auth = service-account token or user API key (A).
- SKILL.md — removed "Legacy API keys are deprecated"; auth line gives Bearer service-account token first, `X-Domino-Api-Key` fallback (A).
- SKILL.md — description: "registered models v1 vs v2 routes" -> "the registered models routes (/api/registeredmodels/v1)".
- SKILL.md — surfaces table, lifecycle step 1 and "Registered models" bullet use `/api/registeredmodels/v1` only (list `GET /v1`, register `POST /v1`, new version `POST /v1/{modelName}/versions`, no deprecated label); removed `huggingFaceSource`, v2, `create`; reader guidance to confirm bodies in `/docs/openapi/openapi-public.json`; MLflow registration kept (registry row).
- SKILL.md — replaced "Which path applies" (Cloud-only `/api/modelServing/beta` visibility/collaborator routes) with an "Access and collaborators" section: UI only (B; Cloud branch would mislead).
- LIFECYCLE.md — schema ref `NewRegisteredModelV2` -> `NewRegisteredModelV1`; removed Cloud-only note and the Cloud visibility/beta-route paragraph.
- LIFECYCLE.md — "Registered models by API" rewritten for v1: `POST /v1` body (`modelName`, `experimentRunId`, `discoverable`, `description` per 6.3 spec schema `NewRegisteredModelV1`), `POST /v1/{name}/versions` (`experimentRunId`, `artifact`, `description`), list/get/patch/versions; removed v2, `huggingFaceSource`, `loggedModelId`/MLflow 3 guidance, deprecated label; 400 -> check `/docs` guidance (registry item).
- LIFECYCLE.md — replaced `GET /api/projects/beta/projects/{id}/commits/latest` (not in 6.1 per compat doc domino-projects row) with MCP upload `commitId` or python-domino `commits_list()` (labelled non-public; check sort order); code snippet updated.
- LIFECYCLE.md — "Cloud returns 200" -> "deployments may return 200"; "on 6.3 confirm" -> "confirm in your deployment's /docs" (x2); "PAT gets 401" -> "API key gets 401" (A).

#### domino-experiment-tracking
- SKILL.md — description: removed the domino-genai-tracing pointer (delisted skill).
- SKILL.md — compatibility/body relabelled to 6.1; outside-run auth = service-account token (or user API key) (A).
- SKILL.md — project visibility "Domino 6.3 also has Public" -> "Public where the deployment allows it".
- SKILL.md — alias promotion qualified with "where the server supports them (check first: MODEL-REGISTRY.md)".
- MODEL-REGISTRY.md — REST registration section: v2/Hugging Face/`loggedModelId` replaced with `POST /api/registeredmodels/v1` and `POST /v1/{modelName}/versions`, spec field list plus `/docs` guidance (registry item).
- MODEL-REGISTRY.md — route table: list -> `GET /api/registeredmodels/v1`; dropped `/unregistered-models` row.
- MODEL-REGISTRY.md — aliases paragraph: removed Cloud/6.3 labels; "run the GET first; 404 -> use tags".
- MODEL-REGISTRY.md — added `ShortLived.ModelRegistry` feature-flag note (optional compat-doc item).
- MODEL-REGISTRY.md — curl comment: PAT -> service-account token or `X-Domino-Api-Key` (A).

#### domino-experiment-setup
- SKILL.md — compatibility/body relabelled to 6.1.
- SKILL.md — removed `domino-trace-setup` pointer; replaced with "GenAI tracing for LLM or agent applications requires Domino 6.2 or later" (delisted skill).

#### domino-model-endpoints
- SKILL.md — compatibility/body relabelled to 6.1; outside-run auth = service-account token or user API key (A); MONITORING.md row no longer advertises CPU/memory; troubleshooting "PATs never work" -> "API keys never work".
- MONITORING.md — removed version-page CPU/memory/traffic/status charts (6.2); replaced with: no such charts on 6.1, admins use Grafana (Admin > Reports > Grafana), non-admins ask an admin; removed Grafana Model Endpoints dashboard deep-link/reference; debugging step 4 now asks an admin for Grafana data; curl comment auth (A).
- SCALING.md — removed hosted-LLM pointer, replaced with "requires Domino 6.2 or later"; Cloud `small-k8s` default note made neutral; Cloud-only `EditCentralConfig` sentence trimmed; cost bullet no longer says "on the version page".
- DEPLOY-ENDPOINT.md — `commits/latest` replaced as in LIFECYCLE.md; PAT -> service-account token / `X-Domino-Api-Key` (A); "Personal Access Token is rejected" -> "API key is rejected"; removed Cloud-only `Discoverable`/`Operator` beta-route sentence.

#### domino-model-delivery
- SKILL.md — compatibility/body relabelled to 6.1; "API keys deprecated; send Bearer" -> service-account Bearer or `X-Domino-Api-Key` (A); "(both specs)" -> Public API.
- EXPORT-API.md — removed "(same content on the 6.3 page)" and "on Domino 6.3 confirm"; AUTH comment = service-account token, with `X-Domino-Api-Key: $DOMINO_USER_API_KEY` alternative; GitHub Actions prose and env comment: PAT removed, "No API key anywhere" removed (A).
- BATCH-SCORING.md — removed "6.3 page" note; alias note no longer Cloud/6.3-labelled; outside AUTH = service-account token or API key (A); "(Public, both specs)" -> "(Public API)" x4; removed "pin a snapshot per asset" from the schedule table (NetApp snapshot pinning at launch is not on 6.1).
- EXPORT-TARGETS.md — removed "(same on 6.3)" x2; deployment targets "(Public API, 6.3 and Cloud)" -> "(Public API)".

#### domino-model-monitoring
- SKILL.md — compatibility/body relabelled to 6.1; outside auth = service-account token or user API key (A); serving-health pointer wording aligned with model-endpoints.
- MONITORING-API.md — token comment: PAT removed; service-account token, or `X-Domino-Api-Key` header (A).

#### Deviations / skipped
- Global change C: docs.domino.ai links left as is (per branch decision). Only link removed: Grafana model-endpoint dashboard page and hosted-LLM page (features/links describing removed content).
- domino-model-serving "Which path applies": not adjusted to cover 6.1.x; removed instead, since its only content was Cloud-only beta routes. No other version checks exist in these skills.
- `commits/latest` replacement in LIFECYCLE.md and DEPLOY-ENDPOINT.md is beyond my rows (it comes from the domino-projects row) but the route is absent on 6.1, so leaving it would break the documented publish flow.
- BATCH-SCORING snapshot-pinning parenthetical removed outright rather than relabelled (unclear what 6.1 supports for Datasets at schedule time).
- MLflow 3 `name=` vs `artifact_path` client note in MODEL-REGISTRY.md kept: it is client-side, not LoggedModel registration.

#### Uncertain
- `POST /api/registeredmodels/v1` and `/v1/{modelName}/versions` bodies on 6.1: written from the 6.3 public spec schemas (`NewRegisteredModelV1`: required `modelName`, `experimentRunId`, `discoverable`; `NewRegisteredModelVersionV1`: required `description`, `experimentRunId`, `artifact`), with `/docs` guidance. Note the v1 create body has no artifact-path field.
- `ShortLived.ModelRegistry` feature-flag note: semantics taken from the compat doc only.
- Project "Public" visibility on 6.1 (worded "where the deployment allows it").
- Admin Grafana location on 6.1 (Admin > Reports > Grafana) and whether endpoint CPU/latency data is there.
- python-domino `commits_list()` sort order on 6.1 (skill tells the reader to check).
- MLflow aliases on 6.1 (MLflow 2.x expected; the skill says to probe the alias GET and fall back to tags).
- Endpoint UI path **Settings** > **Access and Sharing** assumed the same on 6.1.

### Change log: data skills (6.1)

#### domino-data-sdk
- SKILL.md: compatibility and opening line set to Domino 6.1 (branch-wide labels). Pinned `dominodatalab-data==6.3.0` for Domino 6.1.1+ and `==6.2.0` for 6.1.0, with a note that these are Python package versions, and Python 3.9+ (both versions are on PyPI, `requires_python >=3.9`). Dockerfile pin updated (version pin).
- SKILL.md: removed the `domino_data.netapp_volumes` sentence; points to the netapp-volumes skill for mount path or REST access (remove `domino_data.netapp_volumes`).
- SKILL.md: `DOMINO_USER_API_KEY` described as the user API key, not "deprecated, never rely on it"; `api_key=` no longer called deprecated; outside Domino uses a service-account token or `api_key=` with a user API key; PAT and its docs link removed (global A).
- SKILL.md: App-acts-for-viewer bullet replaced with "Apps read as the publisher; viewer reads not available on 6.1" (App viewer pattern).
- SKILL.md: "Exceptions raised by 6.7.4" changed to "by the pinned versions" (version pin).
- DATASETS.md: removed the App-on-behalf-of-user `DatasetClient(token=...)` example (App viewer pattern).
- DATA-SOURCES.md: removed Snowflake `private_key`/`passphrase`, Postgres `client_cert`/`client_key`/`ca_cert`, and the `KeyPair` auth type; added Snowflake `token` (present in both pinned packages); `datetime_precision` noted as package 6.3.0 only; PAT placeholder replaced with a service-account token from an env var (plus `import os`); `api_key=`/`DOMINO_USER_API_KEY` described as the user API key (cert/key-pair item; global A).
- TRAINING-SETS.md: `DOMINO_USER_API_KEY` "(deprecated)" changed to "(user API key)" (global A).
- VECTORDB.md: install pin changed to `==6.3.0` / `==6.2.0` (version pin); removed the LLM Gateway 2.0 pointer and the genai-tracing pointer (delisted skills).

#### netapp-volumes
- SKILL.md: 6.1 labels; description drops "and tags" and the `/remotefs/v1` mention; compatibility uses service-account token or user API key (global A).
- SKILL.md: added base-path guidance (`/remotefs/v1` or `/domino-netapp-volumes/v1`, confirm in `/docs` / `openapi-public.json`); route references made relative to the base (base path item).
- SKILL.md: removed the tagged-snapshot mount column, tag behaviour, pinning at launch, commit messages, `create-snapshot-from-run`, `snapshotNetAppVolumesOnCompletion`, "copied for Project Templates" and `maxSnapshots`; Snapshots section rewritten for the 6.1 UI (Take Snapshot in the Details view, Latest data menu, Readers mark for deletion) (tags/pinning/commit messages item).
- SKILL.md: Roles table drops the `VolumeReader`/`VolumeEditor`/`VolumeOwner` API-value column; grants REST says to copy field values from `GET /volumes/{id}/grants` (6.1 grant body shape).
- API-NETAPP-VOLUMES.md: rewritten. New "Base path" section with a probe; code uses `nv = f"{remotefs_url}/remotefs/v1"` with the alternative noted. Removed `/snapshots/{id}/tags`, `/volumes/{id}/files*`, `/uploads*`, `/webvfs`, bulk-attach and bulk-copy, `create-snapshot-from-run`, `/data-transfers`, `/root-pvcs`, `/staging-volume`, `/volumes/ids`, `/volumes/unique-name`. Body shapes changed to the 6.1 API reference: volume create `{name, filesystemId, capacity, projectId?}` (no grants), snapshot create `{volumeId, name}`, snapshot PUT `{name}`, grants `{volumeId, grants:[{entityId, entityType, accessLevel}]}`, lists `items`/`totalCount`. Volume/snapshot record fields updated to the 6.1 reference. Outside-run auth: service-account token or `X-Domino-Api-Key` (route removals; body shapes; global A).
- API-NETAPP-VOLUMES.md: removed `snapshotNetAppVolumesOnCompletion` from the Jobs section; added "if the deployment rejects `netAppVolumeIds`, confirm the Jobs body in `/docs`".
- DATA-ACCESS.md: removed commit-message row, tag column, tag mounting, pinning, the tagged-snapshot read example, `snapshotNetAppVolumesOnCompletion`, and the "Reference tags" practice (replaced with "Reference snapshot numbers"); snapshot example body `{volumeId, name}` via `nv`; snapshots mount only when selected at launch (from the 6.1 user guide) (tags/pinning item).
- TROUBLESHOOTING.md: removed the "A tag path is missing" section and pinning lines; `data` array changed to `items`; `maxSnapshots` field reference removed; removed `/webvfs` file-route guidance and PAT; added base-path 404 check and 400 body-shape check (TROUBLESHOOTING item; global A).

#### domino-flows
- SKILL.md: 6.1 labels; description says "export to Datasets" (no NetApp); NetApp snapshot mounting and export removed from the rules; `NetAppVolumeSnapshots` dropped from the required-field list, with one line saying NetApp Volumes cannot be mounted in or exported from a flow on 6.1; removed the 6.3/Cloud Flyte native API spec link (NetApp item; Flyte API links item).
- FLOW-BASICS.md: removed `ResolvedMainRepoGitRef`, `UseLatestGitRef`, `ImportedGitRepoOverrides`, `NetAppVolumeSnapshots` (table, import list, required list) and the matching helper kwargs (`resolved_main_git_repo_ref`, `use_latest_git_ref`, `imported_git_repo_overrides`, `netapp_volume_snapshots`) (DominoJobConfig fields item).
- FLOW-BASICS.md: removed `path=` on `Input`/`Output` and the "/mnt works as in a Workspace" behaviour; inputs/outputs only under `/workflow` (task data paths item).
- FLOW-BASICS.md: Re-run no longer offers per-task environment/hardware/Git overrides (rerun overrides item).
- FLOW-BASICS.md: removed the Flyte extensions API link; native API link kept with "describes a later Domino version; if a route returns 404, use the Flows UI"; dropped "(the 6.3 pages are identical)" (Flyte API links item).
- FLOW-BASICS.md: outside-run token comment changed from PAT to service-account token or `X-Domino-Api-Key` (global A).
- EXAMPLES.md: removed `NetAppVolumeSnapshots=[]  # required even when unused`; Example 4 re-run no longer mentions task overrides.

#### domino-datasets
- SKILL.md: 6.1 labels; compatibility outside-run auth is a service-account token or user API key (global A); "6.3 record ... Domino Support on Cloud" changed to "central configuration record"; dropped "(`/6.3/` for self-managed)".
- API.md: "on Domino 6.3 confirm each `/v4` route" changed to "confirm each `/v4` route"; outside-Domino comment names service-account bearer or `X-Domino-Api-Key` (global A); "`totalCount` on Domino Cloud" softened.
- BEST-PRACTICES.md: PAT replaced with service-account token or user API key (global A); "Domino 6.3 enforces" changed to "Domino enforces"; Cloud Support sentence and "on 6.3" removed.

#### domino-data-connectivity
- SKILL.md: 6.1 labels; compatibility no longer mentions Cloud; "Which path applies" now maps `6.1.x` (or any self-managed line) to the self-managed path; Cloud branch kept, without the `/6.3/` admin-pages claim and the "newer than 6.3" line (global B).
- SKILL.md, AWS-IRSA.md, S3-MOUNTPOINT.md, EXTERNAL-DATA-VOLUMES.md, AZURE-CREDENTIALS.md: "6.3" labels on self-managed procedures changed to "6.1" (version labels). EXTERNAL-DATA-VOLUMES.md: the `ShortLived.ExternalDataVolumesFullCensor` flag gets "if your deployment does not list it, ask your administrator" (flag names unverified).

#### Deviations / skipped
- domino-data-sdk certificate/key-pair auth: the compat doc says mark these 6.2+. I removed them instead: neither pinned package (6.2.0 or 6.3.0) has Snowflake `private_key`/`passphrase`, Postgres cert fields, or a `KeyPair` auth type, so with the 6.1 pins they cannot be used.
- netapp-volumes `snapshotNetAppVolumesOnCompletion` (Jobs body): not listed in the compat doc. I removed it as part of the run-snapshot feature set, along with `create-snapshot-from-run`. The 6.1 docs don't mention it.
- netapp-volumes: also removed `/volumes/ids`, `/volumes/unique-name/{uniqueName}`, `/rpc/download-archive`, `/rpc/get-volume-mounts` and the record fields `uniqueName`, `numSnapshots`, `maxSnapshots`, `taxonomyTags`, `properties`, because they are absent from the 6.1 NetApp Volumes API page (docs.dominodatalab.com/en/6.1/api_guide/b3b2a1/domino-netapp-volumes-api/). Added `POST /downloads` and `GET /downloads/{id}`, which that page lists.
- Global C: kept docs.domino.ai links, including `/6.3/` admin links in domino-data-connectivity and domino-datasets and the "Replace `/cloud/` with `/6.3/`" hint in EXTERNAL-DATA-VOLUMES.md. Removed only the Flyte extensions API link, the Flows native-API spec link in SKILL.md, the data-sdk PAT auth link and the NetApp "(API served at `/remotefs/v1`)" note.
- domino-data-connectivity and domino-datasets: kept the remaining Cloud mentions (Support-requested setup, remote Data Plane for EDVs) because they don't mislead a 6.1 reader.

#### Uncertain
- NetApp base path (`/remotefs/v1` vs `/domino-netapp-volumes/v1`). The 6.1 API page documents `/domino-netapp-volumes/v1`; the skill tells the reader to probe and confirm in `/docs`.
- NetApp 6.1 body shapes come from the 6.1 API page, which the compat doc rates Medium confidence. Grants `entityType`/`accessLevel` values are unknown (the page gives examples "user, project" and "read, write, admin"), so the skill says to copy values from `GET .../grants`. Snapshot `version` and the `snapshots/<name>/<number>` mount path are not on the 6.1 page; I kept them, with "on most deployments".
- Whether the in-run `DOMINO_REMOTE_FILE_SYSTEM_HOSTPORT` plus `localhost:8899` bearer pattern applies on 6.1 (the compat doc's live-instance list also questions `localhost:8899`).
- Whether `netAppVolumeIds` on `POST /api/jobs/v1/jobs` and `netAppVolumeMounts` on Workspace sessions exist on 6.1 (kept, with a confirm-in-`/docs` note on the Jobs field).
- `datetime_precision`: the 6.3.0 package sends it, but whether a 6.1 Data Source proxy honours it is unverified.
- Flyte Admin REST routes (relaunch, recover, archive) at `$FLYTE_PLATFORM_URL_HTTP` on 6.1: kept, with a 404 fallback to the UI.
- EDV feature flag `ShortLived.ExternalDataVolumesFullCensor` and the SMB `release_overrides` installer key on 6.1 (compat doc: unverified flag names).

### Change log: compute skills (6.1)

#### domino-llm-access
- SKILL.md — description rewritten: AI Gateway (Gateway LLMs, MLflow Deployment Client, /api/aigateway/v1) and Option A only; Gateway 2.0, Option B, /api/gen-ai/beta, vLLM hosting, migration removed; triggers on "can an LLM be hosted" (llm-access row).
- SKILL.md — compatibility and opening line set to 6.1; outside-run auth = service-account token or user API key (global A).
- SKILL.md — "Which path applies" restructured: 1. AI Gateway (governed path where an administrator has created endpoints), 2. Option A; one line that LLM hosting and LLM Gateway 2.0 are not available on 6.1; version check reads `6.1.x` (global B); endpoint discovery via UI or `GET /api/aigateway/v1/endpoints` (llm-access row).
- SKILL.md — Option B section, in-run-token snippet, PAT/"API keys deprecated" line, Gateway 2.0 paragraph, migration pointer, `domino-genai-tracing` and `domino-llm-gateway` pointers removed; Host an LLM and Gateway 2.0 doc links removed (global C exception: links for removed features).
- SKILL.md — Bedrock `AWS_PROFILE` row: dropped "6.3 / Cloud" labels; reader guidance to use keys if no profile is available (llm-access row, "unverified on 6.1").
- HOST-AN-LLM.md, HOST-AN-LLM-API.md — deleted (exist only for Option B).
- LEGACY-AI-GATEWAY.md — header/gate rewritten: part of 6.1, usable once an administrator has created endpoints (fall back to Option A otherwise; never enable it); 404 retry uses service-account token or API key instead of PAT; "6.3 spec only" label removed; OpenAI-compatible pointer now Option A instead of Option B; "Migrating away" section removed (optional per compat doc; it pointed to Gateway 2.0/Option B).

#### domino-workspaces
- SKILL.md — compatibility/opening line 6.1; outside-run auth per global A.
- SKILL.md — launch step 6: Slurm option and domino-hpc-slurm link removed; "Slurm clusters are not available on Domino 6.1."
- SKILL.md — persistence and SSH notes relabelled (dropped "On Domino 6.3" and the Cloud support clause; setting names unchanged).
- SKILL.md — "Which path applies": `6.1.x` uses the paths table; writable-project-mounts route noted as 6.4+ only (global B).
- SKILL.md — "Coding assistants": DSE does not include assistants; users install them (extension + Home Directory Persistence, or Dockerfile); Gateway 2.0 routing removed. "coding-assistant logins" -> "tool logins".
- SKILL.md — "App Preview is the way to develop a Domino App" replaced with a pointer to domino-apps (App Preview is 6.3).
- API.md — "On 6.3 confirm" relabelled; Slurm removed from clusterType comment, master-tier comment and the Slurm paragraph with its domino-hpc-slurm link.
- JUPYTER.md, VSCODE.md — coding-assistant sections rewritten (user-installed; Gateway 2.0 / domino-llm-gateway link and coding-assistants doc link removed); VS Code intro no longer claims pre-installed assistant extensions.

#### domino-environments
- SKILL.md — compatibility/opening line 6.1; global A.
- SKILL.md — DSE row: `-no-assistants` variant and "coding assistants" removed.
- SKILL.md — REST line "Both specs" -> "On 6.1"; "Which path applies" reads `6.1.x`, v2 routes and name/description PUT marked 6.4+ only (global B).
- API.md — route table column "6.3" -> "6.1", "6.4+ (including Domino Cloud)" -> "6.4+"; version-check text for 6.1.x; beta create heading "6.1", v2 heading "6.4+ only (not on Domino 6.1)"; `slurm` dropped from supportedClusters enum; "on 6.3 confirm" relabelled.

#### domino-distributed-computing
- SKILL.md — description: "Slurm is domino-hpc-slurm" removed.
- SKILL.md — compatibility/opening line 6.1; global A.
- SKILL.md — Slurm pointer replaced by "Slurm clusters are not available on Domino 6.1."; Slurm row removed from the framework table.
- SKILL.md — MPI/cluster image note: 6.1 images tagged `...-domino6.1`, MPI tags carry the Open MPI version; take the exact tag from Domino's 6.1 environment catalog (no full tag invented).
- FRAMEWORK-EXAMPLES.md — "on 6.3 confirm" relabelled.

#### domino-jobs
- SKILL.md — compatibility/opening line 6.1; global A.
- SKILL.md — "both specs" labels removed; "Which path applies" reads `6.1.x`, job-defaults noted as 6.4+ only (global B).
- SKILL.md — Slurm HPC Jobs (`/api/hpc/v1/jobs`, domino-hpc-slurm) doc bullet removed.
- SCRIPT-PATTERNS.md — "Pin the commit after an upload" loop no longer calls `GET /api/projects/beta/projects/{id}/commits/latest` (not in 6.1); uses python-domino `commits_list()[0]` (legacy `/v1/projects/{owner}/{project}/commits`, newest first); "Both routes are in the 6.3 and Cloud specs" replaced with reader guidance for a 404 on the files route; "on 6.3 confirm" relabelled.
- SCHEDULED-JOBS.md — "On 6.3 confirm the bodies" relabelled.

#### domino-launchers
- SKILL.md — compatibility/opening line 6.1; global A.
- SKILL.md — collaborator role grant: "6.3 and Cloud" label removed.
- SKILL.md — "JSON editor exists only on self-managed; on Cloud rebuild" clause removed (Cloud-only branch).
- EXAMPLES.md — "Personal Access Token" -> service-account token, user API key (`X-Domino-Api-Key`) as fallback with 401 guidance.

#### domino-projects
- SKILL.md — compatibility/opening line 6.1 (Cloud visibility/fork caveat dropped); global A.
- SKILL.md — `public` visibility and DFS forks stated without 6.3/Cloud qualifiers; Cloud-only `default-ref` route replaced by "no public route"; "Which path applies" section removed (it only distinguished 6.3 from Cloud).
- PROJECTS-API.md — `commits/latest` row replaced by python-domino `commits_list()` row; "(Cloud)" marker sentence, Cloud-only repository routes (default-ref, readme, file-metadata, rendered-file), "6.3 only"/"6.3 and Cloud"/"on 6.3 confirm" labels removed; fork note "unavailable on Cloud" -> "DFS projects only"; `<PAT credential id>` -> `<Git token credential id>` (Git provider token, not a Domino PAT).

#### Deviations / skipped
- Global C: docs.domino.ai links and their "(same paths under `/6.3/`)" annotations left as is per branch decision; only links for removed features (Host an LLM, LLM Gateway 2.0, coding assistants) were removed.
- domino-projects: global B applied by deleting the "Which path applies" section rather than adding 6.1.x, because its only content was 6.3-vs-Cloud differences that would mislead on 6.1.
- domino-jobs SCRIPT-PATTERNS.md and domino-projects PROJECTS-API.md: instead of only removing `commits/latest`, substituted python-domino `commits_list()` (the commit pin pattern needs some head lookup).
- domino-llm-access: file LEGACY-AI-GATEWAY.md kept under its old name (links elsewhere); its title is now "AI Gateway (Gateway LLMs)".
- domino-environments API.md: "yes, deprecated" in the 6.4+ column for beta create/revision routes kept (fact about the 6.4+ spec, unrelated to API keys).

#### Uncertain
- Whether 6.1 serves `GET /api/projects/v1/projects/{id}/files/{commitId}/{path}/content` (used in the commit-pin loop); reader guidance added.
- `commits_list()` ordering on 6.1 (newest first per python-sdk skill; compat doc asks to confirm sort order).
- Whether the `/u/{owner}/{project}/runLaunchers` web routes accept `X-Domino-Api-Key`; 401 guidance added.
- Bedrock `AWS_PROFILE` credential propagation on 6.1 (compat doc: unverified).
- Exact 6.1 MPI / cluster image tags (`...mpi4.1.4-domino6.1`, medium confidence; not written as a full tag).
- Whether `GET /api/aigateway/v1/endpoints` returns only the caller's permitted endpoints for a non-admin.
