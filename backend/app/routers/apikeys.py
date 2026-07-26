"""API key management router — create, list, revoke keys.

Endpoints:
  POST   /v1/keys             — create a new API key
  GET    /v1/keys             — list all keys (never returns the full key, only prefix)
  GET    /v1/keys/{id}        — get key details + usage stats
  PUT    /v1/keys/{id}        — update key (budget, name, active status)
  DELETE /v1/keys/{id}        — revoke/delete a key
  POST   /v1/keys/{id}/reset  — reset spend counter (new billing cycle)

The full key is only shown ONCE at creation time. We store only the SHA-256 hash.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ApiKey, UsageRecord
from app.auth import require_admin

router = APIRouter(prefix="/v1/keys", tags=["api-keys"])


def _generate_api_key() -> str:
    """Generate a secure random API key. Format: sg-<48 hex chars>."""
    return "sg-" + secrets.token_hex(24)


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash of the key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _key_prefix(raw_key: str) -> str:
    """Display prefix: sg-...abc"""
    return raw_key[:6] + "..." + raw_key[-4:]


# ─── Schemas ───────────────────────────────────────────────────────────

class KeyCreate(BaseModel):
    name: str = Field("default", description="Human-readable label for the key")
    user_email: str | None = None
    monthly_budget_cents: int | None = Field(None, description="Max spend per month in cents")
    per_request_limit_cents: int | None = Field(None, description="Max cost per request in cents")
    agent_id: str | None = None


class KeyUpdate(BaseModel):
    name: str | None = None
    monthly_budget_cents: int | None = None
    per_request_limit_cents: int | None = None
    is_active: bool | None = None


class KeyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    key_prefix: str
    name: str
    user_email: str | None
    monthly_budget_cents: int | None
    per_request_limit_cents: int | None
    agent_id: str | None
    is_active: bool
    total_spend_cents: int
    total_requests: int
    created_at: datetime
    last_used: datetime | None


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_key(
    body: KeyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Create a new API key. The full key is returned ONLY in this response."""
    raw_key = _generate_api_key()
    key_hash = _hash_key(raw_key)

    api_key = ApiKey(
        key_hash=key_hash,
        key_prefix=_key_prefix(raw_key),
        name=body.name,
        user_email=body.user_email,
        monthly_budget_cents=body.monthly_budget_cents,
        per_request_limit_cents=body.per_request_limit_cents,
        agent_id=body.agent_id,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    response = KeyResponse.model_validate(api_key)
    # Attach the full key — only shown once
    response_dict = response.model_dump()
    response_dict["key"] = raw_key
    response_dict["warning"] = "Store this key securely. It will not be shown again."
    return response_dict


@router.get("")
async def list_keys(
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """List all API keys (without exposing the full key)."""
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    keys = result.scalars().all()
    return {
        "keys": [
            {
                "id": k.id,
                "key_prefix": k.key_prefix,
                "name": k.name,
                "user_email": k.user_email,
                "monthly_budget_cents": k.monthly_budget_cents,
                "per_request_limit_cents": k.per_request_limit_cents,
                "agent_id": k.agent_id,
                "is_active": k.is_active,
                "total_spend_cents": k.total_spend_cents,
                "total_requests": k.total_requests,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used": k.last_used.isoformat() if k.last_used else None,
            }
            for k in keys
        ],
        "count": len(keys),
    }


@router.get("/{key_id}")
async def get_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Get detailed info for a specific key, including recent usage."""
    key = await db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "Key not found")

    # Get recent usage records
    usage_result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.api_key_id == key_id)
        .order_by(UsageRecord.created_at.desc())
        .limit(20)
    )
    recent_usage = [
        {
            "model": r.model_served,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_cents": r.total_cost_cents,
            "latency_ms": r.latency_ms,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in usage_result.scalars().all()
    ]

    return {
        "id": key.id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "user_email": key.user_email,
        "monthly_budget_cents": key.monthly_budget_cents,
        "per_request_limit_cents": key.per_request_limit_cents,
        "agent_id": key.agent_id,
        "is_active": key.is_active,
        "total_spend_cents": key.total_spend_cents,
        "total_requests": key.total_requests,
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "last_used": key.last_used.isoformat() if key.last_used else None,
        "budget_used_pct": (
            round((key.total_spend_cents / key.monthly_budget_cents) * 100, 1)
            if key.monthly_budget_cents else None
        ),
        "recent_usage": recent_usage,
    }


@router.put("/{key_id}")
async def update_key(
    key_id: int,
    body: KeyUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Update a key's settings (budget, name, active status)."""
    key = await db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "Key not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(key, field, val)

    await db.commit()
    await db.refresh(key)
    return {"updated": True, "id": key_id}


@router.delete("/{key_id}")
async def delete_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Permanently delete a key. Consider PUT is_active=false instead."""
    key = await db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "Key not found")
    await db.delete(key)
    await db.commit()
    return {"deleted": True, "id": key_id}


@router.post("/{key_id}/reset")
async def reset_spend(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Reset the spend counter (e.g., at the start of a new billing cycle)."""
    key = await db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "Key not found")
    key.total_spend_cents = 0
    key.total_requests = 0
    await db.commit()
    return {"reset": True, "id": key_id}
