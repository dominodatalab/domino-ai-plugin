# GenAI Tracing Setup for Domino

Environment and SDK setup for GenAI tracing on Domino 6.3 and Domino Cloud.

## Environment requirements

**In the Domino Standard Environment (DSE), install nothing.** `dominodatalab` 2.2.0 ships the `domino.agents` code; the package's `agents` extra only adds dependencies (`mlflow-skinny`, `mlflow-tracing`, pandas, numpy) that the DSE already has. Tracing, inline span and trace evaluators, `DominoAgentContext` aggregates and parameters, the SDK's `search_traces` and a later `log_evaluation` were verified on the DSE as shipped (Python 3.12, dominodatalab 2.2.0, MLflow 3.3.2, OpenTelemetry 1.44.0), with results identical to an environment pinned to MLflow 3.2.0. Do **not** install the `agents` extra in the DSE: its metadata caps `mlflow-skinny` and `mlflow-tracing` below 3.3, so `pip install "dominodatalab[data,agents]==2.2.0"` downgrades those two to 3.2.0 while `mlflow` itself stays at 3.3.2, a mismatch. That cap is stricter than it needs to be.

Check what you have before changing anything:

```bash
python - <<'EOF'
import importlib.metadata as m
for p in ("dominodatalab", "mlflow", "opentelemetry-sdk"):
    print(p, m.version(p))
EOF
```

The examples need `dominodatalab` 2.1.0 or later (`span_type` and `attributes` on `@add_tracing` arrived in 2.1.0; 2.2.0 is the verified release) and MLflow 3.2 or later.

**In an environment not based on the DSE** (another base image, or one whose MLflow is older than 3.2), install the tracing stack at or below the versions the current DSE ships: `dominodatalab[data]==2.2.0` (the `data` extra for the Data SDK; not the `agents` extra), `mlflow==3.3.2`, and OpenTelemetry, pandas and numpy capped at the DSE's versions.

Dockerfile instructions:

```dockerfile
USER root

# Tracing stack at the versions the current Domino Standard Environment ships (verified there)
RUN pip install --no-cache-dir "dominodatalab[data]==2.2.0" mlflow==3.3.2 \
    "opentelemetry-sdk<=1.44.0" "opentelemetry-api<=1.44.0" "pandas<=2.3.2" "numpy<=2.5.2"

# Your LLM framework(s), verified to produce spans under MLflow 3.2.0 autologging
# (MLflow's own tested range ends at openai 1.97.1, anthropic 0.59.0, langchain 0.3.27; it warns, then works).
# Autologging on MLflow 3.3.2 is untested: no LLM SDK ships in the DSE.
RUN pip install openai==3.29.0
RUN pip install anthropic==1.13.0
# LangChain: the DSE ships langchain 0.3.30 and its jupyter-ai-magics requires langchain<0.4;
# langchain-openai 0.3.35 (newest for langchain-core 0.3.x) requires openai<3, so this line uses openai 2.54.0
RUN pip install langchain==0.3.30 langchain-openai==0.3.35 openai==2.54.0

USER ubuntu
```

`requirements.txt` alternative:

```text
dominodatalab[data]==2.2.0
mlflow==3.3.2
opentelemetry-sdk<=1.44.0
opentelemetry-api<=1.44.0
pandas<=2.3.2
numpy<=2.5.2
openai==3.29.0
anthropic==1.13.0
# LangChain instead of the openai line above: langchain==0.3.30 langchain-openai==0.3.35 openai==2.54.0
```

Older environments only: MLflow 3.2.0 cannot end spans with `opentelemetry-sdk` 1.36 or later (no traces are written); if you must stay on 3.2.0, also pin `opentelemetry-sdk<1.36` and `opentelemetry-api<1.36`. Never add that pin on the DSE: `opentelemetry-api` 1.35 declares `importlib-metadata<8.8` while the DSE ships 8.9, so pip would downgrade importlib-metadata or fall back to OpenTelemetry 1.16.

## Framework auto-logging

Enable auto-tracing for the LLM framework before the first model call. Either pass the framework to the decorator, which calls `mlflow.<framework>.autolog()` once on the first traced call:

```python
@add_tracing(name="agent", autolog_frameworks=["openai", "anthropic"])
```

or call autolog yourself at startup. Each framework in its own `try/except` so one missing package does not block the others:

```python
import mlflow

for fw in ("openai", "anthropic", "langchain"):
    try:
        getattr(mlflow, fw).autolog()
    except Exception as exc:
        print(f"autolog({fw}) skipped: {exc}")
```

