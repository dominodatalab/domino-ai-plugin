# AI Gateway client patterns

Client-side coding patterns for calling AI Gateway endpoints: stable endpoint names, retry on rate limits, logging token usage, and streaming long responses.

## Best Practices

### 1. Use Endpoint Names Consistently
```python
# Define endpoint once
LLM_ENDPOINT = "production-gpt4"

# Use throughout code
response = client.chat.completions.create(
    model=LLM_ENDPOINT,
    messages=[...]
)
```

### 2. Handle Rate Limits
```python
import time
from openai import RateLimitError

def call_llm_with_retry(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model="openai-gpt4",
                messages=messages
            )
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
```

### 3. Log Important Calls
```python
import logging

logger = logging.getLogger(__name__)

def query_llm(prompt):
    logger.info(f"Querying LLM with prompt length: {len(prompt)}")
    response = client.chat.completions.create(
        model="openai-gpt4",
        messages=[{"role": "user", "content": prompt}]
    )
    logger.info(f"Response tokens: {response.usage.total_tokens}")
    return response.choices[0].message.content
```

### 4. Use Streaming for Long Responses
```python
# Streaming response
stream = client.chat.completions.create(
    model="openai-gpt4",
    messages=[{"role": "user", "content": "Write a long story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```
