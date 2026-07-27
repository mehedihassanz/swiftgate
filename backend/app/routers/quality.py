"""Quality scoring and routing rules router.

Endpoints:
  Quality:
    POST /v1/quality/feedback        — submit explicit feedback (thumbs up/down)
    GET  /v1/quality/{model_id}      — get quality index for a model
    GET  /v1/quality/leaderboard     — quality-per-dollar rankings
    POST /v1/quality/route           — get quality-aware routing recommendation

  Routing Rules:
    GET    /v1/routing/rules         — list rules
    POST   /v1/routing/rules         — create rule
    PUT    /v1/routing/rules/{id}    — update rule
    DELETE /v1/routing/rules/{id}    — delete rule
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_admin
from app.models import QualityScore, RoutingRule
from app.services.quality_router import (
    get_quality_index,
    record_quality_signal,
    route_by_quality_per_dollar,
)

router = APIRouter(prefix="/v1", tags=["quality-routing"])


# ─── Quality Schemas ───────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    model_id: str
    task_type: str = "chat"
    rating: int = Field(..., ge=1, le=10, description="1-10 quality rating")
    signal_type: str = "explicit_rating"
    usage_record_id: int | None = None
    comment: str | None = None


class QualityRouteRequest(BaseModel):
    messages: list[dict[str, Any]]
    max_budget_cents: int | None = None
    min_quality: float = 0.0
    top_n: int = 10


# ─── Quality Endpoints ─────────────────────────────────────────────────

@router.post("/quality/feedback")
async def submit_feedback(body: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    """Submit explicit quality feedback for a model output.

    Accepts ratings 1-10. Converts to a QualityScore record that feeds
    the quality-aware routing engine.
    """
    qs = await record_quality_signal(
        db=db,
        model_id=body.model_id,
        task_type=body.task_type,
        score=float(body.rating),
        signal_source="explicit",
        signal_type=body.signal_type,
        usage_record_id=body.usage_record_id,
    )
    await db.commit()
    return {
        "recorded": True,
        "model_id": body.model_id,
        "score": body.rating,
        "quality_score_id": qs.id,
    }


@router.post("/quality/route")
async def quality_route(body: QualityRouteRequest, db: AsyncSession = Depends(get_db)):
    """Get quality-per-dollar routing recommendation.

    This is the killer feature: routes by measured output quality, not just price.
    Returns models ranked by quality-per-dollar with Pareto-optimal flags.
    """
    results = await route_by_quality_per_dollar(
        db=db,
        messages=body.messages,
        max_budget_cents=body.max_budget_cents,
        min_quality=body.min_quality,
        top_n=body.top_n,
    )
    return {
        "models": results,
        "count": len(results),
        "pareto_optimal": [m for m in results if m.get("pareto_optimal")],
    }


@router.get("/quality/leaderboard")
async def quality_leaderboard(
    task_type: str = Query("chat"),
    min_samples: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get the quality leaderboard — models ranked by empirical quality."""
    from sqlalchemy import func as sqlfunc
    from app.models import Model

    result = await db.execute(
        select(
            QualityScore.model_id,
            sqlfunc.avg(QualityScore.score).label("avg_score"),
            sqlfunc.count(QualityScore.id).label("sample_count"),
        )
        .where(QualityScore.task_type == task_type)
        .group_by(QualityScore.model_id)
        .having(sqlfunc.count(QualityScore.id) >= min_samples)
        .order_by(sqlfunc.avg(QualityScore.score).desc())
    )
    rows = result.all()

    return {
        "task_type": task_type,
        "leaderboard": [
            {
                "model_id": r[0],
                "empirical_score": round(float(r[1]), 2),
                "samples": r[2],
            }
            for r in rows
        ],
    }


# NOTE: This route MUST come after /quality/leaderboard and /quality/route
# because FastAPI matches {model_id} greedily.
@router.get("/quality/{model_id}")
async def get_model_quality(
    model_id: str,
    task_type: str = Query("chat"),
    db: AsyncSession = Depends(get_db),
):
    """Get the empirical quality index for a model+task."""
    score, confidence, samples = await get_quality_index(db, model_id, task_type)
    return {
        "model_id": model_id,
        "task_type": task_type,
        "quality_score": score,
        "confidence": confidence,
        "sample_size": samples,
        "source": "empirical" if samples >= 10 else "static_fallback",
    }


# ─── Routing Rules Schemas ─────────────────────────────────────────────

class RoutingRuleCreate(BaseModel):
    name: str
    task_type: str | None = None
    model_category: str | None = None
    max_cost_per_request_cents: int | None = None
    min_quality_score: float | None = None
    strategy: str = "balanced"
    target_model_id: str | None = None
    priority: int = 100


class RoutingRuleUpdate(BaseModel):
    name: str | None = None
    task_type: str | None = None
    model_category: str | None = None
    max_cost_per_request_cents: int | None = None
    min_quality_score: float | None = None
    strategy: str | None = None
    target_model_id: str | None = None
    is_active: bool | None = None
    priority: int | None = None


# ─── Routing Rules Endpoints ───────────────────────────────────────────

@router.get("/routing/rules")
async def list_routing_rules(db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """List all routing rules, ordered by priority."""
    result = await db.execute(
        select(RoutingRule).order_by(RoutingRule.priority, RoutingRule.created_at.desc())
    )
    rules = result.scalars().all()
    return {
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "task_type": r.task_type,
                "model_category": r.model_category,
                "max_cost_per_request_cents": r.max_cost_per_request_cents,
                "min_quality_score": float(r.min_quality_score) if r.min_quality_score else None,
                "strategy": r.strategy,
                "target_model_id": r.target_model_id,
                "is_active": r.is_active,
                "priority": r.priority,
            }
            for r in rules
        ],
        "count": len(rules),
    }


@router.post("/routing/rules", status_code=201)
async def create_routing_rule(body: RoutingRuleCreate, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Create a routing rule."""
    rule = RoutingRule(**body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"created": True, "id": rule.id}


@router.put("/routing/rules/{rule_id}")
async def update_routing_rule(rule_id: int, body: RoutingRuleUpdate, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Update a routing rule."""
    rule = await db.get(RoutingRule, rule_id)
    if not rule:
        raise HTTPException(404, "Routing rule not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, val)

    await db.commit()
    return {"updated": True, "id": rule_id}


@router.delete("/routing/rules/{rule_id}")
async def delete_routing_rule(rule_id: int, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Delete a routing rule."""
    rule = await db.get(RoutingRule, rule_id)
    if not rule:
        raise HTTPException(404, "Routing rule not found")
    await db.delete(rule)
    await db.commit()
    return {"deleted": True, "id": rule_id}
