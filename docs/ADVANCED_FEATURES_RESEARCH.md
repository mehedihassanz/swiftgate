# SwiftGate — Advanced Features Research Report

> Competitive feature analysis for 15 advanced capabilities offered by AI gateway products (Portkey, LiteLLM, Helicone, OpenRouter, Cloudflare AI Gateway, Bifrost, TensorZero). For each: what it is, how it works, a concrete implementation plan for SwiftGate's FastAPI + React stack, and a build priority.

**Researched:** July 2026
**Stack:** FastAPI (async Python, SQLAlchemy, httpx) + React/TypeScript + SQLite/Postgres + Redis
**Existing capabilities:** cost tracking, model routing, semantic cache, PII redaction, rate limiting, quality scoring, agent budgets, analytics, ML cost prediction, quality-aware routing

**Relationship to `MOAT_FEATURES_RESEARCH.md`:** That document assessed *novel moats* (features competitors do poorly). This document assesses *table-stakes and adjacent features* that the listed competitors offer — things SwiftGate may already partially implement or should add to remain competitive. Where a feature overlaps with a researched moat, cross-references are included. The goal here is feature-parity coverage and clear prioritization, not moat identification.

---

## Executive Summary — Priority Matrix

Features are prioritized by (a) how many competitors already ship it, (b) user expectation level, and (c) incremental effort given SwiftGate's existing architecture.

| # | Feature | Priority | Effort | Status in SwiftGate | Why This Priority |
|---|---------|----------|--------|---------------------|-------------------|
| 1 | Smart model fallback chains | 🔴 **HIGH** | Low | Partial (failover exists, no quality-ordered chains) | Every competitor has this. Users expect it. Small lift from existing `route_by_strategy`. |
| 10 | Provider health monitoring + circuit breaking | 🔴 **HIGH** | Medium | Partial (`avg_latency_ms` on Provider, no circuit breaker) | Required for production reliability. Prevents cascading failures. |
| 8 | Webhook/event system for cost alerts | 🔴 **HIGH** | Low | Partial (`BudgetAlert` table exists, no outbound delivery) | Budget alerts already fire internally; delivering them via webhook/Slack/email is a small, high-value lift. |
| 11 | Request/response logging + audit trail | 🔴 **HIGH** | Medium | Partial (`UsageRecord` stores metadata, not raw prompts/responses) | Required for debugging, compliance, and enterprise. Helicone/Portkey's core value prop. |
| 2 | Load balancing across providers | 🟡 **MEDIUM** | Medium | Partial (failover is sequential, not weighted round-robin) | Important for throughput at scale. Less urgent while single-instance. |
| 14 | Token budget forecasting + spend predictions | 🟡 **MEDIUM** | Medium | Partial (per-request prediction exists; no time-series forecast) | Builds directly on the ML prediction flywheel. Differentiates from pure trackers. |
| 9 | Multi-tenant API key management + per-key quotas | 🟡 **MEDIUM** | Medium | Partial (`ApiKey` + `User` exist; no org/team hierarchy, no per-key RPM/TPM quotas) | Needed for B2B/team plans. Org scoping is the gap. |
| 13 | Custom pricing rules (volume discounts, commits) | 🟡 **MEDIUM** | Medium | Partial (flat `TOKEN_MARGIN`; no tiered/commit pricing) | Enables enterprise sales motion. Billing-aware pricing engine. |
| 7 | Streaming response aggregation + partial caching | 🟡 **MEDIUM** | Medium | Partial (`StreamingUsageTracker` exists; no partial caching) | Nice-to-have for long completions. Partial caching is novel but risky. |
| 15 | Model performance benchmarking | 🟡 **MEDIUM** | Medium | Partial (quality scores + prediction accuracy tracked; no standardized benchmark suite) | Useful for marketing and routing. Builds on quality data. |
| 4 | A/B testing different models on same prompt | 🟢 **LOW** | Medium | Not present | TensorZero/Portkey offer it; valuable but niche. Depends on quality-data volume. |
| 3 | Token-level cost optimization (prompt compression) | 🟢 **LOW** | Medium | Not present | OpenRouter ships a plugin; easily copied. Pairs with cost prediction but not urgent. |
| 6 | Embedding cache for RAG optimization | 🟢 **LOW** | Medium | Not present | Narrow use case (RAG workloads only). Separate from LLM cache. |
| 5 | Custom model fine-tuning management | 🟢 **LOW** | High | Not present | Out of gateway scope. Platforms (Together, Replicate, Fireworks) own this. Low ROI. |
| 12 | SOC2/GDPR compliance features | 🟢 **LOW** | High (process-heavy) | Partial (PII redaction planned) | Certifications are process+time, not code. Defer until enterprise demand is concrete. |

**Recommended sequencing:** Ship the four HIGH-priority items first (features 1, 10, 8, 11) — they are the largest gaps relative to competitor parity and are all incremental on existing tables/services. Then tackle MEDIUM items in the order listed.

---

## Feature 1: Smart Model Fallback Chains

### What It Is
A configurable, ordered chain of models to try for a given request. If the primary model fails (error, timeout, rate limit) or returns low-quality output, the gateway automatically retries with the next model in the chain — e.g., GPT-4 → Claude Opus → DeepSeek. This is distinct from provider failover (same model, different host): fallback chains cross *models* and often *providers*.

**How competitors do it:**
- **Portkey:** First-class "Config" objects defining fallback chains with per-model weights and on-status-code triggers.
- **LiteLLM:** `fallbacks` parameter in router config; supports model→model and model→deployment fallbacks.
- **OpenRouter:** Auto-routing with implicit fallback across providers hosting the same model.
- **Bifrost:** Typed fallback graphs with conditional edges.

### How It Works
1. User defines a fallback config: an ordered list of `(model_id, trigger_conditions)` pairs.
2. Gateway attempts the primary model. On failure (configurable status codes: 429, 5xx, timeout) or quality signal, it advances to the next model.
3. Each attempt is recorded for analytics (attempt number, which model ultimately succeeded).
4. Optional: quality-ordered degradation — if the *response* is received but low-quality (via the quality signal infrastructure), retry with a higher-quality model.

### Implementation for SwiftGate

**Current state:** SwiftGate already has `route_by_strategy()` in `provider_router.py` which builds a failover chain of `(Model, Provider)` pairs, and the gateway loop in `chat_completions()` iterates that chain with `should_retry()`. However, the chain is built automatically from same-category alternatives — there is no user-defined, named fallback config, and no quality-triggered fallback (only error-triggered).

**Changes required:**

1. **New model — `FallbackChain`** (`models.py`):
```python
class FallbackChain(Base):
    __tablename__ = "fallback_chains"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)  # "production-code", "cheap-chat"
    # Ordered list of {model_id, trigger_on: [status_codes], fallback_reason: "error"|"quality"|"timeout"}
    chain_config: Mapped[list] = mapped_column(JSON)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
```

