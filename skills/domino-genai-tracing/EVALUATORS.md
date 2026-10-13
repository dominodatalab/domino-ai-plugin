# GenAI Evaluators Guide

Evaluators score the outputs of traced functions. Scores become metrics on the trace, aggregated per run by `DominoAgentContext` / `DominoRun`, and visible in Experiment Manager.

## Evaluator signatures

The SDK (`dominodatalab` 2.2.0) calls evaluators with MLflow entities, not with raw inputs and outputs:

```python
from mlflow.entities import Span, Trace

def span_evaluator(span: Span) -> dict[str, int | float | str]:
    """Runs after every call of the decorated function.
    span.inputs: dict of the call's arguments by parameter name.
    span.outputs: the return value."""
    return {"metric_name": score}

def trace_evaluator(trace: Trace) -> dict[str, int | float | str]:
    """Runs only when this call started and finished the trace.
    trace.data.spans: every span, including autologged LLM calls and tool spans."""
    return {"metric_name": score}

@add_tracing(name="agent", evaluator=span_evaluator, trace_evaluator=trace_evaluator)
def agent(query: str) -> dict: ...
```

Rules:

- Return a dict. Numeric values are stored as metrics (`domino.prog.metric.<name>` tags on the trace) and can be aggregated; string values are stored as labels. Metric names use letters, digits, `_` and `-`.
- If an evaluator raises, the SDK logs `Inline evaluation failed for evaluator, <name>` and records nothing for that trace. Let failures raise; do not return invented default scores such as 0.5, which would silently pollute the aggregates.
- Evaluators run only in development. In a deployed agent (`DOMINO_AGENT_IS_PROD=true`) they are skipped; see "Production evaluation" below.
- Both evaluators may be given; their results are merged (span results win on name clashes).
- Results are tags on the **trace**, never on an individual span. When decorated functions nest, every evaluator in the call tree writes to the same trace; inner evaluators run first (when their span ends) and the outermost last, so a metric name shared between them keeps only the last value (verified: an inner `impact_score=7.0` was replaced by the outer `0.7`). Prefix metric names per function.
- Omit a metric when the field it needs is absent from `span.outputs`; a default such as `0.0` would be aggregated as a real score.

Helpers used in the examples below:

```python
def output_text(outputs) -> str:
    if isinstance(outputs, dict):
        for key in ("response", "answer", "content", "text"):
            if key in outputs:
                return str(outputs[key])
    return "" if outputs is None else str(outputs)

def input_text(inputs) -> str:
    if isinstance(inputs, dict):
        for key in ("query", "question", "prompt", "message"):
            if key in inputs:
                return str(inputs[key])
    return str(inputs)
```

## Basic evaluators

### Length

```python
def length_evaluator(span):
    length = len(output_text(span.outputs))
    return {"response_length": length, "is_substantial": 1.0 if length > 100 else 0.0}
```

### Keyword presence

```python
def keyword_evaluator(span):
    keywords = ["machine learning", "neural network", "algorithm"]
    text = output_text(span.outputs).lower()
    matches = sum(1 for kw in keywords if kw in text)
    return {"keyword_count": matches, "keyword_coverage": matches / len(keywords)}
```

### Structured output

```python
def confidence_evaluator(span):
    output = span.outputs if isinstance(span.outputs, dict) else {}
    category = output.get("category", "unknown")
    scores = {"has_category": 1.0 if category != "unknown" else 0.0,
              "category": str(category)}        # string: stored as a label
    if isinstance(output.get("confidence"), (int, float)):
        scores["confidence"] = float(output["confidence"])    # omitted when the agent did not report one
    return scores
```

## LLM-as-judge evaluators

Model names in these examples (`gpt-6.1-sol`) are examples; use a model your provider serves, or a gateway alias where the `domino-llm-gateway` extension is installed. The judge's own model call happens after the agent's span has ended. With autologging enabled it is traced too: as a separate trace when the decorated function was the top of the call tree, or as a child span of the still-open outer trace when it was nested. Pause autologging around the judge call to keep judge traffic out of the agent's traces. The pause is process-wide (MLflow autologging has no per-thread state), so an agent call running concurrently in another thread loses its LLM spans while a judge runs: keep evaluation loops single-threaded, or move LLM judging to a post-hoc Job (see below). The helper assumes `mlflow.openai.autolog()` was enabled at startup; do not use it otherwise, since it would switch autologging on.

