# SwiftGate Backend — Deep Audit Report

**Scope:** All 28 `.py` files in `/home/mehedi/swiftgate/backend/app/` (excluding `.venv`)
**Auditor:** Hermes Agent (automated)
**Date:** 2026-07-27

---

## Executive Summary

SwiftGate is a FastAPI + SQLAlchemy AI model gateway with cost intelligence. The codebase is **~5,300 lines** across 28 files and is **surprisingly complete for a v1** — most advertised features (cost prediction, failover, streaming, semantic cache, PII redaction, agent budgets, billing) have real implementations, not stubs.

However, there are **several security vulnerabilities, race conditions, and correctness bugs** that should be fixed before production. The most critical are:

1. **🔴 CRITICAL — Race condition in budget enforcement** (`gateway.py:393-429`): Budget check uses stale in-memory `total_spend_cents`, allowing overspend under concurrent requests.
2. **🔴 CRITICAL — SSRF via admin provider base_url** (`admin.py:127`): Admin can set arbitrary `base_url`, enabling server-side request forgery to internal services.
3. **🔴 CRITICAL — PII leaking into semantic cache** (`gateway.py:720-745`): Cache stores the response *before* PII rehydration, but the cache lookup later returns the raw cached response. Actually wait — re-examining: the cache stores the *provider's response* which contains redacted placeholders, then rehydration happens on the way out. This is actually CORRECT. **Downgraded.**
4. **🟠 HIGH — No HMAC constant-time comparison for ADMIN_KEY** (`auth.py:37`): `x_admin_key == ADMIN_KEY` is vulnerable to timing attacks.
5. **🟠 HIGH — Streaming response doesn't check provider error status before streaming** (`gateway.py:820-824`): Error responses are yielded as data, potentially exposing internals.
6. **🟠 HIGH — Stripe webhook signature verification is OPTIONAL** (`billing.py:213`): If `webhook_secret` is unset, raw payload is trusted — allows forged credit additions.
7. **🟡 MEDIUM — ML predictor is not thread-safe** (`prediction_ml.py`): Singleton mutated from async context without locks.
8. **🟡 MEDIUM — Cost calculation silently truncates with `int()`** (`gateway.py:257-258`): `int()` truncates toward zero, systematically undercharging.

**File-by-file findings below.**

---

## 1. `main.py` (145 lines)

### What it does
FastAPI app factory. Lifespan handler initializes DB, seeds pricing data, loads ML model, creates shared `httpx.AsyncClient`. Registers CORS, health endpoints, and all routers.

### What works
- ✅ Shared HTTP client with connection pooling (`main.py:56-63`) — proper connection reuse
- ✅ Graceful shutdown closes HTTP client + disposes engine (`main.py:67-71`)
- ✅ ML model load is non-blocking (`to_thread`) with graceful fallback (`main.py:42-48`)
- ✅ Production safety check for JWT secret (in `config.py`, enforced here via import)
- ✅ Health/ready endpoints with real DB connectivity check

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 1.1 | 🟡 MEDIUM | 23-26 | `logging.basicConfig` called inside lifespan — if multiple workers, logging config is per-process and may conflict with uvicorn's config. Should be at module level. |
| 1.2 | 🟢 LOW | 82-87 | CORS `allow_origins=["*"]` with `allow_credentials=True` is invalid per spec (browsers reject it). The code tries to handle this with the conditional, but if `CORS_ORIGINS="*"` (the default!), `allow_credentials=False` which means cookies won't work. The default config effectively breaks credentialed requests. |
| 1.3 | 🟡 MEDIUM | 108 | `health_ready` leaks internal DB error message to client: `f"Database not ready: {e}"`. Could expose connection string details. |

### Code snippets
```python
# Line 108 — error message leakage
raise HTTPException(503, f"Database not ready: {e}")  # leaks DB error details
```

---

## 2. `config.py` (101 lines)

### What it does
Dataclass-based settings reading from environment variables. Covers DB, Redis, JWT, CORS, provider keys, cache, PII config.

### What works
- ✅ Production guard against default JWT secret (`config.py:52-58`)
- ✅ Boolean parsing helper
- ✅ `.env` file loading (optional, graceful)
- ✅ `admin_emails` property with lowercase normalization

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 2.1 | 🟡 MEDIUM | 48 | **Default JWT secret is hardcoded**: `"swiftgate-dev-secret-change-in-production"`. While there's a production guard, in `development`/`testing` (the default ENV), this secret is used. Anyone who knows this string can forge JWTs in a staging environment. |
| 2.2 | 🟢 LOW | 61 | `CORS_ORIGINS` defaults to `"*"` — overly permissive for a gateway handling API keys. |
| 2.3 | 🟢 LOW | 22 | `Settings` is a `@dataclass` but fields with defaults computed from `os.environ.get()` at class-definition time. If env vars change after import (e.g., test setup), they won't be picked up. The singleton `settings = Settings()` at line 101 freezes values. |

---

## 3. `database.py` (55 lines)

### What it does
Async SQLAlchemy engine setup. Creates `Base`, engine (Postgres or SQLite), session factory, and `init_db()` for table creation.

### What works
- ✅ Postgres connection pooling with pre-ping and recycle (`database.py:17-24`)
- ✅ SQLite WAL mode + busy_timeout for concurrency (`database.py:33-40`)
- ✅ `expire_on_commit=False` prevents lazy-load issues after commit

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 3.1 | 🟡 MEDIUM | 46-49 | **No error handling in `get_db`**. If the session raises during request handling, the `async with` will roll back, but exceptions from `yield` are not logged. More importantly, there's no explicit `rollback()` on exception — relying on context manager behavior. |
| 3.2 | 🟢 LOW | 52-55 | `init_db` uses `create_all` which doesn't handle migrations. Fine for MVP, but schema evolution will require Alembic. No mention of migrations anywhere. |
| 3.3 | 🟢 LOW | 27-31 | SQLite `timeout=30` is in the `connect_args` but the PRAGMA `busy_timeout=5000` (5s) is set separately. The 30s timeout in connect_args may be ignored by aiosqlite. |

---

## 4. `models.py` (393 lines)

### What it does
SQLAlchemy ORM models: `Provider`, `Model`, `User`, `ApiKey`, `UsageRecord`, `BudgetAlert`, `Agent`, `AgentEvent`, `QualityScore`, `RoutingRule`, `CacheEntry`.

