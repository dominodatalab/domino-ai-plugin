"""
Domino GenAI tracing helpers.

Copy this file next to the agent's entry point. It wraps the Domino agents SDK so an
agent can be traced with @add_tracing, scored by evaluators, and grouped into an
evaluation run with DominoAgentContext (or DominoRun).

Requirements (pin all four together; the `agents` extra of dominodatalab 2.2.0 requires
mlflow 3.2.x, and mlflow 3.2.0 cannot end spans with opentelemetry-sdk 1.36 or later):
    mlflow==3.2.0
    dominodatalab[data,agents]==2.2.0
    opentelemetry-sdk<1.36
    opentelemetry-api<1.36

Usage:
    from tracing_setup import (setup_tracing, create_evaluator,
                               create_llm_judge_evaluator, get_aggregation_metrics)
    from domino.agents.tracing import add_tracing
    from domino.agents.logging import DominoAgentContext

    setup_tracing("openai")

    @add_tracing(name="my_agent", span_type="AGENT", evaluator=create_evaluator())
    def my_agent(query: str) -> dict:
        ...
        return {"response": text}

    with DominoAgentContext(agent_config_path="config.yaml",
                            custom_summary_metrics=get_aggregation_metrics()) as run:
        my_agent("Hello")
        print(run.info.run_id)       # run is the mlflow ActiveRun the context manager returns

Facts about the SDK (dominodatalab 2.2.0, domino/agents) this file relies on:
  * add_tracing(name, autolog_frameworks=[], evaluator=None, trace_evaluator=None,
                eagerly_evaluate_streamed_results=True, span_type="UNKNOWN", attributes=None)
  * evaluator(span) receives the finished mlflow.entities.Span: read span.inputs (a dict of
    the traced function's arguments) and span.outputs (its return value); return
    {metric_name: number} (numbers become metrics, strings become labels).
  * If an evaluator raises, the SDK logs the error and records nothing for that trace.
    Do not return made-up default scores on failure.
  * Evaluator results are tags on the shared trace, not on the span. When decorated functions
    nest, the outer function's evaluator runs last and overwrites same-named metrics, so give
    each function's metrics distinct names.
  * Evaluators run only in development: when DOMINO_AGENT_IS_PROD=true (a deployed agent)
    the SDK skips them. Score production traces out of band with search_agent_traces() and
    log_evaluation().
  * DominoRun / DominoAgentContext(experiment_name=None, run_id=None, agent_config_path=None,
    custom_summary_metrics=None). There is no run_name argument. At exit the run logs one
    aggregated metric per (metric, statistic) pair named "<statistic>_<metric>", for example
    mean_response_length; statistics are mean, median, stdev, max, min.
"""

import os
from contextlib import contextmanager

import mlflow

FRAMEWORKS = ("openai", "anthropic", "langchain")
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"   # keep in sync with models.judge in config.yaml
_openai_autolog_enabled = False       # set by setup_tracing("openai"); read by the judge helper


def setup_tracing(framework: str = "openai") -> None:
    """Enable MLflow autologging for one LLM framework before any model call is made."""
    global _openai_autolog_enabled
    if framework not in FRAMEWORKS:
        raise ValueError(f"Unknown framework: {framework!r}. Use one of {FRAMEWORKS}")
    getattr(mlflow, framework).autolog()
    if framework == "openai":
        _openai_autolog_enabled = True
    print(f"Enabled {framework} auto-tracing")


def output_text(outputs) -> str:
    """Best-effort text of a traced function's return value (span.outputs)."""
    if outputs is None:
        return ""
    if isinstance(outputs, dict):
        for key in ("response", "content", "answer", "text"):
            if key in outputs:
                return str(outputs[key])
    return str(outputs)


def input_text(inputs) -> str:
    """Best-effort text of a traced function's arguments (span.inputs)."""
    if isinstance(inputs, dict):
        for key in ("query", "question", "prompt", "message", "messages"):
            if key in inputs:
                return str(inputs[key])
    return str(inputs)


