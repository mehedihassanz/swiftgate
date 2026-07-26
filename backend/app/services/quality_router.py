"""Quality-aware routing service — the second data flywheel.

Measures real output quality using 3 tiers of signals, then routes by
quality-per-dollar Pareto frontier instead of static quality scores.

Public API:
    get_quality_index(db, model_id, task_type) -> (score, confidence, sample_size)
    record_quality_signal(db, model_id, task_type, score, source, signal_type)
    route_by_quality_per_dollar(db, messages, max_budget) -> list[dict]
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Model, QualityScore
from app.services.tokenizer import classify_task, get_token_count

logger = logging.getLogger(__name__)

# Time window for quality score aggregation (days)
QUALITY_WINDOW_DAYS = 30

# Minimum samples before using empirical quality score
MIN_QUALITY_SAMPLES = 10

# Signal weights — automated (LLM judge) > explicit (thumbs) > implicit (retries)
SIGNAL_WEIGHTS = {
    "automated": 3.0,
    "explicit": 2.0,
    "implicit": 1.0,
}


async def get_quality_index(
    db: AsyncSession,
    model_id: str,
    task_type: str = "chat",
) -> tuple[float, float, int]:
    """Get empirically-measured quality score for a model+task.

    Returns: (weighted_score, confidence, sample_size)
    Falls back to the model's static quality_score if insufficient data.
    """
    since = datetime.utcnow() - timedelta(days=QUALITY_WINDOW_DAYS)

    result = await db.execute(
        select(QualityScore)
        .where(
            QualityScore.model_id == model_id,
            QualityScore.task_type == task_type,
            QualityScore.created_at >= since,
        )
        .order_by(desc(QualityScore.created_at))
        .limit(500)
    )
    scores = result.scalars().all()

    if len(scores) < MIN_QUALITY_SAMPLES:
        # Fall back to static score
        model_result = await db.execute(select(Model).where(Model.model_id == model_id))
        model = model_result.scalar_one_or_none()
        static_score = float(model.quality_score) if model else 7.0
        return static_score, 0.3, len(scores)

    # Weighted average: recent signals weighted higher, automated > explicit > implicit
    weighted_sum = 0.0
    weight_total = 0.0

    for i, qs in enumerate(scores):
        # Recency weight: most recent = highest
        age_days = (datetime.utcnow() - qs.created_at).total_seconds() / 86400
        recency_weight = max(0.1, 1.0 - age_days / QUALITY_WINDOW_DAYS)

        # Signal weight
        signal_weight = SIGNAL_WEIGHTS.get(qs.signal_source, 1.0)

        combined_weight = recency_weight * signal_weight
        weighted_sum += float(qs.score) * combined_weight
        weight_total += combined_weight

    empirical_score = weighted_sum / weight_total if weight_total > 0 else 7.0

    # Confidence: more samples = higher, but capped
    confidence = min(0.95, len(scores) / 100)

    return round(empirical_score, 2), confidence, len(scores)


async def record_quality_signal(
    db: AsyncSession,
    model_id: str,
    task_type: str,
    score: float,
    signal_source: str = "implicit",
    signal_type: str = "generic",
    usage_record_id: int | None = None,
) -> QualityScore:
    """Record a quality signal for a model+task pair.

    signal_source: "implicit", "explicit", or "automated"
    signal_type: "thumbs_up", "thumbs_down", "user_retry", "conversation_continued",
                 "llm_judge", "regenerate", etc.
    """
    qs = QualityScore(
        model_id=model_id,
        task_type=task_type,
        score=score,
        signal_source=signal_source,
        signal_type=signal_type,
        usage_record_id=usage_record_id,
    )
    db.add(qs)
    await db.flush()
    return qs


async def route_by_quality_per_dollar(
    db: AsyncSession,
    messages: list[dict[str, Any]],
    max_budget_cents: int | None = None,
    min_quality: float = 0.0,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Find models ranked by quality-per-dollar.

    Uses empirical quality scores when available (data flywheel),
    falls back to static scores otherwise.

    Returns list of models with quality_score, estimated_cost, and qpd_score.
    """
    from app.services.cost_engine import _get_model
    from app.services.prediction_ml import predictor
    from app.config import settings

    task_type = classify_task(messages)

    result = await db.execute(
        select(Model)
        .options(selectinload(Model.provider))
        .where(Model.is_active == True)  # noqa: E712
        .order_by(Model.quality_score.desc())
    )
    models = result.scalars().all()

    candidates: list[dict[str, Any]] = []

    for model in models:
        # Get input tokens for this model's tokenizer
        input_tokens = get_token_count(messages, model.model_id)

        # Predict output using ML flywheel
        ml_pred = predictor.predict(
            model_id=model.model_id,
            task_type=task_type,
            input_tokens=input_tokens,
        )

        # Get empirical quality score (second flywheel)
        quality, quality_conf, quality_samples = await get_quality_index(
            db, model.model_id, task_type
        )

        # Skip if below minimum quality threshold
        if quality < min_quality:
            continue

        # Compute estimated cost
        margin = 1 + settings.TOKEN_MARGIN
        cost_cents = int(
            (float(model.prompt_price) * input_tokens +
             float(model.completion_price) * ml_pred.predicted_output_tokens)
            * margin * 10000
        )

        # Skip if over budget
        if max_budget_cents and cost_cents > max_budget_cents:
            continue

        # Quality-per-dollar score (higher is better)
        cost_usd = cost_cents / 10000
        qpd_score = quality / max(cost_usd, 0.0001)

        candidates.append({
            "model_id": model.model_id,
            "display_name": model.display_name,
            "provider": model.provider.name if model.provider else None,
            "category": model.category,
            "quality_score": quality,
            "quality_confidence": quality_conf,
            "quality_samples": quality_samples,
            "estimated_cost_cents": cost_cents,
            "estimated_cost_usd": round(cost_usd, 6),
            "qpd_score": round(qpd_score, 2),
            "input_tokens": input_tokens,
            "predicted_output": ml_pred.predicted_output_tokens,
            "prediction_method": ml_pred.method,
        })

    # Sort by quality-per-dollar (descending)
    candidates.sort(key=lambda x: -x["qpd_score"])

    # Mark Pareto-optimal
    _mark_pareto(candidates)

    return candidates[:top_n]


