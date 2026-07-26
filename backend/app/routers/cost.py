"""Cost prediction router — the core value proposition.

Endpoints:
  POST /v1/predict   — predict the cost of a request before sending
  POST /v1/compare   — compare costs across all models
  GET  /v1/models    — list all models with pricing
  GET  /v1/pareto    — get Pareto-optimal models for a task type
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Model
from app.services.cost_engine import compare_models, predict_cost

router = APIRouter(prefix="/v1", tags=["cost-intelligence"])


# ─── Schemas ───────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str | list[Any] | None = None


class PredictRequest(BaseModel):
    model: str
    messages: list[Message]
    max_tokens: int | None = None
    tools: list[dict] | None = None


class CompareRequest(BaseModel):
    messages: list[Message]
    max_tokens: int | None = None
    optimize_for: str = Field("balanced", pattern="^(cheapest|fastest|balanced|quality)$")


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.post("/predict")
async def predict(req: PredictRequest, db: AsyncSession = Depends(get_db)):
    """Predict the exact cost of an API request BEFORE sending it.

    This is SwiftGate's killer feature — no other gateway offers this.

    Returns exact input token count, estimated output, and cost in cents + USD.
    """
    result = await predict_cost(
        db=db,
        model_id=req.model,
        messages=[m.model_dump() for m in req.messages],
        max_tokens=req.max_tokens,
        tools=req.tools,
    )
    return result


@router.post("/compare")
async def compare(req: CompareRequest, db: AsyncSession = Depends(get_db)):
    """Compare costs across ALL available models for the same prompt.

    Returns models sorted by optimization criterion, with Pareto-optimal flags.
    """
    result = await compare_models(
        db=db,
        messages=[m.model_dump() for m in req.messages],
        max_tokens=req.max_tokens,
        optimize_for=req.optimize_for,
    )
    return {
        "models": result,
        "count": len(result),
        "optimize_for": req.optimize_for,
        "pareto_optimal": [m for m in result if m["pareto_optimal"]],
    }


@router.get("/models")
async def list_models(
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all available models with pricing and capabilities."""
    stmt = select(Model).where(Model.is_active == True)  # noqa: E712
    if category:
        stmt = stmt.where(Model.category == category)
    stmt = stmt.order_by(Model.quality_score.desc())

    result = await db.execute(stmt)
    models = result.scalars().all()

    return {
        "models": [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "category": m.category,
                "context_window": m.context_window,
                "supports_tools": m.supports_tools,
                "supports_vision": m.supports_vision,
                "supports_json": m.supports_json,
                "quality_score": m.quality_score,
                "speed_score": m.speed_score,
                "pricing": {
                    "prompt_per_mtok": round(float(m.prompt_price) * 1_000_000, 4),
                    "completion_per_mtok": round(float(m.completion_price) * 1_000_000, 4),
                    "cached_per_mtok": round(float(m.cached_price) * 1_000_000, 4) if m.cached_price else None,
                },
            }
            for m in models
        ],
        "count": len(models),
    }


@router.get("/pareto")
async def pareto_frontier(
    task_type: str = Query("chat"),
    max_tokens: int = Query(1000),
    db: AsyncSession = Depends(get_db),
):
    """Get the Pareto-optimal models — best quality per dollar.

    Uses a synthetic prompt for the given task type to estimate costs.
    """
    # Create a representative prompt for the task type
    sample_prompts = {
        "chat": "Explain how authentication works in web applications.",
        "code": "Write a Python function that merges two sorted lists efficiently.",
        "reasoning": "Analyze the trade-offs between microservices and monolithic architecture.",
        "vision": "Describe what's in this image.",
        "tool_use": "Search for the latest news about AI and summarize the top 3 stories.",
    }
    prompt = sample_prompts.get(task_type, sample_prompts["chat"])

    messages = [{"role": "user", "content": prompt}]

    result = await compare_models(
        db=db,
        messages=messages,
        max_tokens=max_tokens,
        optimize_for="balanced",
    )

    return {
        "pareto_optimal": [m for m in result if m["pareto_optimal"]],
        "task_type": task_type,
        "all_models": result,
    }


@router.get("/models/{model_id}")
async def get_model_detail(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a single model."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Model)
        .options(selectinload(Model.provider))
        .where(Model.model_id == model_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        from fastapi import HTTPException
        raise HTTPException(404, f"Model '{model_id}' not found")

    return {
        "model_id": model.model_id,
        "display_name": model.display_name,
        "provider": model.provider.name if model.provider else None,
        "category": model.category,
        "tokenizer": model.tokenizer,
        "context_window": model.context_window,
        "max_output": model.max_output,
        "supports_tools": model.supports_tools,
        "supports_vision": model.supports_vision,
        "supports_json": model.supports_json,
        "supports_streaming": getattr(model, "supports_streaming", True),
        "quality_score": model.quality_score,
        "speed_score": model.speed_score,
        "pricing": {
            "prompt_per_mtok": round(float(model.prompt_price) * 1_000_000, 4),
            "completion_per_mtok": round(float(model.completion_price) * 1_000_000, 4),
            "cached_per_mtok": round(float(model.cached_price) * 1_000_000, 4) if model.cached_price else None,
        },
    }
