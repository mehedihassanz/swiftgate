"""Rate limiter — per-key request throttling using sliding window.

Uses Redis for distributed rate limiting across multiple workers when
REDIS_URL is configured and Redis is reachable. Falls back to in-memory
storage automatically if Redis is unavailable.

Public API:
    check_rate_limit(key_id) -> (allowed: bool, rate_info: dict)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SlidingWindow:
    """Simple sliding window counter for one entity."""
    timestamps: list[float] = field(default_factory=list)

    def add_and_count(self, now: float, window_seconds: int = 60) -> int:
        """Add a request at `now`, prune old entries, return current count."""
        cutoff = now - window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        self.timestamps.append(now)
        return len(self.timestamps)


# ─── In-memory backend ─────────────────────────────────────────────────

class InMemoryRateLimiter:
    """Per-key sliding window rate limiter. No external deps."""

    def __init__(self):
        self._windows: dict[int, SlidingWindow] = defaultdict(SlidingWindow)
        self._anonymous: SlidingWindow = SlidingWindow()  # shared for anonymous

    async def check(self, key_id: int | None, max_per_minute: int) -> tuple[bool, int, int]:
        """Check if request is allowed under rate limit.

        Returns: (allowed, current_count, limit)
        """
        now = time.time()
        window = self._windows[key_id] if key_id else self._anonymous
        count = window.add_and_count(now)
        allowed = count <= max_per_minute
        return allowed, count, max_per_minute

    async def get_remaining(self, key_id: int | None, max_per_minute: int) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        window = self._windows[key_id] if key_id else self._anonymous
        cutoff = now - 60
        active = [t for t in window.timestamps if t > cutoff]
        return max(0, max_per_minute - len(active))


# ─── Redis backend ─────────────────────────────────────────────────────

class RedisRateLimiter:
    """Distributed sliding window rate limiter using Redis sorted sets.

    Uses ZADD + ZREMRANGEBYSCORE + ZCARD for an atomic-ish sliding window.
    Works across multiple workers/processes.
    """

    def __init__(self, redis_client: Any):
        self._redis = redis_client
        self._prefix = "swiftgate:ratelimit:"

    async def check(self, key_id: int | None, max_per_minute: int) -> tuple[bool, int, int]:
        """Check if request is allowed. Returns (allowed, current_count, limit)."""
        import time as _time
        now = _time.time()
        key = f"{self._prefix}{key_id or 'anonymous'}"

        pipe = self._redis.pipeline()
        # Remove timestamps older than 60 seconds
        pipe.zremrangebyscore(key, 0, now - 60)
        # Add current timestamp
        pipe.zadd(key, {str(now): now})
        # Count entries in window
        pipe.zcard(key)
        # Expire the key after 120s to prevent unbounded growth
        pipe.expire(key, 120)

        results = await pipe.execute()
        count = results[2]  # zcard result
        allowed = count <= max_per_minute
        return allowed, count, max_per_minute

    async def get_remaining(self, key_id: int | None, max_per_minute: int) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        key = f"{self._prefix}{key_id or 'anonymous'}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - 60)
        pipe.zcard(key)
        results = await pipe.execute()
        count = results[1]
        return max(0, max_per_minute - count)


# ─── Backend selection ─────────────────────────────────────────────────

async def _create_backend() -> InMemoryRateLimiter | RedisRateLimiter:
    """Try Redis first, fall back to in-memory."""
    redis_url = settings.REDIS_URL
    if not redis_url:
        return InMemoryRateLimiter()

    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        logger.info(f"Redis rate limiter connected: {redis_url}")
        return RedisRateLimiter(client)
    except ImportError:
        logger.info("redis package not installed — using in-memory rate limiter")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}) — using in-memory rate limiter")

    return InMemoryRateLimiter()


# Lazy-initialized singleton (initialized on first use)
rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


async def _get_limiter():
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = await _create_backend()
    return rate_limiter


# ─── Public API ────────────────────────────────────────────────────────

# Default rate limits
DEFAULT_RPM = 60          # requests per minute for authenticated users
ANONYMOUS_RPM = 10        # very low for anonymous to prevent abuse


async def check_rate_limit(key_id: int | None) -> tuple[bool, dict]:
    """Check rate limit for a key. Returns (allowed, rate_info_dict).

    rate_info_dict contains: limit, remaining, used
    """
    limiter = await _get_limiter()
    limit = DEFAULT_RPM if key_id else ANONYMOUS_RPM
    allowed, count, _ = await limiter.check(key_id, limit)
    remaining = await limiter.get_remaining(key_id, limit)

    rate_info = {
        "limit": limit,
        "remaining": remaining,
        "used": count,
    }

    return allowed, rate_info
