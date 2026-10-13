# @add_tracing Decorator Guide

`domino.agents.tracing.add_tracing` is the core mechanism for capturing traces in Domino GenAI applications. The examples build a plain `OpenAI()` client; where LLM Gateway 2.0 is installed the client may point at the gateway instead, with an alias as the model ([TRACING-SETUP.md](./TRACING-SETUP.md#model-access)); the tracing is identical. Signature in `dominodatalab` 2.2.0:

```python
add_tracing(
    name: str,
    autolog_frameworks: list[str] | None = [],
    evaluator: Callable[[mlflow.entities.Span], dict] | None = None,
    trace_evaluator: Callable[[mlflow.entities.Trace], dict] | None = None,
    eagerly_evaluate_streamed_results: bool = True,
    span_type: str | None = "UNKNOWN",
    attributes: dict | None = None,
)
```

`@add_tracing` creates traces on its own; it does not need `DominoAgentContext` or `DominoRun`. In a deployed agent the decorator alone is sufficient. Apply it directly to the function, with no other decorator in between: it inspects the function's signature to record the arguments by name.

## Decorator parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Span (and, for a top-level call, trace) name shown in the UI. Letters, digits, `_` and `-` only. |
| `span_type` | No | Span classification passed to `mlflow.start_span`. Values in MLflow 3.2 and 3.3: `AGENT`, `CHAIN`, `CHAT_MODEL`, `EMBEDDING`, `LLM`, `PARSER`, `RERANKER`, `RETRIEVER`, `TOOL`, `UNKNOWN` (default). Use `AGENT` for the top-level agent function. |
| `autolog_frameworks` | No | MLflow integrations to autolog on the first call, for example `["openai"]`, `["openai", "anthropic"]`, `["pydantic_ai"]`. |
| `evaluator` | No | `evaluator(span) -> dict`; runs after every call with the finished span. See [EVALUATORS.md](./EVALUATORS.md). |
| `trace_evaluator` | No | `trace_evaluator(trace) -> dict`; runs only when this call started and finished the trace, with the complete trace (all child spans). |
| `attributes` | No | Extra attributes set on the span. |
| `eagerly_evaluate_streamed_results` | No | For generator functions. `True` (default): all yielded values are collected as the span's output and evaluated once. `False`: one span per yielded value, inline evaluators disabled. |

Evaluators run only in development mode; when `DOMINO_AGENT_IS_PROD=true` the SDK skips them. Their results are written as tags on the **trace**, not on the span: when decorated functions nest, every evaluator in the call tree writes to the same trace and the outer function's evaluator, which runs last, overwrites same-named metrics. Use distinct metric names per function.

Supported function kinds in `dominodatalab` 2.2.0: plain functions, `async def` coroutines, and sync generators. **Async generators (`async def` with `yield`) are not supported**: the decorator treats them as a plain function, the span ends immediately with the generator object as its output, and every inner span becomes its own orphan trace. For a streaming agent, decorate a coroutine that collects the stream and returns the result, and stream to the client from outside it (see "Streaming agents" below). `span_type` and `attributes` need `dominodatalab` 2.1.0 or later.

## Basic usage

```python
from domino.agents.tracing import add_tracing
from openai import OpenAI

client = OpenAI()

@add_tracing(name="chat_agent", span_type="AGENT", autolog_frameworks=["openai"])
def chat_agent(user_message: str) -> str:
    """Captured: the arguments (span.inputs), the return value (span.outputs),
    timing, every OpenAI call as a child span, and any exception."""
    response = client.chat.completions.create(
        model="gpt-6.1-sol",
        messages=[{"role": "user", "content": user_message}],
    )
    return response.choices[0].message.content
```

Async:

```python
from openai import AsyncOpenAI

aclient = AsyncOpenAI()

@add_tracing(name="agent_turn", span_type="AGENT", autolog_frameworks=["openai"])
async def run_agent_turn(messages: list[dict]) -> dict:
    response = await aclient.chat.completions.create(model="gpt-6.1-sol", messages=messages)
    return {"content": response.choices[0].message.content}
```

## Manual spans

For steps autologging does not cover (tool calls, non-framework HTTP calls, internal processing), add child spans inside the decorated function. Two equivalent ways:

### `mlflow.start_span` context manager

```python
import mlflow

def execute_tool(tool_name: str, tool_input: dict) -> str:
    with mlflow.start_span(name=f"tool:{tool_name}", span_type="TOOL") as span:
        span.set_inputs({"tool": tool_name, "input": tool_input})
        tool_function = TOOL_FUNCTIONS[tool_name]    # your registry of tool functions
        result = tool_function(**tool_input)
        span.set_outputs({"result": result[:500]})
        return result
```

### `@mlflow.trace` decorator

```python
import mlflow
import requests

@mlflow.trace(span_type="TOOL", name="fetch_weather")
def fetch_weather(city: str) -> dict:
    return requests.get("https://example.invalid/weather", params={"city": city}, timeout=10).json()

@mlflow.trace(span_type="LLM", name="custom_llm_call")
def call_custom_model(prompt: str) -> dict:
    return requests.post(MY_ENDPOINT, json={"prompt": prompt}, timeout=60).json()
```

Both appear as typed child spans under the `@add_tracing` span.

## Complete tool-use agent pattern

A self-contained agent loop: `@add_tracing` on the agent, autologged LLM calls, a `TOOL` span per tool execution.

```python
import json
import mlflow
from domino.agents.tracing import add_tracing
from openai import AsyncOpenAI

client = AsyncOpenAI()      # OPENAI_API_KEY from a Domino environment variable
MODEL = "gpt-6.1-sol"

def get_data(table: str) -> str:
    return json.dumps({"table": table, "rows": 42})

def analyze(table: str, metric: str) -> str:
    return json.dumps({"table": table, "metric": metric, "value": 0.87})

TOOL_FUNCTIONS = {"get_data": get_data, "analyze": analyze}
TOOLS = [
    {"type": "function", "function": {"name": "get_data", "description": "Row count of a table",
     "parameters": {"type": "object", "properties": {"table": {"type": "string"}}, "required": ["table"]}}},
    {"type": "function", "function": {"name": "analyze", "description": "Compute a metric for a table",
     "parameters": {"type": "object", "properties": {"table": {"type": "string"}, "metric": {"type": "string"}},
                    "required": ["table", "metric"]}}},
]


def dispatch_tool(name: str, arguments: str) -> str:
    with mlflow.start_span(name=f"tool:{name}", span_type="TOOL") as span:
        kwargs = json.loads(arguments or "{}")
        span.set_inputs({"tool": name, "input": kwargs})
        try:
            tool_function = TOOL_FUNCTIONS[name]
            result = tool_function(**kwargs)
        except Exception as exc:
            result = json.dumps({"error": str(exc)})
        span.set_outputs({"result": result[:500]})
        return result


@add_tracing(name="agent_turn", span_type="AGENT", autolog_frameworks=["openai"])
async def run_agent(messages: list[dict], max_iterations: int = 8) -> dict:
    mlflow.update_current_trace(tags={"actor": "agent"})
    working = [m.copy() for m in messages]
    tool_calls_made = []
    total_input_tokens = total_output_tokens = 0

    for _ in range(max_iterations):
        response = await client.chat.completions.create(model=MODEL, messages=working, tools=TOOLS)
        usage = response.usage
        total_input_tokens += usage.prompt_tokens if usage else 0
        total_output_tokens += usage.completion_tokens if usage else 0
        choice = response.choices[0]

        if choice.finish_reason != "tool_calls":
            span = mlflow.get_current_active_span()
            if span is not None:
                span.set_attributes({"tool_calls": len(tool_calls_made),
                                     "total_input_tokens": total_input_tokens,
                                     "total_output_tokens": total_output_tokens})
            return {"content": choice.message.content, "tool_calls_made": tool_calls_made}

        working.append(choice.message)
        for tc in choice.message.tool_calls:
            result = dispatch_tool(tc.function.name, tc.function.arguments)
            tool_calls_made.append({"name": tc.function.name, "output": result})
            working.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return {"content": "Max iterations reached.", "tool_calls_made": tool_calls_made}
```

Resulting trace tree (MLflow's OpenAI autologging names the span after the client class, `AsyncCompletions` here and `Completions` for a sync `OpenAI()` client, and types chat completions as `CHAT_MODEL`, not `LLM`):

```
agent_turn (AGENT)
├── AsyncCompletions (CHAT_MODEL, autologged: model, messages, tokens, latency)
├── tool:get_data (TOOL)
├── tool:analyze (TOOL)
└── AsyncCompletions (CHAT_MODEL, autologged)
```

## Streaming agents

`@add_tracing` does not support async generators. Collect the stream inside a decorated coroutine, then stream the collected result to the client; the trace gets the full output and the evaluator sees it:

```python
from fastapi.responses import StreamingResponse

@add_tracing(name="chat_turn", span_type="AGENT", autolog_frameworks=["openai"])
async def chat_turn(message: str) -> dict:
    chunks = []
    stream = await client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": message}], stream=True)
    async for event in stream:
        delta = event.choices[0].delta.content or ""
        chunks.append(delta)
    return {"response": "".join(chunks), "chunks": chunks}

@app.post("/chat")
async def chat(body: dict):
    result = await chat_turn(body["message"])          # traced, evaluated
    return StreamingResponse((c for c in result["chunks"]), media_type="text/plain")
```

Token-by-token delivery to the client then starts after the model finished; if that latency is unacceptable, trace the non-streaming parts (tools, retrieval) with `@mlflow.trace` and leave the streaming call untraced.

## Span annotation APIs

```python
import mlflow

# Tag the whole trace (visible in the trace list, usable for filtering)
mlflow.update_current_trace(tags={"session_id": "abc123", "actor": "agent"})

# Attributes on the current span
span = mlflow.get_current_active_span()
if span is not None:
    span.set_attributes({"tool_calls": 5, "model": "gpt-6.1-sol"})
```

## What gets captured

- **Inputs**: every argument of the decorated function, by parameter name, with defaults applied; `self` and `cls` are excluded.
- **Outputs**: the return value (a dict gives the best trace view).
- **Errors**: an exception ends the span with the error and propagates to the caller.
- **Child spans**: autologged framework calls and manual spans; nested `@add_tracing` functions become child spans too.

```python
@add_tracing(name="classifier", span_type="CHAIN")
def classify(text: str) -> str: ...

@add_tracing(name="responder", span_type="CHAIN")
def respond(text: str, category: str) -> str: ...

@add_tracing(name="pipeline", span_type="AGENT")
def pipeline(text: str) -> dict:
    category = classify(text)             # child span
    return {"category": category, "response": respond(text, category)}   # child span
```

## Graceful fallback when the SDK is absent

```python
try:
    from domino.agents.tracing import add_tracing
except ImportError:
    def add_tracing(*_a, **_kw):
        def deco(fn):
            return fn
        return deco
```

## Best practices

1. Put `@add_tracing` on agent entry points (the request handler or the function the evaluation loop calls); use manual spans or nested decorated functions for the steps inside.
2. Give spans descriptive names (`incident_classification_agent`, not `agent1`) and always set `span_type="AGENT"` on the top-level function.
3. Return structured dicts: evaluators read `span.outputs`, and dicts are easier to score than free text.
4. Keep tool spans small: truncate large results before `set_outputs`.

## Next steps

- [DOMINO-RUN.md](./DOMINO-RUN.md): group evaluation traces into runs
- [EVALUATORS.md](./EVALUATORS.md): evaluator patterns
- [MULTI-AGENT-EXAMPLE.md](./MULTI-AGENT-EXAMPLE.md): complete examples