2. **Extend `route_by_strategy()`** to accept a `fallback_chain_name` parameter. When provided, build the chain from `FallbackChain.chain_config` instead of auto-deriving it. Resolve each entry's `(Model, Provider)` via the existing catalog lookup.

3. **Extend the gateway retry loop** (`gateway.py`) to record per-attempt outcomes on `UsageRecord` (a new `attempt_number` / `fallback_chain_used` field), and to support quality-triggered fallback: after a successful response, if a `min_quality` threshold is set and the response is sampled/evaluated below it, retry with the next model.

4. **API endpoints** (`/v1/fallback-chains` CRUD) and a React UI to define chains visually (drag-to-reorder model list).

**Effort:** ~1 week (the hard infrastructure — failover loop, provider chain — already exists; this adds config + quality triggers).

### Priority: 🔴 HIGH
Every listed competitor ships this. It is table-stakes. SwiftGate's existing failover loop means the lift is small (mostly config + UI). The quality-triggered variant is a genuine enhancement that pairs with the quality-router moat (see `MOAT_FEATURES_RESEARCH.md` Feature 2).

---

## Feature 2: Load Balancing Across Providers

### What It Is
Distributing requests across multiple providers/regions that host the same model to maximize throughput, minimize latency, and avoid per-provider rate limits. Unlike failover (which is reactive), load balancing is *proactive* — splitting traffic to use capacity efficiently.

**How competitors do it:**
- **LiteLLM:** Weighted round-robin and latency-based routing across "deployments" (provider+model pairs).
- **OpenRouter:** Routes to the lowest-latency/cheapest provider hosting a model at request time.
- **Portkey:** Load-balance strategies: simple round-robin, weighted, latency-based.
- **Cloudflare AI Gateway:** Load balancing across upstream endpoints with health checks.

### How It Works
1. Each model maps to one or more "deployments" — a `(provider, endpoint, region)` tuple.
2. A load-balancing strategy selects the deployment per request: round-robin, weighted (by quota/cost), lowest-latency, or least-connections.
3. Selection state (round-robin counters, connection counts) is kept in Redis for multi-worker consistency.
4. Telemetry feeds back into weights: if Provider A's p95 latency rises, its weight decreases.

### Implementation for SwiftGate

**Current state:** `Provider` has `avg_latency_ms`, `uptime_pct`, and `priority`. `route_by_strategy()` orders by these fields but does not *distribute* — it always picks the top-ranked provider and only falls to others on failure. There is no round-robin or weighted distribution.

**Changes required:**

1. **Extend `Model` or add a `ModelDeployment` table** to represent multiple provider-hostings of the same logical model:
```python
class ModelDeployment(Base):
    __tablename__ = "model_deployments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(200), index=True)  # logical model
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    provider_model_id: Mapped[str] = mapped_column(String(200))  # native ID at this provider
    weight: Mapped[int] = mapped_column(Integer, default=1)  # for weighted LB
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

2. **New service — `load_balancer.py`:** strategies `round_robin`, `weighted`, `latency_based`, `least_connections`. Round-robin counters and connection counts stored in Redis (fall back to in-memory like the existing `rate_limiter.py` pattern).

3. **Integrate into `route_by_strategy()`** — when `strategy == "load_balanced"`, call the load balancer to pick a deployment instead of sorting and taking the top.

4. **Feed latency back:** the existing `_record_usage()` already captures `latency_ms` per request. Add a background task (or inline update) that rolls this into `Provider.avg_latency_ms` / `ModelDeployment` stats on a windowed basis.

5. **Least-connections:** increment a Redis counter when a request starts, decrement when it finishes. The `streaming.py` finally-block and `_handle_non_streaming` are the natural decrement points.

**Effort:** ~2 weeks (new table, new service, Redis state, integration into the routing path).

### Priority: 🟡 MEDIUM
Important at scale (multiple workers, high QPS) but SwiftGate's current single-instance + failover is adequate for early traction. Becomes HIGH once a single provider's rate limits become the bottleneck for a paying customer. Pairs naturally with Feature 10 (health monitoring).

---

## Feature 3: Token-Level Cost Optimization (Prompt Compression, Token Pruning)

### What It Is
Reducing the number of tokens sent upstream (and thus billed) by compressing or pruning the prompt before forwarding. Techniques include: removing redundant whitespace, summarizing conversation history, dropping low-relevance retrieved documents, and deduplicating system-prompt prefixes.

**How competitors do it:**
- **OpenRouter:** "Context compression" plugin — summarizes prior messages to shrink context.
- **LiteLLM:** `trim_messages` utility to drop old messages exceeding context window.
- **Portkey:** Prompt-template optimization hooks.

### How It Works
1. Before building the upstream request, run the messages through a compressor.
2. Compression strategies (stackable): whitespace normalization, stopword pruning for cache matching (SwiftGate already does this in `semantic_cache._normalize_text`), conversation summarization (LLM call), relevance filtering of retrieved docs (embedding similarity), tool-definition minification.
3. Record token delta (before/after) for cost-savings analytics.

### Implementation for SwiftGate

**Current state:** `semantic_cache.py` already normalizes text *for matching* but does not alter the forwarded payload. `tokenizer.py` counts tokens but does not prune.

**Changes required:**

1. **New service — `prompt_optimizer.py`:**
```python
async def optimize_prompt(messages, model, mode="aggressive"):
    original_tokens = get_token_count(messages, model)
    # 1. Whitespace + redundancy pass (cheap, always-on)
    messages = _strip_redundancy(messages)
    # 2. Conversation summarization (if history > N messages)
    if len(messages) > 10:
        messages = await _summarize_history(messages, model)
    # 3. Context-window trim (drop oldest beyond limit)
    messages = _trim_to_context(messages, model.context_window)
    optimized_tokens = get_token_count(messages, model)
    return messages, {"saved_tokens": original_tokens - optimized_tokens, ...}
