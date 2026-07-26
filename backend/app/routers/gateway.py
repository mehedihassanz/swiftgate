"""Gateway proxy router — OpenAI-compatible API with full production features.

POST /v1/chat/completions — the main gateway endpoint
  - Requires valid API key (rejects anonymous in production)
  - Rate limiting per key (60 RPM default)
  - Pre-flight cost prediction
  - Budget enforcement
  - Provider failover + automatic retries
  - Streaming with usage tracking
  - Real-time usage recording
  - Post-flight prediction accuracy measurement

This is a drop-in replacement for OpenAI's API.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import ApiKey, Model, Provider, UsageRecord
from app.services.cost_engine import predict_cost
from app.services.provider_router import route_by_strategy, should_retry
from app.services.rate_limiter import check_rate_limit
from app.services.streaming import StreamingUsageTracker, add_stream_usage_option
from app.services.tokenizer import classify_task, get_token_count

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["gateway"])


# ─── Schemas ───────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: Any = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stream: bool = False
    tools: list[dict] | None = None
    tool_choice: Any = None
    response_format: dict | None = None
    # SwiftGate extensions
    agent_id: str | None = None
    cost_prediction: bool = True


# ─── Authentication ────────────────────────────────────────────────────

async def _authenticate(
    authorization: str | None,
    db: AsyncSession,
) -> ApiKey | None:
    """Authenticate via Bearer token. Returns None if no key provided."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    raw_key = authorization[7:]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()

    if api_key and not api_key.is_active:
        raise HTTPException(403, "API key has been revoked")

    return api_key


def _require_auth(api_key: ApiKey | None) -> ApiKey:
    """Enforce authentication.

    Gateway requires an API key in all environments EXCEPT development/testing.
    Set ENV=development to allow anonymous access (rate-limited to 10 RPM).
    """
    allow_anon = settings.ENV in ("development", "testing")
    if not allow_anon and not api_key:
        raise HTTPException(
            401,
            "API key required. Create one at POST /v1/keys "
            "and pass it as: Authorization: Bearer sg-..."
        )
    return api_key


# ─── Provider request building ─────────────────────────────────────────

def _get_api_key_for_provider(provider: Provider) -> str:
    import os
    return os.environ.get(provider.api_key_env, "")


def _build_upstream_request(
    request_body: dict,
    model: Model,
    stream: bool = False,
) -> tuple[str, dict, dict]:
    """Build the upstream API call.

    Returns (url, headers, body).
    """
    provider = model.provider

    if provider.name == "anthropic":
        url = f"{provider.base_url}/messages"
        headers = {
            "x-api-key": _get_api_key_for_provider(provider),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = _convert_to_anthropic(request_body, model)
    elif provider.name == "google":
        api_key = _get_api_key_for_provider(provider)
        url = f"{provider.base_url}/models/{model.model_id}:generateContent"
        headers = {
            "content-type": "application/json",
            "x-goog-api-key": api_key,  # Header-based auth — keeps key out of URLs/logs
        }
        body = _convert_to_gemini(request_body, model)
    else:
        # OpenAI-compatible (most providers)
        url = f"{provider.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {_get_api_key_for_provider(provider)}",
            "content-type": "application/json",
        }
        body = dict(request_body)
        # Replace model_id with the provider's native ID if different
        body["model"] = model.model_id

    # Ensure stream_options for usage tracking
    if stream:
        body = add_stream_usage_option(body)

    return url, headers, body


def _convert_to_anthropic(request: dict, model: Model) -> dict:
    """Convert OpenAI-format request to Anthropic format."""
    messages = request.get("messages", [])
    system_msg = ""
    converted_messages = []

    for msg in messages:
        if msg["role"] == "system":
            system_msg += msg.get("content", "") + "\n"
        else:
            converted_messages.append({
                "role": msg["role"],
                "content": msg.get("content", ""),
            })

    body: dict[str, Any] = {
        "model": model.model_id,
        "messages": converted_messages,
        "max_tokens": request.get("max_tokens") or model.max_output,
    }

    if system_msg:
        body["system"] = system_msg.strip()

    if request.get("temperature") is not None:
        body["temperature"] = request["temperature"]

    if request.get("stream"):
        body["stream"] = True

    return body


