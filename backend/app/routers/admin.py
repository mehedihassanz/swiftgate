"""Admin router — CRUD for providers and models.

Endpoints:
  Providers:
    GET    /admin/providers          — list all
    POST   /admin/providers          — create
    PUT    /admin/providers/{id}     — update
    DELETE /admin/providers/{id}     — delete

  Models:
    GET    /admin/models             — list all (with provider info)
    POST   /admin/models             — create
    PUT    /admin/models/{id}        — update
    DELETE /admin/models/{id}        — delete

  Bulk:
    POST   /admin/seed               — re-seed from defaults
    GET    /admin/stats              — platform stats

Auth: requires X-Admin-Key header matching ADMIN_KEY env var (if set).
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import ApiKey, Model, Provider, UsageRecord

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


def _check_admin(x_admin_key: str | None = Header(None, alias="X-Admin-Key")):
    """Simple admin auth. If ADMIN_KEY is set, require matching header."""
    if ADMIN_KEY and x_admin_key != ADMIN_KEY:
        raise HTTPException(401, "Invalid or missing X-Admin-Key header")
    return True


# ─── Provider Schemas ──────────────────────────────────────────────────

class ProviderCreate(BaseModel):
    name: str = Field(..., description="Unique slug, e.g. 'openai'")
    display_name: str
    base_url: str
    api_key_env: str = Field(..., description="Env var name, e.g. 'OPENAI_API_KEY'")
    priority: int = 100
    active: bool = True


class ProviderUpdate(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    priority: int | None = None
    active: bool | None = None


# ─── Model Schemas ─────────────────────────────────────────────────────

class ModelCreate(BaseModel):
    model_id: str = Field(..., description="Unique ID users specify, e.g. 'claude-opus-5'")
    display_name: str
    provider_id: int
    tokenizer: str = "tiktoken"
    prompt_price: str = Field(..., description="Per-token USD, e.g. '0.000005' for $5/1M")
    completion_price: str
    cached_price: str | None = None
    context_window: int = 4096
    max_output: int = 4096
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json: bool = False
    quality_score: float = 7.0
    speed_score: float = 50.0
    is_active: bool = True
    category: str = "general"


class ModelUpdate(BaseModel):
    display_name: str | None = None
    provider_id: int | None = None
    tokenizer: str | None = None
    prompt_price: str | None = None
    completion_price: str | None = None
    cached_price: str | None = None
    context_window: int | None = None
    max_output: int | None = None
    supports_streaming: bool | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_json: bool | None = None
    quality_score: float | None = None
    speed_score: float | None = None
    is_active: bool | None = None
    category: str | None = None


# ─── Provider Endpoints ────────────────────────────────────────────────

@router.get("/providers")
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """List all providers."""
    result = await db.execute(select(Provider).order_by(Provider.priority))
    providers = result.scalars().all()
    return {
        "providers": [_provider_to_dict(p) for p in providers],
        "count": len(providers),
    }


@router.post("/providers", status_code=201)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Add a new provider."""
    existing = await db.execute(select(Provider).where(Provider.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Provider '{body.name}' already exists")

    provider = Provider(**body.model_dump())
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _provider_to_dict(provider)


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Update a provider."""
    provider = await db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(provider, key, val)

    await db.commit()
    await db.refresh(provider)
    return _provider_to_dict(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Delete a provider. Fails if models are attached."""
    provider = await db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    # Check for attached models
    models = await db.execute(select(Model).where(Model.provider_id == provider_id))
    if models.scalars().first():
        raise HTTPException(
            409,
            f"Cannot delete provider with attached models. Delete or reassign models first."
        )

    await db.delete(provider)
    await db.commit()
    return {"deleted": True, "id": provider_id}


# ─── Model Endpoints ───────────────────────────────────────────────────

@router.get("/models")
async def list_models_admin(
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """List all models with full details including pricing."""
    result = await db.execute(
        select(Model).options(selectinload(Model.provider)).order_by(
            Model.category, Model.quality_score.desc()
        )
    )
    models = result.scalars().all()
    return {
        "models": [_model_to_dict(m) for m in models],
        "count": len(models),
    }


@router.post("/models", status_code=201)
async def create_model(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Add a new model."""
    # Check model_id uniqueness
    existing = await db.execute(select(Model).where(Model.model_id == body.model_id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Model '{body.model_id}' already exists")

    # Check provider exists
    provider = await db.get(Provider, body.provider_id)
    if not provider:
        raise HTTPException(400, f"Provider {body.provider_id} not found")

    data = body.model_dump()
    data["prompt_price"] = Decimal(data["prompt_price"])
    data["completion_price"] = Decimal(data["completion_price"])
    if data.get("cached_price"):
        data["cached_price"] = Decimal(data["cached_price"])

    model = Model(**data)
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return _model_to_dict(model)


@router.put("/models/{model_id}")
async def update_model(
    model_id: int,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Update a model."""
    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        if key in ("prompt_price", "completion_price", "cached_price") and val is not None:
            val = Decimal(val)
        setattr(model, key, val)

    await db.commit()
    await db.refresh(model)
    return _model_to_dict(model)


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Delete a model."""
    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    await db.delete(model)
    await db.commit()
    return {"deleted": True, "id": model_id}


# ─── Bulk Operations ───────────────────────────────────────────────────

@router.post("/seed")
async def reseed(
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Re-seed the database with default providers and models."""
    from app.services.pricing import seed_database
    result = await seed_database(db)
    await db.commit()
    return result


@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(_check_admin),
):
    """Platform-wide admin statistics."""
    from sqlalchemy import func

    providers_count = await db.execute(select(func.count(Provider.id)))
    models_count = await db.execute(select(func.count(Model.id)))
    active_models = await db.execute(
        select(func.count(Model.id)).where(Model.is_active == True)  # noqa: E712
    )
    usage_count = await db.execute(select(func.count(UsageRecord.id)))
    total_spend = await db.execute(select(func.sum(UsageRecord.total_cost_cents)))
    keys_count = await db.execute(select(func.count(ApiKey.id)))

    return {
        "providers": providers_count.scalar(),
        "models": models_count.scalar(),
        "active_models": active_models.scalar(),
        "usage_records": usage_count.scalar(),
        "total_spend_cents": total_spend.scalar() or 0,
        "api_keys": keys_count.scalar(),
    }


# ─── Helpers ───────────────────────────────────────────────────────────

def _provider_to_dict(p: Provider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "display_name": p.display_name,
        "base_url": p.base_url,
        "api_key_env": p.api_key_env,
        "priority": p.priority,
        "active": p.active,
        "avg_latency_ms": p.avg_latency_ms,
        "uptime_pct": p.uptime_pct,
    }


def _model_to_dict(m: Model) -> dict:
    return {
        "id": m.id,
        "model_id": m.model_id,
        "display_name": m.display_name,
        "provider_id": m.provider_id,
        "provider_name": m.provider.name if m.provider else None,
        "tokenizer": m.tokenizer,
        "prompt_price": str(m.prompt_price),
        "completion_price": str(m.completion_price),
        "cached_price": str(m.cached_price) if m.cached_price else None,
        "context_window": m.context_window,
        "max_output": m.max_output,
        "supports_streaming": m.supports_streaming,
        "supports_tools": m.supports_tools,
        "supports_vision": m.supports_vision,
        "supports_json": m.supports_json,
        "quality_score": m.quality_score,
        "speed_score": m.speed_score,
        "is_active": m.is_active,
        "category": m.category,
    }
