# DominoAgentContext and DominoRun

`domino.agents.logging` provides two context managers with the same signature:

```python
DominoAgentContext(experiment_name=None, run_id=None, agent_config_path=None, custom_summary_metrics=None)
DominoRun(experiment_name=None, run_id=None, agent_config_path=None, custom_summary_metrics=None)
```

Both start an MLflow run, log the agent configuration YAML as run parameters (and as an MLflow external model of type `Agent`), and at exit compute aggregated metrics over the evaluated traces created inside the block. `DominoAgentContext` additionally tags the run as an agent version (`domino.internal.run.is_agent=true`); use it for agent evaluation scripts, which Experiment Manager can then deploy when they ran as a Job. `DominoRun` is the same for non-agent evaluations.

There is **no `run_name` parameter**; passing one raises `TypeError`. The object returned by `with ... as run` is the `mlflow.ActiveRun`, so the run id is `run.info.run_id`.

| Parameter | Meaning |
|-----------|---------|
| `experiment_name` | Name of an **existing** MLflow experiment to log to. The SDK raises `Could not find experiment with name ...` if it does not exist. Simplest: call `mlflow.set_experiment(name)` first (it creates the experiment if needed and makes it active) and omit this argument; the run then goes to the active experiment. |
| `run_id` | Continue logging to an existing run instead of starting a new one. |
| `agent_config_path` | YAML file to log as parameters. Omitted: `DOMINO_AGENT_CONFIG_PATH`, else `./agent_config.yaml`. A missing file logs a warning and no parameters. |
| `custom_summary_metrics` | List of `(metric_name, statistic)` tuples; statistics are `mean`, `median`, `stdev`, `max`, `min`. Omitted: the mean of every evaluator metric found. |

Not thread-safe: use one context per thread; parallel work inside one context is fine.

## When to use it

| Context | Use it? | Why |
|---------|---------|-----|
| Evaluation script run as a Domino Job | Yes (`DominoAgentContext`) | Creates a deployable agent version with code, config and traces linked |
| Evaluation script run in a Workspace | Yes | Same grouping, for quick checks; not deployable |
| Non-agent batch evaluation | Yes (`DominoRun`) | Run-level aggregation and config tracking |
| **Deployed agent** (Domino App) | **No** | `@add_tracing` alone is sufficient; the SDK routes production traces to `agent_experiment_<app id>` and skips inline evaluators there |

```python
import asyncio

# DEPLOYED AGENT: no context manager
@app.post("/chat")
async def chat(body: dict):
    return await run_agent_turn(body["message"])     # @add_tracing handles tracing

# EVALUATION: context manager around the loop. run_agent_turn is async, so it must be
# awaited here too; calling it bare returns an un-awaited coroutine and creates no trace.
mlflow.set_experiment("agent-eval")
with DominoAgentContext(agent_config_path="config.yaml") as run:
    for item in test_data:
        asyncio.run(run_agent_turn(item["question"]))
```

## Basic usage

```python
import mlflow
from domino.agents.logging import DominoAgentContext

mlflow.set_experiment("support-agent-eval")        # creates it if missing; experiment_name= needs an existing one

with DominoAgentContext(agent_config_path="config.yaml") as run:
    for question in questions:
        my_traced_agent(question)
    print(f"Run ID: {run.info.run_id}")
```

Continue an earlier run:

```python
with DominoAgentContext(run_id="<existing run id>") as run:
    my_traced_agent("one more question")
```

### Resilient wrapper for shared code

Code that also runs outside Domino can tolerate a missing SDK:

```python
from contextlib import contextmanager

try:
    from domino.agents.logging import DominoAgentContext as _Ctx
except ImportError:
    _Ctx = None

@contextmanager
def evaluation_run(**kwargs):
    if _Ctx is None:
        yield None
        return
    with _Ctx(**kwargs) as run:
        yield run
```

## Configuration file

`agent_config_path` points at a YAML file. The SDK flattens nested keys with dots and logs every leaf as an MLflow parameter, so the run records exactly which models, prompts and settings produced its traces.