Supported values include `openai`, `anthropic`, `langchain`, `pydantic_ai`, `llama_index` and the other MLflow tracing integrations. Anthropic autologging may not capture every call; add manual spans where needed. Autologged LLM spans were verified under MLflow 3.2.0; on the DSE's MLflow 3.3.2 they are untested (no LLM SDK ships in the DSE).

### Where to call autolog

**Deployed agent (FastAPI or Flask app):** at startup, before requests are handled, and nothing else. No `mlflow.set_experiment()`: the SDK selects `agent_experiment_<app id>` when Domino sets `DOMINO_AGENT_IS_PROD=true` and `DOMINO_APP_ID`.

```python
import mlflow
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        mlflow.openai.autolog()
    except Exception:
        pass
    yield

app = FastAPI(lifespan=lifespan)
```

**Evaluation scripts and Jobs:** at the top of the script, before any LLM call. `mlflow.set_experiment()` or `experiment_name=` on the context manager is fine here; the run goes to that experiment.

## Verifying setup

```python
import mlflow
from domino.agents.tracing import add_tracing, search_traces, search_agent_traces
from domino.agents.logging import DominoAgentContext, DominoRun, log_evaluation
print("mlflow", mlflow.__version__)      # 3.3.2 in the current DSE; 3.2 or later works
```

These imports work on the DSE as shipped. Then trace one call. `@add_tracing` creates the trace on its own; no context manager is needed to see it (`gpt-6.1-sol` is an example model name; use one your provider serves):

```python
from domino.agents.tracing import add_tracing
from openai import OpenAI

client = OpenAI()

@add_tracing(name="test_agent", span_type="AGENT", autolog_frameworks=["openai"])
def test_agent(query: str) -> str:
    response = client.chat.completions.create(
        model="gpt-6.1-sol", messages=[{"role": "user", "content": query}])
    return response.choices[0].message.content

print(test_agent("Say hello"))
```

In a Workspace the trace lands in the active MLflow experiment; open **Experiments** and look for it. On MLflow 3.3.2 with OpenTelemetry 1.44 expect one `Failed to end span ... '_metrics'` warning per trace; it is harmless (see Troubleshooting).

Verified on the DSE as shipped: `@add_tracing` with a span and a trace evaluator inside `DominoAgentContext`, manual `mlflow.start_span` children, evaluator results as trace tags, aggregated run metrics and config parameters, `search_traces(run_id=...)`, and a later `log_evaluation`. Untested on MLflow 3.3.2: autologged LLM spans, streamed or generator functions, and the deployed-agent path (`DOMINO_AGENT_IS_PROD`).

## Environment variables

### Model access

Tracing does not depend on where the model runs: `@add_tracing` and autologging capture the call
whichever client the agent uses, so keep the client the agent already has. The client is a separate
choice: LLM Gateway 2.0 where it is installed (`OpenAI(base_url=<gateway URL>/v1, api_key=<in-run
access token>)` with a gateway alias as `model`; `domino-llm-gateway`), a Domino-hosted endpoint
(its **Calling** tab URL and served model name; `domino-llm-access`), or a provider SDK. The first
two need no provider key in the Project. For direct provider calls store API keys as Domino environment variables (**Project > Settings > Environment variables** for a key the Project shares, **Account > Account Settings > User environment variables** for a personal one), never in code, and read them by name:

```python
import os
openai_key = os.environ["OPENAI_API_KEY"]
anthropic_key = os.environ["ANTHROPIC_API_KEY"]
```

### Variables the SDK reads

| Variable | Meaning |
|----------|---------|
| `MLFLOW_TRACKING_URI` | Set by Domino in every execution; required by the SDK |
| `DOMINO_API_HOST` | Set by Domino; the SDK reads `GET $DOMINO_API_HOST/version` to check the platform is 6.2 or later |
| `DOMINO_AGENT_CONFIG_PATH` | Default agent config path when `agent_config_path` is not passed (`./agent_config.yaml` if unset) |
| `DOMINO_AGENT_IS_PROD` | `true` in a deployed agent: traces go to the agent experiment and inline evaluators are skipped |
| `DOMINO_APP_ID` | The deployed agent's id; with `DOMINO_AGENT_IS_PROD` selects `agent_experiment_<id>` |

Also set by Domino: `DOMINO_STARTING_USERNAME`, `DOMINO_PROJECT_NAME`, `DOMINO_PROJECT_ID`, `DOMINO_RUN_ID`.