```python
from contextlib import contextmanager
import mlflow
from openai import OpenAI

judge_client = OpenAI()           # or the LLM Gateway 2.0 client (then an alias as model); TRACING-SETUP.md, Model access
mlflow.openai.autolog()          # enabled at startup; autolog_paused() restores this state

@contextmanager
def autolog_paused():
    mlflow.openai.autolog(disable=True)
    try:
        yield
    finally:
        mlflow.openai.autolog()

def llm_judge_evaluator(span):
    prompt = (
        "Rate the following response on a scale of 0-10 for relevance, completeness and clarity.\n\n"
        f"Question: {input_text(span.inputs)}\nResponse: {output_text(span.outputs)}\n\n"
        "Respond with only a number 0-10."
    )
    with autolog_paused():
        reply = judge_client.chat.completions.create(
            model="gpt-6.1-sol", messages=[{"role": "user", "content": prompt}],
            max_tokens=10, temperature=0)
    text = reply.choices[0].message.content.strip()
    score = float(text)            # raises on a non-numeric reply: the SDK logs it, no score is recorded
    return {"llm_judge_score": max(0.0, min(10.0, score)) / 10.0}
```

### Multi-criteria judge

```python
import json

def multi_criteria_judge(span):
    prompt = (
        "Evaluate this response. Rate each criterion 0-10 and reply with JSON only: "
        '{"relevance": X, "completeness": X, "accuracy": X, "clarity": X}\n\n'
        f"Question: {input_text(span.inputs)}\nResponse: {output_text(span.outputs)}"
    )
    with autolog_paused():
        reply = judge_client.chat.completions.create(
            model="gpt-6.1-sol", messages=[{"role": "user", "content": prompt}],
            max_tokens=100, temperature=0, response_format={"type": "json_object"})
    scores = json.loads(reply.choices[0].message.content)
    return {k: float(v) / 10.0 for k, v in scores.items()}
```

### Pairwise comparison against a baseline

```python
def make_pairwise_judge(baseline_outputs: dict[str, str]):
    """baseline_outputs maps a question to the baseline system's answer."""
    def pairwise_judge(span):
        question = input_text(span.inputs)
        baseline = baseline_outputs.get(question)
        if baseline is None:
            return {}                                  # nothing to compare; records nothing
        prompt = (
            f"Question: {question}\n\nResponse A (baseline): {baseline}\n"
            f"Response B (new): {output_text(span.outputs)}\n\n"
            "Which response is better? Reply with A, B or TIE."
        )
        with autolog_paused():
            reply = judge_client.chat.completions.create(
                model="gpt-6.1-sol", messages=[{"role": "user", "content": prompt}], max_tokens=5, temperature=0)
        verdict = reply.choices[0].message.content.strip().upper()
        return {"wins_vs_baseline": 1.0 if verdict == "B" else 0.0,
                "ties_vs_baseline": 1.0 if verdict == "TIE" else 0.0}
    return pairwise_judge
```

## Trace evaluators

Use `trace_evaluator` when the score depends on the inner spans, for example tool usage or total tokens:

```python
def trace_tool_usage(trace):
    spans = trace.data.spans
    tool_spans = [s for s in spans if s.span_type == "TOOL"]
    llm_spans = [s for s in spans if s.span_type in ("LLM", "CHAT_MODEL")]
    return {"tool_calls": len(tool_spans), "llm_calls": len(llm_spans), "span_count": len(spans)}
```

## Domain-specific evaluators

### Classification

```python
VALID = {"bug", "feature", "question", "other"}

def classification_evaluator(span):
    output = span.outputs if isinstance(span.outputs, dict) else {}
    scores = {"is_valid_category": 1.0 if output.get("category", "") in VALID else 0.0}
    confidence = output.get("confidence")
    if isinstance(confidence, (int, float)):
        scores["classification_confidence"] = float(confidence)
        scores["high_confidence"] = 1.0 if confidence > 0.8 else 0.0
    return scores
```

### RAG

```python
def rag_evaluator(span):
    inputs = span.inputs or {}
    output = span.outputs if isinstance(span.outputs, dict) else {}
    context_words = set(str(inputs.get("context", "")).lower().split())
    answer = str(output.get("answer", ""))
    overlap = len(context_words & set(answer.lower().split())) / max(len(context_words), 1)
    sources = output.get("sources", [])
    return {"context_utilization": overlap, "source_count": len(sources),
            "has_sources": 1.0 if sources else 0.0, "answer_length": len(answer)}
```

### Safety (simple keyword check; replace with a real classifier for production use)

```python
UNSAFE = ("harmful", "illegal", "violence", "hate")

def safety_evaluator(span):
    text = output_text(span.outputs).lower()
    flags = sum(1 for p in UNSAFE if p in text)
    return {"safety_flag_count": flags, "is_safe": 1.0 if flags == 0 else 0.0}
```

An evaluator like this scores a **finished** trace after the fact; it does not stop anything. Where the LLM Gateway 2.0 extension is installed and the requirement is to block or redact content, use the gateway's guardrails: the administrator configures rules that screen prompts and responses at call time (deny, redact or log), which is a different job from scoring. The two combine well: guardrails enforce, evaluators measure. Tracing itself does not depend on the gateway. See the `domino-llm-gateway` skill.

## Composite and conditional evaluators

