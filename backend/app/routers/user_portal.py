"""User-facing API routes — signup, login, key management, usage."""
from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ApiKey, UsageRecord, User
from app.services.rate_limiter import check_rate_limit
from app.user_auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["user-auth"])
user_router = APIRouter(prefix="/user", tags=["user"])


# ─── Schemas ──────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class CreateKeyRequest(BaseModel):
    name: str = Field(default="default", max_length=200)
    monthly_budget_cents: int | None = Field(None, description="Max spend per month in microcents")
    per_request_limit_cents: int | None = Field(None, description="Max cost per request in microcents")


class ApiKeyResponse(BaseModel):
    id: int
    key_prefix: str
    name: str
    is_active: bool
    created_at: str
    total_spend_cents: int
    total_requests: int
    monthly_budget_cents: int | None = None
    per_request_limit_cents: int | None = None
    full_key: str | None = None  # only set on creation


# ─── Auth dependency ─────────────────────────────────────────────────


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and verify JWT from Authorization: Bearer <token>."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth_header[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ─── Auth endpoints (/auth/*) ────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Rate limit: 5 signups per minute per IP (prevents spam/brute-force)
    client_ip = request.client.host if request.client else "unknown"
    import hashlib as _hashlib
    ip_key = int(_hashlib.md5(client_ip.encode()).hexdigest()[:8], 16)
    allowed, _ = await check_rate_limit(ip_key)
    if not allowed:
        raise HTTPException(429, "Too many registration attempts from this IP. Please try again later.")
    try:
        user = await register_user(db, req.email, req.password, req.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered")

    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_admin": user.email.lower() in settings.admin_emails,
            "credits_usd": round(user.credits_cents / 10000, 2),
        },
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Rate limit: 10 login attempts per minute per IP
    client_ip = request.client.host if request.client else "unknown"
    import hashlib as _hashlib
    ip_key = int(_hashlib.md5(f"login:{client_ip}".encode()).hexdigest()[:8], 16)
    allowed, _ = await check_rate_limit(ip_key)
    if not allowed:
        raise HTTPException(429, "Too many login attempts. Please try again later.")
    user = await authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_admin": user.email.lower() in settings.admin_emails,
            "credits_usd": round(user.credits_cents / 10000, 2),
        },
    )


@router.get("/me", response_model=dict)
async def get_me(user: CurrentUser):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_admin": user.email.lower() in settings.admin_emails,
        "credits_cents": user.credits_cents,
        "credits_usd": round(user.credits_cents / 10000, 2),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ─── User key management (/user/keys) ────────────────────────────────


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix)."""
    raw = "sg-" + secrets.token_urlsafe(32)
    return raw, _hash_key(raw), raw[:10] + "..."


@user_router.get("/keys", response_model=list[ApiKeyResponse])
async def list_my_keys(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=k.id,
            key_prefix=k.key_prefix,
            name=k.name,
            is_active=k.is_active,
            created_at=k.created_at.isoformat() if k.created_at else "",
            total_spend_cents=k.total_spend_cents,
            total_requests=k.total_requests,
            monthly_budget_cents=k.monthly_budget_cents,
            per_request_limit_cents=k.per_request_limit_cents,
        )
        for k in keys
    ]


@user_router.post("/keys", response_model=ApiKeyResponse, status_code=201)
async def create_my_key(
    req: CreateKeyRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raw_key, key_hash, key_prefix = _generate_api_key()

    new_key = ApiKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=req.name,
        user_id=user.id,
        user_email=user.email,
        monthly_budget_cents=req.monthly_budget_cents,
        per_request_limit_cents=req.per_request_limit_cents,
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return ApiKeyResponse(
        id=new_key.id,
        key_prefix=key_prefix,
        name=new_key.name,
        is_active=True,
        created_at=new_key.created_at.isoformat() if new_key.created_at else "",
        total_spend_cents=0,
        total_requests=0,
        full_key=raw_key,  # shown ONCE on creation
    )


@user_router.delete("/keys/{key_id}", status_code=204)
async def delete_my_key(
    key_id: int,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.delete(key)
    await db.commit()


class KeyUpdateRequest(BaseModel):
    name: str | None = None
    monthly_budget_cents: int | None = None
    per_request_limit_cents: int | None = None
    is_active: bool | None = None


@user_router.put("/keys/{key_id}")
async def update_my_key(
    key_id: int,
    req: KeyUpdateRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update key settings (name, budget limits, active status)."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    for field, val in req.model_dump(exclude_unset=True).items():
        setattr(key, field, val)

    await db.commit()
    return {"updated": True, "id": key_id}


# ─── User settings (/user/settings) ─────────────────────────────────


@user_router.get("/settings")
async def get_settings(user: CurrentUser):
    """Get user account settings."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_admin": user.email.lower() in settings.admin_emails,
        "credits_cents": user.credits_cents,
        "credits_usd": round(user.credits_cents / 10000, 2),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(None, max_length=200)