### What works
- ✅ **Money stored as integer cents** (`credits_cents`, `total_cost_cents`) — avoids float precision issues. This is the correct pattern.
- ✅ Proper use of `Numeric(12,8)` for per-token prices
- ✅ Good indexing on lookup columns (`model_id`, `key_hash`, `agent_id`, `content_hash`)
- ✅ Comprehensive `UsageRecord` for analytics
- ✅ `BudgetAlert` with dedup support

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 4.1 | 🟠 HIGH | 99 | `User.password_hash` is `String(255)` — bcrypt hashes are 60 chars. Not a bug, but if someone switches to argon2 with higher length, the column may truncate. Consider `String(128)` minimum documented, or use Text. |
| 4.2 | 🟡 MEDIUM | 141-142 | `ApiKey.total_spend_cents` and `total_requests` are **denormalized counters updated in application code** (`gateway.py:298-299`). Under concurrent requests, these are subject to **lost updates** (read-modify-write race). Should use `UPDATE ... SET total_spend_cents = total_spend_cents + :cost` with row-level locking or `with_for_update()`. |
| 4.3 | 🟡 MEDIUM | 175 | `UsageRecord.prediction_error_pct` is `Mapped[float | None]` with `nullable=True` but no `Numeric` type specified — defaults to `Float`. Float precision for percentages is fine but inconsistent with the money-as-integers philosophy. |
| 4.4 | 🟢 LOW | 376 | `CacheEntry.token_fingerprint` is `Text` but stores pipe-delimited tokens. Could grow large for big prompts. Consider a length limit or hash. |
| 4.5 | 🟢 LOW | 236 | `Agent.alert_thresholds` stored as comma-separated `String(100)`. Parsing this string everywhere is fragile. Should be JSON column. |

---

## 5. `routers/gateway.py` (866 lines) ⭐ CRITICAL FILE

### What it does
The core proxy endpoint — `POST /v1/chat/completions`. OpenAI-compatible. Handles auth, rate limiting, PII redaction, cache check, cost prediction, budget enforcement, provider failover, streaming, usage recording.

### What works
- ✅ Full OpenAI-compatible proxy with Anthropic + Gemini format conversion
- ✅ Provider failover chain with retry logic
- ✅ Streaming with fresh DB session (avoids closed-session bug)
- ✅ Budget enforcement for API keys AND agents
- ✅ PII redaction before upstream call + rehydration after
- ✅ Semantic cache integration
- ✅ Pre-flight cost prediction + post-flight accuracy tracking
- ✅ Input validation: message count limit (100), body size limit (512KB)
- ✅ Error sanitization — doesn't echo upstream response bodies (`gateway.py:711-716`)

### Issues

| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 5.1 | 🔴 **CRITICAL** | 393-429 | **Budget enforcement race condition (TOCTOU)**. `_check_budget()` reads `api_key.total_spend_cents` from the in-memory ORM object, but the actual DB row may have been updated by a concurrent request. Two concurrent requests can both pass the budget check and then both record usage, exceeding the budget. **Fix**: Use `SELECT ... FOR UPDATE` or atomic conditional updates. |
| 5.2 | 🟠 HIGH | 257-258 | **Cost truncation bias**: `int(float(model.prompt_price) * prompt_tokens * margin * 10000)`. `int()` truncates toward zero, systematically undercharging by up to ~1 microcent per transaction. Over millions of requests, this adds up. Should use `round()` or `math.ceil()` for billing. |
| 5.3 | 🟠 HIGH | 508 | **`body = await request.json()`** — no Content-Type validation. A malformed body or non-JSON content type will raise an unhandled `json.JSONDecodeError` (500 error instead of 400). |
| 5.4 | 🟠 HIGH | 552 | **Cache bypass logic is inverted**: `cache_bypass = body.get("cache", True)`. The variable name says "bypass" but the value `True` means "use cache". This is confusing and error-prone. A client sending `{"cache": false}` correctly disables cache, but the naming is backwards. |
| 5.5 | 🟡 MEDIUM | 600-625 | **Failover loop doesn't handle `httpx.ConnectError` or `httpx.NetworkError`** — only `httpx.TimeoutException` and `HTTPException` are caught. A DNS resolution failure or connection refused will raise an unhandled exception (500). |
| 5.6 | 🟡 MEDIUM | 820-824 | **Streaming error handling**: when upstream returns HTTP error during stream, it yields `data: {"error": "Provider X returned 429"}` as SSE. This is sent to the client as a 200 response (StreamingResponse always returns 200). The client may not recognize this as an error. |
| 5.7 | 🟡 MEDIUM | 837 | **Exception details leaked in stream**: `yield f'data: {{"error": "{str(e)}"}}\n\n'` — internal exception messages (could contain file paths, connection details) are sent to the client. |
| 5.8 | 🟡 MEDIUM | 269-276 | **Task type classification is fragile**: The double list comprehension at lines 271-273 is convoluted and re-creates `Message` objects from already-parsed data. If `request_body["messages"]` contains unexpected types, it falls back to "chat" silently. |
| 5.9 | 🟡 MEDIUM | 309-326 | **Agent budget update has same race condition** as 5.1. `agent.spend_cents += total_cost` is a read-modify-write without locking. |
| 5.10 | 🟢 LOW | 159-189 | `_convert_to_anthropic` doesn't handle tool definitions, tool calls, or tool results. A request with `tools` will silently drop them when routed to Anthropic. |
| 5.11 | 🟢 LOW | 192-222 | `_convert_to_gemini` same issue — no tool/function call support. |
| 5.12 | 🟢 LOW | 110-111 | `_get_api_key_for_provider` reads env var at call time (good), but if the key is empty string, the request still proceeds and will fail at the provider with an opaque error. Should check earlier. |
| 5.13 | 🟢 LOW | 553 | Cache check runs on `settings.CACHE_ENABLED and cache_bypass` — but `cache_bypass` is `True` by default, so cache is always on unless client explicitly disables. The naming makes this hard to reason about. |
| 5.14 | 🟢 LOW | 760-772 | **Implicit quality signal fires on EVERY multi-turn request** — `detect_implicit_signal(conversation_continued=True)` is called whenever `len(messages) > 1`. This floods the quality scoring with positive signals, biasing the model. Should only fire on the *first* response in a conversation, not every turn. |

