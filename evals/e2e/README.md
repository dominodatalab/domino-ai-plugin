# Live end-to-end evals

This harness runs Claude Code with a weak model (Claude Haiku, the tester) **inside real Domino Workspaces**
and grades each session by what happened in Domino. A Fable-class or Astra-class model, the orchestrator, runs
it: it writes or updates the skill, runs the commands below, reads the results, fixes the skill and runs again
until the skill meets the bar in AGENTS.md "Testing new and updated skills" (CONTRIBUTING standards 8 and 14).
Grading looks at the Job that ran and what it printed, the snapshot that exists, the App that answers, the
healthy Model API, the HPC Job that was (or was not) created. The transcript serves only as evidence of process:
which skill loaded, whether a script was uploaded before a start, the exact request body.
It complements the static checks and the `claude plugin eval` cases in `evals/`; see AGENTS.md "Testing new and
updated skills" for when each level applies.

Nothing here ships: `scripts/build-openai.sh` packages `skills/` only, and `claude plugin eval` discovers
`evals/**/case.yaml` and `prompt.md`, which this directory does not contain.

## How a round works

1. **Lanes.** `provision` creates one Project (DFS or Git-based) with a Dataset and one SSH-enabled Workspace per
   lane, named `<type>-<i>`. Variant *i* of `plugin.variants` runs in lane `<type>-<i>`, so variants run in
   parallel and never share a Project.
2. **Prep.** `prep` copies each plugin build and `remote/` into every Workspace, runs `uv sync` for the bundled MCP
   server, records the Dataset paths, and lists anything in the image that could leak Domino skills into a
   no-plugin run.
3. **Sessions.** For each scenario and variant, `run`:
   - resets the Workspace (`remote/reset.sh`: processes from earlier run directories, user-installed packages and
     new Project-root files are removed);
   - applies the scenario's setup in a fresh working directory;
   - starts `claude -p` detached in the Workspace (`remote/run-claude.sh`) with a fresh `CLAUDE_CONFIG_DIR`,
     `--plugin-dir <build>` (or none), `--output-format stream-json`, `--max-turns`, `--no-session-persistence` and
     `--permission-mode bypassPermissions`. Bypass is acceptable only because the Workspace is disposable;
   - streams the transcript back through short SSH polls, redacting it twice;
   - runs the checks against Domino and the Workspace, then the scenario's cleanup.
4. **Report** and **teardown**.

## Requirements

- A Domino deployment with Workspace SSH enabled and an environment that has `sshd`, Claude Code, `uv`, `git` and
  `python3` (the Domino Standard Environment ships them), and a Workspace hardware tier with about 4 GiB of memory.
- The **Dom CLI** for Workspace SSH, from the **Dom CLI toolkit** link under a running SSH-enabled Workspace's
  **Settings > SSH connection**. See
  https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/launch-a-workspace/streamline-local-development-ssh.
  `dom connect` signs in through your browser the first time; if your browser session has expired it waits for you
  and times out, so sign in to Domino in your default browser before a round.
- Locally: Python 3.10+, `uv`, `ssh` (and `rsync`, optional).
- A Domino credential for the harness: a Personal Access Token in the environment variable named by
  `domino.auth.pat_env`, or the Domino CLI's offline token (`domino.auth.mode: keycloak_refresh`).
- A Claude Code OAuth token from `claude setup-token`, saved to the file named by `claude.oauth_token_file` with
  mode 600.

## Secrets

- The Domino access token is minted or read in memory for each API call and never written anywhere.
- The Claude OAuth token is read from `claude.oauth_token_file` and sent to the Workspace **only over SSH stdin**,
  never as an argument. In the Workspace it lives only in the `claude` process environment and in the redaction
  filter's memory. Tool subprocesses run through `CLAUDE_CODE_SHELL_PREFIX`, a wrapper that unsets it, so a model
  running `env` cannot see it. Sessions are not persisted. The redaction filter (`remote/redact.py`) replaces the
  token, `sk-ant-` strings and JWTs before anything reaches disk, and the harness redacts again locally
  (`e2elib/transcript.py`). Remote output files are deleted after each session.
- `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` is not used because it needs bubblewrap, which cannot create namespaces in a
  Workspace container.
- Never commit `config.local.yaml`, `runs/`, `state/` or `builds/`; `.gitignore` excludes them.

## Configuration

Copy `config.example.yaml` to `config.local.yaml` (git-ignored). Every deployment-specific value lives there.

