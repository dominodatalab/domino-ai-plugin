#!/usr/bin/env bash
set -euo pipefail
cat > agent.py <<'EOF'
import mlflow
from openai import OpenAI
from domino.agents.tracing import add_tracing

mlflow.openai.autolog()
client = OpenAI()


@add_tracing(name="support_agent", autolog_frameworks=["openai"])
def answer(question: str) -> dict:
    r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": question}])
    return {"answer": r.choices[0].message.content}
EOF
cat > requirements.txt <<'EOF'
openai
dominodatalab[data]==2.2.0
mlflow==3.3.2
EOF