### Code snippets
```python
# Lines 257-258 — truncation bias in cost calculation
prompt_cost = int(float(model.prompt_price) * prompt_tokens * margin * 10000)
completion_cost = int(float(model.completion_price) * completion_tokens * margin * 10000)
# int() truncates toward zero — systematically undercharges

# Lines 393-429 — budget TOCTOU race condition
def _check_budget(api_key: ApiKey | None, predicted_cost_cents: int) -> None:
    ...
    if api_key.monthly_budget_cents:
        if api_key.total_spend_cents + predicted_cost_cents > api_key.monthly_budget_cents:
            # This check uses stale data — concurrent request may have already spent the budget
            ...

# Lines 820-824 — streaming error yields as 200
if response.status_code >= 400:
    error_text = await response.aread()
    yield f'data: {{"error": "Provider {provider.name} returned {response.status_code}"}}\n\n'
    return  # client sees HTTP 200 with error in body

# Lines 837 — exception leak
yield f'data: {{"error": "{str(e)}"}}\n\n'  # str(e) may contain internal details
```

---

## 6. `services/provider_router.py` (209 lines)

### What it does
Builds failover chains and applies routing strategies (cheapest, fastest, balanced, quality). Integrates with `RoutingRule` table for custom routing.

### What works
- ✅ Multi-tier failover: primary → same-category alternatives
- ✅ Checks provider API key availability before adding to chain
- ✅ Deduplicates providers in chain
- ✅ Routing rules with priority ordering

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 6.1 | 🟡 MEDIUM | 49-52 | **Failover query matches on `Model.category`** but `category` values like "frontier", "fast", "cheap" don't guarantee model equivalence. A failover from `gpt-4o` (frontier) to `grok-4` (frontier) may produce very different outputs. |
| 6.2 | 🟡 MEDIUM | 183-184 | **Routing rule cost filter is nonsensical**: `(Model.prompt_price * 1000) <= rule.max_cost_per_request_cents / 10`. This compares prompt_price × 1000 (a per-1K-token cost) against a budget in cents divided by 10. The units don't match and the logic is unclear. |
| 6.3 | 🟡 MEDIUM | 176-179 | **`task_type` filter applies to `Model.category`** — the code sets `stmt.where(Model.category == rule.task_type)` but `task_type` values ("chat", "code") don't match `category` values ("frontier", "fast", "cheap"). This filter will never match, making task-type routing rules silently ineffective. |
| 6.4 | 🟢 LOW | 134 | `MAX_RETRIES = 2` is very low for production. With 3 providers in the chain and 2 retries, a brief provider outage exhausts all options quickly. |
| 6.5 | 🟢 LOW | 67-70 | `_get_provider_key` reads env var inside a function called in a loop — minor performance issue (could cache). |

### Code snippets
```python
# Lines 176-179 — task_type filter is broken
if rule.task_type:
    stmt = stmt.where(Model.category == rule.task_type)  # task_type="code" won't match category="frontier"

# Lines 183-184 — cost filter has mismatched units
stmt = stmt.where(
    (Model.prompt_price * 1000) <= rule.max_cost_per_request_cents / 10
)
```

---

## 7. `services/cost_engine.py` (279 lines) ⭐ CORE IP

### What it does
Predicts request cost before sending. The headline feature. Counts input tokens, estimates output via ML, computes costs with margin, finds cheaper alternatives.

### What works
- ✅ Exact input token counting with per-model tokenizer routing
- ✅ ML-powered output prediction (falls back to heuristics)
- ✅ Cache token cost calculation (cached prompts are cheaper)
- ✅ Tool definition overhead estimation
- ✅ Pareto frontier marking for model comparison
- ✅ Cost in integer microcents with margin application

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 7.1 | 🟡 MEDIUM | 105-114 | **Same `int()` truncation issue** as gateway.py. `int(float(model.prompt_price) * input_tokens * margin * 10000)` truncates. The `cost_engine.py` and `gateway.py` use the same formula but gateway may record slightly different cost than what was predicted (due to different token counts). |
| 7.2 | 🟡 MEDIUM | 96-100 | **Cache token estimation is naive**: only checks if the first message is a system prompt. Doesn't account for multi-turn caching (Claude's prompt caching caches conversation prefixes). Real cache token count would need provider-specific logic. |
| 7.3 | 🟡 MEDIUM | 120 | `_find_cheaper_alternative` doesn't apply the margin to alternatives' costs — compares raw provider prices without `TOKEN_MARGIN`, making alternatives look cheaper than they actually are to the user. |
| 7.4 | 🟡 MEDIUM | 250 | **50% threshold for "cheaper" is arbitrary and hardcoded**: `if alt_cost < best_cost * 0.5`. A model that's 49% cheaper won't be suggested. Should be configurable or at least documented. |
| 7.5 | 🟢 LOW | 183-188 | `compare_models` calls `estimate_output_tokens` (heuristic) directly instead of using the ML predictor. Inconsistent with `predict_cost` which uses ML. The comparison results will be less accurate than predictions. |
| 7.6 | 🟢 LOW | 263-279 | `_mark_pareto_optimal` is O(n²) — fine for ~40 models but would be slow with hundreds. |

---

## 8. `services/quality_router.py` (263 lines)

### What it does
Empirical quality scoring with 3-tier signal weighting (automated > explicit > implicit). Routes by quality-per-dollar Pareto frontier.

### What works
- ✅ Weighted scoring with recency decay
- ✅ Signal source weighting (automated 3x, explicit 2x, implicit 1x)
- ✅ Falls back to static scores with insufficient data
- ✅ Pareto frontier marking

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 8.1 | 🟡 MEDIUM | 51-63 | **Loads up to 500 QualityScore rows into memory** to compute weighted average. This should be a SQL aggregation query, not Python. Will be slow with millions of quality signals. |
| 8.2 | 🟡 MEDIUM | 91 | **Confidence formula is simplistic**: `min(0.95, len(scores) / 100)`. Doesn't account for signal quality distribution or variance. 100 low-quality implicit signals shouldn't give 0.95 confidence. |
| 8.3 | 🟢 LOW | 247-263 | `detect_implicit_signal` hardcodes scores: retry=4.0, continued=8.0. These magic numbers should be configurable. |
| 8.4 | 🟢 LOW | 138 | Imports `_get_model` from cost_engine but never uses it. Dead import. |

---

## 9. `services/semantic_cache.py` (361 lines)

