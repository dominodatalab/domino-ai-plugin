# GenAI Tracing Setup for Domino

Environment and SDK setup for GenAI tracing on Domino 6.3 and Domino Cloud.

## Environment requirements

The agents SDK (`domino.agents`) ships in the Domino Standard Environment from Domino 6.2, together with a compatible MLflow. Check the versions before changing anything; the examples in this skill need `dominodatalab` 2.1.0 or later (`span_type` and `attributes` on `@add_tracing` arrived in 2.1.0; 2.2.0 is the verified release), MLflow 3.2.x, and an OpenTelemetry SDK below 1.36:

```bash
python - <<'EOF'
import importlib.metadata as m
for p in ("dominodatalab", "mlflow", "opentelemetry-sdk"):
    print(p, m.version(p))
EOF
```

If any import fails, `dominodatalab` is below 2.1.0, MLflow is not 3.2.x, or `opentelemetry-sdk` is 1.36 or later, install the pinned set below in a custom Compute Environment (or in the Workspace for a quick check). The `agents` extra of `dominodatalab` 2.2.0 requires `mlflow-skinny` and `mlflow-tracing` `>=3.2.0,<3.3.0`, and MLflow 3.2.0 cannot end spans with `opentelemetry-sdk` 1.36 or later (verified: 1.45 fails, 1.35 works), so all four pins belong together.

Dockerfile instructions:

```dockerfile
USER root

# MLflow 3.2.x, the Domino SDK with agents (tracing) support, and the OpenTelemetry SDK MLflow 3.2.0 works with
RUN pip install --no-cache-dir mlflow==3.2.0 "dominodatalab[data,agents]==2.2.0" "opentelemetry-sdk<1.36" "opentelemetry-api<1.36"

# Your LLM framework(s); versions that MLflow 3.2.0 autologging supports
RUN pip install openai==1.97.1
RUN pip install anthropic==0.59.0
RUN pip install langchain==0.3.27

USER ubuntu
```

`requirements.txt` alternative:

```text
mlflow==3.2.0
dominodatalab[data,agents]==2.2.0
opentelemetry-sdk<1.36
opentelemetry-api<1.36
openai==1.97.1
anthropic==0.59.0
langchain==0.3.27
```

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

Supported values include `openai`, `anthropic`, `langchain`, `pydantic_ai`, `llama_index` and the other MLflow tracing integrations. Anthropic autologging may not capture every call; add manual spans where needed.

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
print("mlflow", mlflow.__version__)      # 3.2.x
```

Then trace one call. `@add_tracing` creates the trace on its own; no context manager is needed to see it (`gpt-6.1-sol` is an example model name; use one your provider serves):

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

In a Workspace the trace lands in the active MLflow experiment; open **Experiments** and look for it.

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

### Traces missing from the deployed agent's Performance tab

1. Remove `mlflow.set_experiment()` and any `DominoAgentContext` / `DominoRun` around request handling; the SDK routes production traces itself.
2. Confirm `@add_tracing` is on the function that handles the request (it creates the trace).
3. Confirm autolog is enabled (lifespan, or `autolog_frameworks` on the decorator).
4. Confirm MLflow is 3.2.x.

### Traces missing from the Experiments UI

1. The run must be open while the traced functions execute: put the loop inside the `with DominoAgentContext(...)` block.
2. `experiment_name=` must name an existing experiment; otherwise the SDK raises before the run starts.
3. Autolog must be enabled before the first LLM call.

### Evaluator scores missing

- An evaluator that raises is logged by the SDK as `Inline evaluation failed for evaluator, <name>` and records nothing; fix the evaluator.
- Inline evaluators never run when `DOMINO_AGENT_IS_PROD=true`; score production traces out of band ([EVALUATORS.md](./EVALUATORS.md)).
- With a generator function and `eagerly_evaluate_streamed_results=False`, inline evaluators are disabled; use `log_evaluation` afterwards.

### `Failed to end span ...: 'MlflowV3SpanProcessor' object has no attribute '_shutdown'`

The environment has an `opentelemetry-sdk` MLflow 3.2.0 cannot work with (1.36 or later; 1.45 reproduces it, 1.35 works). No traces or aggregated metrics are written. A custom environment built on an image that already carries a newer OpenTelemetry keeps it when only MLflow is pinned, which is why the install line above pins both:

```bash
pip install "opentelemetry-sdk<1.36" "opentelemetry-api<1.36"
```

### `TypeError: add_tracing() got an unexpected keyword argument 'span_type'`

`dominodatalab` is older than 2.1.0. Install the pinned set from "Environment requirements".

### `module 'mlflow' has no attribute 'openai'` or `No module named 'domino.agents'`

```bash
pip install --no-cache-dir mlflow==3.2.0 "dominodatalab[data,agents]==2.2.0" "opentelemetry-sdk<1.36" "opentelemetry-api<1.36"
```

### `This version of Domino doesn't support the agents package`

The SDK checked `GET $DOMINO_API_HOST/version` and found a platform older than 6.2. The skill targets Domino 6.3 and later; do not try to work around the check.

### `openai.AuthenticationError`

Set the provider key as a Domino environment variable, not in code; see the `domino-llm-access` skill. Through the gateway or a Domino-hosted endpoint, a 401 means a missing or expired access token: re-read it before each call.

## Next steps

- [ADD-TRACING-DECORATOR.md](./ADD-TRACING-DECORATOR.md): `@add_tracing`, span types, manual spans
- [DOMINO-RUN.md](./DOMINO-RUN.md): evaluation runs, config file, aggregated metrics
- [MULTI-AGENT-EXAMPLE.md](./MULTI-AGENT-EXAMPLE.md): complete examples