```

2. **Gateway integration:** optional `optimize_prompt: true` flag on `ChatCompletionRequest`. When set, run the optimizer after PII redaction, before cache check (so cached entries reflect optimized form).

3. **Analytics:** add `tokens_saved_optimization` to `UsageRecord`; surface total savings in the dashboard.

4. **Pair with cost prediction:** the MOAT document (Feature 8) explicitly recommends pairing this with ML cost prediction — "we optimize your prompts AND predict the savings." That combined narrative is stronger than compression alone.

**Effort:** ~2-3 weeks (summarization needs an LLM call + careful quality guardrails; risk of degrading output).

### Priority: 🟢 LOW
Easily copied (OpenRouter already ships it). The value is real (10-30% input savings) but it is not a differentiator on its own. Build it *as a complement* to the ML cost-prediction moat, not as a standalone feature. Risk: aggressive summarization degrades output quality, which conflicts with the quality-routing moat.

---

## Feature 4: A/B Testing Different Models on the Same Prompt

### What It Is
Sending the same prompt to multiple models (or prompt templates) in parallel, then comparing outputs — either for evaluation or to slowly roll out a new model to a fraction of traffic. The gateway manages traffic splitting, collects paired outcomes, and computes statistical significance.

**How competitors do it:**
- **TensorZero:** Built around this — "experimentation platform" with variant assignments and metric collection.
- **Portkey:** A/B test configs with traffic-percentage splits.
- **Braintrust:** Evaluation-focused; runs offline eval suites.

### How It Works
1. Define an experiment: traffic split (e.g., 90% Model A / 10% Model B), a metric (cost, quality score, latency), and a stopping criterion.
2. Gateway assigns each request to a variant (sticky by user/request hash).
3. Both variants' outcomes are recorded with the experiment ID and variant label.
4. Dashboard computes per-variant metric distributions and significance.

### Implementation for SwiftGate

**Current state:** SwiftGate has `QualityScore` records and `compare_models()` (a *preview* of costs, not a live experiment). There is no traffic-splitting or experiment entity.

**Changes required:**

1. **New model — `Experiment`** + `ExperimentVariant`:
```python
class Experiment(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str]
    metric: Mapped[str]  # "cost", "quality", "latency"
    status: Mapped[str] = mapped_column(String(20), default="running")
    variants: Mapped[list] = mapped_column(JSON)  # [{model_id, weight: 90}, ...]
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
```

2. **Gateway integration:** if the request matches an active experiment (by model/task), assign variant by hash(`api_key + experiment_id`) mod 100, route accordingly, and stamp `UsageRecord` + `QualityScore` with `experiment_id` + `variant`.

3. **Analytics endpoint** `/v1/experiments/{id}/results` returning per-variant distributions and a significance test (Mann-Whitney U for quality, t-test for cost).

4. **React UI** to create experiments and view results.

**Effort:** ~2-3 weeks. The machinery is straightforward; the value depends on having enough traffic for statistical power, which is why this is lower priority until volume grows.

### Priority: 🟢 LOW
Niche but high-value for the subset of users who need it. TensorZero owns this niche. Build after the quality-data flywheel has enough volume to make experiments meaningful. The `QualityScore` table is the foundation — this feature is its natural consumer.

---

## Feature 5: Custom Model Fine-Tuning Management

### What It Is
Managing the lifecycle of fine-tuned models — launching fine-tuning jobs from collected prompt/response data, tracking job status, versioning the resulting models, and routing traffic to them.

**How competitors do it:**
- **Together AI / Fireworks / Replicate:** Full fine-tuning platforms (this is their core product, not a gateway feature).
- **OpenRouter:** Routes to fine-tuned models but does not manage training.
- **Portkey:** No fine-tuning; gateway-only.

### How It Works
1. User selects a dataset (filtered `UsageRecord` + stored responses).
2. Gateway submits a fine-tuning job to a provider API (OpenAI, Together).
3. Job status polled; on completion, the resulting model is registered in the catalog.
4. Routing rules can target the fine-tuned model.

### Implementation for SwiftGate

**Current state:** No fine-tuning infrastructure. SwiftGate stores metadata but not raw prompts/responses (see Feature 11) — without stored responses, there is no training dataset.

**Changes required:**
- Response logging (Feature 11) is a hard prerequisite.
- New `FineTuningJob` model + provider API integrations (each provider has a different fine-tuning API).
- Job-status polling (background task or webhook from provider).
- Catalog registration of the resulting model with pricing.

**Effort:** ~4-6 weeks, and ongoing maintenance per provider API. High complexity, narrow audience.

### Priority: 🟢 LOW
**This is out of scope for a gateway.** Fine-tuning is a platform feature owned by Together/Fireworks/Replicate. A gateway should *route to* fine-tuned models (which SwiftGate already can — they are just catalog entries), not *manage* fine-tuning. Building this would mean competing with dedicated ML platforms on their home turf. Recommend: do not build; instead ensure the catalog supports custom/fine-tuned model entries and that routing rules can target them.

---

## Feature 6: Embedding Cache for RAG Optimization

### What It Is
Caching embedding API results so that re-embedding the same text (common in RAG pipelines that re-index or re-query) is free and instant. Distinct from the LLM response cache — this caches the output of `/v1/embeddings` calls.

**How competitors do it:**
- **Helicone:** Caches embeddings as part of its observability/optimization layer.
- **LiteLLM:** Supports caching embedding calls via the same Redis cache mechanism.
- Most gateways treat embeddings as a minor side path.

### How It Works
1. Hash the input text (+ model + dimensions).
2. On cache hit, return the stored vector; on miss, call the provider and store the result.
3. Vectors are larger than text responses (e.g., 1536 floats = ~12KB) — storage cost matters.

### Implementation for SwiftGate

**Current state:** `CacheEntry` is designed for LLM responses. The gateway only proxies `/v1/chat/completions` — there is no `/v1/embeddings` endpoint. Adding an embeddings cache means adding an embeddings *proxy* first.

**Changes required:**
1. New gateway endpoint `/v1/embeddings` (OpenAI-compatible) — a simpler proxy than chat (no streaming, no tools).
2. Extend `CacheEntry` or add `EmbeddingCacheEntry` (store vector as bytes/JSON, keyed on text hash + model + dims).
3. Vector storage: for Postgres, `bytea` or pgvector; for SQLite, JSON text. Eviction by LRU + size cap.
4. Cost tracking: embeddings are cheap but high-volume — important to record usage for billing.

**Effort:** ~2 weeks (embeddings proxy + cache). Straightforward but narrow.

### Priority: 🟢 LOW
Only relevant for RAG workloads. Most gateway users send chat/completion traffic. If SwiftGate sees significant embeddings volume from RAG customers, prioritize; otherwise defer. The existing `CacheEntry` pattern makes this a small lift *technically*, but the demand is unproven.

---

## Feature 7: Streaming Response Aggregation and Partial Caching

### What It Is
Two related capabilities:
1. **Aggregation:** reconstructing the full response from SSE chunks for logging/analytics (SwiftGate already does this via `StreamingUsageTracker`).
2. **Partial caching:** caching a partially-generated response so that if a similar request resumes generation, the cached prefix can be replayed, avoiding re-generating the beginning.

**How competitors do it:**
- **OpenRouter / Anthropic:** Provider-side prompt caching (Anthropic caches the *prompt prefix* server-side, billed at a discount). This is upstream caching, not gateway-side.
- **Cloudflare AI Gateway:** Caches complete responses; no partial/prefix caching.
- No major gateway offers true gateway-side partial-response caching — it is a research-grade feature.

### How It Works
1. As SSE chunks arrive, append them to an accumulator.
2. Periodically checkpoint the accumulated text at "safe" boundaries (sentence/end-of-paragraph).
3. On a new request whose prefix matches a checkpoint, replay the cached prefix as synthetic SSE chunks, then continue generation from the model with a `prefix` hint (where supported).

### Implementation for SwiftGate

**Current state:** `StreamingUsageTracker` (in `streaming.py`) accumulates usage but discards content. The `_handle_streaming` function in `gateway.py` passes chunks through without buffering them (correct for memory efficiency).

**Changes required:**

1. **Aggregation (straightforward):** in `_handle_streaming`, optionally accumulate full content into a buffer and store it (for Feature 11 — audit logging). Guard memory with a size cap.

2. **Partial caching (complex, risky):**
   - Checkpoint accumulator with content-addressed storage.
   - Prefix-matching logic: hash prefixes at fixed token intervals, lookup on new request.
   - Provider support for "continue from prefix" is inconsistent — OpenAI has no such API; Anthropic's prompt caching is server-side. Gateway-side replay would inject synthetic chunks, which is fragile (clients may not expect pre-cached content that doesn't match a fresh model call).
   - Correctness risk: a cached prefix from Model A served to a Model B request may be semantically divergent.

**Effort:** Aggregation ~3 days. Partial caching ~4-6 weeks with significant correctness risk.

### Priority: 🟡 MEDIUM (aggregation only)
- **Aggregation: build it** — it is a prerequisite for response logging (Feature 11) and costs little. The `StreamingUsageTracker` is 90% of the way there.
- **Partial caching: defer.** It is novel but correctness-fragile, no competitor does it well, and provider-side prompt caching (Anthropic, OpenAI's automatic prefix caching) largely addresses the cost-saving use case upstream. The risk of serving wrong/divergent prefixes outweighs the benefit.

---

## Feature 8: Webhook/Event System for Cost Alerts

### What It Is
Delivering gateway events — budget thresholds crossed, agent killed, provider degraded, anomalous spend — to external systems via outbound webhooks, email, Slack, or messaging queues. This turns SwiftGate's internal alerting into actionable, integrable notifications.

**How competitors do it:**
- **Helicone:** Alert rules with email/Slack/webhook destinations.
- **Portkey:** Webhook subscriptions for budget and latency events.
- **OpenRouter:** Spending-limit webhooks.
- **Cloudflare AI Gateway:** Webhook alerts on upstream errors.

### How It Works
1. User registers a webhook URL (+ optional secret for HMAC signing) and selects event types.
2. When an internal event fires (budget threshold, agent status change), the gateway enqueues an outbound HTTP POST.
3. Delivery is retried with exponential backoff on failure.
4. An audit log records delivery attempts.

### Implementation for SwiftGate

**Current state:** SwiftGate *already creates* `BudgetAlert` records and checks thresholds in `_record_usage()` / `_check_agent_budget()`. The alerts are stored in the database but **never delivered externally** — users must poll the API or watch the dashboard. This is the single highest-ROI gap in the product.

**Changes required:**

1. **New model — `WebhookEndpoint`:**
```python
class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    secret: Mapped[str] = mapped_column(String(200))  # HMAC signing secret
    event_types: Mapped[list] = mapped_column(JSON)  # ["budget.threshold", "agent.killed", ...]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)