```yaml
models:
  primary: gpt-6.1-sol        # example model name; use one your provider serves
  judge: gpt-6.1-sol          # example; keep equal to the judge model the evaluator uses

agents:
  classifier:
    temperature: 0.3
    max_tokens: 500
    system_prompt: "You are a classifier."
  responder:
    temperature: 0.7
    max_tokens: 1500
    system_prompt: "You are a helpful assistant."

settings:
  retry_count: 3
  timeout_seconds: 30
```

Logged parameters: `models.primary`, `models.judge`, `agents.classifier.temperature`, and so on. Read the same file in your code so the logged values are the ones in use:

```python
from domino.agents import read_agent_config

config = read_agent_config("config.yaml")
temperature = config["agents"]["classifier"]["temperature"]
```

Switching models is then a config change, visible per run in the UI.

## Aggregated metrics

Evaluators attach metrics to each trace. At exit the context manager reads every evaluated trace of the run and logs one run metric per `(metric, statistic)` pair, named **`<statistic>_<metric>`**:

```python
aggregated = [
    ("classification_confidence", "mean"),
    ("classification_confidence", "min"),
    ("impact_score", "median"),
    ("response_quality", "stdev"),
    ("processing_time", "max"),
]

with DominoAgentContext(agent_config_path="config.yaml", custom_summary_metrics=aggregated) as run:
    for item in batch:
        triage_incident(item)
```

Run metrics: `mean_classification_confidence`, `min_classification_confidence`, `median_impact_score`, `stdev_response_quality`, `max_processing_time`. Without `custom_summary_metrics`, the SDK logs `mean_<metric>` for every metric it finds. Only numeric evaluator results are aggregated; string results are labels. Re-entering the same run with `run_id=` recomputes the aggregates already present on it.

## Complete example

Model names are examples (`gpt-6.1-sol`); use one your provider serves.

```python
import mlflow
from domino.agents.tracing import add_tracing
from domino.agents.logging import DominoAgentContext
from openai import OpenAI

client = OpenAI()

def quality_evaluator(span):
    output = span.outputs or {}
    scores = {"response_length": len(output.get("response", ""))}
    if isinstance(output.get("confidence"), (int, float)):   # omit rather than invent a default
        scores["confidence"] = float(output["confidence"])
    return scores

@add_tracing(name="qa_agent", span_type="AGENT", autolog_frameworks=["openai"], evaluator=quality_evaluator)
def qa_agent(question: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-6.1-sol", messages=[{"role": "user", "content": question}])
    return {"response": response.choices[0].message.content, "confidence": 0.9}

aggregated = [("response_length", "mean"), ("response_length", "max"),
              ("confidence", "mean"), ("confidence", "min")]

mlflow.set_experiment("qa-agent-eval")
with DominoAgentContext(agent_config_path="config.yaml", custom_summary_metrics=aggregated) as run:
    for question in ["What is machine learning?", "How do neural networks work?"]:
        result = qa_agent(question)
        print(f"Q: {question}\nA: {result['response'][:100]}...")
    print(f"Run ID: {run.info.run_id}")
```

## Batch processing pattern

```python
def process_batch(items, batch_name):
    mlflow.set_experiment(f"eval-{batch_name}")                       # get-or-create
    with DominoAgentContext(custom_summary_metrics=[("accuracy", "mean"), ("latency", "max")]) as run:
        results = []
        for item in items:
            try:
                results.append(process_item(item))     # a traced function
            except Exception as exc:
                print(f"Error processing {item}: {exc}")   # the failed trace keeps the error
        return results
```

## Best practices

1. **One run per evaluation configuration.** Compare runs in Experiment Manager (select two to four, **Compare**); for example `mlflow.set_experiment("model-comparison-gpt-vs-claude")` with one run per model, selected through the config file.
2. **Run as a Job** when the result should be deployable; a Workspace run has no code commit lineage.
3. **Keep runs focused**: separate runs for accuracy and latency evaluations rather than one run that does everything.
4. **No context manager in deployed agents**, and no `mlflow.set_experiment()` there either.

## Next steps

- [EVALUATORS.md](./EVALUATORS.md): writing evaluators
- [MULTI-AGENT-EXAMPLE.md](./MULTI-AGENT-EXAMPLE.md): complete example
