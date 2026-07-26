"""Provider router — handles failover, retries, and multi-provider routing.

When a request fails at one provider, this module tries the next provider
that offers the same model (or a compatible fallback).

Public API:
    get_failover_chain(db, model_id) -> list[(Model, Provider)]
    route_request(db, body, strategy) -> (model, provider)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Model, Provider

logger = logging.getLogger(__name__)


async def get_failover_chain(
    db: AsyncSession,
    model: Model,
) -> list[tuple[Model, Provider]]:
    """Get the list of (model, provider) pairs to try for failover.

    Primary: the requested model at its provider
    Secondary: same model at alternate providers (if any provider also hosts it)
    Tertiary: fallback models in the same category with similar quality
    """
    chain: list[tuple[Model, Provider]] = []

    # Get the primary provider
    provider = await db.get(Provider, model.provider_id)
    if provider and _get_provider_key(provider):
        chain.append((model, provider))

    # Find alternate providers offering similar models in same category
    # (for failover — e.g., if OpenAI is down, try a similar model elsewhere)
    result = await db.execute(
        select(Model)
        .options(selectinload(Model.provider))
        .where(
            Model.is_active == True,  # noqa: E712
            Model.model_id != model.model_id,
            Model.category == model.category,
            Model.quality_score >= model.quality_score - 1.0,
        )
        .order_by(Model.quality_score.desc(), Model.prompt_price.asc())
    )
    alternatives = result.scalars().all()

    for alt_model in alternatives:
        alt_provider = alt_model.provider
        if alt_provider and alt_provider.active and _get_provider_key(alt_provider):
            # Only add if the provider is different from ones already in chain
            existing_providers = {p.name for _, p in chain}
            if alt_provider.name not in existing_providers:
                chain.append((alt_model, alt_provider))

    return chain


def _get_provider_key(provider: Provider) -> str:
    """Check if a provider has an API key configured."""
    import os
    return os.environ.get(provider.api_key_env, "")


async def route_by_strategy(
    db: AsyncSession,
    model_id: str | None,
    strategy: str,
) -> list[tuple[Model, Provider]]:
    """Build a failover chain based on routing strategy.

    Applies active RoutingRules first (highest priority first), then falls
    back to the default strategy if no rule matches.

    If model_id is specified, use it as primary with failover.
    If model_id is None, use the strategy (or matching rule) to pick the best model.
    """
    # ── Check routing rules first ──
    rules = await _get_matching_rules(db, strategy)
    if rules:
        for rule in rules:
            chain = await _apply_rule(db, rule)
            if chain:
                return chain

    if model_id:
        # Find the requested model
        result = await db.execute(
            select(Model).options(selectinload(Model.provider)).where(Model.model_id == model_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return []
        return await get_failover_chain(db, model)

    # No specific model — pick by strategy
    if strategy == "cheapest":
        order = (Model.prompt_price.asc(), Model.completion_price.asc())
    elif strategy == "fastest":
        order = (Model.speed_score.desc(),)
    elif strategy == "quality":
        order = (Model.quality_score.desc(),)
    else:  # balanced
        order = (Model.quality_score.desc(), Model.prompt_price.asc())

    result = await db.execute(
        select(Model)
        .options(selectinload(Model.provider))
        .where(Model.is_active == True)  # noqa: E712
        .order_by(*order)
        .limit(5)
    )
    models = result.scalars().all()

    chain: list[tuple[Model, Provider]] = []
    for m in models:
        p = m.provider
        if p and p.active and _get_provider_key(p):
            chain.append((m, p))

    return chain


# ─── Retry logic ──────────────────────────────────────────────────────

MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def should_retry(status_code: int, attempt: int) -> bool:
    """Check if a failed request should be retried at another provider."""
    return status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES


# ─── Routing rules integration ────────────────────────────────────────

async def _get_matching_rules(db: AsyncSession, strategy: str) -> list:
    """Get active routing rules, ordered by priority."""
    from app.models import RoutingRule
    result = await db.execute(
        select(RoutingRule)
        .where(RoutingRule.is_active == True)  # noqa: E712
        .order_by(RoutingRule.priority, RoutingRule.created_at.desc())
    )
    return result.scalars().all()


async def _apply_rule(db: AsyncSession, rule) -> list[tuple[Model, Provider]]:
    """Apply a single routing rule and return a failover chain if it matches."""
    # If the rule specifies a target model, route directly to it
    if rule.target_model_id:
        result = await db.execute(
            select(Model)
            .options(selectinload(Model.provider))
            .where(Model.model_id == rule.target_model_id, Model.is_active == True)  # noqa: E712
        )
        model = result.scalar_one_or_none()
        if model:
            return await get_failover_chain(db, model)

    # Build query with rule constraints
    stmt = (
        select(Model)
        .options(selectinload(Model.provider))
        .where(Model.is_active == True)  # noqa: E712
    )

    if rule.task_type:
        stmt = stmt.where(Model.category == rule.task_type)
    if rule.model_category:
        stmt = stmt.where(Model.category == rule.model_category)
    if rule.max_cost_per_request_cents:
        # Filter by prompt price (rough proxy for cost-per-request)
        stmt = stmt.where(
            (Model.prompt_price * 1000) <= rule.max_cost_per_request_cents / 10
        )
    if rule.min_quality_score:
        stmt = stmt.where(Model.quality_score >= rule.min_quality_score)

    # Apply strategy from rule (or default)
    strat = rule.strategy or "balanced"
    if strat == "cheapest":
        stmt = stmt.order_by(Model.prompt_price.asc(), Model.completion_price.asc())
    elif strat == "fastest":
        stmt = stmt.order_by(Model.speed_score.desc())
    elif strat == "quality":
        stmt = stmt.order_by(Model.quality_score.desc())
    else:
        stmt = stmt.order_by(Model.quality_score.desc(), Model.prompt_price.asc())

    stmt = stmt.limit(5)
    result = await db.execute(stmt)
    models = result.scalars().all()

    chain: list[tuple[Model, Provider]] = []
    for m in models:
        p = m.provider
        if p and p.active and _get_provider_key(p):
            chain.append((m, p))

    return chain
