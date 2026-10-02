---
name: domino-trace-setup
description: Set up GenAI tracing for an LLM or agent application in Domino by checking MLflow 3.2.0 and Domino SDK requirements, then adding a tracing_setup.py helper, evaluators, a config.yaml, and @add_tracing / DominoRun wiring. Use when the user asks to add tracing, observability, or evaluation to an agent or LLM app running on Domino.
---

# Set Up Domino GenAI Tracing

Instrument an agent or LLM application so its calls, spans, and evaluator scores show up in
Domino experiments. For traditional ML tracking, use the `domino-experiment-setup` skill instead.

## Inputs

1. **LLM framework**: `openai` (default), `anthropic`, or `langchain`. Detect from the code if possible.
2. **Agent name**: name for the traced entry-point function.
3. **Evaluator**: whether to add quality scoring, and whether to use an LLM-as-judge.
4. **Aggregated metrics**: which evaluator metrics to summarize per run.

## Steps

1. **Check requirements.** Confirm `mlflow==3.2.0` and the Domino SDK with agents support are
   installed. If not, tell the user to add them to the environment's Dockerfile:

   ```dockerfile
   RUN pip install mlflow==3.2.0
   RUN pip install "dominodatalab[data,aisystems] @ git+https://github.com/dominodatalab/python-domino.git@master"
   ```

2. **Copy helpers** from this skill's `assets/` folder into the project:
   - `assets/tracing_setup.py`: `setup_tracing(framework)`, `create_evaluator()`,
     `create_llm_judge_evaluator()`, and `get_aggregation_metrics()`.
   - `assets/config.yaml`: agent configuration logged with `DominoRun(agent_config_path=...)`.
     Replace the example model names with the ones the user actually calls.
3. **Instrument the agent.** Decorate the entry point with `@add_tracing` and run it inside
   `DominoRun`, following the example below. Keep the user's existing logic unchanged.
4. **Explain how to view traces** (see "Viewing traces").

## Example traced agent

```python
import mlflow
from domino.agents.tracing import add_tracing
from domino.agents.logging import DominoRun
from openai import OpenAI

mlflow.openai.autolog()
client = OpenAI()

def quality_evaluator(inputs, output):
    return {
        "response_length": len(output.get("response", "")),
        "confidence": output.get("confidence", 0),
    }

@add_tracing(name="my_agent", evaluator=quality_evaluator)
def my_agent(query: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": query}],
    )
    return {
        "response": response.choices[0].message.content,
        "confidence": 0.9,
        "model": "gpt-4o-mini",
    }

if __name__ == "__main__":
    aggregated_metrics = [("response_length", "mean"), ("confidence", "mean")]

    with DominoRun(
        run_name="example-run",
        agent_config_path="config.yaml",
        custom_summary_metrics=aggregated_metrics,
    ) as run:
        for query in ["What is machine learning?", "Explain neural networks"]:
            result = my_agent(query)
            print(f"Q: {query}\nA: {result['response'][:100]}...\n")
        print(f"Run ID: {run.run_id}")
```

## Framework autologging

| Framework | Setup |
|---|---|
| OpenAI | `mlflow.openai.autolog()` then `OpenAI()` |
| Anthropic | `mlflow.anthropic.autolog()` then `Anthropic()` |
| LangChain | `mlflow.langchain.autolog()` then e.g. `ChatOpenAI(model="gpt-4o-mini")` |

## Viewing traces

1. Go to **Experiments** in Domino.
2. Open the experiment the run logged to (by default `tracing-{username}`).
3. Select the run and open the **Traces** tab.

The trace view shows the span tree (agents, tools, messages), token usage, latency, and evaluator
scores.

For evaluators, multi-agent patterns, and `DominoRun` details, use the `domino-genai-tracing` skill.
