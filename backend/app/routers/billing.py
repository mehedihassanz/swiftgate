"""Stripe billing router — credit purchases via Stripe Checkout.

Endpoints:
  POST /user/billing/checkout   — create Stripe Checkout session for credit purchase
  POST /user/billing/history    — list user's purchase history
  POST /billing/webhook         — Stripe webhook (adds credits on successful payment)

Flow:
  1. User selects a credit amount on the frontend
  2. Frontend calls /user/billing/checkout → gets Stripe Checkout URL
  3. User pays on Stripe → Stripe redirects back to /settings
  4. Stripe sends webhook → credits added to user account
"""
from __future__ import annotations

import os
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, async_session
from app.models import User, ApiKey
from app.routers.user_portal import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/billing", tags=["billing-webhook"])

# Stripe is imported lazily — the app works without it (billing endpoints return 503)
_stripe = None

def _get_stripe():
    global _stripe
    if _stripe is None:
        try:
            import stripe as _s
            key = os.environ.get("STRIPE_SECRET_KEY", "")
            if not key:
                return None
            _s.api_key = key
            _stripe = _s
        except ImportError:
            logger.warning("stripe package not installed — billing disabled")
            return None
    return _stripe


# ─── Credit packages ───────────────────────────────────────────────────

CREDIT_PACKAGES = [
    {"id": "starter", "label": "Starter", "credits_cents": 500, "price_usd": 5.00},
    {"id": "developer", "label": "Developer", "credits_cents": 2000, "price_usd": 20.00},
    {"id": "pro", "label": "Pro", "credits_cents": 5000, "price_usd": 50.00},
    {"id": "business", "label": "Business", "credits_cents": 20000, "price_usd": 200.00},
]


# ─── Schemas ───────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    package_id: str = Field(..., description="One of: starter, developer, pro, business")
    success_url: str = Field(f"{settings.CORS_ORIGINS.split(',')[0] if settings.CORS_ORIGINS != '*' else ''}/settings?paid=1")
    cancel_url: str = Field(f"{settings.CORS_ORIGINS.split(',')[0] if settings.CORS_ORIGINS != '*' else ''}/settings")


class CheckoutResponse(BaseModel):
    url: str
    session_id: str


class CustomCheckoutRequest(BaseModel):
    """Custom amount checkout — user enters any amount >= $1."""
    amount_usd: float = Field(..., ge=1.0, le=10000.0)
    success_url: str | None = None
    cancel_url: str | None = None


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.get("/packages")
async def get_packages():
    """List available credit packages."""
    return {"packages": CREDIT_PACKAGES}


@router.post("/checkout")
async def create_checkout(
    req: CheckoutRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> CheckoutResponse:
    """Create a Stripe Checkout session for a credit package."""
    stripe = _get_stripe()
    if not stripe:
        raise HTTPException(503, "Stripe is not configured. Set STRIPE_SECRET_KEY.")

    pkg = next((p for p in CREDIT_PACKAGES if p["id"] == req.package_id), None)
    if not pkg:
        raise HTTPException(400, f"Invalid package. Choose from: {[p['id'] for p in CREDIT_PACKAGES]}")

    base_url = req.success_url.split("/settings")[0] or "https://swiftgate.ai"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"SwiftGate Credits — {pkg['label']}",
                        "description": f"${pkg['price_usd']:.2f} credit top-up",
                    },
                    "unit_amount": int(pkg["price_usd"] * 100),  # Stripe uses cents
                },
                "quantity": 1,
            }],
            metadata={
                "user_id": str(user.id),
                "user_email": user.email,
                "credits_cents": str(pkg["credits_cents"]),
                "package_id": pkg["id"],
            },
            success_url=f"{base_url}/settings?paid=1&amount={pkg['credits_cents']}",
            cancel_url=f"{base_url}/settings",
            customer_email=user.email,
        )
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(502, f"Failed to create checkout session: {e}")

    return CheckoutResponse(url=session.url, session_id=session.id)


@router.post("/checkout/custom")
async def create_custom_checkout(
    req: CustomCheckoutRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> CheckoutResponse:
    """Create a Stripe Checkout for a custom amount."""
    stripe = _get_stripe()
    if not stripe:
        raise HTTPException(503, "Stripe is not configured.")

    base_url = (req.success_url or "").split("/settings")[0] or "https://swiftgate.ai"
    # Credits = amount in dollars * 100 (cents) — 1:1 USD to credits
    credits_cents = int(req.amount_usd * 100)

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"SwiftGate Credits — ${req.amount_usd:.2f}",
                    },
                    "unit_amount": int(req.amount_usd * 100),
                },
                "quantity": 1,
            }],
            metadata={
                "user_id": str(user.id),
                "user_email": user.email,
                "credits_cents": str(credits_cents),
                "package_id": "custom",
            },
            success_url=f"{base_url}/settings?paid=1&amount={credits_cents}",
            cancel_url=req.cancel_url or f"{base_url}/settings",
            customer_email=user.email,
        )
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(502, f"Failed to create checkout session: {e}")

    return CheckoutResponse(url=session.url, session_id=session.id)


@router.get("/history")
async def billing_history(
    user: Annotated[User, Depends(get_current_user)],
):
    """Get user's credit balance and purchase info."""
    return {
        "credits_cents": user.credits_cents,
        "credits_usd": round(user.credits_cents / 10000, 2),
    }


# ─── Stripe Webhook ────────────────────────────────────────────────────

@webhook_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
):
    """Handle Stripe webhook events.

    On checkout.session.completed → add credits to user account.
    """
    stripe = _get_stripe()
    if not stripe:
        raise HTTPException(503, "Stripe not configured")

    payload = await request.body()
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        if webhook_secret and stripe_signature:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, webhook_secret
            )
        else:
            import json
            event = json.loads(payload)
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        credits_cents = metadata.get("credits_cents")

        if user_id and credits_cents:
            async with async_session() as db:
                result = await db.execute(select(User).where(User.id == int(user_id)))
                user = result.scalar_one_or_none()
                if user:
                    user.credits_cents += int(credits_cents)
                    await db.commit()
                    logger.info(
                        f"Credits added: {credits_cents} to user {user_id} "
                        f"({user.email}). New balance: {user.credits_cents}"
                    )
                else:
                    logger.error(f"Webhook: user {user_id} not found")
        else:
            logger.warning(f"Webhook: missing metadata in session {session.get('id')}")

    return {"received": True}
