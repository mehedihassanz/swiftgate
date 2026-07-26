# SwiftGate Python SDK

Async-first client for the SwiftGate AI model gateway with cost intelligence.

## Install

```bash
pip install -e .
```

## Quick Start

### Async (recommended)

```python
import asyncio
from swiftgate import SwiftGateClient

async def main():
    client = SwiftGateClient(base_url="http://localhost:8000")

    # Predict cost before sending
    prediction = await client.predict(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Write a Python function"}],
    )
    print(f"Predicted cost: {prediction['formatted']['estimated_total']}")

    # Send through the gateway
    result = await client.chat(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(result["choices"][0]["message"]["content"])

    await client.close()

asyncio.run(main())
```

### Sync

```python
from swiftgate import SwiftGateSyncClient

with SwiftGateSyncClient(base_url="http://localhost:8000") as client:
    result = client.predict(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])
    print(result["formatted"]["estimated_total"])
```

## Features

- **Cost Prediction** — see the cost before you send the request
- **Quality Routing** — route by quality-per-dollar, not just price
- **Semantic Cache** — serve cached responses for similar prompts
- **PII Redaction** — strip sensitive data before it reaches providers
- **Agent Budgets** — per-agent spend tracking and kill-switches
- **OpenAI-compatible** — drop-in replacement for the OpenAI SDK

## API

| Method | Description |
|--------|-------------|
| `client.predict(model, messages)` | Predict cost for a prompt |
| `client.compare(messages)` | Compare all models for a prompt |
| `client.chat(model, messages)` | Send a chat completion |
| `client.chat_stream(model, messages)` | Stream a chat completion |
| `client.list_models()` | List all available models |
| `client.pareto()` | Get Pareto-optimal models |
| `client.quality_feedback(model_id, rating)` | Submit quality feedback |
| `client.quality_route(messages)` | Quality-per-dollar routing |
| `client.quality_leaderboard()` | Quality rankings |
| `client.cache_stats()` | Cache statistics |
| `client.pii_detect(text)` | Detect PII in text |
| `client.pii_redact(messages)` | Redact PII from messages |
| `client.register_agent(agent_id)` | Register an AI agent |
| `client.kill_agent(agent_id)` | Kill an agent |
| `client.usage()` | Get usage records |
| `client.stats()` | Get aggregate stats |
