"""Cache management and PII redaction router.

Endpoints:
  Cache:
    GET    /v1/cache/stats         — cache hit rate, savings, entry count
    DELETE /v1/cache                — invalidate cache (optional: ?model_id=)
    DELETE /v1/cache/expired        — cleanup expired entries only
    POST   /v1/cache/invalidate     — invalidate by pattern (body: {model_id})

  PII Redaction:
    POST   /v1/pii/detect           — detect PII in text (preview, no storage)
    POST   /v1/pii/redact           — redact PII from messages (returns redacted + audit)
    GET    /v1/pii/patterns         — list active PII detection patterns
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_admin
from app.services.pii_redaction import (
    PII_PATTERNS_INFO,
    detect_pii,
    redact_messages,
)
from app.services.semantic_cache import (
    cleanup_expired,
    get_cache_stats,
    invalidate_cache,
)

router = APIRouter(prefix="/v1", tags=["cache-pii"])


# ─── Cache Schemas ─────────────────────────────────────────────────────

class CacheInvalidateRequest(BaseModel):
    model_id: str | None = None
    expired_only: bool = False


# ─── Cache Endpoints ───────────────────────────────────────────────────

@router.get("/cache/stats")
async def cache_stats(db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Get cache statistics: hit rate, cost savings, entry counts."""
    return await get_cache_stats(db)


@router.delete("/cache")
async def cache_invalidate(
    model_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Invalidate cache entries. Optionally filter by model_id."""
    count = await invalidate_cache(db, model_id=model_id)
    return {"invalidated": count, "model_id": model_id}


@router.delete("/cache/expired")
async def cache_cleanup_expired(
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Remove all expired cache entries."""
    count = await cleanup_expired(db)
    return {"cleaned_up": count}


@router.post("/cache/invalidate")
async def cache_invalidate_body(
    body: CacheInvalidateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """Invalidate cache by pattern (body-based for SDK compatibility)."""
    count = await invalidate_cache(db, model_id=body.model_id, expired_only=body.expired_only)
    return {"invalidated": count, "model_id": body.model_id, "expired_only": body.expired_only}


# ─── PII Redaction Schemas ─────────────────────────────────────────────

class PiiDetectRequest(BaseModel):
    text: str


class PiiRedactRequest(BaseModel):
    messages: list[dict[str, Any]]


# ─── PII Endpoints ─────────────────────────────────────────────────────

@router.get("/pii/patterns")
async def pii_patterns():
    """List all active PII detection patterns."""
    return {
        "patterns": PII_PATTERNS_INFO,
        "count": len(PII_PATTERNS_INFO),
    }


@router.post("/pii/detect")
async def pii_detect(body: PiiDetectRequest):
    """Detect PII in a text string. Returns matches without modifying text."""
    matches = detect_pii(body.text)
    return {
        "total_found": len(matches),
        "matches": [
            {
                "type": m.pii_type,
                "start": m.start,
                "end": m.end,
                "length": m.end - m.start,
                # NOTE: the actual matched text is intentionally NOT returned
                # in the response body to avoid accidental exposure in logs.
                # The /redact endpoint returns the redacted version.
            }
            for m in matches
        ],
        "types_found": list(set(m.pii_type for m in matches)),
    }


@router.post("/pii/redact")
async def pii_redact(body: PiiRedactRequest):
    """Redact PII from messages. Returns redacted messages + audit log.

    The response contains:
      - redacted_messages: messages with PII replaced by placeholders
      - audit: summary of what was redacted (types + counts, not values)
      - token_count: number of placeholders generated
    """
    redacted, token_map = redact_messages(body.messages)

    return {
        "redacted_messages": redacted,
        "audit": token_map.to_log(),
        "token_count": len(token_map),
    }
