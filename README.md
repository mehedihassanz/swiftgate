# SwiftGate

**AI model gateway with cost intelligence. See the cost before you pay it.**

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

SwiftGate is a self-hosted AI gateway that sits between your applications and
LLM providers (OpenAI, Anthropic, Google, Mistral, DeepSeek, and 14 others).
It predicts costs before requests are sent, routes by quality-per-dollar,
caches semantically, redacts PII, and tracks per-agent budgets.

## Features

- **Cost Prediction** — See exact token counts and dollar costs before sending
- **Quality-Aware Routing** — Route by quality-per-dollar, not just price
- **Semantic Cache** — Serve cached responses for similar prompts (20-40% savings)
- **PII Redaction** — Strip sensitive data before it reaches providers
- **Agent Budgets** — Per-agent spend tracking with kill-switches
- **34 Models** across 18 providers with real-time pricing
- **OpenAI-compatible** — Drop-in replacement for the OpenAI SDK

## Quick Start

```bash
# Clone and configure
git clone https://github.com/mehedihassanz/swiftgate.git
cd swiftgate
cp backend/.env.example backend/.env  # Edit with your API keys

# Run with Docker
docker compose up --build

# Or run backend only for development
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit:
- Backend API: http://localhost:8000/docs
- Dashboard: http://localhost:3001
- Landing page: http://localhost:3002

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────┐     ┌──────────────┐
│  Your App   │────▶│              SwiftGate Gateway            │────▶│  OpenAI      │
│  / SDK      │◀────│  predict → cache → PII → route → proxy   │◀────│  Anthropic   │
└─────────────┘     └──────────────────────────────────────────┘     │  Google      │
                                                               │  Mistral     │
                     ┌──────────────────────────────────────────┐   │  DeepSeek    │
                     │  PostgreSQL / SQLite                     │   │  +14 others  │
                     │  Usage records, API keys, agents, cache  │   └──────────────┘
                     └──────────────────────────────────────────┘
```

## Client SDKs

**Python:**
```python
from swiftgate import SwiftGateClient

client = SwiftGateClient(base_url="http://localhost:8000")
prediction = await client.predict(model="gpt-4o", messages=[...])
print(f"Cost: {prediction['formatted']['estimated_total']}")
```

**TypeScript:**
```typescript
import { SwiftGateClient } from "@swiftgate/sdk";

const client = new SwiftGateClient({ baseURL: "http://localhost:8000" });
const pred = await client.predict({ model: "gpt-4o", messages: [...] });
```

## Configuration

See [`backend/.env.example`](backend/.env.example) for all configuration options.

**Production checklist:**
- Set `ENV=production`
- Set `ADMIN_KEY` to a strong random string
- Set `CORS_ORIGINS` to your allowed origins (never `*` in production)
- Set provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- Consider PostgreSQL instead of SQLite for multi-user deployments

## Project Structure

```
swiftgate/
├── backend/           # FastAPI backend (Python 3.13)
│   ├── app/
│   │   ├── routers/   # 7 routers, 43 endpoints
│   │   ├── services/  # Pricing, cache, PII, ML predictor, rate limiter
│   │   ├── models.py  # SQLAlchemy models
│   │   └── config.py  # Environment configuration
│   └── tests/         # Pytest test suite
├── web/               # React dashboard (Vite + TypeScript + Tailwind)
│   └── src/pages/     # 9 pages: Dashboard, Predict, Compare, Cache, etc
├── landing/           # Marketing landing page
├── sdk-python/        # Python client SDK
├── sdk-ts/            # TypeScript client SDK
└── docker-compose.yml # Full stack deployment
```

## License

MIT
