"""Cost prediction engine — SwiftGate's core IP.

Predicts the exact cost of an API request BEFORE sending it.
This is what no other gateway offers.

Public API:
    predict_cost(db, model_id, messages, max_tokens) -> dict
    compare_models(db, messages, max_tokens) -> list[dict]
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Model
from app.services.tokenizer import classify_task, estimate_output_tokens, get_token_count

logger = logging.getLogger(__name__)


async def _get_model(db: AsyncSession, model_id: str) -> Model | None:
    """Fetch a model by ID."""
    result = await db.execute(select(Model).where(Model.model_id == model_id))
    return result.scalar_one_or_none()


async def predict_cost(
    db: AsyncSession,
    model_id: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    tools: list[dict] | None = None,
) -> dict[str, Any]:
    """Predict the cost of an API request before sending it.

    Args:
        model_id: The model to use (e.g. "claude-opus-5")
        messages: Chat messages
        max_tokens: Max output tokens (from the request)
        tools: Tool definitions (add ~100-500 tokens overhead)

    Returns:
        {
            "model": str,
            "input_tokens": int,           # exact count
            "estimated_output_tokens": int, # predicted
            "max_possible_tokens": int,     # worst case
            "input_cost_cents": int,        # exact
            "estimated_output_cost_cents": int,
            "estimated_total_cents": int,
            "worst_case_cost_cents": int,
            "price_per_mtok": { ... },      # for transparency
            "confidence": "high" | "medium",
            "task_type": str,
            "routing_suggestion": str | None,  # cheaper alternative if available
        }
    """
    model = await _get_model(db, model_id)
    if not model:
        return {"error": f"Unknown model: {model_id}"}

    # 1. Count input tokens (exact)
    input_tokens = get_token_count(messages, model_id)

    # Add tool definition overhead
    tool_tokens = 0
    if tools:
        # Rough estimate: ~50 tokens per tool definition
        tool_tokens = len(tools) * 50
        input_tokens += tool_tokens

    # 2. Classify task type
    task_type = classify_task(messages)

    # 3. Estimate output tokens — use ML predictor (the data flywheel)
    effective_max = max_tokens or model.max_output

    from app.services.prediction_ml import predictor
    ml_result = predictor.predict(
        model_id=model_id,
        task_type=task_type,
        input_tokens=input_tokens,
        max_tokens=effective_max,
    )
    estimated_output = ml_result.predicted_output_tokens

    # 4. Check cache eligibility
    # First message (system prompt) is often cached on repeat calls
    cached_tokens = 0
    if model.cached_price and len(messages) > 1:
        # Estimate: system prompt is cacheable
        system_msg = messages[0] if messages[0].get("role") == "system" else None
        if system_msg:
            cached_tokens = get_token_count([system_msg], model_id)

    # 5. Compute costs (in cents to avoid float issues)
    margin = 1 + settings.TOKEN_MARGIN  # e.g. 1.01 for 1% margin

    input_cost = int(float(model.prompt_price) * input_tokens * margin * 10000)
    cached_cost = int(float(model.cached_price or 0) * cached_tokens * margin * 10000) if cached_tokens else 0
    # Subtract cached portion from input cost (cached is cheaper)
    if cached_tokens > 0:
        non_cached_input = input_tokens - cached_tokens
        input_cost = int(float(model.prompt_price) * non_cached_input * margin * 10000)
        input_cost += cached_cost

    output_cost = int(float(model.completion_price) * estimated_output * margin * 10000)
    worst_case_output = int(float(model.completion_price) * effective_max * margin * 10000)

    estimated_total = input_cost + output_cost
    worst_case_total = input_cost + worst_case_output

    # 6. Find a cheaper alternative for routing suggestion
    suggestion = await _find_cheaper_alternative(db, model, task_type, estimated_output)

    # 7. Confidence level
    confidence = "high" if ml_result.confidence >= 0.8 else "medium" if ml_result.confidence >= 0.5 else "low"

    return {
        "model": model_id,
        "display_name": model.display_name,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "estimated_output_tokens": estimated_output,
        "max_possible_output_tokens": effective_max,
        "task_type": task_type,
        "costs": {
            "input_cents": input_cost,
            "estimated_output_cents": output_cost,
            "estimated_total_cents": estimated_total,
            "worst_case_cents": worst_case_total,
        },
        "formatted": {
            "input": f"${input_cost / 10000:.6f}",
            "estimated_output": f"${output_cost / 10000:.6f}",
            "estimated_total": f"${estimated_total / 10000:.6f}",
            "worst_case": f"${worst_case_total / 10000:.6f}",
        },
        "pricing_reference": {
            "prompt_per_mtok": f"${float(model.prompt_price) * 1_000_000:.2f}",
            "completion_per_mtok": f"${float(model.completion_price) * 1_000_000:.2f}",
            "cached_per_mtok": f"${float(model.cached_price or 0) * 1_000_000:.4f}" if model.cached_price else None,
            "margin_applied": f"{settings.TOKEN_MARGIN * 100:.1f}%",
        },
        "confidence": confidence,
        "routing_suggestion": suggestion,
        "ml_prediction": {
            "method": ml_result.method,
            "confidence_score": round(ml_result.confidence, 3),
            "sample_size": ml_result.sample_size,
            "p50": ml_result.p50,
            "p90": ml_result.p90,
        },
    }


async def compare_models(
    db: AsyncSession,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    optimize_for: str = "balanced",  # "cheapest", "fastest", "balanced", "quality"
) -> list[dict[str, Any]]:
    """Compare costs across all available models for the same prompt.

    Returns models sorted by the optimization criterion, with predicted costs
    and a Pareto efficiency flag.
    """
    result = await db.execute(
        select(Model).where(Model.is_active == True).options(  # noqa: E712
            selectinload(Model.provider)
        )
    )
    models = result.scalars().all()

    comparisons: list[dict[str, Any]] = []
    task_type = classify_task(messages)
    input_tokens = 0  # will be computed per-model (different tokenizers)

    for model in models:
        # Count tokens with this model's tokenizer
        model_input_tokens = get_token_count(messages, model.model_id)
        estimated_output = estimate_output_tokens(model.model_id, task_type, max_tokens or model.max_output)

        margin = 1 + settings.TOKEN_MARGIN
        total_cents = int(
            (float(model.prompt_price) * model_input_tokens +
             float(model.completion_price) * estimated_output) * margin * 10000
        )

        comparisons.append({
            "model_id": model.model_id,
            "display_name": model.display_name,
            "provider": model.provider.name if model.provider else None,
            "category": model.category,
            "input_tokens": model_input_tokens,
            "estimated_output_tokens": estimated_output,
            "total_cost_cents": total_cents,
            "total_cost_usd": total_cents / 10000,
            "quality_score": model.quality_score,
            "speed_score": model.speed_score,
            "context_window": model.context_window,
            "supports_tools": model.supports_tools,
            "supports_vision": model.supports_vision,
            "supports_json": model.supports_json,
        })

    # Sort by optimization criterion
    if optimize_for == "cheapest":
        comparisons.sort(key=lambda x: x["total_cost_cents"])
    elif optimize_for == "fastest":
        comparisons.sort(key=lambda x: -x["speed_score"])
    elif optimize_for == "quality":
        comparisons.sort(key=lambda x: -x["quality_score"])
    else:  # balanced — sort by quality/cost ratio
        comparisons.sort(key=lambda x: -(x["quality_score"] / max(1, x["total_cost_cents"] / 10000)))

    # Mark Pareto-optimal models (not dominated on both cost AND quality)
    _mark_pareto_optimal(comparisons)

    return comparisons


async def _find_cheaper_alternative(
    db: AsyncSession,
    current_model: Model,
    task_type: str,
    estimated_output: int,
) -> dict[str, Any] | None:
    """Find a cheaper model with acceptable quality for the same task."""
    result = await db.execute(
        select(Model).where(
            Model.is_active == True,  # noqa: E712
            Model.model_id != current_model.model_id,
            Model.quality_score >= current_model.quality_score - 1.0,  # within 1 point
        )
    )
    alternatives = result.scalars().all()

    best: dict[str, Any] | None = None
    best_cost = float(current_model.completion_price) * estimated_output

    for alt in alternatives:
        alt_cost = float(alt.completion_price) * estimated_output
        if alt_cost < best_cost * 0.5:  # at least 50% cheaper on output
            best = {
                "model_id": alt.model_id,
                "display_name": alt.display_name,
                "estimated_savings_pct": int((1 - alt_cost / best_cost) * 100),
                "quality_difference": round(alt.quality_score - current_model.quality_score, 1),
                "reason": f"{alt.display_name} is {int((1 - alt_cost / best_cost) * 100)}% cheaper with similar quality",
            }
            best_cost = alt_cost

    return best


def _mark_pareto_optimal(comparisons: list[dict[str, Any]]) -> None:
    """Mark models that are on the Pareto frontier (cost vs quality).

    A model is Pareto-optimal if no other model is both cheaper AND higher quality.
    """
    for m in comparisons:
        m["pareto_optimal"] = True

    for i, m in enumerate(comparisons):
        for j, other in enumerate(comparisons):
            if i == j:
                continue
            # If 'other' dominates 'm' (cheaper AND better quality)
            if (other["total_cost_cents"] < m["total_cost_cents"] and
                other["quality_score"] >= m["quality_score"]):
                m["pareto_optimal"] = False
                break