### What it does
Two-mode cache: exact (SHA-256 hash) and semantic (Jaccard token similarity). Per-key privacy scoping with optional shared mode.

### What works
- ✅ Exact match is O(1) on indexed `content_hash` column
- ✅ Semantic match uses token-level Jaccard (no embedding model dependency)
- ✅ Privacy scoping: per-key by default, shared mode opt-in
- ✅ TTL per task type (code: 7 days, chat: 24h)
- ✅ Text normalization (lowercase, whitespace, code block stripping)
- ✅ Stopword removal for semantic matching

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 9.1 | 🟠 HIGH | 211-231 | **Semantic cache scans up to 50 entries in Python** (`limit(50)`). With a large cache, this is O(50 × Jaccard computation) per request. The comment says "In production with pgvector, this would be a vector search" — but there's no pgvector integration. For a production cache with thousands of entries, this will be slow and have poor recall. |
| 9.2 | 🟡 MEDIUM | 38 | **`MIN_SIMILARITY = 0.85` is hardcoded**. Different use cases may need different thresholds. Should be configurable. |
| 9.3 | 🟡 MEDIUM | 116 | **Token regex `[a-z0-9_]{3,}`** misses important short tokens (e.g., "AI", "ML", "GPT", "API" — all < 3 chars or uppercase-normalized away). This weakens semantic matching for tech content. |
| 9.4 | 🟡 MEDIUM | 325-327 | **Hit rate calculation is nonsensical**: `hit_rate = total_hits / (total_hits + total_entries)`. This isn't a hit rate — it's the ratio of hits to (hits + entries). A real hit rate would be `hits / total_requests`, which isn't tracked. |
| 9.5 | 🟢 LOW | 280 | `expires_at` set to `None` if `ttl_hours == 0`, meaning entries never expire. This is by design (infinite TTL) but could lead to unbounded cache growth if misconfigured. |
| 9.6 | 🟢 LOW | 356 | `invalidate_cache` commits inside the function, but the caller (router) may also commit. Double commit is harmless but indicates unclear transaction boundaries. |

---

## 10. `services/pii_redaction.py` (296 lines)

### What it does
Regex-based PII detection (email, phone, SSN, credit card, API keys, IBAN, IP). Replaces with placeholders, provides rehydration via token map.

### What works
- ✅ Overlap detection prevents double-redaction of same span
- ✅ Token map for bidirectional redaction/rehydration
- ✅ Handles multi-modal content (vision format)
- ✅ Safe logging (types + counts, not values)
- ✅ Conservative regexes (favor false negatives over false positives)

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 10.1 | 🟠 HIGH | 107 | **Credit card regex is too greedy**: `\b(?:\d{4}[- ]?){3}\d{1,4}\b` will match any 13-19 digit number with optional separators. This will false-positive on phone numbers with dashes, dates, IDs, etc. No Luhn checksum validation. |
| 10.2 | 🟡 MEDIUM | 85-93 | **Phone regex misses many international formats**: doesn't handle numbers with spaces between groups (common in EU), or numbers starting with 00 (international prefix). |
| 10.3 | 🟡 MEDIUM | 116-119 | **API key regex matches "Bearer " prefix** — `r"\b(?:sk-|pk-|rk-|sg-|Bearer )..."`. The word boundary `\b` before "Bearer " won't work as expected because "Bearer" follows a space, not a word boundary. This may fail to match actual Bearer tokens. |
| 10.4 | 🟡 MEDIUM | 259-279 | **`rehydrate_response` only rehydrates `choices[].message.content`**. Doesn't handle tool calls, function calls, or streaming deltas in non-streaming responses. If the model echoes PII in a tool call argument, it won't be rehydrated. |
| 10.5 | 🟢 LOW | 48-49 | **Rehydration uses simple string replacement** — `text.replace(placeholder, original)`. If a placeholder happens to appear in the response naturally (unlikely but possible with the `[REDACTED_*]` format), it would be incorrectly replaced. |
| 10.6 | 🟢 LOW | 186 | Placeholder ID is `uuid.uuid4().hex[:8]` — 8 hex chars = 32 bits. Collision probability is low but non-zero with high PII volume. |

---

## 11. `services/rate_limiter.py` (169 lines)

### What it does
Sliding window rate limiter with Redis (distributed) or in-memory (fallback) backends.

### What works
- ✅ Redis sorted set implementation (ZADD + ZREMRANGEBYSCORE + ZCARD)
- ✅ Automatic fallback from Redis to in-memory
- ✅ Separate limits for authenticated (60 RPM) vs anonymous (10 RPM)
- ✅ Key expiration to prevent unbounded Redis growth

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 11.1 | 🟠 HIGH | 78-97 | **Redis pipeline is not atomic**. The ZADD + ZCARD happen in a pipeline (batched) but are not a Lua script or transaction. Under high concurrency, two requests can both ZADD then both see count < limit. This is a known limitation of pipeline-based rate limiting. Should use a Lua script for true atomicity. |
| 11.2 | 🟡 MEDIUM | 136-143 | **Singleton initialization race condition**: `_get_limiter()` checks `if rate_limiter is None` then creates. Two concurrent requests can both see `None` and create two backends. One will be garbage collected, potentially leaking a Redis connection. |
| 11.3 | 🟡 MEDIUM | 42-43 | **In-memory limiter has unbounded memory growth**: `self._windows: dict[int, SlidingWindow]` grows forever. No eviction of inactive keys. In a long-running process with many API keys, this leaks memory. |
| 11.4 | 🟢 LOW | 149-150 | Rate limits (60 RPM, 10 RPM) are hardcoded constants. Should be configurable per-key or per-tier. |
| 11.5 | 🟢 LOW | 160-161 | `check_rate_limit` calls `check()` then `get_remaining()` — two operations. The `get_remaining` recomputes the window, which is redundant work. |

---

## 12. `services/streaming.py` (114 lines)

### What it does
SSE stream parser that extracts token usage from streamed responses while passing chunks through to the client.