class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("webhook_endpoints.id"))
    event_type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # "pending", "delivered", "failed"
    response_code: Mapped[int | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
```

2. **New service — `webhooks.py`:** `dispatch_event(event_type, payload)` — find matching endpoints, sign payload with HMAC-SHA256, enqueue delivery. Use a background task (FastAPI `BackgroundTasks` or a dedicated async worker) so the request path is not blocked.

3. **Hook into existing alert points:** `_create_budget_alert()` in `gateway.py` already fires on threshold crossings — add a call to `dispatch_event("budget.threshold", ...)`. Similarly for agent kill/pause in `agents.py`.

4. **Retry worker:** a periodic task (or on-failure re-enqueue) that retries `WebhookDelivery` rows in `pending`/`failed` status with exponential backoff (1m, 5m, 30m, 2h, 24h).

5. **API:** `/v1/webhooks` CRUD, `/v1/webhooks/{id}/deliveries` (delivery log), `/v1/webhooks/test` (send a test event).

6. **Additional channels:** Slack (incoming webhook URL), email (SMTP), PagerDuty — all thin adapters over the same dispatch.

**Effort:** ~1-1.5 weeks. The alert *detection* logic is done; this is purely the delivery layer.

### Priority: 🔴 HIGH
Highest ROI on the list. The detection already exists; only delivery is missing. Without outbound notifications, the budget/agent features are passive — users have to remember to check the dashboard. Webhooks make SwiftGate actionable and integration-friendly (the key to embedding in CI/CD and on-call workflows).

---

## Feature 9: Multi-Tenant API Key Management with Per-Key Quotas

### What It Is
A hierarchy for organizing API keys under organizations/teams/projects, with per-key quotas that go beyond simple monthly spend — including requests-per-minute (RPM), tokens-per-minute (TPM), concurrent-request limits, and per-model access controls.

**How competitors do it:**
- **Portkey:** Full org → workspace → key hierarchy with granular per-key limits and model allowlists.
- **LiteLLM:** Per-key budgets, RPM/TPM limits, model allow/deny lists via `litellm_budget_table`.
- **OpenRouter:** Per-key spend limits and model restrictions.
- **Cloudflare AI Gateway:** Per-key rate limiting and quotas.

### How It Works
1. `Organization` → `Team` (optional) → `ApiKey`. Keys inherit defaults from their parent and can override.
2. Per-key quotas: `monthly_budget_cents`, `per_request_limit_cents` (SwiftGate has these), plus `rpm_limit`, `tpm_limit`, `concurrent_limit`, `allowed_models[]`.
3. Rate limiter checks RPM/TPM/concurrent before forwarding.
4. Usage roll-up at each hierarchy level for org-level billing and dashboards.

### Implementation for SwiftGate

**Current state:** SwiftGate has `User` → `ApiKey` (1:many) with `monthly_budget_cents` and `per_request_limit_cents`. There is no Organization/Team layer, no RPM/TPM/concurrent limits, and no per-key model allowlist. The rate limiter (`rate_limiter.py`) applies a global `DEFAULT_RPM=60` to all authenticated keys uniformly.

**Changes required:**

1. **New models:**
```python
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str]
    billing_email: Mapped[str]
    plan: Mapped[str] = mapped_column(String(50), default="free")