def create_evaluator(metrics=None):
    """
    Return a span evaluator for @add_tracing(evaluator=...).

    Supported metric names: "response_length" (characters in the output text) and
    "confidence" (reported only when the output dict carries a numeric "confidence").
    Add your own metrics to the dict; every value must be a number.
    """
    metrics = list(metrics or ["response_length"])

    def evaluator(span):
        outputs = span.outputs
        scores = {}
        if "response_length" in metrics:
            scores["response_length"] = len(output_text(outputs))
        if "confidence" in metrics and isinstance(outputs, dict):
            confidence = outputs.get("confidence")
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                scores["confidence"] = float(confidence)
        return scores

    return evaluator


@contextmanager
def _openai_autolog_paused():
    """
    Keep the judge's own OpenAI call out of the agent's traces.

    Autologging is process-wide: while the judge runs, OpenAI calls in other threads are not
    traced either. Run evaluation loops single-threaded, or score traces post-hoc in a separate
    Job (see the domino-genai-tracing skill, EVALUATORS.md). No-op unless setup_tracing("openai")
    enabled autologging.
    """
    if not _openai_autolog_enabled:
        yield
        return
    mlflow.openai.autolog(disable=True)
    try:
        yield
    finally:
        mlflow.openai.autolog()


def create_llm_judge_evaluator(judge_model: str = None, client=None):
    """
    Return an LLM-as-judge span evaluator that scores the output 0-1 with an OpenAI-style model.

    client is the OpenAI-compatible client the agent already uses (a provider SDK, a Domino-hosted
    endpoint or LLM Gateway 2.0, where judge_model is a gateway alias); defaults to OpenAI().

    judge_model defaults to the JUDGE_MODEL environment variable, then DEFAULT_JUDGE_MODEL;
    pass the value from config.yaml (models.judge) so the run's parameters and the judge agree.
    A non-numeric judge reply or an API error raises; the SDK logs it and records no score.
    """
    judge_model = judge_model or os.environ.get("JUDGE_MODEL", DEFAULT_JUDGE_MODEL)

    def llm_judge(span):
        from openai import OpenAI

        judge_client = client or OpenAI()
        query = input_text(span.inputs)
        response = output_text(span.outputs)
        prompt = (
            "Rate this response on a scale of 0-10 for relevance, completeness and clarity.\n\n"
            f"Question: {query}\nResponse: {response}\n\n"
            "Reply with only a number from 0 to 10."
        )
        with _openai_autolog_paused():
            completion = judge_client.chat.completions.create(
                model=judge_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0,
            )
        text = completion.choices[0].message.content.strip()
        try:
            score = float(text)
        except ValueError:
            raise ValueError(f"LLM judge returned a non-numeric reply: {text!r}")
        return {
            "llm_judge_score": max(0.0, min(10.0, score)) / 10.0,
            "judge_model": judge_model,     # a string: stored as a label, not aggregated
        }

    return llm_judge


def get_aggregation_metrics(metric_names=None):
    """
    Build the custom_summary_metrics list for DominoAgentContext / DominoRun.

    Each (metric, statistic) pair becomes a run metric named "<statistic>_<metric>", for
    example mean_response_length. Without custom_summary_metrics the SDK logs the mean of
    every metric it finds.
    """
    metric_names = list(metric_names or ["response_length", "llm_judge_score"])
    aggregations = []
    for name in metric_names:
        aggregations.append((name, "mean"))
        if name in ("response_length", "latency"):
            aggregations.append((name, "max"))
        if name in ("llm_judge_score", "confidence"):
            aggregations.append((name, "min"))
    return aggregations


if __name__ == "__main__":
    # Minimal end-to-end example; needs OPENAI_API_KEY as a Domino environment variable.
    from domino.agents.logging import DominoAgentContext
    from domino.agents.tracing import add_tracing
    from openai import OpenAI

    setup_tracing("openai")
    client = OpenAI()
    model = "gpt-4o-mini"

    @add_tracing(name="example_agent", span_type="AGENT", evaluator=create_evaluator())
    def example_agent(query: str) -> dict:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": query}],
        )
        return {"response": response.choices[0].message.content, "model": model}

    with DominoAgentContext(
        agent_config_path="config.yaml",
        custom_summary_metrics=get_aggregation_metrics(["response_length"]),
    ) as run:
        result = example_agent("What is machine learning?")
        print(f"Response: {result['response'][:100]}...")
        print(f"Run ID: {run.info.run_id}")
