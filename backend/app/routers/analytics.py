"""Usage analytics router — spend tracking, model stats, budget alerts."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import UsageRecord

router = APIRouter(prefix="/v1", tags=["analytics"])


@router.get("/usage")
async def get_usage(
    days: int = Query(30, ge=1, le=365),
    agent_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get usage analytics for a time period."""
    since = datetime.utcnow() - timedelta(days=days)

    stmt = (
        select(UsageRecord)
        .where(UsageRecord.created_at >= since)
        .order_by(desc(UsageRecord.created_at))
    )
    if agent_id:
        stmt = stmt.where(UsageRecord.agent_id == agent_id)

    result = await db.execute(stmt.limit(1000))
    records = result.scalars().all()

    # Aggregate stats
    total_cost_cents = sum(r.total_cost_cents for r in records)
    total_requests = len(records)
    total_prompt_tokens = sum(r.prompt_tokens for r in records)
    total_completion_tokens = sum(r.completion_tokens for r in records)

    # Per-model breakdown
    model_stats: dict[str, dict] = {}
    for r in records:
        mid = r.model_served
        if mid not in model_stats:
            model_stats[mid] = {
                "model": mid,
                "requests": 0,
                "cost_cents": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "avg_latency_ms": 0,
            }
        model_stats[mid]["requests"] += 1
        model_stats[mid]["cost_cents"] += r.total_cost_cents
        model_stats[mid]["prompt_tokens"] += r.prompt_tokens
        model_stats[mid]["completion_tokens"] += r.completion_tokens

    # Compute average latencies
    for mid in model_stats:
        model_records = [r for r in records if r.model_served == mid]
        if model_records:
            model_stats[mid]["avg_latency_ms"] = int(
                sum(r.latency_ms for r in model_records) / len(model_records)
            )

    return {
        "period_days": days,
        "total_requests": total_requests,
        "total_cost_cents": total_cost_cents,
        "total_cost_usd": total_cost_cents / 10000,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "per_model": sorted(model_stats.values(), key=lambda x: -x["cost_cents"]),
        "recent_requests": [
            {
                "model": r.model_served,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_cents": r.total_cost_cents,
                "latency_ms": r.latency_ms,
                "task_type": r.task_type,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in records[:20]
        ],
    }


@router.get("/usage/daily")
async def get_daily_usage(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get daily cost breakdown for charts."""
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.created_at >= since)
        .order_by(UsageRecord.created_at)
    )
    records = result.scalars().all()

    # Group by day
    daily: dict[str, dict] = {}
    for r in records:
        day = r.created_at.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"date": day, "cost_cents": 0, "requests": 0, "tokens": 0}
        daily[day]["cost_cents"] += r.total_cost_cents
        daily[day]["requests"] += 1
        daily[day]["tokens"] += r.prompt_tokens + r.completion_tokens

    return {"daily": sorted(daily.values(), key=lambda x: x["date"])}


@router.get("/stats")
async def get_platform_stats(db: AsyncSession = Depends(get_db)):
    """Platform-wide statistics."""
    total_result = await db.execute(
        select(
            func.count(UsageRecord.id),
            func.sum(UsageRecord.total_cost_cents),
            func.sum(UsageRecord.prompt_tokens),
            func.sum(UsageRecord.completion_tokens),
        )
    )
    row = total_result.one()

    return {
        "total_requests": row[0] or 0,
        "total_cost_cents": row[1] or 0,
        "total_cost_usd": (row[1] or 0) / 10000,
        "total_prompt_tokens": row[2] or 0,
        "total_completion_tokens": row[3] or 0,
    }
