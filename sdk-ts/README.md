# SwiftGate TypeScript SDK

TypeScript client for the SwiftGate AI model gateway with cost intelligence.

## Install

```bash
npm install @swiftgate/sdk
# or
pnpm add @swiftgate/sdk
```

## Quick Start

```typescript
import { SwiftGateClient } from "@swiftgate/sdk";

const client = new SwiftGateClient({
  baseURL: "http://localhost:8000",
  apiKey: "sg-...", // optional in development
});

// Predict cost before sending
const prediction = await client.predict({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Write a Python function" }],
});
console.log(`Predicted cost: ${prediction.formatted.estimated_total}`);

// Send through the gateway
const result = await client.chat("gpt-4o", [
  { role: "user", content: "Hello!" },
]);
console.log(result.choices[0].message.content);
```

## API

| Method | Description |
|--------|-------------|
| `client.predict(req)` | Predict cost for a prompt |
| `client.compare(messages)` | Compare all models |
| `client.chat(model, messages)` | Send a chat completion |
| `client.listModels()` | List all models |
| `client.pareto()` | Pareto-optimal models |
| `client.qualityFeedback(modelId, rating)` | Submit quality feedback |
| `client.qualityRoute(req)` | Quality-per-dollar routing |
| `client.qualityLeaderboard()` | Quality rankings |
| `client.cacheStats()` | Cache statistics |
| `client.piiDetect(text)` | Detect PII |
| `client.piiRedact(messages)` | Redact PII |
| `client.registerAgent(agentId)` | Register an agent |
| `client.killAgent(agentId)` | Kill an agent |
| `client.usage()` | Usage records |
| `client.stats()` | Aggregate stats |

Zero dependencies — uses native `fetch`.
