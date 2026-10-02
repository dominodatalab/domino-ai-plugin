#!/usr/bin/env bash
set -euo pipefail
cat > agent.py <<'PY'
from openai import OpenAI

client = OpenAI()

def answer(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    print(answer("What is Domino Data Lab?"))
PY