class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str]
```

2. **Extend `ApiKey`:** add `org_id`, `team_id`, `rpm_limit`, `tpm_limit`, `concurrent_limit`, `allowed_models` (JSON list). Add `User.org_id` / `User.role` ("admin", "member").

3. **Extend `check_rate_limit()`** to read per-key RPM/TPM limits from the key record instead of the global default. TPM needs a token-based window (sum of `prompt_tokens + completion_tokens` in the last 60s) — requires a Redis sorted-set keyed by tokens, similar to the existing RPM implementation. Concurrent limit: increment-on-start, decrement-on-finish (same pattern as least-connections in Feature 2).

4. **Model allowlist:** in `_authenticate()` or the gateway, reject requests for models not in `allowed_models`.

5. **Usage roll-up:** queries aggregating `UsageRecord` by `org_id` (via the key's org). New analytics endpoints `/v1/orgs/{id}/usage`.

6. **React UI:** org/team management, per-key quota editor, model allowlist picker.

**Effort:** ~3 weeks (schema + hierarchy + extended rate limiter + UI). The rate-limiter extension is the most intricate part (TPM tracking).

### Priority: 🟡 MEDIUM
Needed for B2B/team sales. The current single-user model is fine for individual developers but blocks team adoption. Not urgent until SwiftGate has paying team customers, but becomes HIGH the moment an enterprise deal requires it. The model-allowlist sub-feature is independently valuable for security (restrict a key to cheap models only).

---

## Feature 10: Provider Health Monitoring and Automatic Circuit Breaking

### What It Is
Continuously tracking each provider's health (error rate, latency, uptime) and automatically "breaking the circuit" — temporarily stop sending traffic to a failing provider — to prevent cascading failures and fast-fail rather than waiting for timeouts.

**How competitors do it:**
- **LiteLLM:** Health checks with auto-disable of unhealthy deployments; cooldown timers.
- **Portkey:** Per-provider health monitoring with circuit-breaker rules.
- **Cloudflare AI Gateway:** Built-in retry + circuit breaking on upstream failures.
- **Bifrost:** Core feature — typed circuit breakers per provider.

### How It Works
1. Sliding-window counters per provider: success count, error count (by status code), latency samples.
2. When error rate exceeds a threshold (e.g., >50% in 60s) or latency p95 exceeds a limit, "open" the circuit: route around the provider for a cooldown period.
3. After cooldown, "half-open": send one probe request; if it succeeds, close the circuit; if it fails, re-open.
4. Health metrics feed into load-balancing weights (Feature 2) and the dashboard.

### Implementation for SwiftGate

**Current state:** `Provider` has `avg_latency_ms` and `uptime_pct` fields, but these are static (seeded, not continuously updated from traffic). `should_retry()` triggers failover *after* a failure, but there is no proactive circuit breaker — SwiftGate will keep sending requests to a failing provider on every new request, only failing over per-request. `get_failover_chain()` already filters by `_get_provider_key()` (key presence) but not by health.

**Changes required:**

1. **New service — `circuit_breaker.py`:** per-provider in-memory (or Redis-backed) state machine:
```python
class CircuitBreaker:
    states: dict[str, str]  # provider_name -> "closed" | "open" | "half_open"
    windows: dict[str, SlidingWindow]  # reuse rate_limiter's SlidingWindow pattern
    thresholds = {"error_rate": 0.5, "latency_p95_ms": 10000, "cooldown_s": 60}

    def record_result(self, provider, success: bool, latency_ms: int): ...
    def is_available(self, provider) -> bool: ...  # closed/half_open=True, open=False
```

2. **Hook into `_record_usage()` and the error path in `_handle_non_streaming`:** call `circuit_breaker.record_result(provider.name, status == "success", latency_ms)` after every request.

3. **Filter `get_failover_chain()` / `route_by_strategy()`:** skip providers where `circuit_breaker.is_available() == False`. This integrates cleanly with the existing failover loop — the chain simply omits tripped providers.

4. **Health metrics roll-up:** a periodic background task (every 60s) that aggregates the sliding window into `Provider.avg_latency_ms` / `uptime_pct` and persists, so the dashboard reflects live health.

5. **Dashboard:** provider health cards (status, error rate, p95 latency, circuit state) with manual "force open/close" controls.

**Effort:** ~2 weeks. The state machine is simple; the integration points already exist (`_record_usage`, `get_failover_chain`).

### Priority: 🔴 HIGH
Required for production reliability. Without it, a degraded provider causes every user to experience a timeout before failover kicks in (currently ~120s per `httpx` timeout in `main.py`). The circuit breaker fast-fails, so users see sub-second failover. This is invisible when things work but critical when they don't. Pairs with Feature 2 (load balancing uses health weights).

---

## Feature 11: Request/Response Logging with Full Audit Trail

### What It Is
Storing the full prompt and response for each request (not just token counts and cost), with configurable retention, redaction, and search. This enables debugging, compliance auditing, prompt-engineering iteration, and fine-tuning dataset curation.

**How competitors do it:**
- **Helicone:** This is their *core product* — full request/response logging with search, filtering, and replay.
- **Portkey:** Full logging with retention policies and PII filtering.
- **LiteLLM:** Logging callbacks to S3, Langfuse, etc.
- **OpenRouter:** Logs prompts by default (1% discount if you allow it) — privacy-controversial.

### How It Works
1. For each request, store: timestamp, api_key, model, full messages (prompt), full response, latency, status, tokens, cost.
2. PII redaction applied *before* storage (SwiftGate already has `pii_redaction` — reuse it).
3. Retention policies: per-key/per-org TTL; "zero-retention" mode stores nothing.
4. Search/filter: by model, by time range, by cost, by status, full-text on prompt content.
5. Replay: re-send a logged request to a different model for comparison.

### Implementation for SwiftGate

**Current state:** `UsageRecord` stores *metadata* (token counts, cost, model, status, latency, task_type) but **not the raw prompt or response**. This is the biggest observability gap. SwiftGate is a cost-intelligence gateway that currently cannot show *what* was sent — only *how much it cost*.

**Changes required:**

1. **New model — `RequestLog`:**
```python
class RequestLog(Base):
    __tablename__ = "request_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usage_record_id: Mapped[int] = mapped_column(ForeignKey("usage_records.id"), index=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), index=True)
    # Full payload (PII-redacted at storage time)
    request_messages: Mapped[dict] = mapped_column(JSON)
    response_data: Mapped[dict] = mapped_column(JSON)
    # Streaming: aggregated content (Feature 7)
    # Privacy / retention
    retention_days: Mapped[int | None]  # null = keep forever, 0 = don't log
    expires_at: Mapped[datetime | None]
    pii_redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
