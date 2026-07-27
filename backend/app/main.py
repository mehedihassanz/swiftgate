"""SwiftGate — AI model gateway with cost intelligence.

'See the cost before you pay it.'
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.config import settings
from app.routers import admin, agents, analytics, apikeys, billing, cache_pii, cost, gateway, quality, user_portal
from app.services.pricing import seed_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + seed pricing data + load ML model."""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("swiftgate")

    await init_db()

    # Seed the pricing database (only inserts new models, doesn't overwrite price changes)
    from app.database import async_session
    async with async_session() as db:
        result = await seed_database(db)
        from app.services.pricing import seed_quality_scores
        quality_count = await seed_quality_scores(db)
        result["quality_scores_seeded"] = quality_count
        await db.commit()
        logger.info(f"Database seeded: {result}")

    # Load the ML prediction model (flywheel persistence)
    try:
        from app.services.prediction_ml import predictor
        import asyncio as _aio
        await _aio.to_thread(predictor.load)
        logger.info("ML prediction model loaded")
    except Exception as e:
        logger.warning(f"Could not load ML model (will use heuristics): {e}")

    # Log which providers have API keys configured
    from app.config import settings
    from app.services.pricing import PROVIDERS
    configured = [p["name"] for p in PROVIDERS if os.environ.get(p["api_key_env"])]
    logger.info(f"Providers with API keys: {configured or 'none — gateway will reject requests'}")

    # Shared HTTP client for upstream provider calls (connection reuse)
    import httpx as _httpx
    shared_client = _httpx.AsyncClient(
        timeout=_httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
        limits=_httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.http_client = shared_client
    logger.info("Shared HTTP client initialized")

    yield

    # Graceful shutdown — close HTTP client + dispose DB engine
    await shared_client.aclose()
    from app.database import engine
    await engine.dispose()
    logger.info("HTTP client closed, database engine disposed")


app = FastAPI(
    title="SwiftGate",
    description="AI model gateway with cost intelligence. See the cost before you pay it.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"],
    allow_credentials=settings.CORS_ORIGINS != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "swiftgate", "version": "1.0.0"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    try:
        from app.database import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"Database not ready: {e}")


# ─── Routers ───────────────────────────────────────────────────────────

app.include_router(cost.router)        # /v1/predict, /v1/compare, /v1/models, /v1/pareto
app.include_router(gateway.router)     # /v1/chat/completions (OpenAI-compatible proxy)
app.include_router(analytics.router)   # /v1/usage, /v1/usage/daily, /v1/stats
app.include_router(admin.router)       # /admin/providers, /admin/models (CRUD)
app.include_router(apikeys.router)     # /v1/keys (create, list, revoke)
app.include_router(agents.router)      # /v1/agents (budget orchestration)
app.include_router(quality.router)     # /v1/quality, /v1/routing (quality-aware routing)
app.include_router(cache_pii.router)   # /v1/cache, /v1/pii (semantic cache + PII redaction)
app.include_router(user_portal.router)       # /auth/register, /auth/login (user portal auth)
app.include_router(user_portal.user_router)  # /user/keys, /user/usage (user portal)
app.include_router(billing.router)           # /user/billing/checkout (Stripe)
app.include_router(billing.webhook_router)   # /billing/webhook (Stripe webhook)


# ─── Root ──────────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {
        "name": "SwiftGate",
        "tagline": "See the cost before you pay it",
        "docs": "/docs",
        "endpoints": {
            "predict": "POST /v1/predict",
            "compare": "POST /v1/compare",
            "models": "GET /v1/models",
            "pareto": "GET /v1/pareto",
            "chat": "POST /v1/chat/completions",
            "usage": "GET /v1/usage",
            "stats": "GET /v1/stats",
            "admin": "GET /admin/providers, /admin/models",
        },
    }