@user_router.put("/settings")
async def update_settings(
    req: UpdateProfileRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update user profile."""
    if req.name is not None:
        user.name = req.name
    await db.commit()
    return {
        "updated": True,
        "id": user.id,
        "name": user.name,
    }


# ─── User usage (/user/usage) ────────────────────────────────────────


@user_router.get("/usage")
async def my_usage(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    """Aggregate usage stats for the current user."""
    # Sum across all keys owned by this user
    result = await db.execute(
        select(
            func.count(UsageRecord.id),
            func.sum(UsageRecord.total_cost_cents),
            func.sum(UsageRecord.prompt_tokens),
            func.sum(UsageRecord.completion_tokens),
        ).join(ApiKey, UsageRecord.api_key_id == ApiKey.id).where(
            ApiKey.user_id == user.id
        )
    )
    row = result.one()
    total_requests = row[0] or 0
    total_spend_cents = row[1] or 0
    total_prompt = row[2] or 0
    total_completion = row[3] or 0

    return {
        "total_requests": total_requests,
        "total_spend_cents": total_spend_cents,
        "total_spend_usd": round(total_spend_cents / 10000, 4),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "credits_remaining_cents": user.credits_cents,
        "credits_remaining_usd": round(user.credits_cents / 10000, 2),
    }


@user_router.get("/usage/recent")
async def my_recent_usage(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
):
    """Recent usage records for the current user."""
    result = await db.execute(
        select(UsageRecord)
        .join(ApiKey, UsageRecord.api_key_id == ApiKey.id)
        .where(ApiKey.user_id == user.id)
        .order_by(UsageRecord.created_at.desc())
        .limit(min(limit, 200))
    )
    records = result.scalars().all()
    return {
        "count": len(records),
        "records": [
            {
                "id": r.id,
                "model_id": r.model_served,
                "provider_name": r.provider,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_cents": r.total_cost_cents,
                "cost_usd": round(r.total_cost_cents / 10000, 6) if r.total_cost_cents else 0,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in records
        ],
    }


@user_router.get("/usage/daily")
async def my_daily_usage(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 30,
):
    """Daily cost breakdown for charts (user-scoped)."""
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=min(days, 365))

    result = await db.execute(
        select(UsageRecord)
        .join(ApiKey, UsageRecord.api_key_id == ApiKey.id)
        .where(
            ApiKey.user_id == user.id,
            UsageRecord.created_at >= since,
        )
        .order_by(UsageRecord.created_at)
    )
    records = result.scalars().all()

    daily: dict[str, dict] = {}
    for r in records:
        day = r.created_at.strftime("%Y-%m-%d") if r.created_at else "unknown"
        if day not in daily:
            daily[day] = {"date": day, "cost_cents": 0, "requests": 0, "tokens": 0}
        daily[day]["cost_cents"] += r.total_cost_cents
        daily[day]["requests"] += 1
        daily[day]["tokens"] += r.prompt_tokens + r.completion_tokens

    return {"daily": sorted(daily.values(), key=lambda x: x["date"])}