```

2. **Gateway integration:** after `_record_usage()` in `_handle_non_streaming` and the streaming finally-block, insert a `RequestLog` row. Apply PII redaction to the stored messages (the request was already redacted before forwarding; store the redacted form, never the raw PII). For streaming, aggregate content via the Feature 7 accumulator.

3. **Zero-retention mode:** per-key flag `log_requests=False` → skip insertion entirely. Also a global setting for compliance-sensitive deployments.

4. **Retention worker:** periodic job deleting `RequestLog` rows past `expires_at`.

5. **API:** `/v1/logs` with filters (model, time, status, cost-range, full-text search on messages). `/v1/logs/{id}` for full detail. `/v1/logs/{id}/replay` to re-run against a different model.

6. **Storage strategy:** JSON blobs grow fast. For Postgres, consider partitioning `request_logs` by time (e.g., weekly) and/or offloading old logs to S3. For SQLite (dev), cap the table size.

7. **React UI:** a "Requests" explorer — searchable list with expandable rows showing prompt/response, cost, latency. Filter by model/status/time. This is the Helicone-equivalent view.

**Effort:** ~2-3 weeks. The schema and insertion are straightforward; the search UX and retention/offload are the time sinks.

### Priority: 🔴 HIGH
This is Helicone's entire business, and SwiftGate cannot meaningfully compete on observability without it. Beyond competitive parity, it is a prerequisite for: fine-tuning dataset curation (Feature 5), prompt optimization measurement (Feature 3), A/B testing replay (Feature 4), and compliance audit (Feature 12). Privacy must be first-class — reuse the existing PII redaction and offer zero-retention mode.

---

## Feature 12: SOC2/GDPR Compliance Features

### What It Is
The combination of technical controls and *certifications* that allow SwiftGate to be used in regulated industries: data residency enforcement, encryption-at-rest, access logging, data processing agreements (DPAs), right-to-erasure (GDPR), and the SOC 2 Type II audit report.

**How competitors do it:**
- **Portkey:** SOC 2 Type II, GDPR-ready, with data residency options.
- **OpenRouter:** Enterprise tier with privacy controls.
- **Helicone:** EU data residency option.

### How It Works (Technical Components)
1. **Data residency:** route EU user data only to EU-region providers (SwiftGate's MOAT doc Feature 5 covers this).
2. **Encryption:** TLS in transit (httpx does this), encryption at rest (Postgres-level, or app-level for sensitive fields).
3. **Access logging:** audit trail of who accessed what data when (admin actions, key creation/revocation).
4. **Right to erasure:** GDPR "right to be forgotten" — delete all data for a user on request.
5. **DPA:** legal agreement template.
6. **SOC 2 audit:** a months-long process with an auditor (Vanta, Drata, Secureframe) — not code.

### Implementation for SwiftGate

**Current state:** PII redaction is planned (MOAT doc Feature 5). `User`, `ApiKey`, `UsageRecord` exist but there is no data-residency routing, no access-audit log, no erasure workflow, and no encryption-at-rest beyond the DB default.

**Changes required (technical):**

1. **Data residency routing** — as described in MOAT doc Feature 5 (filter models by user region).

2. **Access audit log:**
```python
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str]  # user email or "system"
    action: Mapped[str]  # "key.create", "key.revoke", "admin.model.update", "user.delete"
    target: Mapped[str | None]
    metadata: Mapped[dict] = mapped_column(JSON)
    ip_address: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
```
Instrument all admin/auth mutation endpoints to write `AuditEvent` rows.

3. **Right to erasure:** a `/user/delete` endpoint that cascades deletion across `User`, `ApiKey`, `UsageRecord`, `RequestLog`, `CacheEntry`, `QualityScore`, `AgentEvent` for that user. Make it audited and reversible within a grace window.

4. **Encryption at rest:** Postgres-level (cloud provider feature) for the DB; app-level AES for any secrets in config.

5. **Compliance reporting:** generate reports from `AuditEvent` + `RequestLog` + PII-redaction counts ("In July 2026, N PII entities were redacted; zero raw prompts stored for zero-retention keys").

**Changes required (process — not code):**
- SOC 2 Type II audit: 3-6 months and $20K-50K with a firm like Vanta + auditor.
- GDPR: DPA template, appoint a DPO if serving EU at scale, register with authorities.

**Effort:** ~3 weeks technical + 3-6 months process for SOC 2.

### Priority: 🟢 LOW (technical) / Blocking for enterprise (certification)
The *technical* controls are incremental on the PII-redaction moat. The *certification* is a business investment that only makes sense once enterprise demand is concrete (a specific deal requiring SOC 2). Defer the audit until there is a signed or near-signed enterprise customer justifying the cost. Do not build speculative compliance infrastructure without a buyer.

---

## Feature 13: Custom Pricing Rules (Volume Discounts, Commit-Based Pricing)

### What It Is
Moving beyond a flat `TOKEN_MARGIN` percentage to support tiered pricing: volume discounts (price drops as cumulative spend increases), commit-based pricing (negotiated rates for a committed spend level), per-customer custom rates, and passthrough vs. markup models.

**How competitors do it:**
- **OpenRouter:** 5% markup on pay-as-you-go; lower fees at higher tiers; credit pools.
- **LiteLLM:** Custom budget/preference configs per team; passthrough billing options.
- **Portkey:** Enterprise custom pricing.

### How It Works
1. A `PricingRule` defines how to compute the charge for a request: base = provider cost, then apply modifiers (markup %, fixed fee, volume discount tier, commit credit drawdown).
2. Rules can be scoped globally, per-org, or per-key.
3. The cost engine applies the rule at recording time.
4. Commit tracking: a customer pre-pays $10K; each request draws down the commit balance at the negotiated rate.

### Implementation for SwiftGate

**Current state:** `cost_engine._record_usage()` applies a single global `settings.TOKEN_MARGIN` (default 1%) to every request. `pricing.py` seeds per-model token prices. There is no concept of tiers, commits, or per-customer rates.

**Changes required:**

1. **New model — `PricingRule`:**
```python
class PricingRule(Base):
    __tablename__ = "pricing_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str]
    scope: Mapped[str]  # "global", "org", "api_key"
    scope_id: Mapped[int | None]  # org_id or api_key_id
    rule_type: Mapped[str]  # "markup_pct", "fixed_plus", "volume_tiered", "commit"
    config: Mapped[dict] = mapped_column(JSON)
    # volume_tiered example: {"tiers": [{"upto_cents": 100000, "markup": 0.05}, {"markup": 0.02}]}
    # commit example: {"commit_cents": 1000000, "rate_modifier": 0.0, "drawdown_balance_cents": 750000}
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

2. **New service — `pricing_engine.py`:** `compute_charge(base_cost_cents, api_key, org)` → resolves the highest-priority matching rule and applies it. Replaces the inline `margin = 1 + settings.TOKEN_MARGIN` in `_record_usage()`.

3. **Commit drawdown:** when a commit rule matches, subtract from `drawdown_balance_cents`; when exhausted, fall back to the next rule (e.g., pay-as-you-go markup).

