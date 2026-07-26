"""Shared authentication dependencies for SwiftGate.

Auth model:
  - Admin endpoints require X-Admin-Key header matching ADMIN_KEY env var.
  - Management endpoints (keys, agents, cache, analytics) require admin auth.
  - Gateway endpoints (/v1/chat/completions) require a valid API key.
  - Public catalog endpoints (/v1/models, /v1/pareto, /health) are open read-only.

If ADMIN_KEY is not set, the app refuses to start in production mode.
In development, a warning is printed and admin endpoints log each access.
"""
from __future__ import annotations

import os
import logging

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


def require_admin(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> str:
    """Require a valid admin key. Fails closed in production if ADMIN_KEY unset."""
    if not ADMIN_KEY:
        if settings.ENV == "production":
            raise HTTPException(
                503,
                "Admin endpoints disabled: ADMIN_KEY not configured. "
                "Set the ADMIN_KEY environment variable to enable admin access.",
            )
        # Development: allow but log warning
        logger.warning(
            "Admin endpoint accessed without ADMIN_KEY set (development mode). "
            "Set ADMIN_KEY env var to secure these endpoints."
        )
        return "dev-admin"

    if x_admin_key != ADMIN_KEY:
        raise HTTPException(401, "Invalid or missing X-Admin-Key header")

    return x_admin_key or "dev-admin"