```python
def composite_evaluator(span):
    scores = {}
    scores.update(length_evaluator(span))
    scores.update(safety_evaluator(span))
    scores.update(llm_judge_evaluator(span))
    scores["overall_score"] = (scores["llm_judge_score"] * 0.5 + scores["is_safe"] * 0.3
                               + min(scores["response_length"] / 500, 1.0) * 0.2)
    return scores

def conditional_evaluator(span):
    query_type = (span.inputs or {}).get("query_type", "general")
    scores = {"response_length": len(output_text(span.outputs))}
    if query_type == "classification":
        scores.update(classification_evaluator(span))
    elif query_type == "rag":
        scores.update(rag_evaluator(span))
    return scores
```

Keep the metric set stable across calls so aggregates are comparable between runs.

## Post-hoc evaluation of an evaluation run

Score traces after a run finished. `search_traces` returns `SearchTracesResponse(data: list[TraceSummary], page_token)`; each `TraceSummary` has `id`, `name`, `spans` (list of `SpanSummary` with `inputs` and `outputs`; `spans[0]` is the decorated function's span) and `evaluation_results`.

```python
from domino.agents.tracing import search_traces
from domino.agents.logging import log_evaluation

def add_post_hoc_evaluations(run_id: str):
    page_token = None
    while True:
        page = search_traces(run_id=run_id, page_token=page_token)
        for trace in page.data:
            root = trace.spans[0]
            score = my_scoring_function(root.inputs, root.outputs)
            log_evaluation(trace_id=trace.id, name="combined_quality_score", value=round(score, 2))
        page_token = page.page_token
        if not page_token:
            break
```

`search_traces(run_id, trace_name=None, start_time=None, end_time=None, page_token=None, max_results=None)` filters by the run and optionally by trace name and time window (`datetime` values).

### Human-in-the-loop

```python
for trace in search_traces(run_id=run_id).data:
    root = trace.spans[0]
    print("Input:", root.inputs)
    print("Output:", root.outputs)
    rating = input("Rate 1-5: ")
    log_evaluation(trace_id=trace.id, name="human_rating", value=float(rating) / 5.0)
```

Reviewers can also add metrics and labels per trace in the UI (**Add Metric/Label** on the Traces tab).

## Production evaluation of a deployed agent

Inline evaluators do not run in production. Write a separate script that fetches the deployed agent's traces, scores them, and logs the scores back; schedule it as a Domino Job so the agent's latency is unaffected. The agent id and version come from the agent's **Evaluation setup** button in the UI.

```python
from domino.agents.tracing import search_agent_traces
from domino.agents.logging import log_evaluation

AGENT_ID = "<agent id>"
VERSION = "<agent version id>"

page_token = None
while True:
    page = search_agent_traces(agent_id=AGENT_ID, agent_version=VERSION, page_token=page_token)
    for trace in page.data:
        root = trace.spans[0]
        already = {r.name for r in trace.evaluation_results}
        if "my_eval_metric" in already:
            continue                                    # idempotent re-runs
        score = my_evaluate(root.inputs, root.outputs)
        log_evaluation(trace_id=trace.id, name="my_eval_metric", value=score)
    page_token = page.page_token
    if not page_token:
        break
```

`search_agent_traces(agent_id, agent_version=None, trace_name=None, start_time=None, end_time=None, page_token=None, max_results=None)`; omit `agent_version` to search every version. Scores appear on the agent's **Performance** tab.

## Patterns

### Factory with parameters

```python
def create_threshold_evaluator(threshold: float):
    def evaluator(span):
        output = span.outputs if isinstance(span.outputs, dict) else {}
        confidence = output.get("confidence")
        if not isinstance(confidence, (int, float)):
            return {}                                   # nothing to score; records nothing
        return {"meets_threshold": 1.0 if confidence >= threshold else 0.0, "confidence": float(confidence)}
    return evaluator

@add_tracing(name="agent", evaluator=create_threshold_evaluator(0.9))
def my_agent(query: str) -> dict: ...
```

### Caching expensive judge calls

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_judge(question: str, answer: str) -> float:
    with autolog_paused():
        reply = judge_client.chat.completions.create(
            model="gpt-6.1-sol", messages=[{"role": "user", "content": f"Rate 0-10: {question} -> {answer}"}],
            max_tokens=5, temperature=0)
    return float(reply.choices[0].message.content.strip()) / 10

def efficient_evaluator(span):
    return {"quality_score": cached_judge(input_text(span.inputs), output_text(span.outputs))}
```

## Best practices

1. **Stable metric names** across calls and runs, so aggregates and comparisons line up.
2. **Fail loudly**: let parsing and API errors raise; the SDK logs them and the trace simply has no score, which is visible. A fabricated default is not.
3. **Keep inline evaluators fast**; reserve LLM judges for the metrics that need them, or move them to a post-hoc Job.
4. **Document the metrics** an evaluator returns and their ranges (0-1 is easiest to compare).
5. **Pause autologging** inside judge calls so judge traffic does not appear as agent traces.

## Next steps

- [MULTI-AGENT-EXAMPLE.md](./MULTI-AGENT-EXAMPLE.md): evaluators in a complete pipeline
