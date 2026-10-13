# Multi-Agent Tracing Examples

Two complete, self-contained examples:

1. **[Deployed agent](#deployed-agent-example)**: a FastAPI tool-use agent deployed as a Domino App; traces appear on the agent's Performance tab.
2. **[Batch evaluation](#batch-evaluation-example)**: a pipeline of four agents evaluated under `DominoAgentContext`; traces appear in Experiment Manager.

Both use the OpenAI SDK with `OPENAI_API_KEY` stored as a Domino environment variable. Where LLM Gateway 2.0 is deployed, build the client against it instead (`domino-llm-gateway`), or against a Domino-hosted endpoint (`domino-llm-access`); the tracing code does not change.

---

## Deployed agent example

### Architecture

```
backend/
├── main.py              # FastAPI app, lifespan with autolog
├── agent/
│   ├── orchestrator.py  # @add_tracing on the agent loop, TOOL spans
│   ├── llm_client.py    # the LLM call (autologged)
│   └── tools.py         # tool implementations and schemas
├── routers/
│   └── agent.py         # route handler; no DominoAgentContext
└── app.sh
```

### main.py

```python
import mlflow
from contextlib import asynccontextmanager
from fastapi import FastAPI
from routers.agent import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # autolog only; no mlflow.set_experiment() in a deployed agent
    try:
        mlflow.openai.autolog()
    except Exception:
        pass
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(router)
```

### agent/tools.py

```python
import json

def query_data(table: str) -> str:
    return json.dumps({"table": table, "rows": 1250})

def analyze(table: str, metric: str) -> str:
    return json.dumps({"table": table, "metric": metric, "value": 0.87})

TOOL_FUNCTIONS = {"query_data": query_data, "analyze": analyze}

TOOLS = [
    {"type": "function", "function": {
        "name": "query_data", "description": "Row count of a table",
        "parameters": {"type": "object", "properties": {"table": {"type": "string"}}, "required": ["table"]}}},
    {"type": "function", "function": {
        "name": "analyze", "description": "Compute a metric for a table",
        "parameters": {"type": "object",
                       "properties": {"table": {"type": "string"}, "metric": {"type": "string"}},
                       "required": ["table", "metric"]}}},
]
```

### agent/llm_client.py

```python
import os
from openai import AsyncOpenAI

MODEL = os.environ.get("AGENT_MODEL", "gpt-6.1-sol")   # example default; use one your provider serves
SYSTEM_PROMPT = "You are a data assistant. Use the tools to answer questions about tables."

client = AsyncOpenAI()      # OPENAI_API_KEY from a Domino environment variable

async def create_message(messages: list, tools: list):
    """One chat completion. Autologging records it as an LLM span with token usage."""
    return await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        tools=tools,
        max_tokens=1024,
    )
```

### agent/orchestrator.py

```python
import json
import mlflow
from agent.llm_client import MODEL, create_message
from agent.tools import TOOL_FUNCTIONS, TOOLS

try:
    from domino.agents.tracing import add_tracing
except ImportError:                      # lets the app run where the SDK is absent
    def add_tracing(*_a, **_kw):
        def deco(fn):
            return fn
        return deco


def _annotate_active_span(attrs: dict) -> None:
    span = mlflow.get_current_active_span()
    if span is not None:
        span.set_attributes(attrs)


def execute_tool(name: str, arguments: str) -> str:
    """Execute one tool call inside a TOOL span."""
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
async def run_agent(messages: list[dict], context: str = "") -> dict:
    """Core agent loop. @add_tracing creates the outer AGENT span."""
    mlflow.update_current_trace(tags={"context": context, "actor": "agent"})

    working = [m.copy() for m in messages]
    tool_calls_made = []
    total_input_tokens = total_output_tokens = 0

    for _ in range(8):
        response = await create_message(working, TOOLS)
        if response.usage:
            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
        choice = response.choices[0]

        if choice.finish_reason != "tool_calls":
            _annotate_active_span({"tool_calls": len(tool_calls_made),
                                   "total_input_tokens": total_input_tokens,
                                   "total_output_tokens": total_output_tokens,
                                   "model": MODEL})
            return {"content": choice.message.content, "tool_calls_made": tool_calls_made}

        working.append(choice.message)
        for tc in choice.message.tool_calls:
            result = execute_tool(tc.function.name, tc.function.arguments)
            tool_calls_made.append({"name": tc.function.name, "arguments": tc.function.arguments})
            working.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return {"content": "Max iterations reached.", "tool_calls_made": tool_calls_made}
```

### routers/agent.py

```python
from fastapi import APIRouter
from pydantic import BaseModel
from agent.orchestrator import run_agent

router = APIRouter()

class ChatRequest(BaseModel):
    messages: list[dict]
    context: str = ""

@router.post("/chat")
async def chat(request: ChatRequest):
    """No DominoAgentContext: @add_tracing on run_agent handles tracing, and in a deployed
    agent the SDK routes traces to agent_experiment_<app id>."""
    return await run_agent(request.messages, request.context)
```

### Trace tree on the agent's Performance tab

```
agent_turn (AGENT)
├── AsyncCompletions (CHAT_MODEL, autologged: model, messages, tokens, latency)
├── tool:query_data (TOOL)
├── tool:analyze (TOOL)
└── AsyncCompletions (CHAT_MODEL, autologged)
```

MLflow's OpenAI autologging names the span after the client class (`Completions` for a sync `OpenAI()` client, `AsyncCompletions` for `AsyncOpenAI()`) and types chat completions as `CHAT_MODEL`, not `LLM`.

Inline evaluators do not run here; score production traces with a scheduled Job ([EVALUATORS.md](./EVALUATORS.md), "Production evaluation").

---

## Batch evaluation example

An incident-triage pipeline with four agents, evaluated under `DominoAgentContext`. Run `main.py` as a Domino Job to create a comparable, deployable agent version; traces appear in **Experiments**.

1. **Classifier**: categorizes incidents and assigns urgency
2. **Impact**: assesses blast radius and affected users
3. **Resource**: matches responders by skills
4. **Response**: drafts stakeholder communications

**Where evaluator scores go.** The SDK writes every evaluator result as a tag on the **trace**, not on the span whose evaluator produced it. In a call tree of decorated functions the inner evaluators run first (when their spans end) and the outer one runs last, so a metric name used by two evaluators keeps only the last value (verified with 2.2.0: an inner `impact_score=7.0` was silently replaced by the outer `0.7`). Prefix each agent's metrics with the agent's name, as below, and keep the pipeline-level names distinct.

### Project structure

```
incident-triage/
├── agents/
│   ├── __init__.py
│   ├── common.py
│   ├── classifier.py
│   ├── impact.py
│   ├── resource.py
│   └── response.py
├── evaluators/
│   ├── __init__.py
│   └── pipeline_evaluator.py
├── config.yaml
├── main.py
└── requirements.txt
```

### config.yaml

```yaml
models:
  primary: gpt-6.1-sol        # example model name; use one your provider serves

agents:
  classifier:
    temperature: 0.3
    max_tokens: 500
    categories: [security, infrastructure, application, data, network]
    urgency_levels: [critical, high, medium, low]
  impact:
    temperature: 0.3
    max_tokens: 800
  resource:
    temperature: 0.5
    max_tokens: 600
  response:
    temperature: 0.7
    max_tokens: 1500

settings:
  retry_count: 3
  timeout_seconds: 30
```

### agents/common.py

```python
import json
from domino.agents import read_agent_config
from openai import OpenAI

config = read_agent_config("config.yaml")     # the same file DominoAgentContext logs
client = OpenAI()

def ask_json(agent: str, prompt: str) -> dict:
    """One JSON-mode completion using the agent's settings from config.yaml."""
    settings = config["agents"][agent]
    response = client.chat.completions.create(
        model=config["models"]["primary"],
        messages=[{"role": "user", "content": prompt}],
        temperature=settings["temperature"],
        max_tokens=settings["max_tokens"],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
```

### agents/classifier.py

```python
from domino.agents.tracing import add_tracing
from agents.common import ask_json, config

def classifier_evaluator(span):
    output = span.outputs or {}
    scores = {
        "classifier_valid_category": 1.0 if output.get("category") in config["agents"]["classifier"]["categories"] else 0.0,
        "classifier_valid_urgency": 1.0 if output.get("urgency") in config["agents"]["classifier"]["urgency_levels"] else 0.0,
    }
    if isinstance(output.get("confidence"), (int, float)):     # only when the model reported one
        scores["classifier_confidence"] = float(output["confidence"])
        scores["classifier_high_confidence"] = 1.0 if output["confidence"] > 0.8 else 0.0
    return scores

@add_tracing(name="classifier_agent", span_type="CHAIN", evaluator=classifier_evaluator)
def classify_incident(incident: dict) -> dict:
    """Returns {'category', 'urgency', 'confidence', 'reasoning'}."""
    settings = config["agents"]["classifier"]
    prompt = f"""Classify this incident and reply with JSON:
{{"category": "<one of {settings['categories']}>", "urgency": "<one of {settings['urgency_levels']}>",
 "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}}

Title: {incident.get('title', 'N/A')}
Description: {incident.get('description', 'N/A')}
Source: {incident.get('source', 'N/A')}"""
    return ask_json("classifier", prompt)
```

### agents/impact.py

```python
from domino.agents.tracing import add_tracing
from agents.common import ask_json

def impact_evaluator(span):
    output = span.outputs or {}
    scores = {
        "impact_has_affected_users": 1.0 if (output.get("affected_users") or 0) > 0 else 0.0,
        "impact_has_financial_estimate": 1.0 if output.get("financial_exposure") else 0.0,
    }
    if isinstance(output.get("score"), (int, float)):
        scores["impact_raw_score"] = float(output["score"])      # 0-10, as the model returned it
    return scores

@add_tracing(name="impact_agent", span_type="CHAIN", evaluator=impact_evaluator)
def assess_impact(incident: dict, classification: dict) -> dict:
    """Returns {'score', 'affected_users', 'affected_systems', 'financial_exposure', 'reasoning'}."""
    prompt = f"""Assess the impact of this {classification['category']} incident and reply with JSON:
{{"score": <0-10>, "affected_users": <number>, "affected_systems": ["<system>"],
 "financial_exposure": "<estimate or 'unknown'>", "reasoning": "<brief explanation>"}}

Title: {incident.get('title', 'N/A')}
Description: {incident.get('description', 'N/A')}
Urgency: {classification['urgency']}"""
    return ask_json("impact", prompt)
```

### agents/resource.py

```python
from domino.agents.tracing import add_tracing
from agents.common import ask_json

def resource_evaluator(span):
    output = span.outputs or {}
    return {
        "resource_responder_count": len(output.get("responders", [])),
        "resource_has_eta": 1.0 if output.get("eta") else 0.0,
        "resource_meets_sla": 1.0 if output.get("meets_sla", False) else 0.0,
    }

@add_tracing(name="resource_agent", span_type="CHAIN", evaluator=resource_evaluator)
def match_resources(incident: dict, classification: dict, impact: dict) -> dict:
    """Returns {'required_skills', 'responders', 'eta', 'meets_sla', 'escalation_path'}."""
    prompt = f"""Find responders for this incident and reply with JSON:
{{"required_skills": ["<skill>"], "responders": [{{"role": "<role>", "priority": <1-3>}}],
 "eta": "<time estimate>", "meets_sla": <true/false>, "escalation_path": ["<level>"]}}

Category: {classification['category']}
Urgency: {classification['urgency']}
Impact score: {impact['score']}
Affected systems: {impact.get('affected_systems', [])}"""
    return ask_json("resource", prompt)
```

### agents/response.py

```python
from domino.agents.tracing import add_tracing
from agents.common import ask_json

def response_evaluator(span):
    output = span.outputs or {}
    return {
        "response_length": len(output.get("message", "")),
        "response_has_all_audiences": 1.0 if len(output.get("audiences", [])) >= 2 else 0.0,
        "response_has_action_items": 1.0 if output.get("action_items") else 0.0,
    }

@add_tracing(name="response_agent", span_type="CHAIN", evaluator=response_evaluator)
def draft_response(incident: dict, classification: dict, impact: dict, resources: dict) -> dict:
    """Returns {'message', 'audiences', 'action_items', 'follow_up_time'}."""
    prompt = f"""Draft an incident communication and reply with JSON:
{{"message": "<the communication>", "audiences": ["<audience>"], "action_items": ["<action>"],
 "follow_up_time": "<time>"}}

Incident: {incident.get('title', 'N/A')}
Category: {classification['category']}
Urgency: {classification['urgency']}
Impact score: {impact['score']}
Affected users: {impact.get('affected_users', 'Unknown')}
ETA: {resources.get('eta', 'Unknown')}"""
    return ask_json("response", prompt)
```

### evaluators/pipeline_evaluator.py

```python
def pipeline_evaluator(span):
    """Scores the whole pipeline's output (span.outputs of triage_incident).

    Runs after the four agent evaluators and writes to the same trace, so every name here
    must differ from theirs (classifier_*, impact_*, resource_*, response_*)."""
    output = span.outputs or {}
    classification = output.get("classification", {})
    impact = output.get("impact", {})
    resources = output.get("resources", {})
    response = output.get("response", {})

    confidence = classification.get("confidence")
    raw_impact = impact.get("score")
    if not isinstance(confidence, (int, float)) or not isinstance(raw_impact, (int, float)):
        return {"pipeline_incomplete": 1.0}          # do not invent scores for missing fields

    scores = {
        "pipeline_classification_confidence": float(confidence),
        "pipeline_impact_score": float(raw_impact) / 10.0,            # 0-1, unlike impact_raw_score
        "pipeline_resource_coverage": min(len(resources.get("responders", [])) / 3, 1.0),
        "pipeline_meets_sla": 1.0 if resources.get("meets_sla", False) else 0.0,
        "pipeline_response_completeness": (
            (1.0 if response.get("message") else 0.0) * 0.4
            + min(len(response.get("audiences", [])) / 2, 1.0) * 0.3
            + min(len(response.get("action_items", [])) / 3, 1.0) * 0.3
        ),
    }
    scores["overall_quality"] = (
        scores["pipeline_classification_confidence"] * 0.25 + scores["pipeline_impact_score"] * 0.25
        + scores["pipeline_resource_coverage"] * 0.25 + scores["pipeline_response_completeness"] * 0.25
    )
    return scores
```

### main.py

```python
import mlflow
from domino.agents.tracing import add_tracing
from domino.agents.logging import DominoAgentContext

from agents.classifier import classify_incident
from agents.impact import assess_impact
from agents.resource import match_resources
from agents.response import draft_response
from evaluators.pipeline_evaluator import pipeline_evaluator

mlflow.openai.autolog()
EXPERIMENT = "incident-triage-eval"


@add_tracing(name="triage_pipeline", span_type="AGENT", evaluator=pipeline_evaluator)
def triage_incident(incident: dict) -> dict:
    classification = classify_incident(incident)                       # child span
    impact = assess_impact(incident, classification)                   # child span
    resources = match_resources(incident, classification, impact)      # child span
    response = draft_response(incident, classification, impact, resources)
    return {"incident_id": incident.get("id"), "classification": classification,
            "impact": impact, "resources": resources, "response": response}


TEST_INCIDENTS = [
    {"id": "INC-001", "title": "Database connection failures", "source": "monitoring-alert",
     "description": "Users cannot access the main application; connection pool exhaustion in the logs."},
    {"id": "INC-002", "title": "Suspicious login attempts detected", "source": "security-siem",
     "description": "Unusual login patterns from multiple IPs targeting admin accounts."},
    {"id": "INC-003", "title": "API response times degraded", "source": "apm-alert",
     "description": "Customer-facing API endpoints at 5x normal latency; no errors."},
]


def main():
    aggregated = [
        ("classifier_confidence", "mean"),
        ("classifier_confidence", "min"),
        ("impact_raw_score", "median"),
        ("resource_meets_sla", "mean"),
        ("overall_quality", "mean"),
        ("overall_quality", "stdev"),
    ]

    mlflow.set_experiment(EXPERIMENT)        # creates the experiment on first use, then makes it active

    with DominoAgentContext(agent_config_path="config.yaml", custom_summary_metrics=aggregated) as run:
        results = []
        for incident in TEST_INCIDENTS:
            print(f"\nProcessing: {incident['id']} - {incident['title']}")
            result = triage_incident(incident)
            results.append(result)
            print(f"  Category: {result['classification']['category']}")
            print(f"  Urgency: {result['classification']['urgency']}")
            print(f"  Impact: {result['impact']['score']}/10")
            print(f"  SLA met: {result['resources']['meets_sla']}")
        print(f"\nRun completed: {run.info.run_id}; processed {len(results)} incidents")
    return results


if __name__ == "__main__":
    main()
```

### Viewing results

1. In the project, open **Experiments** and the `incident-triage-eval` experiment.
2. Open the run (one per Job execution) and the **Traces** tab.
3. Each `triage_pipeline` trace shows the four agent spans, each with its autologged OpenAI call:

```
triage_pipeline (AGENT)
├── classifier_agent (CHAIN)
│   └── Completions (CHAT_MODEL)
├── impact_agent (CHAIN)
│   └── Completions (CHAT_MODEL)
├── resource_agent (CHAIN)
│   └── Completions (CHAT_MODEL)
└── response_agent (CHAIN)
    └── Completions (CHAT_MODEL)
```

All five evaluators' metrics appear together on the trace (`classifier_*`, `impact_*`, `resource_*`, `response_*`, `pipeline_*`, `overall_quality`); none is attached to an individual span. The run's metrics page shows the aggregates named `<statistic>_<metric>`:

- `mean_classifier_confidence`, `min_classifier_confidence`
- `median_impact_raw_score`
- `mean_resource_meets_sla`
- `mean_overall_quality`, `stdev_overall_quality`

Change `config.yaml` (model, temperatures), run the Job again, then select both runs and **Compare**.

### requirements.txt

```text
mlflow==3.2.0
dominodatalab[data,agents]==2.2.0
opentelemetry-sdk<1.36
opentelemetry-api<1.36
openai==1.97.1
pyyaml==6.0.2
```