4. **Volume tiers:** track rolling 30-day spend per org (cached in Redis) to determine the active tier.

5. **API/UI:** pricing-rule CRUD (admin), per-org commit balance view (customer-facing), invoice preview.

**Effort:** ~2-3 weeks. The rule resolution is a strategy-pattern dispatch; the commit/tier state tracking is the fiddly part.

### Priority: 🟡 MEDIUM
Enables an enterprise/committed-revenue sales motion. Not urgent while the customer base is small and pay-as-you-go, but becomes important when negotiating annual contracts. The flat-margin model is fine for self-serve; this unlocks sales-driven deals.

---

## Feature 14: Token Budget Forecasting and Spend Predictions

### What It Is
Time-series forecasting of future spend based on historical usage patterns — "at the current rate, you will spend $X by month-end" and "your agent-A burn rate increased 40% week-over-week." This is the *aggregate* analog of SwiftGate's per-request cost prediction.

**How competitors do it:**
- **Helicone:** Spend-analytics dashboards with trend lines.
- **OpenRouter:** Spending-limit warnings (post-hoc).
- **Cloudflare AI Gateway:** Analytics with trend visualization.
- None do true *forecasting* — most show historical trends only.

### How It Works
1. Aggregate `UsageRecord.total_cost_cents` by day/hour per api_key/agent/org.
2. Fit a forecast model: simple linear regression on the time series, or exponential smoothing for trend + seasonality.
3. Predict: end-of-month spend, days-until-budget-exhausted, anomaly detection (spend spike alerts).
4. Alert when forecast crosses a threshold (e.g., "projected to exceed budget in 3 days").

### Implementation for SwiftGate

**Current state:** SwiftGate has the per-request ML predictor (`prediction_ml.py`) — a *data flywheel moat* (MOAT doc Feature 1). It also records `total_spend_cents` on `ApiKey` and `spend_cents` on `Agent`. The analytics router (`/v1/usage/daily`) returns historical daily aggregates. There is **no forward-looking forecast** — only historical totals.

**Changes required:**

1. **New service — `spend_forecast.py`:**
```python
async def forecast_spend(db, entity_type, entity_id, horizon_days=30):
    series = await _load_daily_spend(db, entity_type, entity_id, days=90)
    # Simple: linear regression on recent trend
    # Better: Holt's linear trend (handles growth/decay)
    forecast = _holt_forecast(series, horizon_days)
    return {
        "history": series,
        "forecast": forecast,
        "projected_month_end_cents": forecast[-1],
        "trend_pct_week_over_week": ...,
        "days_until_budget_exhausted": ...,
    }
```

2. **Anomaly detection:** flag days where actual spend > forecast + 2σ (spend spike). Emit a webhook event (Feature 8) on anomaly.

3. **Budget-exhaustion alerting:** integrate with the existing `BudgetAlert` / webhook system — "Agent X projected to exhaust budget in 3.2 days at current rate."

4. **API endpoints:** `/v1/forecast?key_id=X`, `/v1/forecast?agent_id=Y`.

5. **React UI:** forecast charts overlaid on actuals; budget-exhaustion countdown.

6. **Model choice:** start with Holt's linear trend (no external deps, captures growth/decay). Escalate to Prophet or a lightweight ML model if seasonality (weekday/weekend patterns) matters. Pure Python `statsmodels` covers both.

**Effort:** ~2 weeks. The data is already being collected; this is analytics + a forecasting library + UI.

### Priority: 🟡 MEDIUM
Builds directly on the cost-prediction moat and differentiates from competitors that only show historical spend. The per-request prediction (already built) tells you "this request costs $X"; the forecast tells you "this month will cost $Y." Together they are the full cost-intelligence story that is SwiftGate's positioning. Medium rather than high only because it is additive value, not a gap users will notice is missing.

---

## Feature 15: Model Performance Benchmarking

### What It Is
Standardized, reproducible benchmarks comparing models on cost, latency, and quality across task types — both SwiftGate-internal (from real traffic via `QualityScore`) and curated benchmark suites (e.g., a set of canonical prompts run periodically).

**How competitors do it:**
- **TensorZero:** Built-in evaluation harness; measures model performance on custom datasets.
- **Artificial Analysis / Marion:** Independent benchmark leaderboards (not gateways).
- **OpenRouter:** Community-driven model rankings.
- **Together / Fireworks:** Publish benchmark results for hosted models.

### How It Works
1. **Empirical benchmarks (from traffic):** aggregate `QualityScore`, `latency_ms`, `total_cost_cents` per (model, task_type) from real `UsageRecord` data. This is the quality-data flywheel (MOAT doc Feature 2) surfaced as a leaderboard.
2. **Curated benchmarks (run on demand):** a fixed set of prompts per task type (coding, reasoning, math, writing). Periodically run each active model against the suite, record quality (LLM-as-judge) + latency + cost. Store as benchmark runs.
3. **Leaderboard:** a public/internal page ranking models by quality-per-dollar per task.

### Implementation for SwiftGate

**Current state:** SwiftGate already has:
- `QualityScore` records (empirical, from signals).
- `route_by_quality_per_dollar()` computing quality-per-dollar rankings.
- `compare_models()` showing cost/quality per model for a given prompt.
- `prediction_ml.get_bucket_details()` showing per-(model, task) output-token stats.

What is missing: a *standardized* benchmark suite (curated prompts, periodic execution, stored results, and a leaderboard view).

**Changes required:**

1. **Curated benchmark suite:** a YAML/JSON file of prompt sets per task type (e.g., 20 coding prompts, 20 reasoning prompts). Ship as part of the repo (`benchmarks/suite.yaml`).

2. **New model — `BenchmarkRun`:**
```python
class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suite_version: Mapped[str]
    model_id: Mapped[str]
    task_type: Mapped[str]
    prompt_id: Mapped[str]
    quality_score: Mapped[float | None]  # from LLM judge
    latency_ms: Mapped[int]
    cost_cents: Mapped[int]
    response_excerpt: Mapped[str | None]
    run_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
```