## Project structure

### Deployed agent (FastAPI)

```
my-agent-app/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, lifespan with autolog (no set_experiment)
│   │   ├── agent/
│   │   │   ├── orchestrator.py # @add_tracing on the agent function; mlflow.start_span for tools
│   │   │   ├── llm_client.py   # LLM calls (autologged, or wrapped in an LLM span)
│   │   │   └── tools.py        # Tool implementations
│   │   └── routers/
│   │       └── agent.py        # Route handler calls the traced function directly
│   └── requirements.txt
├── frontend/
└── app.sh                      # Domino App entry point
```

### Batch evaluation script

```
my-agent-project/
├── agents/
│   ├── classifier.py      # @add_tracing on agent functions
│   ├── responder.py
│   └── evaluators.py      # span and trace evaluators
├── config/
│   └── config.yaml        # agent configuration, logged by agent_config_path
├── sample_questions.csv   # evaluation dataset
├── main.py                # entry point with DominoAgentContext; run as a Job
└── requirements.txt
```

## Troubleshooting

### `Failed to end span ...: 'MlflowV3SpanProcessor' object has no attribute '_metrics'`

Harmless. It is MLflow 3.3.2 with OpenTelemetry 1.44 (the DSE as shipped): OpenTelemetry's span processor runs its self-metrics bookkeeping after the span has been exported, and MLflow's processor lacks that attribute. It fires once per trace on the root span, also with a plain `@mlflow.trace` function and no Domino SDK involved. Traces, spans, evaluator tags and run metrics are all recorded. Do not downgrade or pin anything for it.

### `Failed to end span ...: 'MlflowV3SpanProcessor' object has no attribute '_shutdown'`

Different problem: MLflow 3.2.0 with `opentelemetry-sdk` 1.36 or later. Nothing is written. Either move to the DSE's MLflow 3.3.2 (the install line above) or, if you must stay on 3.2.0, pin `opentelemetry-sdk<1.36` and `opentelemetry-api<1.36`.

### Traces missing from the deployed agent's Performance tab

1. Remove `mlflow.set_experiment()` and any `DominoAgentContext` / `DominoRun` around request handling; the SDK routes production traces itself.
2. Confirm `@add_tracing` is on the function that handles the request (it creates the trace).
3. Confirm autolog is enabled (lifespan, or `autolog_frameworks` on the decorator).
4. Confirm MLflow is 3.2 or later.

### Traces missing from the Experiments UI

1. The run must be open while the traced functions execute: put the loop inside the `with DominoAgentContext(...)` block.
2. `experiment_name=` must name an existing experiment; otherwise the SDK raises before the run starts.
3. Autolog must be enabled before the first LLM call.

### Evaluator scores missing

- An evaluator that raises is logged by the SDK as `Inline evaluation failed for evaluator, <name>` and records nothing; fix the evaluator.
- Inline evaluators never run when `DOMINO_AGENT_IS_PROD=true`; score production traces out of band ([EVALUATORS.md](./EVALUATORS.md)).
- With a generator function and `eagerly_evaluate_streamed_results=False`, inline evaluators are disabled; use `log_evaluation` afterwards.

### `TypeError: add_tracing() got an unexpected keyword argument 'span_type'`

`dominodatalab` is older than 2.1.0. Install `dominodatalab[data]==2.2.0` as in "Environment requirements".

### `No module named 'domino.agents'` or `module 'mlflow' has no attribute 'openai'`

The environment is not the DSE and lacks the SDK or MLflow. Install the set from "Environment requirements" (`dominodatalab[data]==2.2.0`, `mlflow==3.3.2`); the `agents` code is in the base package, no extra needed.

### `This version of Domino doesn't support the agents package`

The SDK checked `GET $DOMINO_API_HOST/version` and found a platform older than 6.2. The skill targets Domino 6.3 and later; do not try to work around the check.

### `openai.AuthenticationError`

Set the provider key as a Domino environment variable, not in code; see the `domino-llm-access` skill. Through the gateway or a Domino-hosted endpoint, a 401 means a missing or expired access token: re-read it before each call.

## Next steps

- [ADD-TRACING-DECORATOR.md](./ADD-TRACING-DECORATOR.md): `@add_tracing`, span types, manual spans
- [DOMINO-RUN.md](./DOMINO-RUN.md): evaluation runs, config file, aggregated metrics
- [MULTI-AGENT-EXAMPLE.md](./MULTI-AGENT-EXAMPLE.md): complete examples
