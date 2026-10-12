---
description: A script that calls OpenAI directly is rewritten to call a gateway alias through Domino LLM Gateway 2.0 with the in-run access token.
tags: [llm, gateway]
max_turns: 15
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

Our Domino admin deployed LLM Gateway 2.0 and gave us the alias `support-llm`. The gateway URL is in the project environment variable `LLM_GATEWAY_URL`. Change `ask.py` so it calls the alias through the gateway when it runs as a Domino Job, without putting any provider key in the code.