### What works
- ✅ Handles `[DONE]` sentinel
- ✅ Extracts usage from final chunk (OpenAI `stream_options.include_usage`)
- ✅ Fallback token estimation from content chunk count
- ✅ JSON decode error handling (skips bad chunks)

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 12.1 | 🟡 MEDIUM | 83-86 | **Fallback token estimation is very rough**: `completion_tokens = content_chunks * 3`. This assumes ~3 tokens per delta chunk, but chunks can contain 1-100+ tokens. Billing based on this estimate when provider doesn't send usage could be significantly off. |
| 12.2 | 🟡 MEDIUM | 61-65 | **Usage from intermediate chunks overwrites previous**: `self.prompt_tokens = usage.get("prompt_tokens", self.prompt_tokens)`. If a provider sends partial usage in multiple chunks, only the last one's value is kept. Should accumulate or take the max. |
| 12.3 | 🟢 LOW | 97-99 | **`estimated` flag logic is confusing**: `self.completion_tokens == 0 or (self.content_chunks > 0 and self.prompt_tokens == 0)`. This flags as estimated even when completion_tokens > 0 but prompt_tokens == 0, which is a valid state. |
| 12.4 | 🟢 LOW | 103-114 | `add_stream_usage_option` mutates the body dict in place AND returns it. The return value is used but the original is also modified — surprising side effect. |

---

## 13. `services/prediction_ml.py` (383 lines)

### What it does
ML-powered output token prediction. Rolling medians per (model, task_type) bucket, with linear regression adjustment. Continuous learning from actual usage.

### What works
- ✅ Graceful degradation: empirical → heuristic
- ✅ Confidence intervals based on sample size and variance
- ✅ Rolling window (last 1000 samples per bucket)
- ✅ Disk persistence (save/load JSON)
- ✅ Batch training from historical data

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 13.1 | 🟠 HIGH | 94-100 | **Not thread-safe**: `OutputTokenPredictor` is a singleton with mutable `_buckets` and `_feature_weights`. `record_actual()` is called from async request handlers (potentially concurrent), mutating shared state without locks. Under high concurrency, sample counts may be lost or corrupted. |
| 13.2 | 🟡 MEDIUM | 206-232 | **Regression is fake**: `_update_regression` doesn't actually correlate input vs output. It uses `typical_input = 500` (hardcoded!) and computes slope from mean output. This is not regression — it's a ratio heuristic disguised as one. The method name `"empirical_regression"` is misleading. |
| 13.3 | 🟡 MEDIUM | 65-69 | `ModelBucket.add()` keeps last 1000 samples as a list. `self.samples = self.samples[-1000:]` creates a new list on every add — O(n) copy. Should use `collections.deque(maxlen=1000)`. |
| 13.4 | 🟡 MEDIUM | 203-204 | **Regression update happens every 50 samples** based on `len(bucket.samples) % 50 == 0`. But `record_actual` is called from concurrent contexts — multiple threads could trigger update simultaneously, or the modulo check could be missed if samples are added concurrently. |
| 13.5 | 🟡 MEDIUM | 257 | `train_from_db` iterates ALL usage rows in Python — `for model_id, task_type, ... in rows`. With millions of records, this loads everything into memory. Should use SQL GROUP BY aggregation. |
| 13.6 | 🟢 LOW | 77-78 | **Median calculation is incorrect for even-length lists**: `sorted_s[n // 2]` gives the upper-middle element, not the true median (average of two middle elements for even n). Minor for large n. |
| 13.7 | 🟢 LOW | 37 | `MODEL_PATH` defaults to `"data/prediction_model.json"` — relative path. If the working directory changes, the model won't be found. |

---

## 14. `services/pricing.py` (775 lines)

### What it does
Static pricing registry for 18 providers and ~40 models. Seeds database on startup. Also seeds initial quality scores.