def _mark_pareto(candidates: list[dict[str, Any]]) -> None:
    """Mark models on the Pareto frontier (quality vs cost)."""
    for m in candidates:
        m["pareto_optimal"] = True

    for i, m in enumerate(candidates):
        for j, other in enumerate(candidates):
            if i == j:
                continue
            if (other["estimated_cost_cents"] < m["estimated_cost_cents"]
                and other["quality_score"] >= m["quality_score"]):
                m["pareto_optimal"] = False
                break


# ─── Implicit signal detection ────────────────────────────────────────

async def detect_implicit_signal(
    db: AsyncSession,
    api_key_id: int | None,
    model_served: str,
    task_type: str,
    usage_record_id: int | None,
    is_retry: bool = False,
    conversation_continued: bool = False,
) -> None:
    """Detect implicit quality signals from user behavior.

    - User retries with different model → negative signal for original model
    - User continues conversation → positive signal
    - User abandons → neutral (no signal)
    """
    if is_retry:
        await record_quality_signal(
            db, model_served, task_type,
            score=4.0,  # below average — user wasn't satisfied
            signal_source="implicit",
            signal_type="user_retry",
            usage_record_id=usage_record_id,
        )

    if conversation_continued:
        await record_quality_signal(
            db, model_served, task_type,
            score=8.0,  # above average — user continued engaging
            signal_source="implicit",
            signal_type="conversation_continued",
            usage_record_id=usage_record_id,
        )