| Key | Meaning |
|---|---|
| `domino.host`, `domino.auth.*` | Domino URL; `pat` (token in `pat_env`) or `keycloak_refresh` (CLI offline token in `token_file`, `realm`, `client_id`) |
| `workspace.environment_id`, `hardware_tier`, `tools`, `ssh_user` | the Workspace each lane starts |
| `workspace.dom_cli`, `ssh_port_base` | Dom CLI path; local ports `base`, `base+10`, ... one per Workspace |
| `workspace.lanes_per_type`, `start_timeout_s` | default lanes per project type; Workspace start timeout |
| `projects.name_prefix`, `git_repo.{uri,service_provider}`, `datasets` | Project names; the public repository behind Git-based Projects; Datasets created before each Workspace starts |
| `compute.job_tier`, `model_api_tier`, `job_timeout_s` | tier ids the prompts name; how long a Job check waits |
| `claude.model`, `max_turns`, `run_timeout_s`, `oauth_token_file`, `extra_env` | the model under test and the session limits |
| `plugin.builds` | name -> local plugin tree (a clone at the commit under test) |
| `plugin.variants`, `variant_build` | variants in lane order; `none` means no `--plugin-dir`; `variant_build` maps repeats (`next-r2: next`) |
| `remote.root`, `run_root`, `reset_between_runs` | remote scratch root outside the Project mounts; per-type parent of the session working directories; the per-session reset |

## Commands

From this directory (`uv` installs PyYAML from the script header):

```bash
git clone -q https://github.com/dominodatalab/domino-ai-plugin builds/next && git -C builds/next checkout -q <commit>
git clone -q https://github.com/dominodatalab/domino-ai-plugin builds/main && git -C builds/main checkout -q main

uv run e2e.py provision --lane dfs-0 --lane dfs-1 --lane dfs-2 --lane git-0 --lane git-1 --lane git-2
uv run e2e.py prep
uv run e2e.py run --run-dir runs/<name> --scenario s12-hpc-submit --scenario s13-hpc-author-dfs \
    --variant next --variant next-r2 --variant none
uv run e2e.py report runs/<name>        # writes runs/<name>/results.md
uv run e2e.py teardown                  # every lane; --lane dfs-1 for one
```

`run` takes the cross product of `--scenario` and `--variant`, groups the sessions by lane and runs the lanes in
parallel; sessions in one lane run one after another. Run separate `run` invocations one after another when
scenarios need different variant sets. `uv run e2e.py connect` restarts `dom connect` for every lane.

Other tools (run them with `uv run tools/<tool>.py`; those that talk to Domino take the config path):

| Tool | Use |
|---|---|
| `tools/dryrun_checks.py` | offline: real scenario YAML and check code against mocked Domino, mocked Workspace and synthetic transcripts. Run it after changing a scenario or a check |
| `tools/show.py TRANSCRIPT [WIDTH]` | condensed transcript: tool calls, results, final reply |
| `tools/regrade.py CONFIG RUN_DIR SCENARIO VARIANT [--cleanup]` | re-run the current checks against a finished session while its lane exists |
| `tools/evidence.py RUN_DIR [--json OUT]` | per-run write-path evidence: pinned commits, creates, log queries, port collisions, `pkill -f` |
| `tools/smoke.py CONFIG [TYPE] [VARIANTS]` | one tiny session per build: auth, model id, plugin and MCP load, token invisible to tools |
| `tools/probe_hpc.py CONFIG` | probes a deployment's HPC/Slurm surface (data planes, `submit-supported`, a start, a Slurm Workspace attach) in a scratch Project, then cleans up |

## Scenarios

`scenarios/*.yaml`, one per user journey. Prompts read like a user's request and never name a skill or route.

| Id | Project | Graded by |
|---|---|---|
| s01-job-stdout | DFS | Job Succeeded, finished before the reply, stdout and reply carry the value |
| s02-large-intermediate | Git | the file is under a Dataset, not `/tmp`, home or the code directory |
| s03-dataset-snapshot | DFS | snapshot active; a tool call read the snapshot (not the live file); row count in the reply |
| s04-api-proxy | Git | the written script runs; it uses `DOMINO_API_PROXY` and no API key |
| s05-app-publish | DFS | App Running and its URL answers 200 |
| s06-mlflow-tracking | Git | MLflow run with the metric in an experiment named with the run tag |
| s07-model-api | DFS | Model API Running, still Running after 60 s, model container loaded, no crash loop; prediction optional (endpoint tokens come only from the UI) |
| s08-genai-tracing | Git | traces in the run's experiment |
| s09-mcp-job | DFS | Job started through the bundled MCP server, Succeeded before the reply, output reported |
| s10-docs-answer | Git | reply carries the documented port and host |
| s11-hpc-availability | Git | platform queried (data planes, `submit-supported`); honest verdict with the prerequisites; nothing created |
| s12-hpc-submit | DFS | support checked or a start attempted with a correct body after an upload; no fallback; nothing created; honest reply |
| s13-hpc-author-dfs / -git | DFS / Git | the written sbatch script: `bash -n`, `--array`, `$SLURM_ARRAY_TASK_ID`, `umask`, results under an existing Dataset, no Workspace paths |
| s14-mpi-disambiguation | Git | an MPI cluster recommended, not Slurm; nothing launched |

### Scenario format