### What works
- ✅ Comprehensive model catalog with real pricing
- ✅ Idempotent seeding (safe on every startup)
- ✅ Respects admin price overrides by default (doesn't overwrite on startup)
- ✅ Quality seed data for leaderboard initialization
- ✅ All prices as strings (converted to Decimal) — correct precision handling

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 14.1 | 🟡 MEDIUM | 610-703 | **`seed_database` is not fully idempotent under concurrent startup**. If two workers start simultaneously, both could insert the same providers. The `select(Provider)` check at line 624 is not locked. In practice, Railway runs one worker, but this is fragile. |
| 14.2 | 🟡 MEDIUM | 677-680 | **Price parsing doesn't validate format**: `Decimal(mdata.pop("prompt_price"))`. If the string is malformed, it raises `InvalidOperation` which would crash startup. Should be wrapped in try/except. |
| 14.3 | 🟢 LOW | 28-155 | Pricing data is hardcoded. No mechanism to auto-refresh from provider APIs. The comment says "Sources: OpenRouter /api/v1/models (live, July 2026)" but there's no live fetch — it's a static snapshot that will go stale. |
| 14.4 | 🟢 LOW | 757-758 | Quality seed check uses `limit(1)` — if the first seed was inserted but later deleted, it won't re-seed. Minor edge case. |

---

## 15. `services/tokenizer.py` (223 lines)

### What it does
Token counting with per-model tokenizer routing: tiktoken (OpenAI), Anthropic (approximated via tiktoken), HuggingFace (Llama/Qwen/Mistral), char-based fallback.

### What works
- ✅ Lazy loading of tokenizers with `lru_cache`
- ✅ Graceful fallback chain: tiktoken → HF → char-based
- ✅ Message overhead accounting (4 tokens per message)
- ✅ Task type classification via keyword heuristics

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 15.1 | 🟡 MEDIUM | 73-83 | **Anthropic tokenizer is just tiktoken**: `_get_anthropic_encoder()` returns `_get_tiktoken_encoder()`. The comment acknowledges this: "Claude's tokenizer is similar enough for cost prediction." But Claude uses a different tokenizer (different byte-pair encoding), so cost predictions for Claude models could be off by 10-20%. |
| 15.2 | 🟡 MEDIUM | 86-110 | **HF tokenizer loading requires network access** on first use (`AutoTokenizer.from_pretrained(repo)`). If the model isn't cached locally and there's no network, it falls back to char-based. This happens at request time, adding latency. |
| 15.3 | 🟡 MEDIUM | 104 | `trust_remote_code=True` in `AutoTokenizer.from_pretrained` — **security risk**: executes arbitrary Python from the HF repo. If a tokenizer repo is compromised, it could execute malicious code on the SwiftGate server. |
| 15.4 | 🟢 LOW | 168-169 | **`estimate_output_tokens` returns `max_tokens` if < 50**. This means a request with `max_tokens=10` estimates 10 output tokens, but the model might generate 10 tokens of reasoning + 100 tokens of output. Doesn't account for reasoning models. |
| 15.5 | 🟢 LOW | 207-223 | **`classify_task` is keyword-based and English-only**. Non-English prompts will default to "chat". No i18n support. |
| 15.6 | 🟢 LOW | 143 | Message overhead is 4 tokens per message — the actual OpenAI overhead varies (3-5 tokens depending on role). Minor inaccuracy. |

---

## 16. `auth.py` (65 lines)

### What it does
Admin authentication dependency. Accepts X-Admin-Key (legacy) or JWT with `is_admin` claim.

### What works
- ✅ Dual auth mode (API key + JWT)
- ✅ Production guard (disabled in production without ADMIN_KEY/ADMIN_EMAILS)
- ✅ Dev mode fallback with warning

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 16.1 | 🟠 HIGH | 37 | **Timing attack on admin key**: `x_admin_key == ADMIN_KEY` uses Python string comparison, which is not constant-time. An attacker can determine the admin key character-by-character by measuring response times. Should use `hmac.compare_digest()`. |
| 16.2 | 🟡 MEDIUM | 22 | `ADMIN_KEY = os.environ.get("ADMIN_KEY", "")` is read **at import time** and stored as a module global. If the env var is changed (e.g., key rotation), the change won't take effect until restart. The `settings.ADMIN_KEY` exists but isn't used here. |
| 16.3 | 🟢 LOW | 59-62 | **Dev mode returns "dev-admin"** — any request in development mode gets admin access without any credential. The warning is logged but this is a broad security hole in non-production environments. |

### Code snippet
```python
# Line 37 — timing-vulnerable comparison
if ADMIN_KEY and x_admin_key and x_admin_key == ADMIN_KEY:  # NOT constant-time
    return x_admin_key
```

---

## 17. `user_auth.py` (86 lines)

### What it does
User registration, login, JWT creation/verification, password hashing with bcrypt.

### What works
- ✅ bcrypt for password hashing (industry standard)
- ✅ JWT with expiration
- ✅ Email lowercasing for consistency
- ✅ `is_active` check during authentication

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 17.1 | 🟡 MEDIUM | 18 | **No password complexity validation**: `hash_password` accepts any string. The router (`user_portal.py:33`) has `min_length=8` but no complexity requirements (uppercase, digits, etc.). |
| 17.2 | 🟡 MEDIUM | 38-44 | **`decode_access_token` returns `None` for both expired and invalid tokens**. The caller can't distinguish between "token expired" (should refresh) and "token forged/corrupt" (security event). Should log invalid token attempts. |
| 17.3 | 🟢 LOW | 26-35 | **No JWT `jti` (JWT ID) or refresh token mechanism**. Once a token is issued, it's valid for 7 days (`JWT_EXPIRY_HOURS=168`). If compromised, there's no way to revoke it. |
| 17.4 | 🟢 LOW | 61-62 | `register_user` commits inside the function. If the caller also commits, this is a double commit. More importantly, if the commit fails (e.g., unique constraint race), the exception propagates without rollback. |

---

## 18. `routers/admin.py` (345 lines)

### What it does
CRUD for providers and models. Admin-only endpoints.

### What works
- ✅ All endpoints protected by `require_admin`
- ✅ Duplicate detection on create
- ✅ Referential integrity check (can't delete provider with models)
- ✅ Bulk re-seed endpoint

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 18.1 | 🔴 **HIGH** | 127 | **SSRF vulnerability**: `Provider(**body.model_dump())` accepts arbitrary `base_url` from admin input. A malicious admin (or compromised admin account) could set `base_url` to `http://169.254.169.254/latest/meta-data/` (AWS metadata) or internal services. When the gateway proxies a request, it would fetch from the attacker-controlled URL. |
| 18.2 | 🟡 MEDIUM | 215-220 | **No validation that `api_key_env` is a real environment variable**. An admin could set it to any string, and the gateway would silently send empty API keys to providers. |
| 18.3 | 🟡 MEDIUM | 66-68 | **Price validation missing**: `prompt_price` and `completion_price` are accepted as strings and converted to `Decimal` without validating they're positive numbers. A negative price would cause negative cost calculations. |
| 18.4 | 🟢 LOW | 269-278 | `reseed` endpoint forces price updates (`overwrite_prices=True`). If called accidentally, it overwrites all admin-customized prices. No confirmation mechanism. |

---

## 19. `routers/apikeys.py` (243 lines)

### What it does
Admin API key management: create, list, get, update, delete, reset spend.

### What works
- ✅ Full key shown only once at creation
- ✅ SHA-256 hashing (never stores raw key)
- ✅ Spend tracking with budget percentage
- ✅ Reset spend endpoint for billing cycles

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 19.1 | 🟡 MEDIUM | 82-110 | **Key creation has no rate limit**. An admin (or script with admin access) can create unlimited keys. Should have a max-keys-per-admin limit. |
| 19.2 | 🟡 MEDIUM | 207-208 | **`update_key` uses `setattr` with user-provided field names** from `body.model_dump(exclude_unset=True)`. While Pydantic validates the schema, if the model changes and new fields are added to `KeyUpdate` but not to `ApiKey`, this will raise an obscure `AttributeError`. |
| 19.3 | 🟢 LOW | 31-33 | API key format `sg-` + 48 hex chars = 51 chars total. This is reasonably secure (192 bits of entropy from `secrets.token_hex(24)`). ✅ |
| 19.4 | 🟢 LOW | 215-227 | `delete_key` permanently deletes the key. Usage records with `api_key_id` FK will have dangling references (FK is nullable, so no constraint violation, but analytics will show orphaned records). |

---

## 20. `routers/agents.py` (311 lines)

### What it does
Agent lifecycle management: create, list, update, kill/pause/resume, reset budget, execution trace events.

### What works
- ✅ Kill-switch immediately blocks requests (enforced in gateway.py)
- ✅ Budget tracking with automatic status change to "budget_exceeded"
- ✅ Execution trace with parent_agent_id and trace_id for multi-agent workflows
- ✅ Event recording updates agent spend

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 20.1 | 🟡 MEDIUM | 264 | **Agent spend update has race condition**: `agent.spend_cents += body.cost_cents` — same read-modify-write pattern as gateway. Concurrent event recording can lose updates. |
| 20.2 | 🟡 MEDIUM | 236-272 | **`record_event` endpoint is admin-only** but records spend. In a multi-agent system, agents need to call this endpoint autonomously. The auth model doesn't support agent-level authentication. |
| 20.3 | 🟢 LOW | 175-189 | `resume_agent` can resume a "killed" agent by setting status to "active". The kill-switch is meant to be permanent — this undermines it. Should require explicit confirmation or separate "unkill" endpoint. |
| 20.4 | 🟢 LOW | 209-233 | `get_agent_trace` applies `trace_id` filter AFTER `limit()`, so the limit applies before filtering. With many events, the trace_id filter may return fewer results than expected. |

---

## 21. `routers/analytics.py` (184 lines)

### What it does
Usage analytics: aggregate stats, daily breakdown, platform stats, ML model stats/training.

### What works
- ✅ Time-windowed aggregation
- ✅ Per-model breakdown
- ✅ Prediction accuracy tracking
- ✅ ML training trigger endpoint

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 21.1 | 🟡 MEDIUM | 35 | **`get_usage` loads up to 1000 records into memory** for aggregation. Should use SQL `GROUP BY` and aggregate functions instead of Python loops. |
| 21.2 | 🟡 MEDIUM | 63-68 | **Average latency computed in Python** with a nested loop: `[r for r in records if r.model_served == mid]`. This is O(n²) — for 1000 records and 40 models, that's 40,000 iterations. |
| 21.3 | 🟢 LOW | 182-183 | `train_ml_model` saves the model in a thread, but doesn't return whether the save succeeded. If save fails, the trained model is lost on restart. |
| 21.4 | 🟢 LOW | 165-171 | `get_ml_stats` exposes internal bucket details. While admin-only, this leaks model architecture details that could help competitors. |

---

## 22. `routers/billing.py` (247 lines)

### What it does
Stripe Checkout integration for credit purchases. Webhook handler adds credits on successful payment.

### What works
- ✅ Lazy Stripe import (works without stripe installed)
- ✅ Credit packages with fixed pricing
- ✅ Custom amount checkout
- ✅ Metadata-based credit attribution

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 22.1 | 🔴 **CRITICAL** | 213-219 | **Webhook signature verification is OPTIONAL**: `if webhook_secret and stripe_signature: verify; else: trust raw payload`. If `STRIPE_WEBHOOK_SECRET` is not set (default is empty string), ANYONE can POST to `/billing/webhook` and add arbitrary credits to any account. This is a direct path to free credits. |
| 22.2 | 🟠 HIGH | 106 | **Open redirect via `success_url`**: `base_url = req.success_url.split("/settings")[0]`. A malicious `success_url` like `https://evil.com/settings?x` would extract `https://evil.com` as the base URL, and Stripe would redirect there after payment. |
| 22.3 | 🟡 MEDIUM | 36-51 | **`_get_stripe` caches the stripe module globally**. If `STRIPE_SECRET_KEY` is rotated, the old key remains cached until restart. |
| 22.4 | 🟡 MEDIUM | 232-243 | **Webhook has no idempotency**. If Stripe retries the webhook (which it does), credits could be added multiple times. Should check for duplicate event IDs. |
| 22.5 | 🟢 LOW | 57-61 | Credit packages give fewer credits than dollars paid (e.g., $5 → 500 cents credits = $0.05 in gateway credits). Wait — credits_cents=500, and the gateway charges in microcents (10000 per USD). So 500 cents = $0.05? This seems like a **unit mismatch** — the packages may be 100x underpriced. |

### Code snippet
```python
# Lines 213-219 — CRITICAL: optional signature verification
if webhook_secret and stripe_signature:
    event = stripe.Webhook.construct_event(
        payload, stripe_signature, webhook_secret
    )
else:
    import json
    event = json.loads(payload)  # NO VERIFICATION — anyone can forge this
```

---

## 23. `routers/cost.py` (195 lines)

### What it does
Cost intelligence endpoints: predict, compare, list models, Pareto frontier.

### What works
- ✅ Clean schema definitions
- ✅ Pareto frontier calculation
- ✅ Model detail endpoint with pricing

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 23.1 | 🟡 MEDIUM | 47-62 | **`/v1/predict` has NO authentication or rate limiting**. Anyone can call it unlimited times, which runs tokenization (CPU-intensive) and DB queries. This is a DoS vector. |
| 23.2 | 🟡 MEDIUM | 65-82 | **`/v1/compare` also unauthenticated** — runs cost comparison across ALL models, which is expensive. |
| 23.3 | 🟢 LOW | 48 | The predict endpoint returns `{"error": "Unknown model"}` as a dict with 200 status instead of raising HTTPException(404). Inconsistent error handling. |
| 23.4 | 🟢 LOW | 123-156 | Pareto endpoint uses hardcoded sample prompts — doesn't reflect actual user prompts. |

---

## 24. `routers/quality.py` (245 lines)

### What it does
Quality feedback, quality-per-dollar routing, leaderboard, routing rule CRUD.

### What works
- ✅ Explicit feedback (thumbs up/down) recording
- ✅ Quality-per-dollar routing recommendation
- ✅ Leaderboard with sample count filtering
- ✅ Full routing rule CRUD

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 24.1 | 🟠 HIGH | 57-79 | **`/v1/quality/feedback` has NO authentication**. Anyone can submit unlimited feedback, poisoning the quality scores. A competitor could downvote rival models. Should require API key or JWT. |
| 24.2 | 🟡 MEDIUM | 82-100 | **`/v1/quality/route` is unauthenticated** — expensive computation (calls ML predictor + quality index for every model). DoS vector. |
| 24.3 | 🟢 LOW | 141-156 | Route ordering comment at line 139 is correct — FastAPI matches greedily, so `{model_id}` must come last. Good documentation. |
| 24.4 | 🟢 LOW | 186-210 | `list_routing_rules` returns all fields as a dict. Inconsistent with other endpoints that use Pydantic response models. |

---

## 25. `routers/cache_pii.py` (145 lines)

### What it does
Cache management (stats, invalidate, cleanup) and PII detection/redaction preview endpoints.

### What works
- ✅ Admin-only cache management
- ✅ PII detection doesn't return matched text (prevents log exposure)
- ✅ Redact endpoint returns audit log

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 25.1 | 🟡 MEDIUM | 108-127 | **`/v1/pii/detect` is unauthenticated**. Anyone can probe the PII detection patterns. While not directly harmful, it reveals the system's PII detection capabilities. |
| 25.2 | 🟡 MEDIUM | 130-145 | **`/v1/pii/redact` is unauthenticated**. Allows unlimited PII redaction requests. Not a major risk (redaction is cheap), but inconsistent with admin-only cache endpoints. |
| 25.3 | 🟢 LOW | 17 | `import json` at module level but never used in this file. Dead import. |

---

## 26. `routers/user_portal.py` (408 lines)

### What it does
User registration, login, JWT-based key management, usage stats, settings.

### What works
- ✅ Email/password validation (min 8 chars)
- ✅ JWT-based auth for all user endpoints
- ✅ User-scoped key management (users can only see/manage their own keys)
- ✅ Proper ownership checks on key operations
- ✅ User-scoped usage aggregation

### Issues
| # | Severity | Lines | Issue |
|---|----------|-------|-------|
| 26.1 | 🟠 HIGH | 98-120 | **No rate limiting on `/auth/register` or `/auth/login`**. Allows brute-force password attacks and registration spam. Should have per-IP rate limiting. |
| 26.2 | 🟡 MEDIUM | 33 | **Password only requires `min_length=8`** — no complexity requirements (uppercase, digit, special char). Weak passwords like "aaaaaaaa" are accepted. |
| 26.3 | 🟡 MEDIUM | 347 | **`my_recent_usage` has unbounded `limit` parameter** (default 50, but `min(limit, 200)` allows up to 200). Not a major issue, but should validate with Pydantic `Query`. |
| 26.4 | 🟢 LOW | 84 | `int(payload["sub"])` — if the JWT payload is malformed (no "sub" key), this raises `KeyError` → 500 error. Should use `.get()` with validation. |
| 26.5 | 🟢 LOW | 168 | User-generated API keys use `secrets.token_urlsafe(32)` — 43 chars, different format from admin keys (`secrets.token_hex(24)` — 48 hex chars). Both are secure but inconsistent. |

---

## 27. `__init__.py` files (2 files, 1 line each)

Trivial docstring-only files. No issues.

---

## Cross-Cutting Concerns

### A. Missing Features / Stubs

| Feature | Status | Notes |
|---------|--------|-------|
| **pgvector semantic cache** | Not implemented | Comment at `semantic_cache.py:209` says "In production with pgvector, this would be a vector search" but uses Python scan instead |
| **LLM-as-judge automated quality scoring** | Not implemented | Referenced in `models.py:289` ("automated: LLM-as-judge evaluator scores (sampled 1% of requests)") but no code implements it |
| **Migration system** | Not implemented | Uses `create_all` only; no Alembic |
| **API key scoped rate limits** | Not implemented | All keys share 60 RPM; no per-tier limits |
| **Token refresh / revocation** | Not implemented | JWT valid for 7 days, no revocation possible |
| **Audit logging** | Not implemented | No record of admin actions (provider/model changes, key creation/deletion) |
| **Prometheus / metrics export** | Not implemented | No `/metrics` endpoint |
| **Request tracing / OpenTelemetry** | Not implemented | No distributed tracing |
| **Multi-tenancy** | Partial | Users have their own keys, but providers/models are global |

### B. Security Summary

| Issue | Severity | Location |
|-------|----------|----------|
| Optional Stripe webhook verification | 🔴 CRITICAL | billing.py:213 |
| Budget enforcement race condition | 🔴 CRITICAL | gateway.py:393-429 |
| SSRF via admin provider base_url | 🟠 HIGH | admin.py:127 |
| Timing attack on admin key | 🟠 HIGH | auth.py:37 |
| Unauthenticated quality feedback | 🟠 HIGH | quality.py:57 |
| No rate limit on auth endpoints | 🟠 HIGH | user_portal.py:98,123 |
| Non-atomic Redis rate limiting | 🟠 HIGH | rate_limiter.py:78-97 |
| ML predictor not thread-safe | 🟠 HIGH | prediction_ml.py |
| `trust_remote_code=True` in HF tokenizer | 🟡 MEDIUM | tokenizer.py:104 |
| Error message leakage | 🟡 MEDIUM | main.py:108, gateway.py:837 |
| No constant-time comparison anywhere | 🟡 MEDIUM | auth.py:37 |

### C. Error Handling Summary

Most error handling is **best-effort with silent fallbacks**. This is generally good for a gateway (don't fail the request because analytics failed), but several places swallow exceptions too broadly:

- `gateway.py:771` — `except Exception: pass` for quality signals
- `gateway.py:275` — `except Exception: task_type = "chat"` (correct fallback)
- `auth.py:49` — `except Exception: pass` for JWT decode (should log invalid tokens)
- `billing.py:132` — catches all exceptions from Stripe (good, but logs at error level)

### D. Performance Concerns

| Issue | Impact |
|-------|--------|
| Analytics loads 1000 records into Python | Slow with scale |
| Quality index loads 500 records into Python | Slow with scale |
| Semantic cache scans 50 entries in Python | O(n) per request |
| ML training loads all records into Python | Won't scale past ~100K records |
| Pareto marking is O(n²) | Fine for 40 models, bad for 400 |
| Rate limiter in-memory dict grows unbounded | Memory leak |

---

## Prioritized Recommendations

### P0 — Fix before any production deployment
1. **Make Stripe webhook verification mandatory** (`billing.py:213`) — reject if no secret
2. **Fix budget race condition** with `SELECT FOR UPDATE` or atomic updates (`gateway.py`)
3. **Add rate limiting to `/auth/register` and `/auth/login`** (`user_portal.py`)
4. **Add authentication to `/v1/quality/feedback`** (`quality.py`)
5. **Use `hmac.compare_digest` for admin key** (`auth.py:37`)

### P1 — Fix before scale
6. **Add `httpx.ConnectError` handling in failover loop** (`gateway.py:600`)
7. **Make ML predictor thread-safe** with `asyncio.Lock` (`prediction_ml.py`)
8. **Move analytics aggregation to SQL** (`analytics.py`, `quality_router.py`)
9. **Add webhook idempotency** (check event ID) (`billing.py`)
10. **Fix `int()` truncation in cost calculation** — use `round()` (`gateway.py:257`)

### P2 — Technical debt
11. **Add Alembic migrations**
12. **Add pgvector for semantic cache** (or accept Python scan limitation)
13. **Implement LLM-as-judge quality scoring**
14. **Add Prometheus metrics endpoint**
15. **Add audit logging for admin actions**

---

*Report generated by Hermes Agent. All findings based on actual source code review.*