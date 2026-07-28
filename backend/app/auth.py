"""Shared authentication dependencies for SwiftGate.

Auth model (unified):
  - Users sign up/login via the portal (/auth/register, /auth/login) and get a JWT.
  - JWT contains an is_admin claim (true if the user's email is in ADMIN_EMAILS).
  - Admin endpoints accept EITHER a valid admin JWT (Authorization: Bearer)
    OR the legacy X-Admin-Key header (for API-only automation access).
  - Gateway endpoints (/v1/chat/completions) require a valid API key.
  - Public catalog endpoints (/v1/models, /v1/pareto, /health) are open read-only.
"""
from __future__ import annotations

import os
import logging

from fastapi import Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


def require_admin(
    request: Request,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> str:
    """Require admin access via JWT (admin user) OR X-Admin-Key header.

    Checks in order:
    1. X-Admin-Key header matches ADMIN_KEY env var (legacy/API automation)
    2. Authorization: Bearer <JWT> with is_admin=True claim (portal users)
    3. Falls back to dev mode if neither ADMIN_KEY nor ADMIN_EMAILS configured
    """
    # ── 1. Legacy X-Admin-Key ──
    if ADMIN_KEY and x_admin_key:
        import hmac
        if hmac.compare_digest(x_admin_key, ADMIN_KEY):
            return x_admin_key

    # ── 2. JWT Bearer token with is_admin claim ──
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from app.user_auth import decode_access_token
            payload = decode_access_token(token)
            if payload and payload.get("is_admin"):
                return payload.get("email", "admin-jwt")
        except Exception:
            pass

    # ── 3. Dev mode fallback ──
    if not ADMIN_KEY and not settings.admin_emails:
        if settings.ENV == "production":
            raise HTTPException(
                503,
                "Admin endpoints disabled. Set ADMIN_EMAILS or ADMIN_KEY.",
            )
        logger.warning(
            "Admin endpoint accessed in dev mode (no ADMIN_KEY/ADMIN_EMAILS set)."
        )
        return "dev-admin"

    # Neither method worked
    raise HTTPException(401, "Admin access required. Log in with an admin account.")