```yaml
id: s12-hpc-submit
title: ...
project_type: dfs                 # dfs or git
timeout_s: 1200
setup:                            # actions before the session: ws_file {path, content}, ws_shell {cmd}
  - type: ws_file
    path: '{{run_dir}}/hpc/sweep.sh'
    content: ...
prompt: |
  ... as a user would write it ...
check:                            # every required check must pass
  - type: nothing_started
  - type: skill_loaded
    skill_regex: 'domino-hpc-slurm'
    only_builds: [next]           # skipped for other builds
  - type: reply_regex
    patterns: ['...']
    required: false               # recorded, not graded
cleanup:                          # delete_apps, delete_model_apis, mlflow_delete_experiments, ws_shell, ws_file
  - type: delete_apps
    name_regex: '{{run_tag}}'
```

Template variables in any string: `{{run_tag}}`, `{{run_dir}}`, `{{run_root}}`, `{{job_tier}}`,
`{{model_api_tier}}`, `{{dataset}}`, `{{dataset_id}}`, `{{datasets_dir}}`, `{{dataset_path}}`, `{{project_name}}`,
`{{project_id}}`, `{{username}}`, `{{home}}`.

Check types (`e2elib/checks.py`):

| Check | Passes when |
|---|---|
| `job_succeeded` | a Job started in the session window Succeeded (`stdout_regex`; `finished_before_reply` requires completion before the session ended) |
| `snapshot_created` | a snapshot of the named Dataset was created in the window and is active |
| `app_running`, `app_url_ok` | the App is Running; its URL answers 200 |
| `model_api_healthy`, `model_api_predicts` | Running twice 60 s apart with `WSGI app 0 ... ready` and no crash loop; a prediction returns 200 |
| `mlflow_runs`, `mlflow_traces` | runs with a metric, or traces, in experiments matching a pattern (queried in the Workspace) |
| `ws_file`, `script_runs`, `source_regex` | a file exists where it should; a script the model wrote runs; its source matches or avoids patterns |
| `script_lint` | `bash -n`, `require`, `require_in_body` (outside `#SBATCH` lines), `forbid`, `dataset_exists` (every Dataset path names an existing Dataset, no `<...>`), `template_name` |
| `nothing_started` | no Job, HPC Job or new Workspace in the Project during the session |
| `skill_loaded`, `tool_used` | the Skill tool loaded a matching skill; a matching tool was called |
| `tool_io_regex` | a call matching `input_regex` returned output matching `output_regex` (`expect: absent` inverts) |
| `conditional_io` | if a call matches `when_input_regex`, it matches `require_input_regex`, avoids `forbid_input_regex`, and a `before_input_regex` call came first |
| `reply_regex`, `reply_not_regex` | the final reply contains, or avoids, patterns |
| `no_domino_skills_visible` | added automatically to every `none` session: the session lists no Domino skill, command or plugin |

Objects are attributed to a session by creation time inside its window and by the per-run tag in names, so
sessions in one lane run sequentially. After changing a scenario or a check, run `tools/dryrun_checks.py` and add
a case for the new behaviour.

## Method

- **Baseline:** include a `none` variant (no plugin) the first time a skill is tested, to show what the plugin adds.
- **Stability:** run each discriminating scenario at least twice on the build under test (`next`, `next-r2`); one
  run can flip.
- **Frozen checks:** write the scenarios and checks before the first run. Change them later only for a harness
  problem (a wrong check, a bad setup), re-grade with `tools/regrade.py`, and say so in the PR.
- **Defects:** record each failure caused by a skill against the owning file, with transcript quotes and API
  evidence, before changing the skill. The orchestrator then fixes the skill; this harness's code never edits
  skills.
- **Iterate** on the fixed build, re-running the failed scenarios plus a short regression pass, until the skill
  meets the bar. The final round adds at least one prompt the skill was not iterated against.
- **Report** pass rates, turns, Claude Code's reported cost and the defects in the PR description, never in skills
  (CONTRIBUTING standard 12).

## Cleanup

`teardown` stops and deletes each lane's Workspace (retrying the delete, which can answer 500 right after a stop),
deletes its Datasets, archives its Project, kills its `dom connect` and removes its `Host` entry from
`~/.domino/ssh/config`. Verify afterwards: each Workspace reads `deleted: true`, each Project returns 404, no
Dataset remains, no `dom connect` process is left, and `~/.domino/ssh/config` holds only entries that were there
before. Scenario cleanups archive Apps and Model APIs; a Model API's deployment is stopped first (archive answers
500 while it runs). Jobs stay in the archived Project's history.

## Behaviour to expect

- Domino Connect SSH sessions can drop mid-session; `run-claude.sh` detaches Claude from SSH and the harness
  reconnects, so a drop costs nothing.
- Claude Code blocks a standalone `sleep`; waiting belongs in a single command or in a tool that waits server-side.
- A Workspace image can preinstall a Domino plugin under `~/.claude`; the fresh `CLAUDE_CONFIG_DIR` keeps it out of
  every session, and `no_domino_skills_visible` proves it for the baseline.
- A Model API prediction needs an access token. The skills create one by API (`domino-model-endpoints`, "Access
  tokens"); `s07` still grades a healthy deployment, records the prediction as optional, and treats asking the user
  for the URL and token as correct.
