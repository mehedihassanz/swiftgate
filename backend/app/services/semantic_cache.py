"""Semantic cache service — serves LLM responses without hitting providers.

Two matching strategies:
  1. Exact match: SHA-256 hash of normalized messages (zero false positives)
  2. Semantic match: token-level Jaccard similarity (no external dependency)

Public API:
    check_cache(db, messages, model_id, api_key_id) -> dict | None
    store_cache(db, messages, response, model_id, cost_cents, ...) -> CacheEntry
    get_cache_stats(db) -> dict
    invalidate_cache(db, pattern) -> int

Design decisions:
  - No embedding model dependency (Jaccard on token sets is fast, deterministic, zero cost)
  - Per-key privacy by default (is_shared=False). Shared mode for collaborative caching.
  - Configurable TTL per task type (code: 7 days, chat: 24h, news: 1h)
  - User can bypass with `cache: false` header
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CacheEntry

logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────

# Minimum Jaccard similarity for semantic cache hit (0.0-1.0)
MIN_SIMILARITY = 0.85

# TTL per task type (hours)
TASK_TTL_HOURS = {
    "code": 24 * 7,      # code snippets rarely change semantics
    "chat": 24,
    "reasoning": 12,
    "tool_use": 6,
    "vision": 24,
    "embedding": 24 * 30, # embeddings are deterministic-ish
}
DEFAULT_TTL_HOURS = 24

# Max messages to consider for fingerprinting (avoid massive conversations)
MAX_FINGERPRINT_MESSAGES = 10

# Stopwords to strip for semantic matching (reduces noise)
_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "could should may might must can to of in on at for with by about against "
    "between into through during before after above below from up down out off "
    "over under again further then once here there when where why how all any "
    "both each few more most other some such no nor not only own same so than "
    "too very s t can just don should now i me my we our you your he him his "
    "she her it its they them their what which who whom this that these those "
    "am if or because as until while of a an the and but if or nor for so yet"
    .split()
)


# ─── Normalization & Fingerprinting ───────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normalize text for consistent hashing.

    Lowercases, strips whitespace, removes code block markers, collapses spaces.
    """
    if not text:
        return ""
    # Lowercase
    t = text.lower()
    # Remove markdown code block markers
    t = re.sub(r"```[a-z]*", "", t)
    # Remove extra whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_content(messages: list[dict]) -> str:
    """Extract and concatenate user/system content from messages."""
    parts = []
    for msg in messages[-MAX_FINGERPRINT_MESSAGES:]:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            # Vision format: [{"type": "text", "text": "..."}]
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return " ".join(parts)


def _content_hash(messages: list[dict]) -> str:
    """SHA-256 hash of normalized message content — for exact matching."""
    normalized = _normalize_text(_extract_content(messages))
    return hashlib.sha256(normalized.encode()).hexdigest()


def _token_fingerprint(messages: list[dict]) -> str:
    """Generate a token set fingerprint for Jaccard similarity.

    Returns a pipe-delimited sorted string of unique meaningful tokens.
    """
    text = _extract_content(messages)
    normalized = _normalize_text(text)

    # Simple tokenization: word boundaries, length >= 3
    tokens = re.findall(r"\b[a-z0-9_]{3,}\b", normalized)
    # Remove stopwords
    meaningful = {t for t in tokens if t not in _STOPWORDS}

    return "|".join(sorted(meaningful))


def _jaccard_similarity(set_a: str, set_b: str) -> float:
    """Compute Jaccard similarity between two pipe-delimited token sets."""
    if not set_a or not set_b:
        return 0.0

    tokens_a = set(set_a.split("|"))
    tokens_b = set(set_b.split("|"))

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    if not union:
        return 0.0

    return len(intersection) / len(union)


# ─── Core cache operations ────────────────────────────────────────────