def _convert_to_gemini(request: dict, model: Model) -> dict:
    """Convert OpenAI-format request to Google Gemini format."""
    messages = request.get("messages", [])
    system_msg = ""
    contents = []

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system_msg += msg.get("content", "") + "\n"
        else:
            gemini_role = "user" if role == "user" else "model"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": msg.get("content", "")}],
            })

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": request.get("max_tokens") or model.max_output,
        },
    }

    if system_msg:
        body["systemInstruction"] = {"parts": [{"text": system_msg.strip()}]}

    if request.get("temperature") is not None:
        body["generationConfig"]["temperature"] = request["temperature"]

    return body


# ─── Usage recording ───────────────────────────────────────────────────

async def _record_usage(
    db: AsyncSession,
    api_key: ApiKey | None,
    model: Model,
    request_body: dict,
    response_data: dict | None,
    prediction: dict | None,
    latency_ms: int,
    status: str = "success",
    agent_id: str | None = None,
    streaming_usage: dict | None = None,
) -> None:
    """Record the actual token usage and cost."""
    # Extract token counts
    if streaming_usage:
        prompt_tokens = streaming_usage.get("prompt_tokens", 0)
        completion_tokens = streaming_usage.get("completion_tokens", 0)
    elif response_data and "usage" in response_data:
        usage = response_data["usage"]
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
    elif prediction:
        prompt_tokens = prediction.get("input_tokens", 0)
        completion_tokens = prediction.get("estimated_output_tokens", 0)
    else:
        prompt_tokens = 0
        completion_tokens = 0

    # Compute actual cost (cents)
    margin = 1 + settings.TOKEN_MARGIN
    prompt_cost = int(float(model.prompt_price) * prompt_tokens * margin * 10000)
    completion_cost = int(float(model.completion_price) * completion_tokens * margin * 10000)
    total_cost = prompt_cost + completion_cost

    # Prediction accuracy
    pred_error = None
    if prediction and "costs" in prediction:
        pred = prediction["costs"]["estimated_total_cents"]
        if total_cost > 0:
            pred_error = abs(pred - total_cost) / total_cost * 100

    # Robustly classify task type — don't let a bad message lose the entire record
    try:
        task_type = classify_task(
            [m if isinstance(m, dict) else m.model_dump() for m in
             [Message(**m) if isinstance(m, dict) else m
              for m in request_body.get("messages", [])]]
        )
    except Exception:
        task_type = "chat"  # safe fallback

    record = UsageRecord(
        api_key_id=api_key.id if api_key else None,
        agent_id=agent_id,
        model_requested=request_body.get("model"),
        model_served=model.model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_cost_cents=prompt_cost,
        completion_cost_cents=completion_cost,
        total_cost_cents=total_cost,
        latency_ms=latency_ms,
        provider=model.provider.name if model.provider else None,
        was_predicted=bool(prediction),
        prediction_error_pct=pred_error,
        status=status,
        task_type=task_type,
    )
    db.add(record)

    if api_key:
        api_key.total_spend_cents += total_cost
        api_key.total_requests += 1
        api_key.last_used = datetime.now(timezone.utc)

        # Deduct credits from the user's balance
        if api_key.user_id:
            from app.models import User as UserModel
            user_result = await db.execute(
                select(UserModel).where(UserModel.id == api_key.user_id)
            )
            user_obj = user_result.scalar_one_or_none()
            if user_obj:
                user_obj.credits_cents = max(0, user_obj.credits_cents - total_cost)

    # Update agent spend if agent_id is set
    if agent_id:
        from app.models import Agent as AgentModel
        agent_result = await db.execute(
            select(AgentModel).where(AgentModel.agent_id == agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent:
            agent.spend_cents += total_cost
            agent.request_count += 1
            agent.last_active = datetime.now(timezone.utc)
            # Check if budget now exceeded
            if agent.budget_cents and agent.spend_cents >= agent.budget_cents:
                agent.status = "budget_exceeded"
                await _create_budget_alert(
                    db, api_key.id if api_key else None, agent_id,
                    100, agent.spend_cents, agent.budget_cents,
                    f"Agent '{agent_id}' reached 100% of budget"
                )

    # Check budget thresholds for API key (50%, 80%, 100%)
    if api_key and api_key.monthly_budget_cents:
        pct = (api_key.total_spend_cents / api_key.monthly_budget_cents) * 100
        for threshold in (50, 80, 100):
            if pct >= threshold:
                await _create_budget_alert(
                    db, api_key.id, agent_id,
                    threshold, api_key.total_spend_cents, api_key.monthly_budget_cents,
                    f"API key '{api_key.name}' reached {threshold}% of monthly budget"
                )
                break  # only fire highest threshold

    # Feed the ML predictor (the data flywheel)
    if completion_tokens > 0:
        from app.services.prediction_ml import predictor
        predictor.record_actual(
            model_id=model.model_id,
            task_type=task_type,
            actual_output_tokens=completion_tokens,
            input_tokens=prompt_tokens,
        )

    await db.flush()


async def _create_budget_alert(
    db: AsyncSession,
    api_key_id: int | None,
    agent_id: str | None,
    threshold_pct: int,
    spend_cents: int,
    budget_cents: int,
    message: str,
) -> None:
    """Create a budget alert if one doesn't already exist for this threshold."""
    from app.models import BudgetAlert
    if not api_key_id and not agent_id:
        return  # nothing to alert on

    # Build dedup query — check if already alerted for this threshold
    conditions = [BudgetAlert.threshold_pct == threshold_pct, BudgetAlert.acknowledged == False]  # noqa: E712
    if api_key_id:
        conditions.append(BudgetAlert.api_key_id == api_key_id)
    if agent_id:
        conditions.append(BudgetAlert.agent_id == agent_id)

    result = await db.execute(
        select(BudgetAlert).where(*conditions).limit(1)
    )
    if result.scalar_one_or_none():
        return  # already alerted
    alert = BudgetAlert(
        api_key_id=api_key_id,
        agent_id=agent_id,
        threshold_pct=threshold_pct,
        spend_cents=spend_cents,
        budget_cents=budget_cents,
        message=message,
    )
    db.add(alert)
    logger.info(f"Budget alert: {message}")


# ─── Budget enforcement ────────────────────────────────────────────────

def _check_budget(api_key: ApiKey | None, predicted_cost_cents: int) -> None:
    if not api_key or not api_key.is_active:
        return

    # Check user credits (if linked to a user)
    if api_key.user and api_key.user.credits_cents <= 0:
        raise HTTPException(
            402,
            f"No credits remaining. Please add credits to your account."
        )
    if api_key.user and api_key.user.credits_cents < predicted_cost_cents:
        raise HTTPException(
            402,
            f"Insufficient credits. Remaining: ${api_key.user.credits_cents / 100:.4f}, "
            f"Predicted cost: ${predicted_cost_cents / 10000:.4f}. "
            f"Please add credits to your account."
        )

    if api_key.per_request_limit_cents:
        if predicted_cost_cents > api_key.per_request_limit_cents:
            raise HTTPException(
                402,
                f"Predicted cost (${predicted_cost_cents / 10000:.4f}) exceeds "
                f"per-request limit (${api_key.per_request_limit_cents / 10000:.4f})"
            )

    if api_key.monthly_budget_cents:
        if api_key.total_spend_cents + predicted_cost_cents > api_key.monthly_budget_cents:
            remaining = api_key.monthly_budget_cents - api_key.total_spend_cents
            raise HTTPException(
                402,
                f"Monthly budget exceeded. Spent: ${api_key.total_spend_cents / 10000:.2f}, "
                f"Budget: ${api_key.monthly_budget_cents / 10000:.2f}. "
                f"Remaining: ${remaining / 10000:.2f}. "
                f"Predicted cost: ${predicted_cost_cents / 10000:.4f}"
            )


async def _check_agent_budget(
    db: AsyncSession,
    agent_id: str | None,
    predicted_cost_cents: int,
) -> None:
    """Check agent budget and kill-switch status.

    If the agent exists and has a budget, verify the request won't exceed it.
    If the agent is killed or paused, reject the request.
    """
    if not agent_id:
        return

    from app.models import Agent as AgentModel
    result = await db.execute(select(AgentModel).where(AgentModel.agent_id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        return  # Agent not registered — allow (lazy registration)

    if agent.status == "killed":
        raise HTTPException(
            403,
            f"Agent '{agent_id}' has been killed. Reason: {agent.killed_reason or 'manual kill-switch'}. "
            f"No further requests allowed until explicitly resumed."
        )

    if agent.status == "paused":
        raise HTTPException(
            403,
            f"Agent '{agent_id}' is paused. Resume it to continue."
        )

    if agent.status == "budget_exceeded":
        raise HTTPException(
            402,
            f"Agent '{agent_id}' has exceeded its budget. "
            f"Spent: ${agent.spend_cents / 10000:.2f}, "
            f"Budget: ${agent.budget_cents / 10000 if agent.budget_cents else 0:.2f}. "
            f"Reset the budget to continue."
        )

    if agent.budget_cents and agent.spend_cents + predicted_cost_cents > agent.budget_cents:
        remaining = agent.budget_cents - agent.spend_cents
        raise HTTPException(
            402,
            f"Agent '{agent_id}' budget exceeded. "
            f"Spent: ${agent.spend_cents / 10000:.4f}, "
            f"Budget: ${agent.budget_cents / 10000:.2f}, "
            f"Remaining: ${remaining / 10000:.4f}, "
            f"Predicted: ${predicted_cost_cents / 10000:.4f}"
        )


# ─── Main gateway endpoint ─────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
):
    """OpenAI-compatible chat completions with full production features.

    Drop-in replacement for api.openai.com/v1/chat/completions.

    Features:
      - Auth required (in production mode)
      - Rate limiting (60 RPM authenticated, 10 anonymous)
      - Pre-flight cost prediction
      - Budget enforcement
      - Provider failover (tries alternate providers on error)
      - Automatic retries on 429/5xx
      - Streaming usage tracking
      - Post-flight accuracy measurement
    """
    body = await request.json()

    # ── Input validation (M3/M4) ──
    messages = body.get("messages", [])
    if not messages or not isinstance(messages, list):
        raise HTTPException(400, "messages array is required")
    if len(messages) > 100:
        raise HTTPException(400, f"Too many messages: {len(messages)} (max 100)")
    # Total prompt size limit (512KB — prevents DoS)
    prompt_size = len(str(body).encode())
    if prompt_size > 512_000:
        raise HTTPException(413, f"Request body too large: {prompt_size} bytes (max 512KB)")

    try:
        req = ChatCompletionRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request: {e}")

    # ── Auth ──
    api_key = await _authenticate(authorization, db)
    _require_auth(api_key)

    # ── Rate limiting ──
    allowed, rate_info = await check_rate_limit(api_key.id if api_key else None)
    if not allowed:
        raise HTTPException(
            429,
            f"Rate limit exceeded. Limit: {rate_info['limit']} req/min. "
            f"Retry in {60 - rate_info['remaining']}s."
        )

    # ── PII Redaction (before anything else touches the messages) ──
    pii_token_map = None
    if settings.PII_REDACTION_ENABLED:
        from app.services.pii_redaction import redact_messages
        messages_dicts = [m.model_dump() for m in req.messages]
        redacted_msgs, pii_token_map = redact_messages(messages_dicts)
        # Replace messages in both req and body with redacted versions
        req.messages = [Message(**m) for m in redacted_msgs]
        body["messages"] = redacted_msgs
        if pii_token_map and len(pii_token_map) > 0:
            logger.info(f"PII redacted {len(pii_token_map)} entities for this request")

    # ── Cache check (after PII redaction so cached hash is consistent) ──
    cache_bypass = body.get("cache", True)  # default: use cache
    if settings.CACHE_ENABLED and cache_bypass:
        from app.services.semantic_cache import check_cache
        messages_for_cache = [m.model_dump() for m in req.messages]
        cached = await check_cache(
            db=db,
            messages=messages_for_cache,
            model_id=req.model,
            api_key_id=api_key.id if api_key else None,
            semantic=settings.CACHE_SEMANTIC_MATCH,
        )
        if cached:
            # Rehydrate PII in cached response
            if pii_token_map and settings.PII_REHYDRATE_RESPONSE:
                from app.services.pii_redaction import rehydrate_response
                cached = rehydrate_response(cached, pii_token_map)
            await db.commit()
            cached.setdefault("swiftgate", {})["cache_hit"] = True
            return cached

    # ── Build failover chain ──
    strategy = body.get("optimize_for", settings.DEFAULT_ROUTING)
    failover_chain = await route_by_strategy(db, req.model, strategy)

    if not failover_chain:
        raise HTTPException(404, f"No available provider for model '{req.model}'. Check API key configuration.")

    primary_model = failover_chain[0][0]

    # ── Predict cost ──
    prediction = None
    if req.cost_prediction:
        prediction = await predict_cost(
            db=db,
            model_id=primary_model.model_id,
            messages=[m.model_dump() for m in req.messages],
            max_tokens=req.max_tokens,
            tools=req.tools,
        )

    # ── Budget check ──
    if prediction and "costs" in prediction:
        _check_budget(api_key, prediction["costs"]["worst_case_cents"])
        await _check_agent_budget(db, req.agent_id, prediction["costs"]["worst_case_cents"])

    # ── Try providers with failover ──
    last_error = None
    shared_client = getattr(request.app.state, "http_client", None)
    for attempt, (model, provider) in enumerate(failover_chain):
        try:
            return await _forward_request(
                db, api_key, model, provider, body, req, prediction,
                attempt, len(failover_chain),
                pii_token_map=pii_token_map,
                cache_enabled=settings.CACHE_ENABLED and cache_bypass,
                http_client=shared_client,
            )
        except httpx.TimeoutException:
            logger.warning(f"Provider {provider.name} timed out (attempt {attempt + 1})")
            last_error = HTTPException(504, f"Provider {provider.name} timed out")
            continue
        except HTTPException as e:
            if should_retry(e.status_code, attempt):
                logger.warning(
                    f"Provider {provider.name} returned {e.status_code}, "
                    f"retrying with next provider (attempt {attempt + 1}/{len(failover_chain)})"
                )
                last_error = e
                continue
            raise

    if last_error:
        raise last_error
    raise HTTPException(503, "All providers failed")


async def _forward_request(
    db: AsyncSession,
    api_key: ApiKey | None,
    model: Model,
    provider: Provider,
    body: dict,
    req: ChatCompletionRequest,
    prediction: dict | None,
    attempt: int,
    total_attempts: int,
    pii_token_map=None,
    cache_enabled: bool = False,
    http_client: httpx.AsyncClient | None = None,
):
    """Forward request to a single provider. Handles both streaming and non-streaming."""
    upstream_url, upstream_headers, upstream_body = _build_upstream_request(
        body, model, stream=req.stream,
    )

    start_time = time.time()

    # Use shared HTTP client for connection reuse (or fallback for tests)
    owns_client = False
    if http_client:
        client = http_client
    else:
        try:
            from app.database import async_session
            # Fallback: create a standalone client (tests, etc.)
            client = httpx.AsyncClient(timeout=120.0)
            owns_client = True
        except Exception:
            client = httpx.AsyncClient(timeout=120.0)
            owns_client = True

    try:
        if req.stream:
            return await _handle_streaming(
                client, db, api_key, model, provider,
                upstream_url, upstream_headers, upstream_body,
                prediction, req.agent_id, start_time,
                pii_token_map=pii_token_map,
                cache_enabled=cache_enabled,
            )
        else:
            return await _handle_non_streaming(
                client, db, api_key, model, provider,
                upstream_url, upstream_headers, upstream_body,
                prediction, req.agent_id, start_time,
                pii_token_map=pii_token_map,
                cache_enabled=cache_enabled,
            )
    finally:
        if owns_client:
            await client.aclose()


async def _handle_non_streaming(
    client: httpx.AsyncClient,
    db: AsyncSession,
    api_key: ApiKey | None,
    model: Model,
    provider: Provider,
    url: str,
    headers: dict,
    body: dict,
    prediction: dict | None,
    agent_id: str | None,
    start_time: float,
    pii_token_map=None,
    cache_enabled: bool = False,
):
    """Handle a non-streaming request."""
    response = await client.post(url, headers=headers, json=body)
    latency_ms = int((time.time() - start_time) * 1000)

    if response.status_code >= 400:
        # Record the error for analytics
        await _record_usage(
            db, api_key, model, body, None, prediction,
            latency_ms, status="error", agent_id=agent_id,
        )
        await db.commit()
        # Sanitize error — don't echo upstream response body (may contain keys/data)
        raise HTTPException(
            response.status_code,
            f"Upstream provider {provider.name} returned error {response.status_code}. "
            f"Check provider API key and request format."
        )

    response_data = response.json()

    # ── Store in semantic cache (before PII rehydration) ──
    if cache_enabled and response_data.get("choices"):
        from app.services.semantic_cache import store_cache
        # Determine task type for TTL
        task_type = prediction.get("task_type") if prediction else None
        # Calculate saved cost
        usage = response_data.get("usage", {})
        saved_tokens = usage.get("total_tokens", 0)
        saved_cost = (
            int(float(model.prompt_price) * usage.get("prompt_tokens", 0) * 10000) +
            int(float(model.completion_price) * usage.get("completion_tokens", 0) * 10000)
        )
        try:
            await store_cache(
                db=db,
                messages=body.get("messages", []),
                response=response_data,
                model_id=model.model_id,
                task_type=task_type,
                api_key_id=api_key.id if api_key else None,
                saved_cost_cents=saved_cost,
                saved_tokens=saved_tokens,
                is_shared=settings.CACHE_SHARED_DEFAULT,
            )
        except Exception as e:
            logger.warning(f"Failed to store cache entry: {e}")

    # ── PII rehydration (restore original PII in response) ──
    if pii_token_map and settings.PII_REHYDRATE_RESPONSE:
        from app.services.pii_redaction import rehydrate_response
        response_data = rehydrate_response(response_data, pii_token_map)

    # Record actual usage
    await _record_usage(
        db, api_key, model, body, response_data, prediction,
        latency_ms, agent_id=agent_id,
    )

    # Implicit quality signal: multi-turn conversation = positive signal
    # (user continued the conversation, implying satisfaction)
    if len(body.get("messages", [])) > 1:
        try:
            from app.services.quality_router import detect_implicit_signal
            await detect_implicit_signal(
                db=db,
                api_key_id=api_key.id if api_key else None,
                model_served=model.model_id,
                task_type=prediction.get("task_type", "chat") if prediction else "chat",
                usage_record_id=None,
                conversation_continued=True,
            )
        except Exception:
            pass  # quality signals are best-effort

    await db.commit()

    # Embed prediction info in response — use same margin as recorded cost
    if prediction:
        margin = 1 + settings.TOKEN_MARGIN
        actual_cost = (
            int(float(model.prompt_price) * response_data.get("usage", {}).get("prompt_tokens", 0) * margin * 10000) +
            int(float(model.completion_price) * response_data.get("usage", {}).get("completion_tokens", 0) * margin * 10000)
        )
        response_data["swiftgate"] = {
            "predicted_cost_cents": prediction["costs"]["estimated_total_cents"],
            "actual_cost_cents": actual_cost,
            "model_served": model.model_id,
            "provider": provider.name,
            "input_tokens": prediction["input_tokens"],
            "task_type": prediction["task_type"],
            "routing_suggestion": prediction.get("routing_suggestion"),
            "prediction_confidence": prediction["confidence"],
        }

    return response_data


async def _handle_streaming(
    client: httpx.AsyncClient,
    db: AsyncSession,
    api_key: ApiKey | None,
    model: Model,
    provider: Provider,
    url: str,
    headers: dict,
    body: dict,
    prediction: dict | None,
    agent_id: str | None,
    start_time: float,
    pii_token_map=None,
    cache_enabled: bool = False,
):
    """Handle a streaming request with usage tracking and PII rehydration."""
    from app.database import async_session

    usage_tracker = StreamingUsageTracker()

    async def stream_generator():
        # Use a FRESH session — the request-scoped session may close before streaming finishes
        try:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code >= 400:
                    error_text = await response.aread()
                    yield f'data: {{"error": "Provider {provider.name} returned {response.status_code}"}}\n\n'
                    return

                async for line in response.aiter_lines():
                    # PII rehydration: restore original values in streamed chunks
                    if pii_token_map:
                        line = pii_token_map.rehydrate(line)
                    if line.startswith("data: "):
                        chunk_data = line[6:]
                        usage_tracker.process_chunk(chunk_data)
                    yield f"{line}\n"

        except Exception as e:
            logger.error(f"Streaming error from {provider.name}: {e}")
            yield f'data: {{"error": "{str(e)}"}}\n\n'

        finally:
            # Record usage with a fresh session (request session may be closed)
            latency_ms = int((time.time() - start_time) * 1000)
            streaming_usage = usage_tracker.get_usage()

            try:
                async with async_session() as stream_db:
                    await _record_usage(
                        stream_db, api_key, model, body, None, prediction,
                        latency_ms, agent_id=agent_id,
                        streaming_usage=streaming_usage,
                    )
                    await stream_db.commit()
            except Exception as e:
                logger.error(f"Failed to record streaming usage: {e}")

    response_headers = {}
    if prediction:
        response_headers["X-Predicted-Cost-Cents"] = str(prediction["costs"]["estimated_total_cents"])
        response_headers["X-Predicted-Input-Tokens"] = str(prediction["input_tokens"])
    response_headers["X-Model-Served"] = model.model_id
    response_headers["X-Provider"] = provider.name

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers=response_headers,
    )
