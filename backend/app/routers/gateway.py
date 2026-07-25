"""Gateway proxy router — OpenAI-compatible API that routes to upstream providers.

POST /v1/chat/completions — the main gateway endpoint
  - Accepts standard OpenAI chat completion format
  - Predicts cost before sending
  - Checks budget limits
  - Routes to the cheapest/best provider
  - Records actual token usage after completion

This is a drop-in replacement for OpenAI's API.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ApiKey, Model, Provider, UsageRecord
from app.services.cost_engine import predict_cost
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
    # NeuralWatt extensions
    optimize_for: str | None = None  # "cheapest", "fastest", "balanced", "quality"
    agent_id: str | None = None
    cost_prediction: bool = True  # return prediction in response headers


# ─── API key authentication ────────────────────────────────────────────

async def _authenticate(
    authorization: str | None,
    db: AsyncSession,
) -> ApiKey | None:
    """Authenticate via Bearer token. Returns None if no key (free tier)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    raw_key = authorization[7:]  # strip "Bearer "
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    return result.scalar_one_or_none()


# ─── Provider routing ──────────────────────────────────────────────────

async def _get_model_and_provider(
    db: AsyncSession,
    model_id: str,
) -> tuple[Model, Provider]:
    """Look up the model and its provider."""
    result = await db.execute(
        select(Model).where(Model.model_id == model_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(400, f"Unknown model: {model_id}")

    provider = await db.get(Provider, model.provider_id)
    if not provider:
        raise HTTPException(500, f"Provider not found for model {model_id}")

    return model, provider


def _get_api_key_for_provider(provider: Provider) -> str:
    """Get the API key for a provider from environment."""
    import os
    return os.environ.get(provider.api_key_env, "")


def _build_upstream_request(
    request_body: dict,
    model: Model,
) -> tuple[str, dict, dict]:
    """Build the upstream API call.

    Returns (url, headers, body).
    """
    provider = model.provider

    # Most providers use OpenAI-compatible format
    # Anthropic has its own format
    if provider.name == "anthropic":
        url = f"{provider.base_url}/messages"
        headers = {
            "x-api-key": _get_api_key_for_provider(provider),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Convert to Anthropic format
        body = _convert_to_anthropic(request_body, model)
    else:
        # OpenAI-compatible (OpenAI, DeepInfra, Together, Mistral, etc.)
        url = f"{provider.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {_get_api_key_for_provider(provider)}",
            "content-type": "application/json",
        }
        body = request_body

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

    if request.get("tools"):
        body["tools"] = request["tools"]

    return body


# ─── Usage tracking ────────────────────────────────────────────────────

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
) -> None:
    """Record the actual token usage and cost."""
    # Extract actual token counts from the response
    if response_data and "usage" in response_data:
        usage = response_data["usage"]
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
    elif prediction:
        # No usage data (some providers don't return it) — use prediction
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

    # Calculate prediction accuracy
    pred_error = None
    if prediction and prediction.get("estimated_total_cents"):
        pred = prediction["costs"]["estimated_total_cents"]
        if total_cost > 0:
            pred_error = abs(pred - total_cost) / total_cost * 100

    task_type = classify_task([m.model_dump() for m in [
        Message(**m) if isinstance(m, dict) else m
        for m in request_body.get("messages", [])
    ]])

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

    # Update API key spend tracking
    if api_key:
        api_key.total_spend_cents += total_cost
        api_key.total_requests += 1
        api_key.last_used = datetime.utcnow()

    await db.flush()


# ─── Budget enforcement ────────────────────────────────────────────────

def _check_budget(api_key: ApiKey | None, predicted_cost_cents: int) -> None:
    """Check if this request would exceed budget limits."""
    if not api_key or not api_key.is_active:
        return

    # Per-request limit
    if api_key.per_request_limit_cents:
        if predicted_cost_cents > api_key.per_request_limit_cents:
            raise HTTPException(
                402,
                f"Predicted cost (${predicted_cost_cents / 10000:.4f}) exceeds "
                f"per-request limit (${api_key.per_request_limit_cents / 10000:.4f})"
            )

    # Monthly budget
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


# ─── Main gateway endpoint ─────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
):
    """OpenAI-compatible chat completions endpoint with cost intelligence.

    Drop-in replacement for `https://api.openai.com/v1/chat/completions`.

    Extra features:
      - Pre-flight cost prediction (returned in headers)
      - Budget enforcement (rejects if over budget)
      - Automatic provider routing
      - Real-time usage tracking
    """
    body = await raw_request.json()

    # Parse request
    try:
        req = ChatCompletionRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request: {e}")

    # Authenticate
    api_key = await _authenticate(authorization, db)

    # Get model + provider
    model, provider = await _get_model_and_provider(db, req.model)

    # Check provider API key is configured
    if not _get_api_key_for_provider(provider):
        raise HTTPException(
            503,
            f"Provider '{provider.name}' API key not configured. "
            f"Set the {provider.api_key_env} environment variable."
        )

    # Predict cost (the killer feature)
    prediction = None
    if req.cost_prediction:
        prediction = await predict_cost(
            db=db,
            model_id=req.model,
            messages=[m.model_dump() for m in req.messages],
            max_tokens=req.max_tokens,
            tools=req.tools,
        )

    # Check budget
    if prediction and "costs" in prediction:
        _check_budget(api_key, prediction["costs"]["worst_case_cents"])

    # Build upstream request
    upstream_url, upstream_headers, upstream_body = _build_upstream_request(
        body, model,
    )

    # Forward the request
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            if req.stream:
                # Streaming — proxy the SSE stream
                async def stream_generator():
                    try:
                        async with client.stream(
                            "POST", upstream_url, headers=upstream_headers, json=upstream_body
                        ) as response:
                            async for line in response.aiter_lines():
                                yield f"{line}\n"
                    except Exception as e:
                        logger.error(f"Streaming error: {e}")
                        yield f'data: {{"error": "{str(e)}"}}\n\n'

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "X-Predicted-Cost-Cents": str(prediction["costs"]["estimated_total_cents"]) if prediction else "",
                        "X-Predicted-Input-Tokens": str(prediction["input_tokens"]) if prediction else "",
                        "X-Model-Served": model.model_id,
                    },
                )

            else:
                # Non-streaming
                response = await client.post(
                    upstream_url,
                    headers=upstream_headers,
                    json=upstream_body,
                )
                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code >= 400:
                    # Record the error
                    await _record_usage(
                        db, api_key, model, body, None, prediction,
                        latency_ms, status="error", agent_id=req.agent_id,
                    )
                    await db.commit()
                    raise HTTPException(
                        response.status_code,
                        f"Upstream error: {response.text[:500]}"
                    )

                response_data = response.json()

                # Record actual usage
                await _record_usage(
                    db, api_key, model, body, response_data, prediction,
                    latency_ms, agent_id=req.agent_id,
                )
                await db.commit()

                # Add NeuralWatt headers to response
                # (FastAPI doesn't let us add headers to a returned dict directly,
                # so we embed prediction info in the response)
                if prediction:
                    response_data["neuralwatt"] = {
                        "predicted_cost_cents": prediction["costs"]["estimated_total_cents"],
                        "actual_cost_cents": (
                            int(float(model.prompt_price) * response_data.get("usage", {}).get("prompt_tokens", 0) * 10000) +
                            int(float(model.completion_price) * response_data.get("usage", {}).get("completion_tokens", 0) * 10000)
                        ),
                        "input_tokens": prediction["input_tokens"],
                        "task_type": prediction["task_type"],
                        "routing_suggestion": prediction.get("routing_suggestion"),
                        "prediction_confidence": prediction["confidence"],
                    }

                return response_data

    except httpx.TimeoutException:
        raise HTTPException(504, "Upstream provider timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gateway error: {e}", exc_info=True)
        raise HTTPException(500, f"Gateway error: {str(e)}")