async def check_cache(
    db: AsyncSession,
    messages: list[dict],
    model_id: str,
    api_key_id: int | None = None,
    semantic: bool = True,
) -> dict | None:
    """Check if a cached response exists for this request.

    Returns the cached response dict, or None if no cache hit.
    Marks the entry's hit_count and last_hit_at on a hit.
    """
    content_hash = _content_hash(messages)

    # ── Step 1: Try exact match (fast, O(1) on indexed column) ──
    stmt = (
        select(CacheEntry)
        .where(
            CacheEntry.content_hash == content_hash,
            CacheEntry.model_id == model_id,
        )
    )

    # Privacy scoping: exact match on own entries + shared entries
    if api_key_id is not None:
        stmt = stmt.where(
            (CacheEntry.api_key_id == api_key_id) | (CacheEntry.is_shared == True)  # noqa: E712
        )
    else:
        # Anonymous: match entries with no key scope OR shared entries
        stmt = stmt.where(
            (CacheEntry.api_key_id == None) | (CacheEntry.is_shared == True)  # noqa: E711,E712
        )

    # Not expired
    now = datetime.now(timezone.utc)
    stmt = stmt.where(
        (CacheEntry.expires_at == None) | (CacheEntry.expires_at > now)  # noqa: E711
    )

    result = await db.execute(stmt.limit(1))
    entry = result.scalar_one_or_none()

    if entry:
        entry.hit_count += 1
        entry.last_hit_at = now
        await db.flush()
        logger.debug(f"Cache EXACT hit: model={model_id}, hits={entry.hit_count}")
        response = json.loads(entry.response_json)
        response["_cache"] = {
            "hit": True,
            "match_type": "exact",
            "entry_id": entry.id,
            "hit_count": entry.hit_count,
            "saved_cost_cents": entry.saved_cost_cents,
        }
        return response

    # ── Step 2: Try semantic match (Jaccard similarity) ──
    if not semantic:
        return None

    fp = _token_fingerprint(messages)
    if not fp:
        return None  # Can't do semantic matching without meaningful tokens

    # Pull candidates with same model_id + same first token (indexable)
    # In production with pgvector, this would be a vector search.
    # For SQLite/Postgres without pgvector, we scan recent entries.
    candidate_stmt = (
        select(CacheEntry)
        .where(
            CacheEntry.model_id == model_id,
            (CacheEntry.expires_at == None) | (CacheEntry.expires_at > now),  # noqa: E711
        )
    )

    if api_key_id is not None:
        candidate_stmt = candidate_stmt.where(
            (CacheEntry.api_key_id == api_key_id) | (CacheEntry.is_shared == True)  # noqa: E712
        )
    else:
        candidate_stmt = candidate_stmt.where(
            (CacheEntry.api_key_id == None) | (CacheEntry.is_shared == True)  # noqa: E711,E712
        )

    candidate_stmt = candidate_stmt.order_by(CacheEntry.last_hit_at.desc().nullslast()).limit(50)

    result = await db.execute(candidate_stmt)
    candidates = result.scalars().all()

    best_entry = None
    best_score = 0.0

    for c in candidates:
        if not c.token_fingerprint:
            continue
        score = _jaccard_similarity(fp, c.token_fingerprint)
        if score > best_score:
            best_score = score
            best_entry = c

    if best_entry and best_score >= MIN_SIMILARITY:
        best_entry.hit_count += 1
        best_entry.last_hit_at = now
        await db.flush()
        logger.info(f"Cache SEMANTIC hit: model={model_id}, similarity={best_score:.2f}")
        response = json.loads(best_entry.response_json)
        response["_cache"] = {
            "hit": True,
            "match_type": "semantic",
            "similarity": round(best_score, 3),
            "entry_id": best_entry.id,
            "hit_count": best_entry.hit_count,
            "saved_cost_cents": best_entry.saved_cost_cents,
        }
        return response

    return None


async def store_cache(
    db: AsyncSession,
    messages: list[dict],
    response: dict,
    model_id: str,
    task_type: str | None = None,
    api_key_id: int | None = None,
    saved_cost_cents: int = 0,
    saved_tokens: int = 0,
    is_shared: bool = False,
    ttl_hours: int | None = None,
) -> CacheEntry:
    """Store a response in the cache for future retrieval."""
    # Determine TTL
    if ttl_hours is None:
        ttl_hours = TASK_TTL_HOURS.get(task_type or "chat", DEFAULT_TTL_HOURS)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours) if ttl_hours > 0 else None

    entry = CacheEntry(
        content_hash=_content_hash(messages),
        model_id=model_id,
        task_type=task_type,
        messages_json=json.dumps(messages, ensure_ascii=False),
        response_json=json.dumps(response, ensure_ascii=False),
        token_fingerprint=_token_fingerprint(messages),
        saved_cost_cents=saved_cost_cents,
        saved_tokens=saved_tokens,
        api_key_id=api_key_id,
        is_shared=is_shared,
        expires_at=expires_at,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_cache_stats(db: AsyncSession) -> dict[str, Any]:
    """Get aggregate cache statistics for the dashboard."""
    now = datetime.now(timezone.utc)

    # Total entries
    total_result = await db.execute(select(func.count(CacheEntry.id)))
    total_entries = total_result.scalar() or 0

    # Active (not expired)
    active_result = await db.execute(
        select(func.count(CacheEntry.id)).where(
            (CacheEntry.expires_at == None) | (CacheEntry.expires_at > now)  # noqa: E711
        )
    )
    active_entries = active_result.scalar() or 0

    # Total hits across all entries
    hits_result = await db.execute(select(func.sum(CacheEntry.hit_count)))
    total_hits = hits_result.scalar() or 0

    # Total saved cost
    saved_result = await db.execute(select(func.sum(CacheEntry.saved_cost_cents)))
    total_saved_cents = saved_result.scalar() or 0

    # Average similarity for semantic hits (stored in hit_count; we approximate hit rate)
    hit_rate = 0.0
    if total_entries > 0:
        hit_rate = total_hits / (total_hits + total_entries) if total_hits > 0 else 0.0

    return {
        "total_entries": total_entries,
        "active_entries": active_entries,
        "expired_entries": total_entries - active_entries,
        "total_hits": total_hits,
        "estimated_hit_rate": round(hit_rate, 4),
        "total_saved_cents": total_saved_cents,
        "total_saved_usd": round(total_saved_cents / 10000, 4),
    }


async def invalidate_cache(
    db: AsyncSession,
    model_id: str | None = None,
    expired_only: bool = False,
) -> int:
    """Invalidate cache entries. Returns count of deleted entries."""
    stmt = delete(CacheEntry)

    if model_id:
        stmt = stmt.where(CacheEntry.model_id == model_id)

    if expired_only:
        stmt = stmt.where(CacheEntry.expires_at <= datetime.now(timezone.utc))

    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


async def cleanup_expired(db: AsyncSession) -> int:
    """Remove all expired cache entries. Called by periodic cleanup job."""
    return await invalidate_cache(db, expired_only=True)