3. **Benchmark runner service:** iterates the suite, sends each prompt to each active model via the gateway, invokes the LLM-as-judge (reuse the quality-router's automated-evaluation path), stores results. Run via a CLI command or scheduled job.

4. **Leaderboard API + UI:** `/v1/benchmarks/leaderboard?task=code` returning ranked models by quality-per-dollar. React page with filters and historical trend (did Model X get better after the vendor's update?).

5. **Marketing surface:** a public leaderboard page (like Artificial Analysis) that showcases SwiftGate's measurement infrastructure and drives organic traffic.

**Effort:** ~2-3 weeks. The empirical side is 90% built; the curated suite + runner + leaderboard UI is the lift.

### Priority: 🟡 MEDIUM
Valuable for three reasons: (1) internal — better routing data; (2) user-facing — "which model should I use?"; (3) marketing — a public leaderboard is a strong organic-acquisition channel. It compounds with the quality-data flywheel. Medium priority because it depends on having enough models in the catalog and enough traffic for empirical data to be meaningful; the curated suite can ship independently.

---

## Cross-Feature Dependencies and Sequencing

```
Ship first (HIGH priority, high ROI, low effort):
  ┌─────────────────────────────────────────────────┐
  │ 8.  Webhook/event delivery (1-1.5 wk)           │ ← alerts already detected
  │ 1.  Fallback chains config (1 wk)               │ ← failover loop exists
  │ 10. Circuit breaker (2 wk)                      │ ← integrates with failover
  │ 11. Request/response logging (2-3 wk)           │ ← prerequisite for several
  └─────────────────────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
  ┌────────────┐ ┌────────────┐ ┌──────────────┐
  │ 2. Load    │ │ 14. Spend  │ │ 9. Multi-    │
  │ balancing  │ │ forecast   │ │ tenant keys  │
  │ (2 wk)     │ │ (2 wk)     │ │ (3 wk)       │
  └────────────┘ └────────────┘ └──────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │ 13. Custom pricing (2-3 wk)                       │
  │ 7. Streaming aggregation (3 days — partial only)  │
  │ 15. Benchmarking (2-3 wk)                         │
  └──────────────────────────────────────────────────┘
                        │
         Defer (LOW priority or out of scope):
         ┌────────────────────────────────────────────┐
         │ 4. A/B testing — needs volume              │
         │ 3. Prompt compression — pair w/ prediction │
         │ 6. Embedding cache — narrow use case       │
         │ 12. SOC2/GDPR — process, not code          │
         │ 5. Fine-tuning — out of scope (platform)   │
         └────────────────────────────────────────────┘
```

**Hard dependency:** Feature 11 (request/response logging) is a prerequisite for Features 5 (fine-tuning datasets), 4 (A/B replay), and strengthens 12 (compliance audit). Build it early.

**Strong pairing:** Features 8 (webhooks) + 14 (forecast) + 10 (circuit breaker) together make SwiftGate *proactive* rather than passive — it notifies before budgets break, routes around failures, and predicts spend. This trio is the "operational intelligence" layer that competitors lack in integrated form.

---

## Competitive Feature Matrix (Extended)

| Feature | SwiftGate (current) | Portkey | LiteLLM | Helicone | OpenRouter | Cloudflare AI GW | TensorZero |
|---------|:-------------------:|:-------:|:-------:|:--------:|:----------:|:----------------:|:----------:|
| 1. Fallback chains | ⚠️ partial | ✅ | ✅ | ❌ | ⚠️ | ✅ | ✅ |
| 2. Load balancing | ❌ | ✅ | ✅ | ❌ | ⚠️ | ✅ | ❌ |
| 3. Prompt compression | ❌ | ❌ | ⚠️ | ❌ | ✅ | ❌ | ❌ |
| 4. A/B testing | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 5. Fine-tuning mgmt | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 6. Embedding cache | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| 7. Streaming aggregation | ⚠️ partial | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 8. Webhook alerts | ⚠️ detected, not delivered | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| 9. Multi-tenant keys | ⚠️ user-only | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| 10. Circuit breaker | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| 11. Full req/resp logging | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| 12. SOC2/GDPR | ⚠️ PII planned | ✅ | ❌ | ✅ | ⚠️ | ✅ | ❌ |
| 13. Custom pricing | ❌ flat only | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| 14. Spend forecasting | ❌ | ❌ | ❌ | ⚠️ | ❌ | ⚠️ | ❌ |
| 15. Benchmarking | ⚠️ empirical only | ❌ | ❌ | ❌ | ⚠️ | ❌ | ✅ |

Legend: ✅ = ships it | ⚠️ = partial / implicit | ❌ = does not

**Key takeaways from the matrix:**
- SwiftGate's biggest parity gaps are **8 (webhook delivery)**, **10 (circuit breaker)**, **11 (full logging)**, and **1 (configurable fallback chains)** — all HIGH priority and all incremental on existing code.
- SwiftGate's biggest *differentiation opportunities* among these are **14 (forecasting)** — almost no competitor does forward-looking spend prediction — and **15 (benchmarking)** as a marketing surface, both building on the cost/quality data flywheels.
- **Feature 5 (fine-tuning)** is uniformly absent from gateways because it is a platform feature — confirming the recommendation not to build it.

---

## Relationship to Existing Moat Research

This document covers *competitive parity* features. The `MOAT_FEATURES_RESEARCH.md` covers *differentiation* features. Several items interact:

| This report's feature | Moat-doc relationship |
|-----------------------|----------------------|
| 1. Fallback chains | Moat doc Feature 6 (assessed as weak moat, build as feature) — *same conclusion* |
| 3. Prompt compression | Moat doc Feature 8 (weak moat, pair with ML prediction) — *same conclusion* |
| 7. Streaming aggregation | Enables moat doc Feature 4 (semantic cache correctness checks) |
| 11. Request/response logging | Prerequisite for moat doc Feature 2 (quality data) at scale |
| 12. SOC2/GDPR | Overlaps moat doc Feature 5 (PII + data residency) |
| 14. Spend forecasting | Extends moat doc Feature 1 (ML cost prediction) to aggregate forecasts |
| 15. Benchmarking | Extends moat doc Feature 2 (quality-aware routing) into a public leaderboard |

The moat features (ML cost prediction, quality-aware routing, agent budgets, semantic cache, PII redaction) remain SwiftGate's differentiation. The features in this report are the *table-stakes* and *adjacent* capabilities needed to be credible against Portkey/LiteLLM/Helicone/OpenRouter. Building both in the recommended sequence yields a product that is both competitive *and* differentiated.

---

## Methodology

- **Codebase analysis:** Inspected SwiftGate's actual FastAPI backend (`models.py`, `gateway.py`, `cost_engine.py`, `provider_router.py`, `rate_limiter.py`, `semantic_cache.py`, `quality_router.py`, `prediction_ml.py`, `streaming.py`, `config.py`, `main.py`, `agents.py`, `pricing.py`) to assess each feature against the real implementation — not assumptions about a generic gateway.
- **Existing research:** Cross-referenced `MOAT_FEATURES_RESEARCH.md` (768 lines) to avoid duplication and to identify where parity features reinforce moat features.
- **Competitive landscape:** Assessed Portkey, LiteLLM, Helicone, OpenRouter, Cloudflare AI Gateway, Bifrost, and TensorZero based on their documented feature sets and known positioning.
- **Prioritization framework:** Each feature scored on (a) competitor coverage, (b) user expectation, (c) incremental effort given existing code, (d) dependency on other features.

---

*Generated: July 27, 2026*
