---
name: domino-trace-setup
description: Set up GenAI tracing for an LLM or agent application in Domino by checking the mlflow 3.2.0 and Domino SDK (dominodatalab[agents] 2.2.0) requirements, then adding a tracing_setup.py helper, span evaluators, a config.yaml, and @add_tracing / DominoAgentContext wiring. Use when the user asks to add tracing, observability, or evaluation to an agent or LLM app running on Domino.
compatibility: Domino 6.3 and Domino Cloud (the agents SDK requires Domino 6.2 or later and mlflow 3.2.x). Runs inside a Domino Workspace or Job, where MLFLOW_TRACKING_URI and DOMINO_API_HOST are set by Domino.
---

# Set Up Domino GenAI Tracing

Applies to Domino 6.3 and Domino Cloud.

Instrument an agent or LLM application so its calls, spans, and evaluator scores show up in
Domino's Experiment Manager. For traditional ML tracking, use the `domino-experiment-setup`
skill instead. For evaluator patterns, multi-agent examples and the full context-manager
reference, use the `domino-genai-tracing` skill.

## Inputs

1. **LLM framework**: `openai` (default), `anthropic`, or `langchain`. Detect from the code if possible.
2. **Agent name**: name for the traced entry-point function (letters, digits, `_` and `-` only).
3. **Evaluator**: whether to add quality scoring, and whether to use an LLM-as-judge.
4. **Aggregated metrics**: which evaluator metrics to summarize per run, and with which statistic.

Model access is not an input. Tracing instruments whichever client the agent already uses (a
provider SDK, a Domino-hosted endpoint, or LLM Gateway 2.0 where it is installed: `domino-llm-access`,
`domino-llm-gateway`); do not change it. Pass that client to `create_llm_judge_evaluator(client=...)`
so the judge shares it; through the gateway, model names are aliases.

## Steps

1. **Check requirements.** The Domino Standard Environment on 6.3 and Cloud ships the agents SDK,
   but the examples need `dominodatalab` 2.1.0 or later (`span_type` on `@add_tracing`), mlflow
   3.2.x, and `opentelemetry-sdk` below 1.36 (mlflow 3.2.0 cannot end spans with a newer one):

   ```bash
   python -c "import importlib.metadata as m; print({p: m.version(p) for p in ('dominodatalab', 'mlflow', 'opentelemetry-sdk')})"
   ```

   If anything is missing or outside those ranges, add the pinned set to the environment's
   Dockerfile instructions (or `requirements.txt`); the four pins belong together:

   ```dockerfile
   RUN pip install mlflow==3.2.0 "dominodatalab[data,agents]==2.2.0" "opentelemetry-sdk<1.36" "opentelemetry-api<1.36"
   ```

2. **Copy helpers** from this skill's `assets/` folder next to the agent's entry point:
   - `assets/tracing_setup.py`: `setup_tracing(framework)`, `create_evaluator()`,
     `create_llm_judge_evaluator()`, `get_aggregation_metrics()`, plus `input_text()` and
     `output_text()` for reading a span.
   - `assets/config.yaml`: agent configuration logged as run parameters through
     `agent_config_path`. Replace the model names with the ones the user actually calls; keep
     `models.judge` equal to the judge model the evaluator uses.
3. **Instrument the agent.** Decorate the entry point with `@add_tracing` and run the evaluation
   loop inside `DominoAgentContext`, as below. Keep the user's existing logic unchanged.
4. **Explain how to view traces** (see "Viewing traces").

## Example traced agent

```python
import mlflow
from domino.agents.tracing import add_tracing
from domino.agents.logging import DominoAgentContext
from openai import OpenAI

mlflow.openai.autolog()
client = OpenAI()     # the agent's existing client; a gateway or Domino-hosted-endpoint client traces the same way

def quality_evaluator(span):
    """Span evaluator: span.inputs is a dict of the call's arguments, span.outputs its return value."""
    output = span.outputs or {}
    scores = {"response_length": len(output.get("response", ""))}
    if isinstance(output.get("confidence"), (int, float)):   # report it only when the agent set it
        scores["confidence"] = float(output["confidence"])
    return scores

@add_tracing(name="my_agent", span_type="AGENT", evaluator=quality_evaluator)
def my_agent(query: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": query}],
    )
    return {"response": response.choices[0].message.content, "confidence": 0.9, "model": "gpt-4o-mini"}

if __name__ == "__main__":
    aggregated_metrics = [("response_length", "mean"), ("confidence", "mean"), ("confidence", "min")]
    mlflow.set_experiment("my-agent-eval")        # creates the experiment if it does not exist

    with DominoAgentContext(
        agent_config_path="config.yaml",
        custom_summary_metrics=aggregated_metrics,
    ) as run:                                      # run is the mlflow ActiveRun
        for query in ["What is machine learning?", "Explain neural networks"]:
            result = my_agent(query)
            print(f"Q: {query}\nA: {result['response'][:100]}...\n")
        print(f"Run ID: {run.info.run_id}")
```

Facts the example depends on (dominodatalab 2.2.0, `domino/agents`):

- `add_tracing(name, autolog_frameworks=[], evaluator=None, trace_evaluator=None, eagerly_evaluate_streamed_results=True, span_type="UNKNOWN", attributes=None)`. Put it directly on the function, with no decorator in between.
- The evaluator receives the finished span and returns `{metric: number}`; a string value is stored as a label. If it raises, the SDK logs the error and records nothing: never return a made-up default score, and omit a metric whose input is missing.
- Every evaluator result in a call tree is written to the shared **trace**, not to its span; when decorated functions nest, the outer evaluator runs last and overwrites same-named metrics. Give each function's metrics distinct names.
- Evaluators run only in development. In a deployed agent (`DOMINO_AGENT_IS_PROD=true`) the SDK skips them; score production traces out of band (`domino-genai-tracing` skill, EVALUATORS.md).
- `DominoAgentContext` and `DominoRun` take `experiment_name`, `run_id`, `agent_config_path`, `custom_summary_metrics` and nothing else (no `run_name`). `DominoAgentContext` marks the run as an agent version, which the Experiment Manager can deploy when the script ran as a Job. `experiment_name` must name an experiment that already exists (the SDK raises otherwise); `mlflow.set_experiment(name)` beforehand creates it and makes it the active experiment the run then uses.
- At exit the context manager logs one run metric per `(metric, statistic)` pair, named `<statistic>_<metric>` (for example `mean_response_length`); statistics are `mean`, `median`, `stdev`, `max`, `min`. Without `custom_summary_metrics` it logs the mean of every metric.

## Framework autologging

| Framework | Setup |
|---|---|
| OpenAI | `mlflow.openai.autolog()` then `OpenAI()` |
| Anthropic | `mlflow.anthropic.autolog()` then `Anthropic()` (may need manual spans for some calls) |
| LangChain | `mlflow.langchain.autolog()` then e.g. `ChatOpenAI(model="gpt-4o-mini")` |

`@add_tracing(autolog_frameworks=["openai"])` does the same lazily on the first traced call.

## Viewing traces

1. Go to **Experiments** in the Domino project.
2. Open the experiment the run logged to and select the run (an agent version).
3. Open the **Traces** tab: one trace per call of the decorated function, with the span tree
   (agent, tools, LLM calls), token usage, latency and evaluator scores. Aggregated metrics are
   on the run.

Run the evaluation script as a Domino Job rather than from the Workspace when the run should be
deployable as an agent: only Job-originated runs keep the code commit and config lineage.

Docs: https://docs.domino.ai/cloud/platform-capabilities/features/agents/develop (6.3: replace `cloud` with `6.3`).
